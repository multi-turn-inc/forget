"""일일 응고 사이클 — P-F-2 채택분의 제품화 (망각 헌장 L1-②).

선별(결정론) → 일일 요약(로컬 LLM, 핸들 코드 보존) → 침강(superseded_by
마킹 — 기존 억제 파이프라인이 자동 처리, 신규 기전 0, 가역).

선별 제1원칙 (P-F-2 감사 3반복의 수확): **출처가 사람이면 남긴다 — 침강은
시스템 산문만.** 보존: 사용자 발화(trust.source=user) · self층 · 사건
(P-WM-3c 게이트) · 성향(P-PF-2 게이트) · 교훈·미결·영어사건(KEEP_RE) ·
hook · 기침강. 대상: 14일+ 경과분만.

사용:
  .venv/bin/python -m forget.consolidation_cycle --db <사본.sqlite3>          # 검증 실행
  .venv/bin/python -m forget.consolidation_cycle --live --yes                 # 실DB (게이트 뒤)
기본은 dry-run 계획 인쇄 — --apply 없이는 아무것도 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sqlite3
from typing import Any

from . import worldmodel
from .selfharness import _local_distill_llm, extract_handles

KEEP_RE = re.compile(
    r"교훈|규칙|원칙|착각|본체|눈뜸|정체성|필수|해야 한|미결|대기 중인|"
    r"\b(lift|fixe?d|found|completed|achiev|discover|confirm|verified|re-?run|added)", re.I)
MIN_AGE_DAYS = 14
MIN_BATCH = 5    # 하루 5건 미만이면 요약 가치 없음 — 그대로 둔다


def sink_candidates(db: str) -> dict[str, list[tuple[str, str, dict]]]:
    """날짜 → [(id, text, meta)] — 침강 후보만."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT id, memory, metadata, created_at FROM memories WHERE deleted=0"
        ).fetchall()
    finally:
        conn.close()
    now = datetime.datetime.now(datetime.timezone.utc)
    by_day: dict[str, list[tuple[str, str, dict]]] = {}
    for mid, mem, meta_s, created in rows:
        try:
            meta = json.loads(meta_s or "{}")
        except ValueError:
            meta = {}
        if meta.get("hook") or meta.get("superseded_at") or meta.get("superseded_by"):
            continue
        trust = meta.get("trust") or {}
        if str(trust.get("source") or "") == "user":       # 사람의 말은 남긴다
            continue
        if str(meta.get("layer") or "") == "self":
            continue
        text = str(mem or "")
        ts = str(created or "").replace("Z", "+00:00")
        try:
            age = (now - datetime.datetime.fromisoformat(ts)).days
        except ValueError:
            continue
        if age < MIN_AGE_DAYS:
            continue
        anchor = ((meta.get("episode") or {}).get("anchor") or "").strip()
        if worldmodel._classify_event(text, anchor)[0]:
            continue
        if worldmodel._classify_disposition(text, source=str(trust.get("source") or "") or None):
            continue
        if KEEP_RE.search(text):
            continue
        by_day.setdefault(str(created)[:10], []).append((mid, text, meta))
    return {d: items for d, items in by_day.items() if len(items) >= MIN_BATCH}


HANDLE_KEEP_MIN = 0.7    # 침강 품질 문턱 — 이 미만이면 그날 침강 보류


def consolidate_day(db: str, day: str, items: list[tuple[str, str, dict]],
                    user_id: str) -> dict[str, Any]:
    corpus = "\n".join(f"- {t[:200]}" for _, t, _ in items)[:16000]
    summary = _local_distill_llm(
        f"Condense these low-value working notes from {day} into ONE dense Korean "
        "paragraph (≤120 words) preserving any concrete identifiers verbatim. "
        "This replaces them in recall.\n\n" + corpus).strip()
    if not summary:
        return {"day": day, "skipped": "llm_unavailable"}
    handles = extract_handles(corpus, cap=20)
    body = f"[일일 응고 {day}] {summary[:800]}"
    if handles:
        body += "\n핸들: " + ", ".join(h["value"] for h in handles[:12])
        # 침강 품질 계기 (대장 #20 자동화): 요약+핸들 블록이 원본 핸들을
        # 얼마나 보존하는가 — 손실 응고는 집계가 멀쩡해 보여도 행동 핸들을
        # 죽인다. 문턱 미달이면 그날은 침강하지 않는다 (보류가 손실보다 낫다).
        kept = sum(1 for h in handles if h["value"] in body)
        keep_rate = kept / len(handles)
        if keep_rate < HANDLE_KEEP_MIN:
            return {"day": day, "skipped": "handle_loss",
                    "handle_keep_rate": round(keep_rate, 3)}
    keep_rate = (sum(1 for h in handles if h["value"] in body) / len(handles)) if handles else 1.0
    from .store import add_memories
    add_memories({"messages": [{"role": "assistant", "content": body}],
                  "user_id": user_id, "infer": False, "hebbian": False,
                  "metadata": {"source": "consolidation_daily", "day": day,
                               "sank_count": len(items),
                               "handle_keep_rate": round(keep_rate, 3),
                               "trust": {"kind": "summary", "light": "yellow",
                                         "source": "assistant"}}})
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT id FROM memories WHERE memory LIKE ? ORDER BY created_at DESC LIMIT 1",
            (f"[일일 응고 {day}]%",)).fetchone()
        if row is None:
            return {"day": day, "skipped": "summary_not_found"}
        sid = row[0]
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for mid, _, meta in items:
            meta = dict(meta)
            meta["superseded_by"] = sid
            meta["superseded_at"] = stamp
            meta["sank_by"] = "consolidation_daily"       # 가역 복원의 표식
            conn.execute("UPDATE memories SET metadata=? WHERE id=?",
                         (json.dumps(meta, ensure_ascii=False), mid))
        conn.commit()
    finally:
        conn.close()
    return {"day": day, "summary_id": sid, "sank": len(items)}


