#!/usr/bin/env python3
"""B층 — 작업 상태 자동 캡처 (Stop·PreCompact·SessionEnd 훅).

P39 실증(2026-08-15, e1f6a94): 4청크 구조화 상태 {목표, 직전 사건, 미결,
다음 손}는 같은 예산의 원문보다 턴-수준 예측 정보를 +62% 더 만든다.
이 훅은 그 상태를 사람 규율 없이 자동으로 유지한다 — 인간 작업 기억의
기계판: 작게(≤600자), 항상 최신, 세션이 죽어도 살아남는다.

설계 제약과 해법:
- 훅 타임아웃은 5초, LLM 요약은 10~40초 → 훅은 **분리-발사**: 워커를
  setsid로 떼어 즉시 exit 0. 캡처 실패는 다음 캡처가 덮는다 (fail-open).
- Stop은 매 턴 발화 → mtime 스로틀(THROTTLE_MIN분). SessionEnd·PreCompact은
  무조건 캡처 — 노트북 덮음·압축이 바로 B층이 살아남아야 할 순간이다.
- LLM 불가 시 구조적 폴백 — 마지막 사용자 요구·어시스턴트 보고 머리로
  4청크를 기계 조립. 낮은 품질의 상태가 무상태보다 낫다.
- 쓰기는 원자적(tmp+rename), 이력은 append(계기용) — 원장 불변 규율.

저장: ~/.forget/bstate/<project>.json (현재) + <project>.history.jsonl (이력).
주입: forget_sessionstart.py가 파일을 직접 읽는다 — 회상 경합·슬롯 경쟁 없음.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from forget_project import project_key_for_path  # noqa: E402

BSTATE_DIR = os.path.expanduser("~/.forget/bstate")
THROTTLE_MIN = int(os.environ.get("FORGET_BSTATE_THROTTLE_MIN", "10"))
DIALOGUE_BUDGET = 6000          # 요약 입력 (P39와 동일)
STATE_BUDGET = 600              # 4청크 상태 예산 (P39와 동일)
SUMM_ENGINES = (                # 순서대로 시도 — Spark 27B → 로컬 ollama
    ("http://127.0.0.1:11435/api/chat", "qwen3.6:27b"),
    ("http://127.0.0.1:11434/api/chat", "qwen3.5:9b"),
)
CHUNK_KEYS = ("목표", "직전 사건", "미결", "다음 손")

NOISE = re.compile(
    r"\[forget 회상|\[forget 캡슐|<command-|<local-command|<bash-input"
    r"|<system-reminder|Caveat:|\[SYSTEM NOTIFICATION|<task-notification"
    r"|SUGGESTION MODE|Recap in under", re.I)


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content
                         if isinstance(p, dict) and p.get("type") == "text")
    return ""


def extract_dialogue(transcript_path: str, budget: int = DIALOGUE_BUDGET) -> list[tuple[str, str]]:
    """트랜스크립트에서 (역할, 텍스트) 대화 턴 — 꼬리 budget자."""
    turns: list[tuple[str, str]] = []
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                typ = row.get("type")
                if typ not in ("user", "assistant"):
                    continue
                t = _text_of((row.get("message") or {}).get("content")).strip()
                if not t:
                    continue
                if typ == "user":
                    head = re.split(r"\n\[forget|\n<system-reminder|\nSessionStart:|<local-command", t)[0].strip()
                    if not head or head.startswith("[{") or NOISE.search(head[:200]):
                        continue
                    turns.append(("user", head[:800]))
                else:
                    turns.append(("assistant", t[:2000]))
    except OSError:
        return []
    # 꼬리 예산 절단
    out, total = [], 0
    for role, t in reversed(turns):
        take = t[: max(0, budget - total)]
        if not take:
            break
        out.append((role, take))
        total += len(take)
    return list(reversed(out))


def dialogue_text(turns: list[tuple[str, str]]) -> str:
    return "\n".join(f"[{'정훈' if r == 'user' else '에이전트'}] {t}" for r, t in turns)


def parse_chunks(text: str) -> dict:
    """요약 출력에서 4청크를 관대하게 파싱 — 누락 키는 폴백 몫."""
    chunks = {}
    for key in CHUNK_KEYS:
        m = re.search(rf"{key}\s*[:：]\s*(.+)", text)
        if m:
            chunks[key] = m.group(1).strip()[:160]
    return chunks


def llm_state(turns: list[tuple[str, str]]) -> dict:
    prompt = ("다음은 개발자(정훈)와 에이전트의 대화다. 이 시점의 작업 상태를 정확히 4줄로 압축하라.\n"
              "형식(각 줄 120자 이내):\n목표: …\n직전 사건: …\n미결: …\n다음 손: …\n\n"
              + dialogue_text(turns))
    for url, model in SUMM_ENGINES:
        try:
            req = urllib.request.Request(url, data=json.dumps({
                "model": model, "stream": False, "think": False, "keep_alive": "3h",
                "messages": [{"role": "user", "content": prompt}],
                "options": {"temperature": 0.0, "num_predict": 300},
            }).encode(), headers={"Content-Type": "application/json"})
            body = json.loads(urllib.request.urlopen(req, timeout=90).read())
            chunks = parse_chunks(str((body.get("message") or {}).get("content") or ""))
            if len(chunks) >= 3:
                chunks["_engine"] = model
                return chunks
        except Exception:
            continue
    return {}


def structural_state(turns: list[tuple[str, str]]) -> dict:
    """LLM 불가 시 기계 조립 — 낮은 품질의 상태가 무상태보다 낫다."""
    last_user = next((t for r, t in reversed(turns) if r == "user"), "")
    last_asst = next((t for r, t in reversed(turns) if r == "assistant"), "")
    return {
        "목표": last_user[:160] or "(요약 불가)",
        "직전 사건": last_asst[:160] or "(요약 불가)",
        "미결": "(구조적 폴백 — LLM 요약 실패)",
        "다음 손": last_user[:160] or "(요약 불가)",
        "_engine": "structural-fallback",
    }


def write_state(project: str, chunks: dict, transcript_path: str, event: str) -> None:
    os.makedirs(BSTATE_DIR, exist_ok=True)
    state = {
        "project": project,
        "captured_at": time.strftime("%FT%T%z"),
        "event": event,
        "engine": chunks.pop("_engine", "?"),
        "chunks": {k: chunks.get(k, "") for k in CHUNK_KEYS},
        "transcript": os.path.basename(transcript_path),
    }
    path = os.path.join(BSTATE_DIR, f"{project}.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)  # 원자적 — 반쯤 쓰인 상태 파일은 존재하지 않는다
    with open(os.path.join(BSTATE_DIR, f"{project}.history.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(state, ensure_ascii=False) + "\n")


def load_state(project: str) -> dict | None:
    try:
        with open(os.path.join(BSTATE_DIR, f"{project}.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def render_block(state: dict) -> str:
    """세션 시작 주입용 — 작게, 신선도 명기."""
    try:
        captured = time.mktime(time.strptime(state["captured_at"][:19], "%Y-%m-%dT%H:%M:%S"))
        age_min = int((time.time() - captured) / 60)
    except Exception:
        age_min = -1
    age = (f"{age_min}분 전" if 0 <= age_min < 120 else
           f"{age_min // 60}시간 전" if age_min >= 0 else "시각 불명")
    stale = " ⚠오래됨 — 재검증 후 행동" if age_min > 24 * 60 else ""
    lines = [f"[B층 — 마지막 작업 상태 (캡처 {age}{stale}, {state.get('event', '?')})]"]
    for k in CHUNK_KEYS:
        v = (state.get("chunks") or {}).get(k, "")
        if v:
            lines.append(f"{k}: {v}")
    return "\n".join(lines)[:STATE_BUDGET + 200]


def worker(transcript_path: str, project: str, event: str) -> None:
    turns = extract_dialogue(transcript_path)
    if len(turns) < 2:
        return
    chunks = llm_state(turns) or structural_state(turns)
    write_state(project, chunks, transcript_path, event)


def hook_entry() -> None:
    """훅 본체 — 즉시 반환. 판단은 전부 여기서, 노동은 워커에서."""
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    transcript = str(payload.get("transcript_path") or "")
    cwd = str(payload.get("cwd") or os.getcwd())
    event = str(payload.get("hook_event_name") or "?")
    if not transcript or not os.path.exists(transcript):
        return
    project = project_key_for_path(cwd) or "global"
    # Stop은 매 턴 — 스로틀. 종료·압축은 B층이 살아남아야 할 순간이라 무조건.
    if event == "Stop":
        try:
            age = time.time() - os.path.getmtime(os.path.join(BSTATE_DIR, f"{project}.json"))
            if age < THROTTLE_MIN * 60:
                return
        except OSError:
            pass  # 상태 없음 — 첫 캡처
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--worker", transcript, project, event],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,  # 훅 프로세스와 운명 분리
    )


if __name__ == "__main__":
    if len(sys.argv) >= 5 and sys.argv[1] == "--worker":
        worker(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        hook_entry()
