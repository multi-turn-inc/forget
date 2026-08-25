"""P-H-1 릴레이 — 연속성 충실도의 정량화 (헌장 H-1 핵심 계기의 운영화).

## 세목 등록 (2026-08-26 새벽, 숫자 보기 전 고정)

원문(헌장): "같은 규격의 장기 작업을 두 몸에서 — 전량 압축 vs 응고화.
인계 이벤트 각 10회, 인계 오류율 절반 이하 → 채택."

운영화 (개정 사유 공시: 대조군을 Claude Code가 아니라 **같은 pi에서
forget 확장만 끈 몸**으로 — 같은 몸에서 압축 방식만 격리해야 순수 비교.
Claude Code는 실험자 자신이라 자동화 불가):

  팔 A (전량 압축) = pi + 프로바이더 전용 확장(-ne -e provider_only) —
        압축은 pi 기본 요약.
  팔 B (응고화)   = pi + forget 확장(자동 로드) — session_before_compact
        대체 + persist + 재수화.

  릴레이 규격 (시드 고정, 이벤트당 신규 생성):
    ①프로젝트 상태 주입 — 핸들 12개(가짜 커밋 8자리 4·URL 2·날짜 3·
      수치 3)와 미완 의도 3개를 담은 상태 문서를 세션에 준다.
    ②잡음 노동 — 대량 무관 도구 출력(base64 16k)으로 압축을 강제 발동.
    ③인계 질문 — 압축 후 같은 세션에 "핸들 전부와 미완 의도를 정확히
      나열하라"를 묻는다.
  채점 (결정론): 핸들 = 정확 문자열 포함 여부 · 의도 = 키워드(각 의도의
  고유 명사) 포함 여부. 인계 이벤트당 오류율 = 놓친 항목/전체(15).
  유형 분해: 핸들 오류(표본 1호 계열) vs 의도 오류(표본 2호 계열).

  판정: 이벤트 각 10회 — 팔 B 평균 오류율 ≤ 팔 A의 절반 → **채택**
        (연속성 주장의 숫자 확보) / B ≥ A → 응고화 무익 판정, 병소 해부 /
        사이 회색. 부기: 압축 발동 확인(fromHook)·유형 분해·비용($0) 의무.

사용: .venv/bin/python scripts/ph1_relay.py [--events 10] [--arms AB]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PI = Path.home() / ".nvm/versions/node/v22.22.0/bin/pi"
MODEL = "Qwen3.8-27B-UD-Q4_K_XL.gguf"
OUT = REPO / "research/eval/ph1_relay_rows.jsonl"
SESS_DIR = Path.home() / ".pi/agent/sessions"


def make_state(rng: random.Random, event_id: str) -> dict:
    handles = {
        "commits": ["".join(rng.choices("0123456789abcdef", k=8)) for _ in range(4)],
        "urls": [f"https://svc-{rng.randint(100,999)}.example.com/api/v{rng.randint(1,9)}"
                 for _ in range(2)],
        "dates": [f"2026-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}" for _ in range(3)],
        "numbers": [str(rng.randint(10000, 99999)) for _ in range(3)],
    }
    nouns = rng.sample(["heliograph", "quartzite", "peregrine", "malachite",
                        "solenoid", "tamarind", "obsidian", "zephyr"], 3)
    intents = [f"finish the {n}-{rng.randint(10,99)} migration" for n in nouns]
    flat = handles["commits"] + handles["urls"] + handles["dates"] + handles["numbers"]
    doc = (f"PROJECT STATE [{event_id}] — memorize precisely; you will be asked later.\n"
           f"Commits: {', '.join(handles['commits'])}\n"
           f"Endpoints: {', '.join(handles['urls'])}\n"
           f"Key dates: {', '.join(handles['dates'])}\n"
           f"Metrics: {', '.join(handles['numbers'])}\n"
           f"UNFINISHED INTENTS: " + "; ".join(intents))
    return {"doc": doc, "handles": flat, "intents": intents, "nouns": nouns}


def run_pi(arm: str, session_id: str, prompt: str, timeout: int = 480) -> tuple[int, str]:
    cmd = [str(PI), "-p", "--approve", "--session-id", session_id,
           "--provider", "local-qwen", "--model", MODEL]
    if arm == "A":
        cmd[1:1] = ["-ne", "-e", str(REPO / "scripts/ph1_provider_only.ts")]
    cmd.append(prompt)
    try:
        proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True,
                              timeout=timeout)
        return proc.returncode, (proc.stdout + proc.stderr)[-3000:]
    except subprocess.TimeoutExpired:
        return 124, "(timeout)"


def score(answer: str, state: dict) -> dict:
    missed_handles = [h for h in state["handles"] if h not in answer]
    missed_intents = [n for n in state["nouns"] if n not in answer]
    total = len(state["handles"]) + len(state["nouns"])
    missed = len(missed_handles) + len(missed_intents)
    return {"total": total, "missed": missed, "err_rate": round(missed / total, 3),
            "missed_handles": len(missed_handles), "missed_intents": len(missed_intents)}


def compaction_count(session_id: str) -> tuple[int, int]:
    """세션 파일에서 (압축 수, fromHook 수)."""
    n = hook = 0
    for f in SESS_DIR.glob(f"*/*{session_id}*.jsonl"):
        for line in f.read_text(errors="replace").splitlines():
            if '"type":"compaction"' in line or '"type": "compaction"' in line:
                n += 1
                try:
                    if json.loads(line).get("fromHook"):
                        hook += 1
                except ValueError:
                    pass
    return n, hook


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=10)
    ap.add_argument("--arms", default="AB")
    ap.add_argument("--seed", type=int, default=20260826)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    states = [make_state(rng, f"E{i}") for i in range(args.events)]
    with open(OUT, "a") as fout:
        for i, state in enumerate(states):
            for arm in args.arms:
                sid = f"ph1-{arm}-{args.seed}-{i}"
                t0 = time.time()
                c1, _ = run_pi(arm, sid,
                               state["doc"] + "\n\nAcknowledge in one short sentence.")
                time.sleep(2)   # 연속 -p 경합 가드 — 세션 쓰기 완료 대기
                # 잡음 노동으로 압축 강제 (h1-compact 시리즈 검증 기법)
                c2, _ = run_pi(arm, sid,
                               "Step 1: use bash to run: head -c 24000 /dev/urandom | "
                               "base64 | head -c 16000. Step 2: run: echo NOISE-DONE. "
                               "Keep your reply short.")
                time.sleep(2)
                c3, out3 = run_pi(arm, sid,
                                  "HANDOVER CHECK: from the project state given earlier, "
                                  "list EVERY commit hash, endpoint URL, key date, metric "
                                  "number, and every unfinished intent — exactly as given. "
                                  "No commentary.")
                n_comp, n_hook = compaction_count(sid)
                row = {"arm": arm, "event": i, "codes": [c1, c2, c3],
                       "compactions": n_comp, "from_hook": n_hook,
                       "secs": round(time.time() - t0, 1), **score(out3, state),
                       "answer": out3[-600:]}
                fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                fout.flush()
                print(f"[{arm}{i}] comp={n_comp}(hook {n_hook}) err={row['err_rate']} "
                      f"(핸들 {row['missed_handles']}·의도 {row['missed_intents']} 누락) "
                      f"{row['secs']}s", flush=True)
    rows = [json.loads(l) for l in open(OUT)]
    for arm in "AB":
        sub = [r for r in rows if r["arm"] == arm and r["compactions"] > 0]
        if sub:
            avg = sum(r["err_rate"] for r in sub) / len(sub)
            print(f"팔 {arm}: 압축 발동 이벤트 {len(sub)} · 평균 인계 오류율 {avg:.3f}")


if __name__ == "__main__":
    main()
