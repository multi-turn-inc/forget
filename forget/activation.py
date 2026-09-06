"""활성(activation) — «떠오름»의 첫 장치 (2026-09-07, goal:observe-junghun 첫 손).

실측(2026-09-07): 최근 3,000회 검색의 상위 5건에 devloop 기계 문장 하나가 1,041회 등장했다.
어휘·벡터 점수는 «존재»를 재고, 뇌의 기저 활성은 «사용»을 잰다(ACT-R):

    A_i = B_i + Σ_j W_j·S_ji − hub_i − machine_i
    B_i = ln Σ_k t_k^(-d)          # t_k = i가 실제로 쓰인 과거 시점(일), d = 0.5

재료는 원장에 이미 있다.
- context_traces.selected_ids × context_outcomes(first_action_productive, used_memory_ids) → 쓰임(used)·노출(shown)·소음(noise)
- events(SEARCH).results 상위 5 → 노출 빈도(허브)
- 같은 trace에 함께 선택된 이력 → 확산 연결 S_ji
원칙: 원장은 건드리지 않는다. 읽기 전용. 통계는 ~/.forget/attention/stats.json에 캐시(TTL 10분).
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DECAY_D = 0.5
STATS_TTL_S = 600
ATTN_DIR = Path(os.getenv("FORGET_ATTENTION_DIR") or Path.home() / ".forget" / "attention")

# 기계 기록(에이전트 사무 장부) 판별 — 정훈 관찰 원장과 분리한다.
MACHINE_RE = re.compile(
    r"^\[devloop\]|사이클 ?\d{2,3}|\bc\d{2,3}\b.*(감사|회고|정산|일반)|restore_turns|next_actions\b|"
    r"[㉭㉨㉩㉳㉶㉼]|tests \d{3}/\d|서비스율 0|봉쇄 \d{2,3}|이동기 \d+세대|관측 \d{2,3}\b|\bP\d{2}\b.*(판정|표본)",
)

WEIGHTS = {"base": 0.15, "hub": 0.60, "machine": 0.35, "spread": 0.15, "noise": 0.15}
HUB_FLOOR, HUB_CEIL = 30, 1500   # 노출 30회 미만은 허브가 아니다(오늘 프로브 몇 번으로 벌점 받지 않게), 1,500회면 만점
PRODUCTIVE_CREDIT = 0.15   # 생산적 트레이스에 «노출만» 된 것의 약한 크레딧 — 명시 used_memory_ids가 1.0


def _db_path() -> Path:
    return Path(os.getenv("MEM1_DB_PATH") or Path.home() / ".forget" / "forget.sqlite3")


def _ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _days_ago(ts: str, now: float) -> float:
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 365.0
    return max(0.02, (now - t) / 86400.0)


def _loads(s: Any) -> Any:
    try:
        return json.loads(s) if isinstance(s, str) else (s or [])
    except Exception:
        return []


def is_machine_record(text: str) -> bool:
    return bool(MACHINE_RE.search(text or ""))


def compute_usage_stats(db: Path | None = None, since_days: int = 180) -> dict[str, Any]:
    """원장 읽기 → id별 shown/used/noise/used_days + 공동 선택 연결."""
    now = time.time()
    stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"shown": 0, "used": 0, "noise": 0, "used_days": []})
    co: dict[str, Counter] = defaultdict(Counter)
    with _ro(db or _db_path()) as conn:
        cutoff = datetime.fromtimestamp(now - since_days * 86400, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        outcomes: dict[str, dict[str, Any]] = {}
        for r in conn.execute("SELECT trace_id, first_action_productive, used_memory_ids, harmful_memory_ids, created_at FROM context_outcomes WHERE created_at > ?", (cutoff,)):
            outcomes[r["trace_id"]] = {"ok": bool(r["first_action_productive"]), "used": _loads(r["used_memory_ids"]),
                                       "harmful": _loads(r["harmful_memory_ids"]), "at": r["created_at"]}
        for r in conn.execute("SELECT trace_id, selected_ids, created_at FROM context_traces WHERE created_at > ? AND selected_ids != '[]'", (cutoff,)):
            sel = [s for s in _loads(r["selected_ids"]) if isinstance(s, str)]
            days = _days_ago(r["created_at"], now)
            oc = outcomes.get(r["trace_id"])
            for m in sel:
                stats[m]["shown"] += 1
                if oc:
                    if m in oc["used"]:                      # 명시적으로 쓰였다
                        stats[m]["used"] += 1
                        stats[m]["used_days"].append(days)
                    elif oc["ok"]:                           # 생산적 턴에 노출만 — 약한 크레딧
                        stats[m]["credit"] = stats[m].get("credit", 0) + 1
                        stats[m].setdefault("credit_days", []).append(days)
                    else:
                        stats[m]["noise"] += 1
                    if m in oc["harmful"]:
                        stats[m]["noise"] += 2
            for a in sel:
                for b in sel:
                    if a != b:
                        co[a][b] += 1
        for r in conn.execute("SELECT results FROM events WHERE event_type='SEARCH' AND created_at > ? AND LENGTH(results) > 2", (cutoff,)):
            res = _loads(r["results"])
            if not isinstance(res, list):
                continue
            for x in res[:5]:
                mid = x.get("id") if isinstance(x, dict) else None
                if mid:
                    stats[mid]["shown"] += 1
    return {"computed_at": now, "since_days": since_days,
            "stats": {k: v for k, v in stats.items()},
            "co": {k: dict(v.most_common(20)) for k, v in co.items()}}


def load_stats(refresh: bool = False) -> dict[str, Any]:
    ATTN_DIR.mkdir(parents=True, exist_ok=True)
    cache = ATTN_DIR / "stats.json"
    if not refresh and cache.exists():
        try:
            d = json.loads(cache.read_text())
            if time.time() - float(d.get("computed_at", 0)) < STATS_TTL_S:
                return d
        except Exception:
            pass
    d = compute_usage_stats()
    cache.write_text(json.dumps(d, ensure_ascii=False))
    return d


def base_activation(st: dict[str, Any] | None, created_days: float | None = None) -> float:
    """ACT-R 기저 활성. 사용 시점이 없으면 생성 시점만(약하게) 센다."""
    terms = [d ** (-DECAY_D) for d in (st or {}).get("used_days", []) if d > 0]
    terms += [PRODUCTIVE_CREDIT * d ** (-DECAY_D) for d in (st or {}).get("credit_days", [])[:50] if d > 0]
    if created_days is not None and created_days > 0:
        terms.append(0.5 * created_days ** (-DECAY_D))          # 생성도 한 번의 제시다
    return math.log(sum(terms)) if terms else -3.0


def hub_penalty(st: dict[str, Any] | None) -> float:
    if not st:
        return 0.0
    shown, used = st.get("shown", 0), st.get("used", 0)
    if shown < HUB_FLOOR:
        return 0.0
    ratio = (used + 0.5) / (shown + 1)        # 노출 대비 «명시적» 쓰임
    scale = (math.log(shown) - math.log(HUB_FLOOR)) / (math.log(HUB_CEIL) - math.log(HUB_FLOOR))
    return max(0.0, min(1.0, scale)) * (1.0 - min(1.0, ratio * 4))


def score_breakdown(item: dict[str, Any], stats: dict[str, Any], now: float | None = None) -> dict[str, float]:
    now = now or time.time()
    st = stats["stats"].get(item.get("id"))
    created = _days_ago(str(item.get("created_at") or ""), now) if item.get("created_at") else None
    b = base_activation(st, created)
    b_term = WEIGHTS["base"] * math.tanh(b / 2.0)
    hub = WEIGHTS["hub"] * hub_penalty(st)
    machine = WEIGHTS["machine"] if is_machine_record(str(item.get("memory", ""))) else 0.0
    noise = WEIGHTS["noise"] * min(1.0, (st or {}).get("noise", 0) / 3.0)
    return {"search": float(item.get("score") or 0.0), "base": b_term, "hub": -hub, "machine": -machine, "noise": -noise}


def rerank(results: list[dict[str, Any]], stats: dict[str, Any] | None = None, exclude_machine: bool = False) -> list[dict[str, Any]]:
    """검색 결과에 활성을 얹어 다시 줄 세운다. 확산은 후보 안에서만(외부 인출 없음)."""
    stats = stats or load_stats()
    now = time.time()
    out = []
    for it in results:
        bd = score_breakdown(it, stats, now)
        it = dict(it)
        it["activation_breakdown"] = bd
        it["activation"] = sum(bd.values())
        out.append(it)
    # 확산: 후보끼리 공동 선택 이력이 있으면 서로 끌어올린다
    ids = {it["id"]: it for it in out if it.get("id")}
    for it in list(out):
        if it["activation_breakdown"]["hub"] < -0.05 or it["activation_breakdown"]["machine"] < 0:
            continue                                   # 허브·기계 기록은 확산의 원천이 못 된다(허브 반향실 차단)
        for nb, c in stats.get("co", {}).get(it.get("id", ""), {}).items():
            if nb in ids and nb != it["id"]:
                s = WEIGHTS["spread"] * max(0.0, it["activation"]) * min(1.0, c / 3.0)
                cur = ids[nb]["activation_breakdown"].get("spread", 0.0)
                s = min(s, WEIGHTS["spread"] - cur)   # 대상당 상한
                if s <= 0:
                    continue
                ids[nb]["activation"] += s
                ids[nb]["activation_breakdown"]["spread"] = cur + s
    if exclude_machine:
        out = [it for it in out if not is_machine_record(str(it.get("memory", "")))]
    out.sort(key=lambda x: x["activation"], reverse=True)
    return out
