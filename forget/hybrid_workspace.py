from __future__ import annotations

import hashlib
import re
from typing import Any

from .db import json_dumps, json_loads
from .utils import new_id


SCHEMA_VERSION = "hybrid-workspace-v0-alpha"
REDUCER_VERSION = "hybrid-workspace-v0"
MODEL_POLICY_VERSION = "llm-model-policy-v1"

DEFAULT_DECISION_TIERS = {
    "boundary_decision": "decision",
    "durable_write_decision": "decision",
    "context_access_decision": "decision",
    "adaptive_pulse_decision": "fast",
    "contradiction_review": "critic",
}

TIER_MODEL_SETTINGS = {
    "fast": "llm_fast_model",
    "decision": "llm_decision_model",
    "critic": "llm_critic_model",
}

TERMINAL_EVIDENCE_MARKERS = {
    "pass",
    "passed",
    "passing",
    "success",
    "successful",
    "successfully",
    "succeeded",
    "verified",
    "confirmed",
    "deployed",
    "green",
    "user_confirmed",
    "terminal",
}


def json_list(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value)
    return [value]


def has_terminal_evidence_marker(text: str) -> bool:
    normalized = text.lower().replace("-", "_")
    return any(re.search(rf"(?<![a-z0-9_]){re.escape(marker)}(?![a-z0-9_])", normalized) for marker in TERMINAL_EVIDENCE_MARKERS)


