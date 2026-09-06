import os
import re
import time
import json
import copy
import traceback
from datetime import datetime, timezone
from dotenv import load_dotenv
from concurrent.futures import ProcessPoolExecutor, as_completed

from tqdm import tqdm
import sqlite3, sys
sys.path.insert(0, os.getenv('FORGET_REPO', os.path.expanduser('~/orca/workspaces/forget/내-프롬프트를-공유하기-싫어')))
from forget import db as _fdb, store as _fstore   # forget 인프로세스 어댑터 (2026-09-07)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed
)

from llms import llm_request
from prompts import PROMPT_MEMZERO
TEMPLATE_FORGET = """Memories for user {user_id}:
{memories}"""


load_dotenv()

# Update custom instructions
custom_instructions = """
Generate personal memories that follow these guidelines:

1. Each memory should be self-contained with complete context, including:
   - The person's name, do not use "user" while creating memories
   - Personal details (career aspirations, hobbies, life circumstances)
   - Emotional states and reactions
   - Ongoing journeys or future plans
   - Specific dates when events occurred

2. Include meaningful personal narratives focusing on:
   - Identity and self-acceptance journeys
   - Family planning and parenting
   - Creative outlets and hobbies
   - Mental health and self-care activities
   - Career aspirations and education goals
   - Important life events and milestones

3. Make each memory rich with specific details rather than general statements
   - Include timeframes (exact dates when possible)
   - Name specific activities (e.g., "charity race for mental health" rather than just "exercise")
   - Include emotional context and personal growth elements

4. Extract memories only from user messages, not incorporating assistant responses

5. Format each memory as a paragraph with a clear narrative structure that captures the person's experience, challenges, and aspirations
"""

TEMPLATE_MEM0 = """Memories for user {user_id}:

    {memories}
"""

RETRY_TIMES = 10
WAIT_TIME = 60

client = None  # forget 인프로세스 — 클라이언트 없음
# (forget: 프로젝트 지시 없음)


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_fixed(WAIT_TIME),
    stop=stop_after_attempt(RETRY_TIMES),
    reraise=True
)
def add_memory(client, user_id, message, timestamp):
    """forget: store.add_memories는 동기적으로 원장에 쓰지만 추출 목록을 돌려주지 않는다 → 원장에서 t0 이후 행을 읽는다."""
    start = time.time()
    t0 = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    _fstore.add_memories({"messages": message, "user_id": user_id, "metadata": {"timestamp": timestamp, "bench": "halumem"}})
    conn = sqlite3.connect(os.environ["MEM1_DB_PATH"]); conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT memory, created_at FROM memories WHERE user_id = ? AND created_at >= ? ORDER BY created_at", (user_id, t0)).fetchall()
    conn.close()
    result = {"results": [{"memory": r["memory"], "event": "ADD"} for r in rows]}
    duration_ms = (time.time() - start) * 1000
    return result, duration_ms


@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_fixed(WAIT_TIME),
    stop=stop_after_attempt(RETRY_TIMES),
    reraise=True
)
def search_memory(client, query, user_id, top_k=20):
    start = time.time()
    res = _fstore.search_memories({"query": query, "filters": {"user_id": user_id}, "limit": top_k})
    memories = [
        {"memory": m.get("memory", ""), "timestamp": m.get("created_at", ""), "score": round(float(m.get("score") or 0.0), 2)}
        for m in (res.get("results") or [])
    ]
    memories = [f"{item['timestamp']}: {item['memory']}" for item in memories]
    context = TEMPLATE_FORGET.format(user_id=user_id, memories=json.dumps(memories, indent=4))
    duration_ms = (time.time() - start) * 1000
    return context, memories, duration_ms


def extract_user_name(persona_info: str):
    match = re.search(r'Name:\s*(.*?); Gender:', persona_info)

    if match:
        username = match.group(1).strip()
        return username
    else:
        raise ValueError("No name found.")
    

