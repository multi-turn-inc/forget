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
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,          -- ev-<memory_id>
    title TEXT NOT NULL,          -- 일화 앵커 또는 본문 머리
    t TEXT NOT NULL,              -- 발생 시각 (UTC ISO)
    t_precision TEXT NOT NULL,    -- 'second' | 'day' | 'unknown'
    source_ref TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event_order (
    before_id TEXT NOT NULL,      -- 부분순서: 날짜 없이도 "A 다음 B"를 담는다
    after_id TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (before_id, after_id)
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


def _ledger_loop_rows(ledger_db: str, user_id: str | None = None) -> list[dict[str, Any]]:
    """원장에서 열린-고리 후보를 읽는다 (SELECT만). v0 원천: action_report 기억.

    trust.kind == action_report 인 기억이 곧 '미검증 완료 주장' 고리다:
    yellow = 열림(증거 대기) · green = 확정 종결 · red/superseded = 철회 종결.
    user_id: 다중 스코프 원장(벤치·멀티유저)에서 한 사용자의 세계만 파생 —
    None이면 종전대로 전체 (실DB는 단일 사용자라 동작 불변).
    """
    conn = sqlite3.connect(f"file:{ledger_db}?mode=ro", uri=True)
    try:
        sql = ("SELECT id, memory, metadata, created_at, updated_at FROM memories "
               "WHERE deleted = 0 AND metadata LIKE '%action_report%'")
        args: list[Any] = []
        if user_id:
            sql += " AND user_id = ?"
            args.append(user_id)
        rows = conn.execute(sql, args).fetchall()
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


def _ledger_event_rows(ledger_db: str, user_id: str | None = None) -> list[dict[str, Any]]:
    """원장 → 사건 기록 v0. 기억 한 건 = 발생 기록 한 건 (제목 = 일화 앵커).

    상태 유형 감사(P-WM-1b)가 밝힌 최대 수요(56%)는 세기·정렬·간격 —
    v0는 그 시간 축 절반(t·정밀도·부분순서)을 구현한다. SPO 구조 절반은
    그래프 기질(엔티티 언급) 연결로 후속 계단에서 잇는다.
    user_id: 다중 스코프 원장에서 한 사용자의 세계만 (None = 전체, 동작 불변).
    """
    conn = sqlite3.connect(f"file:{ledger_db}?mode=ro", uri=True)
    try:
        sql = "SELECT id, memory, metadata, created_at FROM memories WHERE deleted = 0"
        args: list[Any] = []
        if user_id:
            sql += " AND user_id = ?"
            args.append(user_id)
        rows = conn.execute(sql, args).fetchall()
    finally:
        conn.close()
    out = []
    for mid, memory, metadata, created_at in rows:
        try:
            meta = json.loads(metadata or "{}")
        except ValueError:
            meta = {}
        anchor = ((meta.get("episode") or {}).get("anchor") or "").strip()
        title = anchor or re.sub(r"\s+", " ", str(memory or "")).strip()[:90]
        if not title:
            continue
        ts = str(created_at or "")
        parsed = _parse_ts(ts)
        if parsed is None:
            precision = "unknown"
        elif re.search(r"[T ]\d{2}:\d{2}", ts):
            precision = "second"
        else:
            precision = "day"
        out.append({"id": f"ev-{mid}", "title": title,
                    "t": _iso(parsed) if parsed else "", "t_precision": precision,
                    "source_ref": f"memories:{mid}"})
    return out


def rebuild(world_db: str = DEFAULT_WORLD_DB, ledger_db: str = DEFAULT_LEDGER_DB,
            now: datetime | None = None, user_id: str | None = None) -> dict[str, int]:
    """원장 → 상태 코어 재구축. 기존 고리의 opened_at은 보존하고 상태만 재판정.

    user_id를 주면 그 스코프의 세계만 파생한다 (P-WM-2 벤치 파생 경로).
    """
    now = now or _utcnow()
    conn = _open_world(world_db)
    stats = {"seen": 0, "opened": 0, "closed": 0, "transitions": 0}
    try:
        existing = {r[0]: r[1] for r in conn.execute("SELECT id, status FROM loops")}
        for cand in _ledger_loop_rows(ledger_db, user_id=user_id):
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
        for ev in _ledger_event_rows(ledger_db, user_id=user_id):
            conn.execute(
                "INSERT INTO events (id, title, t, t_precision, source_ref) VALUES (?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET title=excluded.title, t=excluded.t,"
                " t_precision=excluded.t_precision",
                (ev["id"], ev["title"], ev["t"], ev["t_precision"], ev["source_ref"]),
            )
            stats["events"] = stats.get("events", 0) + 1
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


def timeline(world_db: str = DEFAULT_WORLD_DB, like: str | None = None,
             since: str | None = None, until: str | None = None,
             limit: int = 50) -> list[dict[str, Any]]:
    """사건 질의 ① 정렬 — 시간 오름차순 사건 목록. 창은 반열림 [since, until)."""
    conn = _open_world(world_db)
    try:
        sql = "SELECT id, title, t, t_precision FROM events WHERE t != ''"
        args: list[Any] = []
        if like:
            sql += " AND title LIKE ?"
            args.append(f"%{like}%")
        if since:
            sql += " AND t >= ?"
            args.append(_iso(_parse_ts(since) or _utcnow()))
        if until:
            sql += " AND t < ?"
            args.append(_iso(_parse_ts(until) or _utcnow()))
        sql += " ORDER BY t ASC LIMIT ?"
        args.append(limit)
        rows = conn.execute(sql, args).fetchall()
    finally:
        conn.close()
    return [{"id": r[0], "title": r[1], "t": r[2], "t_precision": r[3]} for r in rows]


def count_events(world_db: str = DEFAULT_WORLD_DB, like: str | None = None,
                 since: str | None = None, until: str | None = None) -> int:
    """사건 질의 ② 세기 — 같은 반열림 창 규약."""
    return len(timeline(world_db, like, since, until, limit=10**9))


def interval_days(world_db: str, id_a: str, id_b: str) -> int | None:
    """사건 질의 ③ 간격 — b − a 를 일 단위 내림으로. 시각 미상이면 None."""
    conn = _open_world(world_db)
    try:
        rows = dict(conn.execute(
            "SELECT id, t FROM events WHERE id IN (?, ?)", (id_a, id_b)))
    finally:
        conn.close()
    ta, tb = _parse_ts(rows.get(id_a)), _parse_ts(rows.get(id_b))
    if ta is None or tb is None:
        return None
    seconds = (tb - ta).total_seconds()
    return int(seconds // 86400) if seconds >= 0 else -int((-seconds) // 86400)


def order_of(world_db: str, id_a: str, id_b: str) -> str | None:
    """사건 질의 ④ 부분순서 — 'before'|'after'|None(비교 불능).

    1순위: 명시 순서 간선(event_order, 직접 간선만 — 이행 폐쇄는 후속).
    2순위: 두 시각이 모두 있으면 t 비교. 둘 다 없으면 None — 부분순서의
    정직함: 모르는 순서를 지어내지 않는다.
    """
    conn = _open_world(world_db)
    try:
        edge = conn.execute(
            "SELECT 1 FROM event_order WHERE before_id=? AND after_id=?", (id_a, id_b)
        ).fetchone()
        redge = conn.execute(
            "SELECT 1 FROM event_order WHERE before_id=? AND after_id=?", (id_b, id_a)
        ).fetchone()
        if edge:
            return "before"
        if redge:
            return "after"
        rows = dict(conn.execute(
            "SELECT id, t FROM events WHERE id IN (?, ?)", (id_a, id_b)))
    finally:
        conn.close()
    ta, tb = _parse_ts(rows.get(id_a)), _parse_ts(rows.get(id_b))
    if ta is None or tb is None or ta == tb:
        return None
    return "before" if ta < tb else "after"


def add_order_edge(world_db: str, before_id: str, after_id: str, source: str) -> None:
    """날짜 없는 사건의 순서 지식을 명시 간선으로 — lifespan 부분순서의 자리."""
    conn = _open_world(world_db)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO event_order (before_id, after_id, source) VALUES (?,?,?)",
            (before_id, after_id, source))
        conn.commit()
    finally:
        conn.close()


DEFAULT_SUBSTRATE_DB = str(Path.home() / ".forget" / "graph_substrate.sqlite3")

ROUTINE_MIN_N = 5
ROUTINE_PERIODS = {"daily": 86400.0, "weekly": 7 * 86400.0}
ROUTINE_TOL = 0.2      # 주기 허용 오차 (중앙값이 주기의 ±20% 안)
ROUTINE_GRACE = 0.5    # 이탈 판정 유예 (주기의 +50% 지나면 부재)


def _routine_key(title: str) -> str:
    """반복 구조의 키 — 앵커 머리(괄호·대시 앞)를 정규화. 회차는 내용, 머리가 구조."""
    head = re.split(r"[(—\-—]", str(title or ""), maxsplit=1)[0]
    head = re.sub(r"\d+", "", head)          # 회차 번호는 구조가 아니다
    return re.sub(r"\s+", " ", head).strip().lower()[:40]


def detect_routines(world_db: str = DEFAULT_WORLD_DB,
                    min_n: int = ROUTINE_MIN_N) -> list[dict[str, Any]]:
    """루틴 기관 v0 — 사건 시간축에서 주기 구조를 검출한다 (수요 3.6%).

    기전: 같은 머리의 사건들 사이 간격 중앙값이 일/주 주기의 ±20% 안이고
    산포(IQR/중앙값 ≤ 0.5)가 낮으면 루틴. 고전 기법(모티프 검출)의 최소형 —
    LLM 불요. 시각 규율: 계산은 UTC, 전형 시각은 KST 병기(+09).
    """
    conn = _open_world(world_db)
    try:
        rows = conn.execute("SELECT title, t FROM events WHERE t != ''").fetchall()
    finally:
        conn.close()
    groups: dict[str, list[datetime]] = {}
    for title, t in rows:
        parsed = _parse_ts(t)
        key = _routine_key(title)
        if parsed and len(key) >= 4:
            groups.setdefault(key, []).append(parsed)
    out = []
    for key, times in groups.items():
        if len(times) < min_n:
            continue
        times.sort()
        gaps = sorted((b - a).total_seconds() for a, b in zip(times, times[1:]) if b > a)
        if not gaps:
            continue
        med = gaps[len(gaps) // 2]
        q1, q3 = gaps[len(gaps) // 4], gaps[(3 * len(gaps)) // 4]
        if med <= 0 or (q3 - q1) / med > 0.5:
            continue
        for period_name, period_s in ROUTINE_PERIODS.items():
            if abs(med - period_s) / period_s <= ROUTINE_TOL:
                hours_kst = sorted(((t.hour + 9) % 24) for t in times)
                out.append({"key": key, "period": period_name, "n": len(times),
                            "median_gap_s": int(med),
                            "typical_hour_kst": hours_kst[len(hours_kst) // 2],
                            "last_seen": _iso(times[-1])})
                break
    out.sort(key=lambda r: r["n"], reverse=True)
    return out


def routine_expectations(world_db: str = DEFAULT_WORLD_DB,
                         now: datetime | None = None) -> list[dict[str, Any]]:
    """루틴 기대 — 부재가 정보다: 주기+유예가 지나도록 다음 회차가 없으면
    이탈을 기대로 승격 (헌장 빈칸 ②, grid cell의 공학 번역)."""
    now = now or _utcnow()
    out = []
    for routine in detect_routines(world_db):
        period_s = ROUTINE_PERIODS[routine["period"]]
        last = _parse_ts(routine["last_seen"]) or now
        overdue_s = (now - last).total_seconds() - period_s * (1 + ROUTINE_GRACE)
        if overdue_s >= 0:
            missed = int((now - last).total_seconds() // period_s)
            out.append({**routine, "missed_cycles": missed,
                        "expectation": f"루틴 '{routine['key']}' ({routine['period']}, "
                                       f"보통 {routine['typical_hour_kst']}시 KST) — "
                                       f"{missed}주기째 부재: 확인 후보"})
    out.sort(key=lambda r: r["missed_cycles"], reverse=True)
    return out


def entity_card(name: str, substrate_db: str = DEFAULT_SUBSTRATE_DB,
                ledger_db: str = DEFAULT_LEDGER_DB, top_facts: int = 5) -> dict[str, Any] | None:
    """엔티티 기관 v0 질의 ① — 현황 카드 (수요 29%의 "X가 지금 어떤 상태지").

    기반은 정제 기질(Graphiti-방식 재구축)이다 — 실원장 memory_entities는
    구식 추출기의 정크 허브('users'=person 2,986)라 쓰지 않는다(공시).
    카드 = 최신 비-superseded 사실 + 관계 간선(valid_at 병기) + 시간 창.
    """
    sub = sqlite3.connect(f"file:{substrate_db}?mode=ro", uri=True)
    try:
        row = sub.execute("SELECT name, freq FROM entities WHERE name = ? "
                          "OR name LIKE ? ORDER BY freq DESC LIMIT 1",
                          (name.lower().strip(), f"%{name.lower().strip()}%")).fetchone()
        if not row:
            return None
        ent, freq = row
        memory_ids = [r[0] for r in sub.execute(
            "SELECT DISTINCT memory_id FROM mentions WHERE entity = ?", (ent,))]
        relations = [{"relation": r[0], "other": (r[2] if r[1] == ent else r[1]),
                      "fact": r[3], "valid_at": r[4]}
                     for r in sub.execute(
                         "SELECT relation, src, dst, fact, valid_at FROM edges "
                         "WHERE src = ? OR dst = ? ORDER BY valid_at DESC LIMIT 8",
                         (ent, ent))]
    finally:
        sub.close()
    facts: list[dict[str, Any]] = []
    first_seen = last_seen = None
    if memory_ids:
        led = sqlite3.connect(f"file:{ledger_db}?mode=ro", uri=True)
        try:
            marks = ",".join("?" * len(memory_ids))
            rows = led.execute(
                f"SELECT id, memory, metadata, created_at FROM memories "
                f"WHERE id IN ({marks}) AND deleted = 0 ORDER BY created_at", memory_ids
            ).fetchall()
        finally:
            led.close()
        for mid, memory, metadata, created in rows:
            try:
                meta = json.loads(metadata or "{}")
            except ValueError:
                meta = {}
            trust = meta.get("trust") or {}
            superseded = bool(meta.get("superseded_by") or trust.get("light") == "red")
            first_seen = first_seen or created
            last_seen = created
            if not superseded:
                facts.append({"memory_id": mid, "at": str(created or "")[:10],
                              "fact": re.sub(r"\s+", " ", str(memory or "")).strip()[:200]})
    return {"entity": ent, "freq": freq, "live_memories": len(facts),
            "first_seen": first_seen, "last_seen": last_seen,
            "current_facts": facts[-top_facts:][::-1], "relations": relations}


def stale_entities(min_freq: int = 10, stale_days: int = 21,
                   substrate_db: str = DEFAULT_SUBSTRATE_DB,
                   ledger_db: str = DEFAULT_LEDGER_DB,
                   now: datetime | None = None, limit: int = 10) -> list[dict[str, Any]]:
    """엔티티 기관 v0 질의 ② — 무소식 기대 (시간 구동, 분리 원칙 A).

    자주 언급되던 엔티티가 stale_days 이상 조용하면 "무소식이 정보다"를
    기대로 승격: 후속 확인 후보. 문턱은 이상(≥), 경과일은 내림.
    """
    now = now or _utcnow()
    sub = sqlite3.connect(f"file:{substrate_db}?mode=ro", uri=True)
    try:
        ents = [r[0] for r in sub.execute(
            "SELECT name FROM entities WHERE freq >= ? ORDER BY freq DESC", (min_freq,))]
        mention_map: dict[str, list[str]] = {}
        for ent in ents:
            mention_map[ent] = [r[0] for r in sub.execute(
                "SELECT DISTINCT memory_id FROM mentions WHERE entity = ?", (ent,))]
    finally:
        sub.close()
    led = sqlite3.connect(f"file:{ledger_db}?mode=ro", uri=True)
    out = []
    try:
        for ent, mids in mention_map.items():
            if not mids:
                continue
            marks = ",".join("?" * len(mids))
            row = led.execute(
                f"SELECT max(created_at) FROM memories WHERE id IN ({marks}) AND deleted = 0",
                mids).fetchone()
            last = _parse_ts(row[0]) if row and row[0] else None
            if last is None:
                continue
            days_quiet = int((now - last).total_seconds() // 86400)
            if days_quiet >= stale_days:
                out.append({"entity": ent, "days_quiet": days_quiet,
                            "last_seen": _iso(last),
                            "expectation": f"'{ent}' — {days_quiet}일째 무소식: 상태 변화 확인 후보"})
    finally:
        led.close()
    out.sort(key=lambda e: e["days_quiet"], reverse=True)
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
