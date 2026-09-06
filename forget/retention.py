"""Retention — 기록이 기억보다 무거워지지 않게 (2026-09-07).

실측(정훈 도그푸딩 DB, 2026-09-06): memories 48MB · context_traces 717MB(7,920행, 건당 30~70KB의
자료화·캡슐·후보 스냅샷·디버그) · events 580MB(SEARCH 결과 전문 361MB). 보존 정책 0. 주 64MB 증가.

원칙
- 기억(memories·claims·memory_history)은 건드리지 않는다. 여기는 «기록(trace/event)»만 다룬다.
- 파괴 대신 **압축**: 오래된 trace의 payload를 요약 스텁으로, SEARCH 이벤트의 results를 id·score로 바꾼다.
  피드백이 달린 trace(context_outcomes에 있는 것)는 보존 기간이 길다.
- 기본은 dry-run. `apply=True`일 때만 쓴다. VACUUM은 별도 단계(디스크 2배 필요).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import get_db

TRACE_HEAVY_KEYS = (
    "materialization", "use_now", "candidate_snapshots", "debug", "resume_workspace",
    "final_model_context", "context_hygiene", "working_memory", "query_evidence", "role_backfill",
)
TRACE_KEEP_KEYS = ("schema_version", "trace_id", "trace_query", "search_payload", "context_capsule",
                   "context_capsule_text", "context_status", "context_access_decision_id")


def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_loads(s: Any) -> Any:
    try:
        return json.loads(s) if isinstance(s, str) else s
    except Exception:
        return None


def compact_trace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """무거운 키를 떼고 캡슐·질의·상태만 남긴다. 무엇을 뗐는지 기록한다."""
    keep = {k: payload[k] for k in TRACE_KEEP_KEYS if k in payload}
    dropped = [k for k in payload if k not in keep]
    snaps = payload.get("candidate_snapshots")
    if isinstance(snaps, list):
        keep["candidate_ids"] = [str(s.get("id")) for s in snaps if isinstance(s, dict) and s.get("id")][:200]
    keep["compacted_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    keep["dropped_keys"] = dropped
    return keep


def compact_search_results(results: Any, text_chars: int = 0) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(results, list):
        return out
    for item in results:
        if not isinstance(item, dict):
            continue
        row = {"id": item.get("id"), "score": item.get("score")}
        if text_chars and isinstance(item.get("memory"), str):
            row["memory"] = item["memory"][:text_chars]
        out.append(row)
    return out


def report(project_id: str | None = None) -> dict[str, Any]:
    """무엇이 얼마나 무거운가. 읽기만."""
    with get_db() as conn:
        sizes: dict[str, float] = {}
        try:
            for row in conn.execute("SELECT name, SUM(pgsize) AS b FROM dbstat GROUP BY name ORDER BY b DESC LIMIT 12"):
                sizes[row["name"]] = round(row["b"] / 1048576, 1)
        except Exception:
            pass
        page = conn.execute("PRAGMA page_size").fetchone()[0]
        pages = conn.execute("PRAGMA page_count").fetchone()[0]
        free = conn.execute("PRAGMA freelist_count").fetchone()[0]
        tr = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(LENGTH(payload)),0) b FROM context_traces").fetchone()
        ev = conn.execute("SELECT event_type, COUNT(*) c, COALESCE(SUM(LENGTH(results)),0) b FROM events GROUP BY event_type").fetchall()
        wk_tr = conn.execute("SELECT COUNT(*) c, COALESCE(SUM(LENGTH(payload)),0) b FROM context_traces WHERE created_at > ?", (_cutoff(7),)).fetchone()
        wk_ev = conn.execute("SELECT COALESCE(SUM(LENGTH(results)),0) b FROM events WHERE event_type='SEARCH' AND created_at > ?", (_cutoff(7),)).fetchone()
    return {
        "db_mb": round(page * pages / 1048576, 1),
        "free_mb": round(page * free / 1048576, 1),
        "tables_mb": sizes,
        "context_traces": {"rows": tr["c"], "payload_mb": round(tr["b"] / 1048576, 1)},
        "events": {r["event_type"]: {"rows": r["c"], "results_mb": round(r["b"] / 1048576, 1)} for r in ev},
        "growth_7d_mb": {"context_traces": round(wk_tr["b"] / 1048576, 1), "search_results": round(wk_ev["b"] / 1048576, 1)},
    }


def run(older_than_days: int = 14, labeled_days: int = 90, apply: bool = False, project_id: str | None = None) -> dict[str, Any]:
    """오래된 trace payload를 스텁으로, SEARCH results를 id·score로. dry-run이 기본."""
    cutoff = _cutoff(older_than_days)
    cutoff_labeled = _cutoff(labeled_days)
    out: dict[str, Any] = {"apply": apply, "older_than_days": older_than_days, "labeled_days": labeled_days,
                           "traces": {"candidates": 0, "compacted": 0, "bytes_before": 0, "bytes_after": 0, "skipped_labeled": 0},
                           "search_events": {"candidates": 0, "compacted": 0, "bytes_before": 0, "bytes_after": 0}}
    with get_db() as conn:
        labeled = {r["trace_id"] for r in conn.execute("SELECT DISTINCT trace_id FROM context_outcomes")}
        rows = conn.execute(
            "SELECT trace_id, payload, created_at FROM context_traces WHERE created_at < ? AND LENGTH(payload) > 2048",
            (cutoff,),
        ).fetchall()
        for r in rows:
            p = _json_loads(r["payload"])
            if not isinstance(p, dict) or p.get("compacted_at"):
                continue
            if r["trace_id"] in labeled and r["created_at"] >= cutoff_labeled:
                out["traces"]["skipped_labeled"] += 1
                continue
            out["traces"]["candidates"] += 1
            before = len(r["payload"])
            new = json.dumps(compact_trace_payload(p), ensure_ascii=False)
            out["traces"]["bytes_before"] += before
            out["traces"]["bytes_after"] += len(new)
            if apply:
                conn.execute("UPDATE context_traces SET payload = ? WHERE trace_id = ?", (new, r["trace_id"]))
                out["traces"]["compacted"] += 1
        ev = conn.execute(
            "SELECT id, results FROM events WHERE event_type = 'SEARCH' AND created_at < ? AND LENGTH(results) > 1024",
            (cutoff,),
        ).fetchall()
        for r in ev:
            res = _json_loads(r["results"])
            if not isinstance(res, list) or (res and isinstance(res[0], dict) and set(res[0].keys()) <= {"id", "score", "memory"}):
                continue
            out["search_events"]["candidates"] += 1
            new = json.dumps(compact_search_results(res), ensure_ascii=False)
            out["search_events"]["bytes_before"] += len(r["results"])
            out["search_events"]["bytes_after"] += len(new)
            if apply:
                conn.execute("UPDATE events SET results = ? WHERE id = ?", (new, r["id"]))
                out["search_events"]["compacted"] += 1
        if apply:
            conn.commit()
    for k in ("traces", "search_events"):
        out[k]["reclaim_mb"] = round((out[k]["bytes_before"] - out[k]["bytes_after"]) / 1048576, 1)
    out["reclaim_mb_total"] = out["traces"]["reclaim_mb"] + out["search_events"]["reclaim_mb"]
    out["note"] = "압축은 논리 크기만 줄인다. 파일 크기는 VACUUM 뒤에 준다(디스크 여유 = 현재 파일 크기만큼 필요)."
    return out


def vacuum() -> dict[str, Any]:
    with get_db() as conn:
        before = conn.execute("PRAGMA page_count").fetchone()[0] * conn.execute("PRAGMA page_size").fetchone()[0]
        conn.execute("VACUUM")
        after = conn.execute("PRAGMA page_count").fetchone()[0] * conn.execute("PRAGMA page_size").fetchone()[0]
    return {"before_mb": round(before / 1048576, 1), "after_mb": round(after / 1048576, 1)}


def trace_verbose() -> bool:
    return os.getenv("FORGET_TRACE_VERBOSE", "").lower() in ("1", "true", "yes")
