#!/usr/bin/env python3
"""섀도 곡선 소급 채점 — 라이브 재료 고갈(공통 64/100)의 정직한 보충.

문제: 곡선은 정훈의 실발화가 도착해야 자란다. 밤사이 새 턴이 없어 64에서
정체했고, §9 선등록("순위 주장은 공통 턴 n>=100")을 며칠 못 채운다.

처치: 로컬 트랜스크립트(4월~)의 과거 턴을 같은 데몬 로직으로 채점한다.
정직 규율 — 이것은 라이브 예측이 아니다:
- 변형 라벨에 `retro:` 접두를 박는다. 라이브 곡선과 절대 한 분모에 안 섞인다.
- 순위 비교는 retro 변형끼리만 (동일 재료·동일 시각·짝지음 보장).
- 컨텍스트는 그 턴 이전의 어시스턴트 발화만 (미래 누출 없음 — 트랜스크립트
  순서가 곧 시간 순서).
- 채점 방법(k=5 표집·sim 평균·방향 다수결)은 데몬과 동일 — 자[尺] 불변.

사용: TWIN_MODEL/TWIN_VARIANT/TWIN_URL은 데몬과 동일 환경변수.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".forget/twin"))
from shadow_daemon import (  # noqa: E402  데몬의 자를 그대로 빌린다
    CORRECT, APPROVE, EMB_MODEL, EMB_URL, NOISE, SAMPLES_PER_TURN, TWIN_MODEL,
    _text, direction, embed_sim, twin_predict,
)

TRANSCRIPT_DIR = Path.home() / ".claude/projects"
TWIN_DIR = Path.home() / ".forget/twin"
SCORES = TWIN_DIR / "shadow_scores.jsonl"
VARIANT = "retro:" + os.environ.get("TWIN_VARIANT", f"prompt-only/{TWIN_MODEL}")
# 변형별 상태 분리 (2026-08-15 결함 ⑨): 공유 상태로 돌렸더니 첫 변형이 채점한
# 턴을 두 번째가 건너뛰어 공통 턴 0 — 짝지은 비교가 구조적으로 불가능했다.
# 데몬에는 이미 있던 규율의 반쪽 이식이 원인. 같은 턴을 두 변형이 각각 채점해야
# 짝지음이 성립한다.
_SLUG = "".join(c if c.isalnum() else "-" for c in VARIANT)
STATE = TWIN_DIR / f"shadow_retro_state.{_SLUG}.json"
MAX_TURNS = int(os.environ.get("RETRO_MAX", "60"))


def iter_past_turns():
    """트랜스크립트에서 (직전 어시스턴트 발화, 정훈 실발화, ts) — 최신 파일부터."""
    files = sorted(TRANSCRIPT_DIR.glob("*/*.jsonl"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        last_asst = ""
        try:
            for line in f.open():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                typ, msg = row.get("type"), (row.get("message") or {})
                if typ == "assistant":
                    t = _text(msg.get("content")).strip()
                    if t:
                        last_asst = t
                    continue
                if typ != "user":
                    continue
                u = _text(msg.get("content")).strip()
                u = re.split(r"\n\[forget|\n<system-reminder|\nSessionStart:|<local-command", u)[0].strip()
                if not u or len(u) < 4 or u.startswith("[{") or NOISE.search(u[:200]):
                    continue
                if not last_asst.strip():
                    continue
                digest = hashlib.md5(u[:80].encode("utf-8", "ignore")).hexdigest()[:8]
                yield {"key": f"retro:{f.name}:{row.get('timestamp','')}:{digest}",
                       "ctx": last_asst, "actual": u[:800],
                       "ts": str(row.get("timestamp") or "")}
        except OSError:
            continue


def main() -> None:
    try:
        done = set(json.loads(STATE.read_text()).get("done", []))
    except Exception:
        done = set()
    scored = 0
    for turn in iter_past_turns():
        if turn["key"] in done or scored >= MAX_TURNS:
            if scored >= MAX_TURNS:
                break
            continue
        preds = []
        for _ in range(SAMPLES_PER_TURN):
            try:
                p = twin_predict(turn["ctx"])
            except Exception as exc:
                print(f"[skip] 생성 실패: {exc}", file=sys.stderr)
                STATE.write_text(json.dumps({"done": sorted(done)[-8000:]}))
                sys.exit(1)
            if p:
                preds.append(p)
        if not preds:
            done.add(turn["key"])
            continue
        sims = [s for s in (embed_sim(p, turn["actual"]) for p in preds) if s >= 0]
        sim = sum(sims) / len(sims) if sims else -1.0
        dirs_pred = [direction(p) for p in preds]
        d_pred = max(set(dirs_pred), key=dirs_pred.count)
        d_act = direction(turn["actual"])
        with SCORES.open("a") as fh:
            fh.write(json.dumps({
                "ts": turn["ts"], "scored_at": time.strftime("%F %T"),
                "sim": round(sim, 4), "dir_pred": d_pred, "dir_actual": d_act,
                "dir_match": d_pred == d_act, "k": len(preds),
                "dir_votes": {d: dirs_pred.count(d) for d in set(dirs_pred)},
                "pred_head": preds[0][:160], "actual_head": turn["actual"][:160],
                "ctx": turn["ctx"][-1600:], "actual": turn["actual"],
                "engine": TWIN_MODEL, "variant": VARIANT, "retro": True,
            }, ensure_ascii=False) + "\n")
        done.add(turn["key"])
        scored += 1
        if scored % 10 == 0:
            print(f"  {scored}턴 채점", file=sys.stderr)
    STATE.write_text(json.dumps({"done": sorted(done)[-8000:], "updated": time.strftime("%F %T")}))
    print(f"소급 채점 {scored}턴 ({VARIANT})")


if __name__ == "__main__":
    main()
