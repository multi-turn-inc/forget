#!/usr/bin/env python3
"""리플레이 장치 v0 — 훈련쌍 채굴기 (research/replay-device-v0.md 스펙의 [선별] 구현).

Claude Code 세션 트랜스크립트에서 어댑터 훈련쌍 후보를 채굴한다.
클래스 서열은 스펙 그대로: 교정(3) > 함정(2) > helped(1). 각 후보에
출처(세션·행 번호)를 달아 검수 가능하게 남긴다 — 자동 승격은 하지 않는다
(EDV: 증류자와 검증자 분리). NLL-놀라움 가중은 v1(모델 패스 필요), 여기선
시효 감쇠만 곱한다 (Freshness-PER 2604.16918).
"""
import json
import math
import os
import re
import sys
import time
from pathlib import Path

PROJECT_DIRS = [
    Path.home() / ".claude/projects/-Users-junghunkim-orca-workspaces-forget----------------",
    Path.home() / ".claude/projects/-Users-junghunkim-Documents-forget",
]
# 교정 신호: 사용자 턴 서두의 부정·정정 표지. 보수적으로 서두 40자만 본다 —
# 본문 중간의 "아니"는 담화 표지일 때가 많다 (오탐이 정탐보다 비싸다).
SYS_NOISE = re.compile(r"task-notification|<task-id>|tool-use-id|SYSTEM NOTIFICATION|<summary>|Monitor event|<local-command|<command-name>|<bash-input>|0{8,}|This is how Claude Code|stepped away|Recap in under")
CORRECTION_HEAD = re.compile(
    r"^(아니|아냐|그게 아니라|틀렸|잘못|하지 ?마|왜 |그러지 말고|다시 해|말고)", re.U
)
HALF_LIFE_DAYS = 14.0  # 시효 감쇠 반감기 — 크럭스 2주 창과 정렬


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
        )
    return ""


def _decay(ts: str, now: float) -> float:
    try:
        age_days = max(0.0, (now - time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))) / 86400)
    except Exception:
        return 1.0
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


def mine_session(path: Path, now: float):
    rows = []
    for lineno, line in enumerate(path.open(), 1):
        try:
            d = json.loads(line)
        except Exception:
            continue
        d["_line"] = lineno
        rows.append(d)
    return mine_rows(rows, path.name, now)


def mine_rows(rows: list, source_label: str, now: float):
    """행 리스트에서 채굴 — CC 트랜스크립트와 프록시 스트림(to_cc_rows) 공용 진입점."""
    for i, d in enumerate(rows, 1):
        d.setdefault("_line", i)

    class path:  # src 표기 호환용 최소 셔밍
        name = source_label

    out = []
    # 함정 아크: is_error 도구 결과 → 이후 6턴 내 같은 도구의 성공 호출.
    tooluse_by_id = {}
    for i, d in enumerate(rows):
        if d.get("type") != "assistant":
            continue
        for p in (d.get("message") or {}).get("content") or []:
            if isinstance(p, dict) and p.get("type") == "tool_use":
                tooluse_by_id[p.get("id")] = (i, p)
    for i, d in enumerate(rows):
        if d.get("type") != "user":
            continue
        for p in (d.get("message") or {}).get("content") or []:
            if not (isinstance(p, dict) and p.get("type") == "tool_result" and p.get("is_error")):
                continue
            src = tooluse_by_id.get(p.get("tool_use_id"))
            if not src:
                continue
            _, failed_use = src
            tool = failed_use.get("name")
            for j in range(i + 1, min(i + 13, len(rows))):  # ~6턴(어시+유저 쌍)
                nxt = rows[j]
                if nxt.get("type") != "assistant":
                    continue
                for q in (nxt.get("message") or {}).get("content") or []:
                    if isinstance(q, dict) and q.get("type") == "tool_use" and q.get("name") == tool:
                        out.append({
                            "class": "trap", "weight": 2.0,
                            "tool": tool,
                            "error_head": str(_text_of([p]) or p.get("content"))[:200],
                            "failed_input_head": json.dumps(failed_use.get("input", {}), ensure_ascii=False)[:200],
                            "retry_input_head": json.dumps(q.get("input", {}), ensure_ascii=False)[:200],
                            "src": f"{path.name}:{d['_line']}",
                            "ts": d.get("timestamp", ""),
                        })
                        break
                else:
                    continue
                break
    # 교정 후보: 사용자 텍스트 턴 서두가 정정 표지 → 직전 어시스턴트 턴이 거부 후보.
    for i, d in enumerate(rows):
        if d.get("type") != "user":
            continue
        text = _text_of((d.get("message") or {}).get("content"))
        if not text or not CORRECTION_HEAD.match(text.strip()[:40]):
            continue
        prev_assist = next((rows[j] for j in range(i - 1, max(-1, i - 4), -1)
                            if rows[j].get("type") == "assistant"), None)
        if prev_assist is None:
            continue
        out.append({
            "class": "correction", "weight": 3.0,
            "user_head": text.strip()[:200],
            "rejected_head": _text_of((prev_assist.get("message") or {}).get("content"))[:200],
            "src": f"{path.name}:{d['_line']}",
            "ts": d.get("timestamp", ""),
        })
    for r in out:
        r["priority"] = r["weight"] * _decay(r.get("ts", ""), now)
    return out


def main():
    now = time.time()
    all_rows = []
    n_sessions = 0
    for pdir in PROJECT_DIRS:
        if not pdir.is_dir():
            continue
        for f in sorted(pdir.glob("*.jsonl")):
            if f.stat().st_size < 1024:
                continue
            n_sessions += 1
            all_rows += mine_session(f, now)
    all_rows.sort(key=lambda r: -r["priority"])
    # 세션 재개/포크가 트랜스크립트를 통째로 복제한다 (실측: 같은 교정이 3벌).
    # 내용 지문으로 중복 제거 — src는 제외 (다른 파일의 같은 사건은 같은 사건).
    seen_fp = set()
    deduped = []
    for r in all_rows:
        fp = (r["class"], r.get("user_head") or "", r.get("error_head") or "",
              r.get("failed_input_head") or "")
        if fp in seen_fp:
            continue
        seen_fp.add(fp)
        deduped.append(r)
    all_rows = deduped
    out_path = Path(__file__).parent / "candidates_v0.jsonl"
    with out_path.open("w") as fh:
        for r in all_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_trap = sum(1 for r in all_rows if r["class"] == "trap")
    n_corr = sum(1 for r in all_rows if r["class"] == "correction")
    print(f"세션 {n_sessions}개 → 후보 {len(all_rows)}건 (함정 {n_trap}, 교정 {n_corr}) → {out_path}")
    print("--- 우선순위 상위 5 ---")
    for r in all_rows[:5]:
        head = r.get("user_head") or f"{r.get('tool')}: {r.get('error_head', '')[:80]}"
        print(f"[{r['class']} p={r['priority']:.2f}] {head[:110]}  ({r['src']})")


if __name__ == "__main__":
    main()
