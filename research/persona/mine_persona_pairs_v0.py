#!/usr/bin/env python3
"""인격 코퍼스 v0 — (문맥 → 나의 발화) 채굴 (persona-pivot.md §4.2).

voice_pairs 채굴기의 반전판: 프록시 스트림의 request_messages 안에서
각 assistant 텍스트 발화를 표적으로, 직전 문맥(마지막 user 텍스트 + 그
이전 assistant 요약분)을 입력으로 캔다.

러닝북 적용 (2026-08-13~14 결함 5건의 교훈):
- 중복 제거 키 = hashlib.md5 (결정론 — 내장 hash() 금지)
- 표적 필터: 빈 발화·초단문(<20자)·자동화 지문 — 단 표적은 '나'의 산출이라
  인간-발화 오염축은 없음; 문맥 오염은 입력이므로 허용(학습 분포의 일부)
- 시간 컷오프 스탬프: 매니페스트에 채굴 시점·소스 파일 목록 기록
- 홀드아웃: 시간순 꼬리 60쌍을 훈련 파일과 별도 저장 (train_twin_v0 관례)
- 파일명: 버전 명시, 조건이 갈리면 접미사 축 추가 (덮어쓰기 사고 2호 교훈)

원점 계기 주의 (게이트 감사 §5·§9 구속): 인격 v0의 판별기 원점은 보강판
게이트(길이-통제/묶음, n>=40, 널 선등재)로만 측정한다 — 이 채굴기는 재료만 만든다.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path

STREAM_DIR = Path.home() / ".forget/proxy/stream"
# 본광맥 (becoming-junghun.md §0 '말' 기관 원료): Claude Code 로컬 트랜스크립트.
# 프록시 스트림(8/12 개통)보다 훨씬 깊은 이력 — 수천 세션의 나의 발화.
TRANSCRIPT_DIR = Path.home() / ".claude/projects"
OUT_DIR = Path(__file__).resolve().parent
TRAIN = OUT_DIR / "persona_pairs_v0.jsonl"
HOLDOUT = OUT_DIR / "persona_holdout_v0.json"
MANIFEST = OUT_DIR / "persona_pairs_v0.manifest.json"
HOLDOUT_N = 60
MIN_CHARS = 20
MAX_RESP_CHARS = 6000  # 초장문은 꼬리 절단 아닌 제외 — 발화의 자연 단위 보존
CTX_TAIL = 1600

# 표적(나의 발화)에 섞이면 안 되는 것: 시스템 산출·자동화 지문
TARGET_CONTAM = re.compile(
    r"\[Request interrupted|\[SUGGESTION MODE|SIMULATION|<system-reminder"
    r"|API Error|no content yet",
    re.I,
)


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content
                         if isinstance(p, dict) and p.get("type") == "text")
    return ""


def mine() -> tuple[list[dict], dict]:
    seen: set[str] = set()
    pairs: list[dict] = []
    stats = {"rows": 0, "assistant_turns": 0, "dropped_short": 0,
             "dropped_long": 0, "dropped_contam": 0, "dropped_dup": 0}
    files = sorted(STREAM_DIR.glob("*.jsonl"))
    for f in files:
        for line in f.open():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            stats["rows"] += 1
            msgs = row.get("request_messages") or []
            # 마지막 assistant 텍스트 발화를 표적으로 — 그 앞이 문맥.
            # (요청마다 대화가 통째로 실려오므로, 마지막 것만 취하고 중복
            #  제거가 이전 요청에서 이미 캔 발화를 걸러낸다.)
            for idx in range(len(msgs) - 1, -1, -1):
                if msgs[idx].get("role") != "assistant":
                    continue
                resp = _text(msgs[idx].get("content")).strip()
                if not resp:
                    continue
                stats["assistant_turns"] += 1
                if len(resp) < MIN_CHARS:
                    stats["dropped_short"] += 1
                    break
                if len(resp) > MAX_RESP_CHARS:
                    stats["dropped_long"] += 1
                    break
                if TARGET_CONTAM.search(resp[:400]):
                    stats["dropped_contam"] += 1
                    break
                key = hashlib.md5(resp[:120].encode("utf-8", "ignore")).hexdigest()
                if key in seen:
                    stats["dropped_dup"] += 1
                    break
                # 문맥: 표적 직전의 마지막 user 텍스트 (도구 결과 제외)
                ctx = ""
                for m in reversed(msgs[:idx]):
                    if m.get("role") == "user":
                        t = _text(m.get("content")).strip()
                        if t:
                            ctx = t
                            break
                if not ctx:
                    break
                seen.add(key)
                pairs.append({"context": ctx[-CTX_TAIL:], "response": resp,
                              "ts": row.get("ts", ""), "src": f.name})
                break  # 요청당 마지막 발화 1건
    # 소스 B: 로컬 트랜스크립트 — 행 스키마 {type, message:{role, content}, timestamp}
    stats["transcript_files"] = 0
    for f in TRANSCRIPT_DIR.glob("*/*.jsonl"):
        stats["transcript_files"] += 1
        last_user = ""
        try:
            lines = f.open()
            for line in lines:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                typ = row.get("type")
                msg = row.get("message") or {}
                if typ == "user":
                    t = _text(msg.get("content")).strip()
                    if t and not t.startswith("[{"):
                        last_user = t
                    continue
                if typ != "assistant":
                    continue
                resp = _text(msg.get("content")).strip()
                if not resp:
                    continue
                stats["assistant_turns"] += 1
                if len(resp) < MIN_CHARS:
                    stats["dropped_short"] += 1
                    continue
                if len(resp) > MAX_RESP_CHARS:
                    stats["dropped_long"] += 1
                    continue
                if TARGET_CONTAM.search(resp[:400]):
                    stats["dropped_contam"] += 1
                    continue
                key = hashlib.md5(resp[:120].encode("utf-8", "ignore")).hexdigest()
                if key in seen:
                    stats["dropped_dup"] += 1
                    continue
                if not last_user:
                    continue
                seen.add(key)
                pairs.append({"context": last_user[-CTX_TAIL:], "response": resp,
                              "ts": str(row.get("timestamp") or ""), "src": f.parent.name[:40]})
        except OSError:
            continue
    pairs.sort(key=lambda p: p["ts"])
    return pairs, stats


def main() -> None:
    pairs, stats = mine()
    if len(pairs) <= HOLDOUT_N:
        sys.exit(f"쌍 {len(pairs)}개 — 홀드아웃({HOLDOUT_N}) 분리 불가, 재료 부족")
    holdout = pairs[-HOLDOUT_N:]
    train = pairs[:-HOLDOUT_N]
    with TRAIN.open("w") as fh:
        for p in train:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    HOLDOUT.write_text(json.dumps(holdout, ensure_ascii=False))
    lens = sorted(len(p["response"]) for p in pairs)
    manifest = {
        "built_at": time.strftime("%FT%T%z"),
        "source_files": [f.name for f in sorted(STREAM_DIR.glob("*.jsonl"))],
        "train_n": len(train), "holdout_n": len(holdout),
        "response_chars": {"median": lens[len(lens) // 2],
                           "p10": lens[len(lens) // 10],
                           "p90": lens[len(lens) * 9 // 10]},
        "filters": {"min_chars": MIN_CHARS, "max_chars": MAX_RESP_CHARS,
                    "target_contam": TARGET_CONTAM.pattern},
        "stats": stats,
        "gate_constraint": "원점 판별기는 보강판(길이-통제/묶음, n>=40, 널 선등재)으로만",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({"train": len(train), "holdout": len(holdout),
                      "resp_median": manifest["response_chars"]["median"],
                      **stats}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
