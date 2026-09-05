#!/usr/bin/env python3
"""ai.forget.replay — 야간 리플레이 v0 (매일 04:17, launchd).

수면 응고의 기계 몫: ① 스트림 TTL 집행 ② 프록시 스트림 + CC 트랜스크립트에서
훈련쌍 후보 채굴·병합. 어댑터 훈련 자체는 아직 사람 게이트 뒤(데이터 ≥300 +
연구실 4090 반입) — 이 잡은 원료를 매일 신선하게 유지한다.
설계 정본: research/replay-device-v0.md. 결정론·무LLM — 심장박동(의식)과 분리.
"""
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from forget.proxy_stream import purge_expired, reconstruct, to_cc_rows  # noqa: E402
import mine_pairs  # noqa: E402

STREAM_DIR = Path.home() / ".forget/proxy/stream"
LOG = Path.home() / ".forget/proxy/replay-nightly.log"
CANDIDATES = HERE / "candidates_v0.jsonl"


def fingerprint(r: dict):
    return (r["class"], r.get("user_head") or "", r.get("error_head") or "",
            r.get("failed_input_head") or "")


def main() -> None:
    now = time.time()
    summary = {"ts": time.strftime("%F %T")}

    # ① TTL — 원료는 14일만 산다 (증류물만 영속)
    try:
        removed = purge_expired(STREAM_DIR, ttl_days=14)
        summary["ttl_removed"] = len(removed)
    except Exception as exc:
        summary["ttl_error"] = str(exc)[:120]

    # ② 스트림 채굴 (프록시가 있는 날만)
    stream_rows = []
    try:
        if STREAM_DIR.is_dir():
            result = reconstruct(STREAM_DIR)
            summary["stream_stats"] = result["stats"]
            for sess in result["sessions"]:
                for si, seg in enumerate(sess["segments"]):
                    rows = to_cc_rows(seg)
                    stream_rows += mine_pairs.mine_rows(rows, f"stream:{sess['key']}:{si}", now)
    except Exception as exc:
        summary["stream_error"] = str(exc)[:120]
    summary["stream_candidates"] = len(stream_rows)

    # ③ 병합 — 기존 후보에 지문 중복 제거로 증분만
    existing = []
    seen = set()
    if CANDIDATES.exists():
        for line in CANDIDATES.open():
            try:
                r = json.loads(line)
            except Exception:
                continue
            existing.append(r)
            seen.add(fingerprint(r))
    added = 0
    for r in stream_rows:
        if fingerprint(r) in seen:
            continue
        seen.add(fingerprint(r))
        r["priority"] = r["weight"]  # 신선 후보 — 감쇠 전
        existing.append(r)
        added += 1
    if added:
        existing.sort(key=lambda r: -r.get("priority", 0))
        with CANDIDATES.open("w") as fh:
            for r in existing:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary["added"] = added
    summary["total"] = len(existing)

    with LOG.open("a") as fh:
        fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