def task_terminal_evidence_refs(payload: dict[str, Any], item: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    if payload.get("terminal_evidence") is True:
        refs.append({"kind": "terminal_evidence", "id": "payload.terminal_evidence"})
    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    if evidence.get("terminal_evidence") is True or evidence.get("terminal") is True:
        refs.append({"kind": "terminal_evidence", "id": "evidence.terminal"})
    for key, value in evidence.items():
        if has_terminal_evidence_marker(f"{key} {value}".strip()):
            refs.append({"kind": "evidence", "id": str(key)})
    for index, value in enumerate(json_list(payload.get("verified_results") or payload.get("verified"))):
        if has_terminal_evidence_marker(str(value)):
            refs.append({"kind": "verified_result", "id": str(index)})
    for index, command in enumerate(item.get("commands") or []):
        if has_terminal_evidence_marker(str(command)):
            refs.append({"kind": "command", "id": str(index)})
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        key = (ref["kind"], ref["id"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped


def task_claim_lifecycle(payload: dict[str, Any], item: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    status = str(item.get("status") or "").lower()
    terminal_refs = task_terminal_evidence_refs(payload, item)
    if status in {"abandoned", "cancelled", "canceled", "retracted"}:
        return "RETRACTED", terminal_refs
    if status in {"contradicted", "failed", "failure", "regressed"}:
        return "CONTRADICTED", terminal_refs
    if status in {"complete", "completed", "done", "succeeded", "success", "verified", "passed"}:
        return ("CONFIRMED" if terminal_refs else "PROVISIONAL"), terminal_refs
    return "PROVISIONAL", terminal_refs


def task_relation_refs(item: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for key in ("goal_id", "parent_goal_id"):
        value = str(item.get(key) or "").strip()
        if value:
            refs.append({"kind": key, "id": value})
    for value in json_list(item.get("related_task_ids")):
        related_id = str(value or "").strip()
        if related_id:
            refs.append({"kind": "related_task", "id": related_id})
    return refs


def task_relations_from_refs(evidence_refs: list[dict[str, Any]]) -> dict[str, Any]:
    relations = {"goal_id": "", "parent_goal_id": "", "related_task_ids": []}
    related_ids: list[str] = []
    seen_related: set[str] = set()
    for ref in evidence_refs:
        if not isinstance(ref, dict):
            continue
        kind = str(ref.get("kind") or "")
        ref_id = str(ref.get("id") or "").strip()
        if not ref_id:
            continue
        if kind in {"goal_id", "parent_goal_id"}:
            relations[kind] = ref_id
        elif kind == "related_task" and ref_id not in seen_related:
            seen_related.add(ref_id)
            related_ids.append(ref_id)
    relations["related_task_ids"] = related_ids
    return relations


def workspace_snapshot(payload: dict[str, Any], item: dict[str, Any], evidence_refs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    relevant_artifacts = list(
        dict.fromkeys(
            [
                *item.get("evidence_files", []),
                *[str(value) for value in json_list(payload.get("relevant_artifacts"))],
            ]
        )
    )
    return {
        "current_goal": str(payload.get("current_goal") or payload.get("goal") or item.get("summary") or ""),
        "current_status": str(item.get("status") or ""),
        "active_hypothesis": str(payload.get("active_hypothesis") or payload.get("hypothesis") or ""),
        "blockers": item.get("blockers", []),
        "next_actions": item.get("next_actions", []),
        "task_relations": {
            "goal_id": str(item.get("goal_id") or ""),
            "parent_goal_id": str(item.get("parent_goal_id") or ""),
            "related_task_ids": [str(value) for value in json_list(item.get("related_task_ids")) if str(value).strip()],
        },
        "constraints": json_list(payload.get("constraints")),
        "verified_results": json_list(payload.get("verified_results") or payload.get("verified")),
        "unresolved_questions": json_list(payload.get("unresolved_questions") or payload.get("questions")),
        "relevant_artifacts": relevant_artifacts,
        "evidence_refs": evidence_refs or [],
    }


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    stable_snapshot = {key: value for key, value in snapshot.items() if key != "evidence_refs"}
    return hashlib.sha256(json_dumps(stable_snapshot).encode("utf-8")).hexdigest()


def epoch_snapshot(row: Any) -> dict[str, Any]:
    evidence_refs = json_loads(row["evidence_refs_json"], [])
    return {
        "current_goal": row["current_goal"],
        "current_status": row["current_status"],
        "active_hypothesis": row["active_hypothesis"],
        "blockers": json_loads(row["blockers_json"], []),
        "next_actions": json_loads(row["next_actions_json"], []),
        "task_relations": task_relations_from_refs(evidence_refs),
        "constraints": json_loads(row["constraints_json"], []),
        "verified_results": json_loads(row["verified_results_json"], []),
        "unresolved_questions": json_loads(row["unresolved_questions_json"], []),
        "relevant_artifacts": json_loads(row["relevant_artifacts_json"], []),
        "evidence_refs": evidence_refs,
    }


def boundary_reason_codes(previous_epoch: Any | None, snapshot: dict[str, Any], snapshot_digest: str) -> list[str]:
    if previous_epoch is None:
        return ["task_started"]
    if previous_epoch["snapshot_hash"] == snapshot_digest:
        return []
    previous = epoch_snapshot(previous_epoch)
    reasons: list[str] = []
    if previous.get("current_goal") != snapshot.get("current_goal"):
        reasons.append("goal_changed")
    if previous.get("current_status") != snapshot.get("current_status"):
        reasons.append("status_changed")
    if previous.get("blockers") != snapshot.get("blockers"):
        reasons.append("blockers_changed")
    if previous.get("next_actions") != snapshot.get("next_actions"):
        reasons.append("next_actions_changed")
    if previous.get("task_relations") != snapshot.get("task_relations"):
        reasons.append("task_relations_changed")
    if previous.get("constraints") != snapshot.get("constraints"):
        reasons.append("constraints_changed")
    if previous.get("verified_results") != snapshot.get("verified_results"):
        reasons.append("verified_results_changed")
    if previous.get("unresolved_questions") != snapshot.get("unresolved_questions"):
        reasons.append("unresolved_questions_changed")
    if previous.get("relevant_artifacts") != snapshot.get("relevant_artifacts"):
        reasons.append("relevant_artifacts_changed")
    if previous.get("active_hypothesis") != snapshot.get("active_hypothesis"):
        reasons.append("active_hypothesis_changed")
    return reasons or ["workspace_changed"]


def _float_payload(payload: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def _int_payload(payload: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def soft_boundary_reason_codes(payload: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    if payload.get("topic_drift") is True or _float_payload(payload, "topic_drift_score") >= 0.75:
        candidates.append("soft_boundary:topic_drift")
    repeated_failures = max(_int_payload(payload, "repeated_failure_count"), _int_payload(payload, "repeated_error_count"))
    if repeated_failures >= 2:
        candidates.append("soft_boundary:repeated_failure")
    if _float_payload(payload, "novelty_score") >= 0.85:
        candidates.append("soft_boundary:novelty")
    if payload.get("contradiction") is True or _float_payload(payload, "contradiction_score") >= 0.75:
        candidates.append("soft_boundary:contradiction")
    if _float_payload(payload, "uncertainty") >= 0.75 or _float_payload(payload, "uncertainty_score") >= 0.75:
        candidates.append("soft_boundary:uncertainty")
    if _int_payload(payload, "inactivity_seconds") >= 120:
        candidates.append("soft_boundary:inactivity")

    persisted_pulses = max(_int_payload(payload, "soft_boundary_pulses"), _int_payload(payload, "soft_boundary_count"))
    confidence_margin = _float_payload(payload, "boundary_confidence_margin")
    if payload.get("force_soft_boundary") is True or persisted_pulses >= 2 or confidence_margin >= 0.2 or len(candidates) >= 2:
        return candidates or ["soft_boundary:forced"]
    return []


def adaptive_pulse(
    payload: dict[str, Any],
    item: dict[str, Any],
    reasons: list[str],
    soft_reasons: list[str],
) -> dict[str, Any]:
    if reasons:
        return {"decision": "pulse_immediate", "interval_ms": 0, "reason_codes": ["boundary_crossed", *reasons]}
    if soft_reasons or _float_payload(payload, "uncertainty") >= 0.75:
        return {"decision": "pulse_short", "interval_ms": 5_000, "reason_codes": ["soft_signal_watch", *soft_reasons]}
    if item.get("blockers") or str(item.get("status") or "") in {"blocked", "failed"}:
        return {"decision": "pulse_short", "interval_ms": 20_000, "reason_codes": ["blocked_or_failed_state"]}
    if _int_payload(payload, "tool_call_count") >= 3 or str(payload.get("activity_level") or "").lower() == "active":
        return {"decision": "pulse_medium", "interval_ms": 30_000, "reason_codes": ["active_tool_sequence"]}
    if _int_payload(payload, "inactivity_seconds") >= 120:
        return {"decision": "pulse_idle_close_proposal", "interval_ms": 120_000, "reason_codes": ["idle_close_proposal"]}
    return {"decision": "pulse_stable", "interval_ms": 300_000, "reason_codes": ["stable_workspace"]}


def evidence_ref(evidence_refs: list[Any], kind: str) -> str | None:
    for ref in evidence_refs:
        if isinstance(ref, dict) and ref.get("kind") == kind and ref.get("id"):
            return str(ref["id"])
    return None


def decision_model_profile(settings: dict[str, Any] | None, decision_type: str) -> dict[str, str]:
    settings = settings or {}
    policy = settings.get("llm_model_policy") if isinstance(settings.get("llm_model_policy"), dict) else {}
    tier = str(policy.get(decision_type) or DEFAULT_DECISION_TIERS.get(decision_type) or "decision")
    model_setting = TIER_MODEL_SETTINGS.get(tier, "llm_model")
    model = str(settings.get(model_setting) or settings.get("llm_model") or "local")
    provider = str(settings.get("llm_provider") or "local")
    return {
        "policy_version": MODEL_POLICY_VERSION,
        "decision_type": decision_type,
        "provider": provider,
        "tier": tier,
        "model": model,
    }


def decision_model_evidence_refs(profile: dict[str, str] | None) -> list[dict[str, str]]:
    if not profile:
        return []
    return [
        {"kind": "model_policy", "id": profile["policy_version"]},
        {"kind": "model_decision_type", "id": profile["decision_type"]},
        {"kind": "model_provider", "id": profile["provider"]},
        {"kind": "model_tier", "id": profile["tier"]},
        {"kind": "model", "id": profile["model"]},
    ]


def workspace_epoch_result(row: Any) -> dict[str, Any]:
    evidence_refs = json_loads(row["evidence_refs_json"], [])
    claim_id = evidence_ref(evidence_refs, "claim")
    event_id = evidence_ref(evidence_refs, "event")
    source_hash = evidence_ref(evidence_refs, "source_hash") or row["snapshot_hash"]
    claim_lifecycle = evidence_ref(evidence_refs, "claim_lifecycle") or "PROVISIONAL"
    task_relations = task_relations_from_refs(evidence_refs)
    terminal_evidence_refs = [
        ref
        for ref in evidence_refs
        if isinstance(ref, dict) and ref.get("kind") in {"terminal_evidence", "evidence", "verified_result", "command"}
    ]
    return {
        "task_id": row["task_id"],
        "status": row["current_status"],
        "summary": row["current_goal"],
        "current_goal": row["current_goal"],
        "active_hypothesis": row["active_hypothesis"],
        "next_actions": json_loads(row["next_actions_json"], []),
        "blockers": json_loads(row["blockers_json"], []),
        "evidence": {
            "workspace_epoch_id": row["workspace_epoch_id"],
            "evidence_refs": evidence_refs,
            "state_source": "workspace_epoch",
        },
        "evidence_files": json_loads(row["relevant_artifacts_json"], []),
        "commands": [],
        "goal_id": task_relations["goal_id"],
        "parent_goal_id": task_relations["parent_goal_id"],
        "related_task_ids": task_relations["related_task_ids"],
        "claim_id": claim_id,
        "claim_lifecycle": claim_lifecycle,
        "terminal_evidence_refs": terminal_evidence_refs,
        "source_event_ids": [event_id] if event_id else [],
        "source_hashes": [source_hash],
        "supersedes_claim_ids": [],
        "scope": json_loads(row["scope_json"], {}),
        "workspace_epoch_id": row["workspace_epoch_id"],
        "predecessor_epoch_id": row["predecessor_epoch_id"],
        "valid_from": row["valid_from"],
        "valid_to": row["valid_to"],
        "snapshot_hash": row["snapshot_hash"],
        "reducer_version": row["reducer_version"],
        "created_at": row["valid_from"],
        "updated_at": row["valid_from"],
    }


def insert_decision(
    conn: Any,
    *,
    project_id: str,
    task_id: str,
    decision_type: str,
    subject_id: str,
    decision: str,
    reason_codes: list[str],
    evidence_refs: list[Any],
    decided_at: str,
    model_profile: dict[str, str] | None = None,
) -> str:
    decision_id = str(new_id())
    stored_evidence_refs = [*evidence_refs, *decision_model_evidence_refs(model_profile)]
    conn.execute(
        """
        INSERT INTO hybrid_decisions (
            decision_id, project_id, task_id, decision_type, subject_id,
            decision, reason_codes, evidence_refs, decided_at, decider_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision_id,
            project_id,
            task_id,
            decision_type,
            subject_id,
            decision,
            json_dumps(reason_codes),
            json_dumps(stored_evidence_refs),
            decided_at,
            REDUCER_VERSION,
        ),
    )
    return decision_id


def _append_open_episode_observation(conn: Any, *, project_id: str, task_id: str, observation_id: str, now: str) -> Any:
    open_episode = conn.execute(
        """
        SELECT * FROM hybrid_episodes
         WHERE project_id = ?
           AND task_id = ?
           AND state = 'open'
         ORDER BY started_at DESC
         LIMIT 1
        """,
        (project_id, task_id),
    ).fetchone()
    if open_episode:
        observation_ids = json_loads(open_episode["observation_ids"], [])
        if observation_id not in observation_ids:
            observation_ids.append(observation_id)
            conn.execute(
                """
                UPDATE hybrid_episodes
                   SET observation_ids = ?
                 WHERE project_id = ?
                   AND episode_id = ?
                """,
                (json_dumps(observation_ids), project_id, open_episode["episode_id"]),
            )
        return conn.execute(
            "SELECT * FROM hybrid_episodes WHERE project_id = ? AND episode_id = ?",
            (project_id, open_episode["episode_id"]),
        ).fetchone()

    episode_id = str(new_id())
    conn.execute(
        """
        INSERT INTO hybrid_episodes (
            episode_id, project_id, task_id, started_at, closed_at, state,
            boundary_reason_codes, observation_ids, integrated_summary,
            outcome, evidence_refs, integrator_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            episode_id,
            project_id,
            task_id,
            now,
            None,
            "open",
            "[]",
            json_dumps([observation_id]),
            "",
            "",
            "[]",
            REDUCER_VERSION,
        ),
    )
    return conn.execute(
        "SELECT * FROM hybrid_episodes WHERE project_id = ? AND episode_id = ?",
        (project_id, episode_id),
    ).fetchone()


def record_task_observation(
    conn: Any,
    *,
    project_id: str,
    task_id: str,
    scope: dict[str, Any],
    payload: dict[str, Any],
    item: dict[str, Any],
    actor_id: str,
    source_role: str,
    authority: str,
    claim_id: str,
    event_id: str,
    legacy_observation_id: str,
    source_hash: str,
    claim_lifecycle: str,
    terminal_evidence_refs: list[dict[str, str]],
    now: str,
    model_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hybrid_observation_id = str(new_id())
    hybrid_payload = {
        "task_id": task_id,
        "scope": scope,
        "item": item,
        "source_role": source_role,
        "authority": authority,
    }
    hybrid_source_hash = hashlib.sha256(json_dumps(hybrid_payload).encode("utf-8")).hexdigest()
    idempotency_key = str(
        payload.get("idempotency_key")
        or payload.get("observation_id")
        or f"task_state:{project_id}:{task_id}:{hybrid_source_hash}"
    )
    hybrid_insert = conn.execute(
        """
        INSERT OR IGNORE INTO hybrid_observations (
            observation_id, tenant_id, project_id, task_id, session_id, actor_id,
            source_type, event_type, payload_json, observed_at, recorded_at,
            authority, trust_level, source_hash, idempotency_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hybrid_observation_id,
            str(payload.get("tenant_id") or "local"),
            project_id,
            task_id,
            str(payload.get("session_id") or payload.get("run_id") or ""),
            actor_id,
            str(payload.get("source_type") or "mcp"),
            str(payload.get("event_type") or "task_state"),
            json_dumps({**hybrid_payload, "event_id": event_id, "claim_id": claim_id}),
            str(payload.get("observed_at") or now),
            now,
            authority,
            str(payload.get("trust_level") or "normal"),
            hybrid_source_hash,
            idempotency_key,
        ),
    )
    observation_inserted = hybrid_insert.rowcount == 1
    previous_epoch = conn.execute(
        """
        SELECT * FROM workspace_epochs
         WHERE project_id = ?
           AND task_id = ?
           AND scope_json = ?
           AND valid_to IS NULL
         ORDER BY valid_from DESC
         LIMIT 1
        """,
        (project_id, task_id, json_dumps(scope)),
    ).fetchone()
    evidence_refs = [
        {"kind": "claim", "id": claim_id},
        {"kind": "event", "id": event_id},
        {"kind": "legacy_observation", "id": legacy_observation_id},
        {"kind": "hybrid_observation", "id": hybrid_observation_id},
        {"kind": "source_hash", "id": source_hash},
        {"kind": "claim_lifecycle", "id": claim_lifecycle},
        *task_relation_refs(item),
        *terminal_evidence_refs,
    ]
    open_episode = _append_open_episode_observation(
        conn,
        project_id=project_id,
        task_id=task_id,
        observation_id=hybrid_observation_id,
        now=now,
    ) if observation_inserted else None
    open_episode_id = open_episode["episode_id"] if open_episode else None

    snapshot = workspace_snapshot(payload, item, evidence_refs)
    snapshot_digest = snapshot_hash(snapshot)
    hard_reasons = boundary_reason_codes(previous_epoch, snapshot, snapshot_digest)
    soft_reasons = soft_boundary_reason_codes(payload)
    if hard_reasons and soft_reasons:
        reasons = list(dict.fromkeys([*hard_reasons, *soft_reasons]))
    elif soft_reasons:
        reasons = soft_reasons
    else:
        reasons = hard_reasons
    pulse = adaptive_pulse(payload, item, reasons, soft_reasons)

    workspace_epoch_id: str | None = None
    episode_id: str | None = None
    predecessor_epoch_id = previous_epoch["workspace_epoch_id"] if previous_epoch else None
    epoch_created = False
    boundary_decision = "duplicate_observation"
    if observation_inserted:
        boundary_decision = "create_epoch" if reasons else "no_change"

    if observation_inserted and reasons:
        workspace_epoch_id = str(new_id())
        if open_episode:
            episode_id = open_episode["episode_id"]
            conn.execute(
                """
                UPDATE hybrid_episodes
                   SET closed_at = ?,
                       state = 'closed',
                       boundary_reason_codes = ?,
                       integrated_summary = ?,
                       outcome = ?,
                       evidence_refs = ?
                 WHERE project_id = ?
                   AND episode_id = ?
                """,
                (
                    now,
                    json_dumps(reasons),
                    snapshot["current_goal"],
                    snapshot["current_status"],
                    json_dumps(evidence_refs),
                    project_id,
                    episode_id,
                ),
            )
        else:
            episode_id = str(new_id())
            conn.execute(
                """
                INSERT INTO hybrid_episodes (
                    episode_id, project_id, task_id, started_at, closed_at, state,
                    boundary_reason_codes, observation_ids, integrated_summary,
                    outcome, evidence_refs, integrator_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode_id,
                    project_id,
                    task_id,
                    previous_epoch["valid_from"] if previous_epoch else now,
                    now,
                    "closed",
                    json_dumps(reasons),
                    json_dumps([hybrid_observation_id]),
                    snapshot["current_goal"],
                    snapshot["current_status"],
                    json_dumps(evidence_refs),
                    REDUCER_VERSION,
                ),
            )
        if previous_epoch:
            conn.execute(
                """
                UPDATE workspace_epochs
                   SET valid_to = ?
                 WHERE project_id = ?
                   AND workspace_epoch_id = ?
                """,
                (now, project_id, previous_epoch["workspace_epoch_id"]),
            )
        conn.execute(
            """
            INSERT INTO workspace_epochs (
                workspace_epoch_id, project_id, task_id, scope_json,
                predecessor_epoch_id, valid_from, valid_to, current_goal,
                current_status, active_hypothesis, blockers_json,
                next_actions_json, constraints_json, verified_results_json,
                unresolved_questions_json, relevant_artifacts_json,
                evidence_refs_json, snapshot_hash, reducer_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_epoch_id,
                project_id,
                task_id,
                json_dumps(scope),
                predecessor_epoch_id,
                now,
                None,
                snapshot["current_goal"],
                snapshot["current_status"],
                snapshot["active_hypothesis"],
                json_dumps(snapshot["blockers"]),
                json_dumps(snapshot["next_actions"]),
                json_dumps(snapshot["constraints"]),
                json_dumps(snapshot["verified_results"]),
                json_dumps(snapshot["unresolved_questions"]),
                json_dumps(snapshot["relevant_artifacts"]),
                json_dumps(snapshot["evidence_refs"]),
                snapshot_digest,
                REDUCER_VERSION,
            ),
        )
        epoch_created = True
    else:
        workspace_epoch_id = previous_epoch["workspace_epoch_id"] if previous_epoch else None
        episode_id = open_episode_id

    boundary_decision_id = insert_decision(
        conn,
        project_id=project_id,
        task_id=task_id,
        decision_type="boundary_decision",
        subject_id=hybrid_observation_id,
        decision=boundary_decision,
        reason_codes=reasons,
        evidence_refs=evidence_refs,
        decided_at=now,
        model_profile=decision_model_profile(model_settings, "boundary_decision"),
    )
    durable_reasons = ["task_state_transition", f"claim_lifecycle:{claim_lifecycle.lower()}"]
    durable_reasons.append("terminal_evidence_present" if terminal_evidence_refs else "terminal_evidence_missing")
    durable_write_decision_id = insert_decision(
        conn,
        project_id=project_id,
        task_id=task_id,
        decision_type="durable_write_decision",
        subject_id=claim_id,
        decision="write_compat_task_state_claim",
        reason_codes=durable_reasons,
        evidence_refs=evidence_refs,
        decided_at=now,
        model_profile=decision_model_profile(model_settings, "durable_write_decision"),
    )
    adaptive_pulse_decision_id = insert_decision(
        conn,
        project_id=project_id,
        task_id=task_id,
        decision_type="adaptive_pulse_decision",
        subject_id=hybrid_observation_id,
        decision=str(pulse["decision"]),
        reason_codes=[*pulse["reason_codes"], f"interval_ms:{pulse['interval_ms']}"],
        evidence_refs=evidence_refs,
        decided_at=now,
        model_profile=decision_model_profile(model_settings, "adaptive_pulse_decision"),
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "observation_id": hybrid_observation_id,
        "observation_inserted": observation_inserted,
        "idempotency_key": idempotency_key,
        "boundary_decision_id": boundary_decision_id,
        "boundary_decision": boundary_decision,
        "boundary_reason_codes": reasons,
        "durable_write_decision_id": durable_write_decision_id,
        "durable_write_decision": "write_compat_task_state_claim",
        "soft_boundary_reason_codes": soft_reasons,
        "adaptive_pulse_decision_id": adaptive_pulse_decision_id,
        "adaptive_pulse_decision": pulse["decision"],
        "adaptive_pulse_interval_ms": pulse["interval_ms"],
        "episode_id": episode_id,
        "workspace_epoch_id": workspace_epoch_id,
        "predecessor_epoch_id": predecessor_epoch_id,
        "epoch_created": epoch_created,
        "snapshot_hash": snapshot_digest,
    }


def record_context_access_decision(
    conn: Any,
    *,
    project_id: str,
    workspace_current: dict[str, Any],
    decided_at: str,
    model_settings: dict[str, Any] | None = None,
) -> str:
    task_id = str(workspace_current.get("task_id") or "")
    evidence_refs: list[Any] = []
    evidence = workspace_current.get("evidence") if isinstance(workspace_current.get("evidence"), dict) else {}
    if isinstance(evidence.get("evidence_refs"), list):
        evidence_refs.extend(evidence["evidence_refs"])
    subject_id = str(workspace_current.get("workspace_epoch_id") or task_id or "workspace")
    return insert_decision(
        conn,
        project_id=project_id,
        task_id=task_id,
        decision_type="context_access_decision",
        subject_id=subject_id,
        decision="resume_workspace_plus_query_evidence",
        reason_codes=["resume_workspace", "query_evidence", "workspace_first"],
        evidence_refs=evidence_refs,
        decided_at=decided_at,
        model_profile=decision_model_profile(model_settings, "context_access_decision"),
    )
