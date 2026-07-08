"""Consolidation worker — the verification loop as a product behavior.

The brand promise is memory that keeps itself fresh, but until now the loop
(stale-candidates → adjudication → supersede) only ran when an agent or a
benchmark runner drove it by hand. This worker runs it in the background,
per project, against entities with recent write activity:

  1. find entities that stored memories since the last cycle (overlap-safe)
  2. surface same-topic old/new pairs via stale_candidate_pairs (a hint
     generator — precision tuned for triage, the adjudicator decides)
  3. adjudicate each pair batch with a small LLM; two supersede registers:
     state replacement (moved cities, changed stack) and plan completion
     (a newer memory records that the older todo/intention got done or
     dropped — the dogfood pain this worker exists to remove)
  4. supersede the losers (non-destructive; search demotes, rows stay)

Fail-safe posture: no adjudicator (missing API key, bad response) means no
supersession — the worker never guesses. Everything is capped per cycle so
a pathological corpus cannot melt the server or the LLM bill.

Gates: project setting `consolidation_enabled` (dogfood-first, like
temporal_rerank), env kill switch MEM1_CONSOLIDATION=0.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from .db import get_db
from .providers import get_project_settings

ADJUDICATE_SYSTEM_PROMPT = (
    "You maintain a long-term memory store. You are given pairs of memories "
    "about the same subject: an OLDER one and a NEWER one. For each pair, "
    "decide whether the newer memory makes the older one stale. Mark "
    "supersede=true in exactly two situations:\n"
    "1. State replacement: both describe the same fact or state and the newer "
    "one replaces or invalidates the older one (moved cities, changed stack, "
    "condition resolved, decision reversed).\n"
    "2. Plan completion: the older memory is a plan, todo, or intention and "
    "the newer memory records that it was completed, shipped, or abandoned.\n"
    "If they cover different topics, or both can be true at once, answer "
    "false. When unsure, answer false.\n"
    'Reply with a JSON array only, one object per pair, in the same order: '
    '[{"pair": <index>, "supersede": true|false}]'
)


def consolidation_env_enabled() -> bool:
    return (os.getenv("MEM1_CONSOLIDATION") or "1").strip().lower() not in {"0", "false", "no"}


def _consolidation_params() -> dict[str, Any]:
    return {
        "model": os.getenv("MEM1_CONSOLIDATION_MODEL") or "gpt-4o-mini",
        "base_url": (os.getenv("MEM1_CONSOLIDATION_BASE_URL") or "https://api.openai.com/v1").rstrip("/"),
        "api_key": os.getenv("MEM1_CONSOLIDATION_API_KEY") or os.getenv("OPENAI_API_KEY") or "",
        "max_entities": int(os.getenv("MEM1_CONSOLIDATION_MAX_ENTITIES", "20")),
        "max_pairs_per_entity": int(os.getenv("MEM1_CONSOLIDATION_MAX_PAIRS", "60")),
        "max_supersedes_per_cycle": int(os.getenv("MEM1_CONSOLIDATION_MAX_SUPERSEDES", "40")),
        "activity_window_hours": float(os.getenv("MEM1_CONSOLIDATION_WINDOW_HOURS", "26")),
        # optional floor override for the pair inbox (embedding-scale dependent:
        # production bge sits at ~0.80, the deterministic test embedding lower)
        "min_similarity": os.getenv("MEM1_CONSOLIDATION_MIN_SIMILARITY"),
        "batch_size": 12,
    }


def _recently_active_entities(window_hours: float, limit: int) -> list[dict[str, str]]:
    """(project, entity) pairs with new memories inside the window.

    The window deliberately overlaps consecutive cycles: rerunning an entity
    is idempotent (surfaced pairs whose loser is already superseded drop out
    of the inbox), so a restart never loses work, only repeats cheap reads.
    """
    from datetime import datetime, timedelta, timezone

    cutoff_iso = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT project_id, user_id, agent_id, MAX(created_at) AS latest
              FROM memories
             WHERE deleted = 0 AND created_at > ?
               AND (user_id IS NOT NULL AND user_id != '' OR agent_id IS NOT NULL AND agent_id != '')
             GROUP BY project_id, user_id, agent_id
             ORDER BY latest DESC
            """,
            (cutoff_iso,),
        ).fetchall()
    entities: list[dict[str, str]] = []
    for row in rows[: max(limit, 0)]:
        field = "user_id" if row["user_id"] else "agent_id"
        entities.append({"project_id": row["project_id"], "field": field, "value": row[field]})
    return entities


