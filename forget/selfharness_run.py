"""자기 하네스 H-0 러너 — Tool Runner 루프 (헌장 개정 1의 채택안 실물).

사용:
  ANTHROPIC_API_KEY=... .venv/bin/python -m forget.selfharness_run "<작업>"
  ANTHROPIC_API_KEY=... .venv/bin/python -m forget.selfharness_run --resume  # 죽은 run 이어받기

P-H-0 시나리오: ①실작업 완주(done 도구 + 인계 노트) ②도중 SIGKILL →
--resume 기상 → 이어받기 성공(인계 오류 0) ③비용 병기(CostGuard, $2 상한).

도구 최소셋 (H-0): bash(저장소 안, 타임아웃) · read_file · forget_search
(B-② instrument 동봉 — 자기사용 규약 3항의 실소비) · world_timeline ·
arm_hand/release_hand(유언장 — 표본 2호의 답) · done.
context_management: clear_tool_uses_20250919 배선 (발동 검증은 H-1).
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

from anthropic import Anthropic, beta_tool

from . import selfharness as sh
from . import worldmodel

REPO = Path(__file__).resolve().parent.parent
_STATE: dict = {"done_note": None}


@beta_tool
def bash(command: str) -> str:
    """Run a shell command inside the repository (cwd fixed, 60s timeout)."""
    proc = subprocess.run(command, shell=True, cwd=str(REPO), timeout=60,
                          capture_output=True, text=True)
    out = (proc.stdout + proc.stderr)[-4000:]
    return f"exit={proc.returncode}\n{out}"


@beta_tool
def read_file(path: str, offset: int = 0, limit: int = 200) -> str:
    """Read a file inside the repository (line offset/limit)."""
    target = (REPO / path).resolve()
    if not str(target).startswith(str(REPO)):
        return "거부: 저장소 밖 경로"
    lines = target.read_text(errors="replace").splitlines()
    return "\n".join(lines[offset:offset + limit])[:16000]


@beta_tool
def forget_search(query: str, top_k: int = 5) -> str:
    """Search the forget memory ledger. Returns results plus the instrument
    block (top_score / strength / evidence_span_days / pool_exhausted) —
    use it to decide whether to keep groping or stop."""
    req = urllib.request.Request(
        f"{sh.FORGET_URL}/v1/memories/search/",
        data=json.dumps({"query": query, "filters": {"user_id": sh.USER_ID},
                         "top_k": top_k}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
    lines = [f"[instrument] {json.dumps(data.get('instrument'), ensure_ascii=False)}"]
    for m in data.get("results") or []:
        lines.append(f"- ({m.get('score')}) {str(m.get('memory'))[:200]}")
    return "\n".join(lines)[:8000]


@beta_tool
def world_timeline(keyword: str = "", since: str = "", until: str = "") -> str:
    """Query the world model event timeline (structure layer: dates and titles)."""
    events = worldmodel.timeline(worldmodel.DEFAULT_WORLD_DB, like=keyword or None,
                                 since=since or None, until=until or None, limit=40)
    return "\n".join(f"{e['t'][:10]} · {e['title'][:90]}" for e in events) or "(없음)"


@beta_tool
def arm_hand(hand_id: str, kind: str, what: str, why: str, source_ref: str) -> str:
    """Register a standing hand (watch|intent|resume) so the NEXT wake inherits
    it. Required whenever you leave something running or unfinished."""
    out = worldmodel.arm_hand(worldmodel.DEFAULT_WORLD_DB, hand_id, kind, what, why, source_ref)
    return json.dumps(out, ensure_ascii=False)


@beta_tool
def release_hand(hand_id: str, reason: str) -> str:
    """Release a standing hand with a reason (no empty releases)."""
    out = worldmodel.release_hand(worldmodel.DEFAULT_WORLD_DB, hand_id, reason)
    return json.dumps(out, ensure_ascii=False)


@beta_tool
def done(handover_note: str) -> str:
    """Declare the task complete. handover_note = what the next wake must know
    (what was done, receipts, what remains). This ends the run."""
    _STATE["done_note"] = handover_note
    return "run 종료 등록됨"


TOOLS = [bash, read_file, forget_search, world_timeline, arm_hand, release_hand, done]


def run(task: str, resume_run: int | None = None, max_iterations: int = 40) -> dict:
    state = sh.wake(task, resume_run=resume_run)
    run_id = state["run_id"]
    guard = sh.CostGuard()
    client = Anthropic()
    seq = 0
    for msg in state["messages"]:
        sh.record_turn(run_id, seq, msg["role"], msg["content"])
        seq += 1
    runner = client.beta.messages.tool_runner(
        model=sh.MODEL,
        max_tokens=4096,
        system=state["system"],
        messages=state["messages"],
        tools=TOOLS,
        max_iterations=max_iterations,
        context_management={"edits": [{
            "type": "clear_tool_uses_20250919",
            "trigger": {"type": "input_tokens", "value": 60000},
            "keep": {"type": "tool_uses", "value": 5},
        }]},
    )
    end_reason = "max_iterations"
    for message in runner:
        sh.record_turn(run_id, seq, "assistant",
                       [b.model_dump() for b in message.content])
        seq += 1
        step_cost = guard.add_usage(message.usage)
        print(f"[h0 run {run_id}] step {seq} · +${step_cost:.4f} · 누적 ${guard.spent_usd:.4f}",
              flush=True)
        if _STATE["done_note"] is not None:
            end_reason = "done"
            break
        if guard.exceeded:
            end_reason = "cost_cap"
            print(f"[h0] 비용 상한 ${guard.cap_usd} 도달 — 정중히 종료", flush=True)
            break
    sh.finish_run(run_id, end_reason, guard.spent_usd)
    result = {"run_id": run_id, "end_reason": end_reason,
              "cost_usd": round(guard.spent_usd, 4), "handover": _STATE["done_note"]}
    print(json.dumps(result, ensure_ascii=False))
    return result


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--resume":
        prior = sh.last_unfinished_run()
        if prior is None:
            sys.exit("이어받을 미종결 run 없음")
        conn_task = None
        import sqlite3
        conn = sqlite3.connect(sh.HARNESS_DB)
        conn_task = conn.execute("SELECT task FROM runs WHERE id=?", (prior,)).fetchone()[0]
        conn.close()
        run(conn_task, resume_run=prior)
    elif args:
        run(" ".join(args))
    else:
        sys.exit('사용: python -m forget.selfharness_run "<작업>" | --resume')


if __name__ == "__main__":
    main()