def process_user(user_data, top_k, save_path):

    user_name = extract_user_name(user_data["persona_info"])
    sessions = user_data["sessions"]

    tmp_dir = os.path.join(save_path, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    tmp_file = os.path.join(tmp_dir, f"{user_data['uuid']}.json")

    # forget: 사용자 스코프 초기화 — 벤치 전용 DB이므로 직접 지운다
    _c = sqlite3.connect(os.environ["MEM1_DB_PATH"]); _c.execute("DELETE FROM memories WHERE user_id = ?", (user_name,)); _c.commit(); _c.close()

    new_user_data = {
        "uuid": user_data["uuid"],
        "user_name": user_name,
        "sessions": []
    }

    try:

        for session in tqdm(sessions, total=len(sessions), desc=f"Processing user {user_name}"):
            new_session = {
                "memory_points": session["memory_points"],
                "dialogue": session["dialogue"]
            }

            # add messages
            dialogue = session["dialogue"]
            formatted_dialogue = [
                {
                    "role": turn["role"],
                    "content": turn["content"],
                }
                for turn in dialogue
            ]

            date_format = "%b %d, %Y, %H:%M:%S"
            dt = datetime.strptime(session["start_time"], date_format).replace(tzinfo=timezone.utc)
            iso_date = dt.isoformat()
            timestamp = int(dt.timestamp())

            result, duration_ms = add_memory(
                client=client, 
                user_id=user_name, 
                message=formatted_dialogue, 
                timestamp=timestamp
            )

            if session.get('is_generated_qa_session', False):
                new_session["add_dialogue_duration_ms"] = duration_ms
                new_session["is_generated_qa_session"] = True
                del new_session["dialogue"]
                del new_session["memory_points"]
                new_user_data["sessions"].append(new_session)
                continue

            extracted_memories = [
                item["memory"] for item in result["results"]
            ]
            new_session["extracted_memories"] = extracted_memories
            new_session["add_dialogue_duration_ms"] = duration_ms

            # search updated memories
            for memory in new_session["memory_points"]:
                if memory["is_update"] == "False" or not memory["original_memories"]:
                    continue

                _, memories_from_system, duration_ms = search_memory(
                    client=client, 
                    query=memory["memory_content"],
                    user_id=user_name, 
                    top_k=10
                )

                memory["memories_from_system"] = memories_from_system

            # search and query
            if "questions" not in session:
                new_user_data["sessions"].append(new_session)
                continue

            new_session["questions"] = []

            for qa in session["questions"]:

                context, _, duration_ms = search_memory(
                    client=client, 
                    query=qa["question"], 
                    user_id=user_name, 
                    top_k=top_k
                )

                new_qa = copy.deepcopy(qa)
                new_qa["context"] = context
                new_qa["search_duration_ms"] = duration_ms

                prompt = PROMPT_MEMZERO.format(
                    context=context,
                    question=qa["question"]
                )

                start_time = time.time()
                response = llm_request(prompt)
                new_qa["system_response"] = response
                new_qa["response_duration_ms"] = (time.time() - start_time) * 1000

                new_session["questions"].append(new_qa)
            
            new_user_data["sessions"].append(new_session)
        
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(new_user_data, f, ensure_ascii=False)

        print(f"✅ Saved user {user_name} to {tmp_file}")
        return {"uuid": user_data["uuid"], "status": "ok", "path": tmp_file}

    except Exception as e:
        error_path = os.path.join(tmp_dir, f"{user_data['uuid']}_error.log")
        with open(error_path, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        print(f"❌ Error in user {user_name}: {e}")
        return {"uuid": user_data["uuid"], "status": "error", "path": error_path}


def iter_jsonl(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def main(
    data_path: str,
    version: str = "default",
    top_k: int = 20,
    max_workers: int = 2
):
    frame = "forget"
    _fdb.init_db()
    limit_users = int(os.getenv("HALUMEM_LIMIT_USERS", "0") or 0)
    save_path = f"results/{frame}-{version}/"
    os.makedirs(save_path, exist_ok=True)

    output_file = os.path.join(save_path, f"{frame}_eval_results.jsonl")
    tmp_dir = os.path.join(save_path, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    start_time = time.time()

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for idx, user_data in enumerate(iter_jsonl(data_path), 1):
            if limit_users and idx > limit_users:
                idx -= 1
                break
            uuid = user_data["uuid"]
            future = executor.submit(process_user, user_data, top_k, save_path)
            futures[future] = uuid

        total_users = idx

        for i, future in enumerate(as_completed(futures), 1):
            uuid = futures[future]
            try:
                result = future.result()
                print(f"[{i}/{total_users}] ✅ Finished {uuid} ({result['status']})")
            except Exception as e:
                print(f"[{i}/{total_users}] ❌ Error processing {uuid}: {e}")
                traceback.print_exc()

    with open(output_file, "a", encoding="utf-8") as f_out:
        for file in os.listdir(tmp_dir):
            if file.endswith(".json"):
                file_path = os.path.join(tmp_dir, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f_in:
                        data = json.load(f_in)
                        f_out.write(json.dumps(data, ensure_ascii=False) + "\n")
                except Exception as e:
                    print(f"⚠️ Skipped {file}: {e}")

    elapsed = time.time() - start_time
    print(f"✅ All done in {elapsed:.2f}s")
    print(f"✅ Final results saved to: {output_file}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="pilot"); ap.add_argument("--data", default="../data/HaluMem-Medium.jsonl")
    ap.add_argument("--top-k", type=int, default=20); ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args()
    main(data_path=a.data, version=a.version, top_k=a.top_k, max_workers=a.workers)