def _adjudicate_batch(pairs: list[dict[str, Any]], params: dict[str, Any]) -> list[bool]:
    """One LLM call per batch; any failure refuses the whole batch."""
    lines = []
    for index, pair in enumerate(pairs):
        older, newer = pair.get("older") or {}, pair.get("newer") or {}
        lines.append(
            f"PAIR {index}:\n"
            f"  OLDER ({str(older.get('created_at'))[:10]}): {str(older.get('memory'))[:400]}\n"
            f"  NEWER ({str(newer.get('created_at'))[:10]}): {str(newer.get('memory'))[:400]}"
        )
    body = {
        "model": params["model"],
        "messages": [
            {"role": "system", "content": ADJUDICATE_SYSTEM_PROMPT},
            {"role": "user", "content": "\n\n".join(lines)},
        ],
        "temperature": 0,
    }
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{params['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {params['api_key']}", "Content-Type": "application/json"},
                json=body,
            )
        response.raise_for_status()
        content = str(response.json()["choices"][0]["message"]["content"]).strip()
        if content.startswith("```"):
            content = content.strip("`")
        array = json.loads(content[content.index("[") : content.rindex("]") + 1])
        verdicts = [False] * len(pairs)
        for entry in array:
            index = int(entry.get("pair", -1))
            if 0 <= index < len(pairs):
                verdicts[index] = bool(entry.get("supersede"))
        return verdicts
    except Exception:
        return [False] * len(pairs)


# Pairs already adjudicated "keep both" this process lifetime. The inbox
# resurfaces the same stable pairs every cycle; without this, the worker
# re-buys the same LLM verdicts every 30 minutes. Process-lifetime is enough:
# a restart re-judges once, and superseded pairs leave the inbox on their own.
_adjudicated_keep: set[tuple[str, str]] = set()


def consolidation_cycle() -> dict[str, Any]:
    """One pass over recently-active entities. Returns a cycle report."""
    report: dict[str, Any] = {"entities": 0, "pairs": 0, "superseded": 0, "skipped_projects": 0}
    if not consolidation_env_enabled():
        report["disabled"] = "env"
        return report
    params = _consolidation_params()
    if not params["api_key"]:
        # no adjudicator → no judgments → no supersession; stay silent but honest
        report["disabled"] = "no_api_key"
        return report

    # imported here: store imports providers, and this module rides on store's
    # public operations — a top-level import would create a cycle
    from .store import stale_candidate_pairs, supersede_memory

    settings_cache: dict[str, bool] = {}
    supersedes_left = params["max_supersedes_per_cycle"]
    for entity in _recently_active_entities(params["activity_window_hours"], params["max_entities"]):
        project_id = entity["project_id"]
        if project_id not in settings_cache:
            settings_cache[project_id] = bool(get_project_settings(project_id).get("consolidation_enabled"))
        if not settings_cache[project_id]:
            report["skipped_projects"] += 1
            continue
        min_days = get_project_settings(project_id).get("temporal_min_days")
        payload: dict[str, Any] = {
            "filters": {entity["field"]: entity["value"]},
            "top_n": params["max_pairs_per_entity"],
            "project_id": project_id,
        }
        if min_days is not None:
            payload["min_days"] = min_days
        if params["min_similarity"] is not None:
            payload["min_similarity"] = float(params["min_similarity"])
        try:
            pairs = (stale_candidate_pairs(payload, project_id=project_id) or {}).get("pairs") or []
        except Exception:
            continue
        pairs = [
            pair for pair in pairs
            if ((pair.get("older") or {}).get("id"), (pair.get("newer") or {}).get("id")) not in _adjudicated_keep
        ]
        report["entities"] += 1
        report["pairs"] += len(pairs)
        for start in range(0, len(pairs), params["batch_size"]):
            if supersedes_left <= 0:
                break
            batch = pairs[start : start + params["batch_size"]]
            verdicts = _adjudicate_batch(batch, params)
            for pair, verdict in zip(batch, verdicts):
                pair_key = ((pair.get("older") or {}).get("id"), (pair.get("newer") or {}).get("id"))
                if not verdict:
                    _adjudicated_keep.add(pair_key)
                    continue
                if supersedes_left <= 0:
                    continue
                older, newer = pair.get("older") or {}, pair.get("newer") or {}
                if not older.get("id") or not newer.get("id"):
                    continue
                try:
                    supersede_memory(
                        older["id"],
                        {
                            "superseded_by": newer["id"],
                            "reason": "consolidation worker: newer state or completion supersedes",
                        },
                        project_id=project_id,
                    )
                    report["superseded"] += 1
                    supersedes_left -= 1
                except Exception:
                    continue
    return report