def restore_day(db: str, day: str) -> dict[str, Any]:
    """침강 복원 — 가역성의 실물 (L2-1 "침강이지 삭제 아님"의 증명).

    그날 요약으로 침강된 원본들의 마킹을 벗기고, 요약 자체를 superseded
    처리(요약이 이제 구본). 회수 질서가 원상 복귀한다.
    """
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT id, metadata FROM memories WHERE deleted=0 AND metadata LIKE ?",
            (f'%"sank_by": "consolidation_daily"%',)).fetchall()
        restored = 0
        summary_ids = set()
        for mid, meta_s in rows:
            try:
                meta = json.loads(meta_s or "{}")
            except ValueError:
                continue
            if str(meta.get("superseded_at") or "")[:10] and meta.get("sank_by") == "consolidation_daily":
                # 날짜 매칭: 요약 id 경유 — 요약의 day 메타가 정본
                sid = str(meta.get("superseded_by") or "")
                srow = conn.execute("SELECT metadata FROM memories WHERE id=?", (sid,)).fetchone()
                if not srow:
                    continue
                try:
                    sday = str((json.loads(srow[0] or "{}")).get("day") or "")
                except ValueError:
                    continue
                if sday != day:
                    continue
                for key in ("superseded_by", "superseded_at", "sank_by"):
                    meta.pop(key, None)
                conn.execute("UPDATE memories SET metadata=? WHERE id=?",
                             (json.dumps(meta, ensure_ascii=False), mid))
                restored += 1
                summary_ids.add(sid)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for sid in summary_ids:
            srow = conn.execute("SELECT metadata FROM memories WHERE id=?", (sid,)).fetchone()
            if srow:
                try:
                    smeta = json.loads(srow[0] or "{}")
                except ValueError:
                    smeta = {}
                smeta["superseded_at"] = stamp
                smeta["superseded_reason"] = "restored — 침강 복원으로 요약 은퇴"
                conn.execute("UPDATE memories SET metadata=? WHERE id=?",
                             (json.dumps(smeta, ensure_ascii=False), sid))
        conn.commit()
    finally:
        conn.close()
    return {"day": day, "restored": restored, "summaries_retired": len(summary_ids)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", help="대상 DB (사본 검증용)")
    ap.add_argument("--live", action="store_true", help="실DB 대상 (게이트 뒤)")
    ap.add_argument("--apply", action="store_true", help="실제 침강 (기본 dry-run)")
    ap.add_argument("--yes", action="store_true", help="--live --apply 확인")
    ap.add_argument("--user", default="junghunkim")
    ap.add_argument("--max-days", type=int, default=3, help="한 번에 응고할 날짜 수")
    ap.add_argument("--restore", metavar="DAY", help="그날 침강을 복원 (YYYY-MM-DD)")
    args = ap.parse_args()
    if args.live:
        if not (args.apply and args.yes):
            raise SystemExit("실DB는 --live --apply --yes 전부 필요 (정훈 게이트 뒤에만)")
        import os
        db = os.path.expanduser("~/.forget/forget.sqlite3")
    elif args.db:
        db = args.db
    else:
        raise SystemExit("--db <사본> 또는 --live 필요")
    import os
    os.environ["MEM1_DB_PATH"] = db
    if args.restore:
        if args.live and not args.yes:
            raise SystemExit("실DB 복원은 --yes 필요")
        print(json.dumps(restore_day(db, args.restore), ensure_ascii=False))
        return
    days = sink_candidates(db)
    total = sum(len(v) for v in days.values())
    print(f"침강 후보: {len(days)}일 · {total}건 (일 {MIN_BATCH}건 이상만)")
    for day in sorted(days)[: args.max_days]:
        if not args.apply:
            print(f"  [dry] {day}: {len(days[day])}건")
            continue
        out = consolidate_day(db, day, days[day], args.user)
        print(f"  {json.dumps(out, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
