"""텍스트 세계모델 v0 — 관측과 분리되어 시간으로도 흐르는 상태 코어.

정훈 명명·승인 (2026-08-24): "텍스트월드모델. 이걸 만들자."
설계 정본: docs/personal-world-model-design.md (탑다운 헌장, ca99c50).
L3 온톨로지 다섯 유형 중 v0는 **열린 고리(open loop)** 하나만 구현한다 —
실수요에 이미 존재하고(캡슐의 "N일째" 노화 줄), P-WM-1 감사의 어떤 결과에서도
살아남을 유형이다. 나머지 유형은 감사 판정 뒤에 짓는다.

v0가 구현하는 분리 원칙은 A(관측 ↔ 상태)다: 사건은 카메라 밖에서도 결말까지
진행한다 — tick()이 관측 없이 시간만으로 상태를 전이시키고, 전이는 cause와
함께 기록된다. 이것이 WRBench가 픽셀 세계모델에 요구한 "영속 상태 코어"의
개인-텍스트 번역이다.

파생 저장소 원칙(그래프 기질과 동일): world DB는 원장에서 언제든 재구축
가능한 파생물이다. 원장에는 SELECT만 한다 — 쓰기 없음, 게이트 불요.

시각 규율(time-comparison-discipline): 내부는 전부 UTC ISO-8601(Z).
경과 비교는 초 단위 부등식으로만 하고, 문턱은 "이상(≥)"으로 명시한다 —
STALE_AFTER_S 정확히 그 초에 낡음이 된다.

생애주기 FSM (v0, kind="unverified_claim"):
    open --(시간: 증거 없이 STALE_AFTER_S 경과)--> stale
    open|stale --(관측: trust green 확정)--> closed_confirmed
    open|stale --(관측: supersede/red)-----> closed_retracted
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_WORLD_DB = str(Path.home() / ".forget" / "worldmodel.sqlite3")
DEFAULT_LEDGER_DB = str(Path.home() / ".forget" / "forget.sqlite3")
STALE_AFTER_S = 14 * 86400  # 열린 고리가 증거 없이 낡음으로 전이하는 문턱 (≥)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS loops (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    last_evidence_at TEXT NOT NULL,
    deadline TEXT,
    source_ref TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transitions (
    loop_id TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    cause TEXT NOT NULL,          -- 'observation' | 'time' | 'rebuild'
    at TEXT NOT NULL
);
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", text)
        if not m:
            return None
        parsed = datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}+00:00")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _open_world(world_db: str) -> sqlite3.Connection:
    conn = sqlite3.connect(world_db)
    conn.executescript(_SCHEMA)
    return conn


def _ledger_loop_rows(ledger_db: str) -> list[dict[str, Any]]:
    """원장에서 열린-고리 후보를 읽는다 (SELECT만). v0 원천: action_report 기억.

    trust.kind == action_report 인 기억이 곧 '미검증 완료 주장' 고리다:
    yellow = 열림(증거 대기) · green = 확정 종결 · red/superseded = 철회 종결.
    """
    conn = sqlite3.connect(f"file:{ledger_db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT id, memory, metadata, created_at, updated_at FROM memories "
            "WHERE deleted = 0 AND metadata LIKE '%action_report%'"
        ).fetchall()
    finally:
        conn.close()
    out = []
    for mid, memory, metadata, created_at, updated_at in rows:
        try:
            meta = json.loads(metadata or "{}")
        except ValueError:
            continue
        trust = meta.get("trust") or {}
        if trust.get("kind") != "action_report":
            continue
        light = str(trust.get("light") or "yellow")
        superseded = bool(meta.get("superseded") or meta.get("superseded_by") or light == "red")
        out.append({
            "id": f"loop-{mid}",
            "kind": "unverified_claim",
            "title": re.sub(r"\s+", " ", str(memory or "")).strip()[:120],
            "opened_at": str(created_at or ""),
            "evidence_at": str(updated_at or created_at or ""),
            "resolution": ("closed_retracted" if superseded
                           else "closed_confirmed" if light == "green" else None),
            "source_ref": f"memories:{mid}",
        })
    return out


def _record(conn: sqlite3.Connection, loop_id: str, frm: str, to: str, cause: str, now: datetime) -> None:
    conn.execute(
        "INSERT INTO transitions (loop_id, from_status, to_status, cause, at) VALUES (?,?,?,?,?)",
        (loop_id, frm, to, cause, _iso(now)),
    )


def rebuild(world_db: str = DEFAULT_WORLD_DB, ledger_db: str = DEFAULT_LEDGER_DB,
            now: datetime | None = None) -> dict[str, int]:
    """원장 → 상태 코어 재구축. 기존 고리의 opened_at은 보존하고 상태만 재판정."""
    now = now or _utcnow()
    conn = _open_world(world_db)
    stats = {"seen": 0, "opened": 0, "closed": 0, "transitions": 0}
    try:
        existing = {r[0]: r[1] for r in conn.execute("SELECT id, status FROM loops")}
        for cand in _ledger_loop_rows(ledger_db):
            stats["seen"] += 1
            opened = _parse_ts(cand["opened_at"]) or now
            evidence = _parse_ts(cand["evidence_at"]) or opened
            status = cand["resolution"]
            if status is None:
                elapsed = (now - max(opened, evidence)).total_seconds()
                status = "stale" if elapsed >= STALE_AFTER_S else "open"
            prev = existing.get(cand["id"])
            conn.execute(
                "INSERT INTO loops (id, kind, title, status, opened_at, last_evidence_at,"
                " deadline, source_ref, updated_at) VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET title=excluded.title, status=excluded.status,"
                " last_evidence_at=excluded.last_evidence_at, updated_at=excluded.updated_at",
                (cand["id"], cand["kind"], cand["title"], status, _iso(opened),
                 _iso(evidence), None, cand["source_ref"], _iso(now)),
            )
            if prev is None:
                stats["opened"] += 1
                _record(conn, cand["id"], "(none)", status, "rebuild", now)
                stats["transitions"] += 1
            elif prev != status:
                cause = "observation" if status.startswith("closed") else "time"
                _record(conn, cand["id"], prev, status, cause, now)
                stats["transitions"] += 1
            if status.startswith("closed"):
                stats["closed"] += 1
        conn.commit()
    finally:
        conn.close()
    return stats


def tick(world_db: str = DEFAULT_WORLD_DB, now: datetime | None = None) -> int:
    """관측 없는 시간 전이 — 세계는 카메라 밖에서도 흐른다. 전이 수를 반환."""
    now = now or _utcnow()
    conn = _open_world(world_db)
    moved = 0
    try:
        rows = conn.execute(
            "SELECT id, opened_at, last_evidence_at FROM loops WHERE status = 'open'"
        ).fetchall()
        for loop_id, opened_at, evidence_at in rows:
            anchor = max(_parse_ts(opened_at) or now, _parse_ts(evidence_at) or now)
            if (now - anchor).total_seconds() >= STALE_AFTER_S:
                conn.execute("UPDATE loops SET status='stale', updated_at=? WHERE id=?",
                             (_iso(now), loop_id))
                _record(conn, loop_id, "open", "stale", "time", now)
                moved += 1
        conn.commit()
    finally:
        conn.close()
    return moved


def expectations(world_db: str = DEFAULT_WORLD_DB, now: datetime | None = None,
                 limit: int = 10) -> list[dict[str, Any]]:
    """기대 헤드 v0 — 미종결 고리마다 '다음에 존재해야 할 증거'를 서술."""
    now = now or _utcnow()
    conn = _open_world(world_db)
    try:
        rows = conn.execute(
            "SELECT id, kind, title, status, opened_at FROM loops "
            "WHERE status IN ('open','stale')"
        ).fetchall()
    finally:
        conn.close()
    out = []
    for loop_id, kind, title, status, opened_at in rows:
        opened = _parse_ts(opened_at) or now
        days_open = int((now - opened).total_seconds() // 86400)
        out.append({
            "loop_id": loop_id, "kind": kind, "title": title, "status": status,
            "days_open": days_open,
            "expectation": f"'{title[:60]}' — {days_open}일째 미검증: 증거 확인 또는 정정이 존재해야 한다",
        })
    out.sort(key=lambda e: e["days_open"], reverse=True)
    return out[:limit]


def main() -> None:
    ap = argparse.ArgumentParser(description="텍스트 세계모델 v0 상태 코어")
    ap.add_argument("command", choices=["rebuild", "tick", "snapshot"])
    ap.add_argument("--world-db", default=DEFAULT_WORLD_DB)
    ap.add_argument("--ledger-db", default=DEFAULT_LEDGER_DB)
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()
    if args.command == "rebuild":
        print(json.dumps(rebuild(args.world_db, args.ledger_db), ensure_ascii=False))
    elif args.command == "tick":
        print(f"시간 전이 {tick(args.world_db)}건")
    else:
        for exp in expectations(args.world_db, limit=args.limit):
            print(f"[{exp['status']:5s}] {exp['days_open']:4d}일 · {exp['title'][:70]}")


if __name__ == "__main__":
    main()
