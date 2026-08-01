from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException

from . import __version__
from .provider_matrix import provider_parity_payload
from .provider_runtime import configure_provider_payload, provider_catalog_payload, provider_health_payload
from .store import (
    list_gate_log,
    add_memories,
    assemble_context,
    create_claim_evaluation,
    create_summary,
    delete_memories,
    delete_memory,
    get_event,
    get_memories,
    get_memory,
    has_entity_filter,
    validate_filters,
    get_summary,
    lora_base_model_plan,
    lora_training_readiness,
    judge_memories,
    list_events,
    list_memory_dicts,
    list_summaries,
    model_adapter_promotion_report,
    get_task_state,
    prepare_context_autopilot,
    record_context_observation,
    record_context_outcome,
    record_task_state,
    confirm_memory,
    current_project_id,
    search_memories,
    self_improvement_status,
    stale_candidate_pairs,
    supersede_memory,
    update_memory,
    verify_context_evidence,
    verify_judgment_evidence,
    verify_memory_claims,
)

def _default_scope_user_id() -> str:
    """Fallback owner for calls that arrive with no scope at all.

    The unscoped /mcp endpoint used to hardcode user_id='codex' × app_id='codex',
    so every cold install pooled its memories into one ghost scope regardless of
    which client connected (cold-install audit 2026-07-29, defect 1). The OS
    account name is the honest single-tenant default: it matches the machine's
    real owner and stays stable across clients on the same host.
    """
    configured = (os.getenv("MEM1_MCP_DEFAULT_USER_ID") or "").strip()
    if configured:
        return configured
    try:
        import getpass

        username = getpass.getuser().strip()
    except Exception:
        username = ""
    return username or "local"


# No implicit app_id: when the client is unknown we record ownership only.
# Inventing an app pool ("codex", "default", …) silently partitions the user's
# memories by a fiction — reads scoped to it miss every real client's writes.
MCP_DEFAULT_USER_ID = _default_scope_user_id()
MCP_DEFAULT_APP_ID = (os.getenv("MEM1_MCP_DEFAULT_APP_ID") or "").strip()

# Keep in sync with store.ALLOWED_FILTER_KEYS: unknown keys are rejected with a
# 400 instead of silently matching nothing (the pre-2026-07-05 behavior).
_FILTERS_PROPERTY = {
    "type": "object",
    "description": (
        "Scope filters. Keys: user_id, agent_id, app_id, run_id, task_id, goal_id, task_phase, phase, "
        "id, memory, hash, categories, created_at, updated_at, expiration_date, immutable, project_id, "
        "metadata.<path>; combine with AND/OR/NOT lists; compare with "
        "{\"in\"|\"contains\"|\"icontains\"|\"ne\"|\"gte\"|\"lte\"|\"gt\"|\"lt\": value} or \"*\" for any. "
        "Unknown keys are rejected. There is no 'scope' key — scope by entity id."
    ),
}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_mem1_capabilities",
        "description": "Discover Forget preferred API namespaces and compatibility routes.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_provider_parity",
        "description": "Read the Mem0 provider-module parity matrix and current Forget provider adapter status.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_provider_catalog",
        "description": "Read configurable provider options, active project provider settings, and adapter gaps.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
            },
        },
    },
    {
        "name": "get_provider_health",
        "description": "Validate active provider configuration without making external LLM or vector-store calls.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
            },
        },
    },
    {
        "name": "configure_provider",
        "description": "Preview or apply a supported Forget provider configuration for a project.",
        "inputSchema": {
            "type": "object",
            "required": ["category", "provider"],
            "properties": {
                "project_id": {"type": "string"},
                "category": {"type": "string"},
                "provider": {"type": "string"},
                "model": {"type": "string"},
                "model_id": {"type": "string"},
                "base_url": {"type": "string"},
                "api_key_env": {"type": "string"},
                "apply": {"type": "boolean"},
            },
        },
    },
    {
        "name": "get_preflight_status",
        "description": "Check combined Forget API, contract, evaluation, LoRA, and promotion readiness gates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "limit": {"type": "integer"},
                "min_adapter_accuracy": {"type": "number"},
                "min_benchmark_accuracy": {"type": "number"},
                "min_claim_accuracy": {"type": "number"},
                "min_context_accuracy": {"type": "number"},
                "min_shadow_precision": {"type": "number"},
                "min_shadow_reviews": {"type": "integer"},
                "require_self_improvement_ready": {"type": "boolean"},
                "require_promotion_ready": {"type": "boolean"},
                "require_lora_ready": {"type": "boolean"},
                "require_provider_ready": {"type": "boolean"},
                "include_details": {"type": "boolean"},
            },
        },
    },
    {
        "name": "get_model_adapter_promotion_report",
        "description": "Read the server-owned model adapter promotion report and blocker list without applying promotion.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "limit": {"type": "integer"},
                "min_adapter_accuracy": {"type": "number"},
                "min_benchmark_accuracy": {"type": "number"},
                "min_context_accuracy": {"type": "number"},
                "min_shadow_precision": {"type": "number"},
                "min_shadow_reviews": {"type": "integer"},
                "require_self_improvement_ready": {"type": "boolean"},
            },
        },
    },
    {
        "name": "get_self_improvement_status",
        "description": "Read the server-owned Forget self-improvement readiness snapshot without recomputing it in MCP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "min_context_accuracy": {"type": "number"},
                "min_adapter_accuracy": {"type": "number"},
                "min_claim_accuracy": {"type": "number"},
            },
        },
    },
    {
        "name": "get_lora_readiness",
        "description": (
            "Read the server-owned LoRA training readiness snapshot for approved data, packages, and GPU state."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
            },
        },
    },
    {
        "name": "get_lora_base_model_plan",
        "description": (
            "Read the server-owned LoRA base-model cache plan without downloading or selecting models in MCP."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "candidates": {"type": "array"},
                "disk_safety_multiplier": {"type": "number"},
            },
        },
    },
    {
        "name": "add_memory",
        "description": "Save a durable fact the user states about themselves, their work, or their decisions — so future conversations remember it. Call this whenever the user shares a decision, preference, or lasting fact worth recalling later. The server extracts only what is durable. Provenance: `text` saves are recorded as agent-reported (yellow trust) by default; pass source_role=\"user\" ONLY when relaying the user's own words verbatim. Never record a planned action as completed — completion claims without evidence stay unverified.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messages": {"type": "array"},
                "text": {"type": "string"},
                "source_role": {
                    "type": "string",
                    "enum": ["user", "assistant", "tool", "system", "imported"],
                    "description": "Who vouches for this fact. Default for text saves: assistant (agent-authored summary).",
                },
                "user_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "app_id": {"type": "string"},
                "run_id": {"type": "string"},
                "metadata": {"type": "object"},
                "infer": {"type": "boolean"},
                "categories": {"type": "array", "items": {"type": "string"}},
                "category_ids": {"type": "array", "items": {"type": "string"}},
                "expiration_date": {"type": "string"},
                "immutable": {"type": "boolean"},
            },
        },
    },
    {
        "name": "add_memories",
        "description": "Save a durable fact the user states — so future conversations remember it (OpenMemory-compatible alias of add_memory). Call this whenever the user shares a decision, preference, or lasting fact worth recalling later. The server extracts only what is durable.",
        "inputSchema": {
            "type": "object",
            "required": ["text"],
            "properties": {"text": {"type": "string"}, "infer": {"type": "boolean"}},
        },
    },
    {
        "name": "list_gate_log",
        "description": "What the observation gate refused to remember, and why — the audit trail of forgetting. Use when the user asks \"why wasn't X saved?\" or to review what the editor dropped. Entries expire (default 30 days); the log itself forgets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "days": {"type": "number"},
                "filters": _FILTERS_PROPERTY,
            },
        },
    },
    {
        "name": "recall_episode",
        "description": "Episodic recall — search raw local session transcripts for the SCENE behind a conclusion (who said it, in what words, when). Use when a memory or summary feels too thin and you need the original moment: founding incidents, the exact phrasing of a decision, an idea's first appearance. Returns dated excerpts with file:line receipts. Local-only; reads transcripts on this machine, copies nothing.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "terms that must ALL appear in the scene (dumb-and-precise matching; iterate on queries)"},
                "limit": {"type": "integer"},
                "days": {"type": "number", "description": "only scan transcripts modified in the last N days"},
            },
        },
    },
    {
        "name": "search_memories",
        "description": "The user's authoritative long-term memory. ALWAYS call this FIRST — before answering from your own knowledge — whenever the user refers to their own past decisions, preferences, plans, projects, people, or anything that may have been discussed before (e.g. \"what did I decide\", \"do you remember\", \"which X did I pick\"). Returns durable facts newest-first; trust recent over old. Omit filters to use the current session scope. Results may carry a `trust` label — treat it as a permission, not a decoration: green (user-stated or tool-observed) = safe to act on; yellow (agent-inferred or self-summarized) = CONFIRM WITH THE USER before taking real-world action based on it, especially kind=action_report (an unverified claim that something was already done); red (superseded) = reference only. Results without `trust` predate provenance stamping — treat as yellow.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "filters": _FILTERS_PROPERTY,
                "top_k": {"type": "integer"},
                "limit": {"type": "integer", "description": "Alias of top_k (top_k wins when both are given)."},
                "threshold": {"type": "number"},
                "rerank": {"type": "boolean"},
            },
        },
    },
    {
        "name": "search_memory",
        "description": "The user's authoritative long-term memory (OpenMemory-compatible alias of search_memories). ALWAYS call this or search_memories FIRST — before answering from your own knowledge — whenever the user refers to their own past decisions, preferences, plans, projects, people, or anything that may have been discussed before. Returns durable facts; trust recent over old.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}, "threshold": {"type": "number"}},
        },
    },
    {
        "name": "judge_memory",
        "description": "Run the server-owned Forget memory policy judgment contract without reimplementing it in MCP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messages": {"type": "array"},
                "facts": {"type": "array"},
                "text": {"type": "string"},
                "user_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "app_id": {"type": "string"},
                "run_id": {"type": "string"},
                "metadata": {"type": "object"},
                "infer": {"type": "boolean"},
                "apply": {"type": "boolean"},
                "shadow": {"type": "boolean"},
                "shadow_provider": {"type": "string"},
                "shadow_model": {"type": "string"},
                "shadow_adapter_url": {"type": "string"},
                "shadow_timeout": {"type": "number"},
            },
        },
    },
    {
        "name": "assemble_context",
        "description": "Build a policy-aware context capsule about the user for the current task — durable facts, preferences, and recent outcomes assembled under a token budget. Prefer this over answering from your own knowledge when the task depends on what you know about this user.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "project": {"type": "string", "description": "Project layer for task/goal sections; hides tasks tagged with a different project."},
                "filters": _FILTERS_PROPERTY,
                "budget_tokens": {"type": "integer"},
                "working_memory_slots": {"type": "integer"},
                "slot_capacity": {"type": "integer"},
                "top_k": {"type": "integer"},
                "threshold": {"type": "number"},
                "rerank": {"type": "boolean"},
                "reference_date": {"type": "string"},
                "composer_provider": {"type": "string"},
                "composer_model": {"type": "string"},
                "composer_url": {"type": "string"},
                "composer_timeout": {"type": "number"},
                "verify_evidence": {"type": "boolean"},
            },
        },
    },
    {
        "name": "prepare_context_autopilot",
        "description": "Return an action-ready pre-turn Context Capsule with use_now, status, provenance, and debug without dumping raw assembled context.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "project": {"type": "string", "description": "Project layer for task/goal sections; hides tasks tagged with a different project."},
                "filters": _FILTERS_PROPERTY,
                "budget_tokens": {"type": "integer"},
                "working_memory_slots": {"type": "integer"},
                "slot_capacity": {"type": "integer"},
                "top_k": {"type": "integer"},
                "threshold": {"type": "number"},
                "rerank": {"type": "boolean"},
                "reference_date": {"type": "string"},
                "composer_provider": {"type": "string"},
                "composer_model": {"type": "string"},
                "composer_url": {"type": "string"},
                "composer_timeout": {"type": "number"},
                "verify_evidence": {"type": "boolean"},
                "include_debug": {"type": "boolean"},
                "include_context": {"type": "boolean"},
                "client_workdir": {"type": "string"},
                "workdir": {"type": "string"},
                "cwd": {"type": "string"},
                "workspace": {"type": "string"},
            },
        },
    },
    {
        "name": "record_task_state",
        "description": "Record the current agent task state as an observation-backed task_state claim.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "goal_id": {"type": "string"},
                "parent_goal_id": {"type": "string"},
                "parent_task_id": {"type": "string"},
                "related_task_ids": {"type": "array", "items": {"type": "string"}},
                "status": {"type": "string"},
                "summary": {"type": "string"},
                "next_actions": {"type": "array", "items": {"type": "string"}},
                "blockers": {"type": "array", "items": {"type": "string"}},
                "evidence": {"type": "object"},
                "evidence_files": {"type": "array", "items": {"type": "string"}},
                "commands": {"type": "array", "items": {"type": "string"}},
                "filters": _FILTERS_PROPERTY,
                "user_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "app_id": {"type": "string"},
                "run_id": {"type": "string"},
                "confidence": {"type": "number"},
                "source_role": {"type": "string"},
                "authority": {"type": "string"},
                "retention_policy": {"type": "string"},
                "project": {"type": "string", "description": "Project key this task belongs to (usually stamped by the client hook from cwd). Project-scoped reads hide tasks tagged with a different project."},
                "metadata": {"type": "object"},
            },
        },
    },
    {
        "name": "record_context_observation",
        "description": "Record a passive runtime observation for a context trace without requiring an outcome label.",
        "inputSchema": {
            "type": "object",
            "required": ["trace_id"],
            "properties": {
                "trace_id": {"type": "string"},
                "task_id": {"type": "string"},
                "source": {"type": "string"},
                "used_memory_ids": {"type": "array", "items": {"type": "string"}},
                "missing_memory_ids": {"type": "array", "items": {"type": "string"}},
                "harmful_memory_ids": {"type": "array", "items": {"type": "string"}},
                "first_action": {"type": "string"},
                "first_tool_call": {"type": "object"},
                "tool_result": {"type": "object"},
                "used_context_surfaces": {"type": "array", "items": {"type": "string"}},
                "used_current_workspace": {"type": "boolean"},
                "used_action_hint_group": {"type": "string"},
                "used_action_hint_source": {"type": "string"},
                "used_action_hint_target": {"type": "string"},
                "user_correction_signal": {"type": "boolean"},
                "repeated_work": {"type": "boolean"},
                "wrong_target": {"type": "boolean"},
                "metadata": {"type": "object"},
                "observed": {"type": "object"},
            },
        },
    },
    {
        "name": "record_context_outcome",
        "description": "Record whether an assembled context actually supported the first useful agent action.",
        "inputSchema": {
            "type": "object",
            "required": ["trace_id"],
            "properties": {
                "trace_id": {"type": "string"},
                "task_id": {"type": "string"},
                "used_memory_ids": {"type": "array", "items": {"type": "string"}},
                "missing_memory_ids": {"type": "array", "items": {"type": "string"}},
                "harmful_memory_ids": {"type": "array", "items": {"type": "string"}},
                "first_action_productive": {"type": "boolean"},
                "user_correction_required": {"type": "boolean"},
                "repeated_work": {"type": "boolean"},
                "wrong_target": {"type": "boolean"},
                "failure_stage": {
                    "type": "string",
                    "enum": [
                        "none",
                        "write_failure",
                        "retrieval_failure",
                        "selection_failure",
                        "packing_failure",
                        "reasoning_failure",
                        "unknown",
                    ],
                },
                "first_action": {"type": "string"},
                "first_tool_call": {"type": "object"},
                "tool_result": {"type": "object"},
                "used_context_surfaces": {"type": "array", "items": {"type": "string"}},
                "used_current_workspace": {"type": "boolean"},
                "used_action_hint_group": {"type": "string"},
                "used_action_hint_source": {"type": "string"},
                "used_action_hint_target": {"type": "string"},
                "notes": {"type": "string"},
                "metadata": {"type": "object"},
                "observed": {"type": "object"},
                "inferred": {"type": "object"},
                "inference_confidence": {"type": "number"},
            },
        },
    },
    {
        "name": "get_task_state",
        "description": "Read active task_state claims for the MCP session scope.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "project": {"type": "string", "description": "Limit to this project's tasks plus untagged ones; omit for the cross-project view."},
                "filters": _FILTERS_PROPERTY,
                "user_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "app_id": {"type": "string"},
                "run_id": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "verify_context_evidence",
        "description": "Verify a Forget context result or evidence object against current memory hashes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context_result": {"type": "object"},
                "evidence": {"type": "object"},
                "context": {"type": "string"},
            },
        },
    },
    {
        "name": "verify_judgment_evidence",
        "description": "Verify a Forget judgment result or judgment evidence object against current memory hashes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "judgment_result": {"type": "object"},
                "result": {"type": "object"},
                "evidence": {"type": "object"},
            },
        },
    },
    {
        "name": "verify_memory_claims",
        "description": "Check whether answer claims are supported by current scoped memories or context evidence.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claims": {"type": "array"},
                "answer": {"type": "string"},
                "text": {"type": "string"},
                "filters": _FILTERS_PROPERTY,
                "context_result": {"type": "object"},
                "evidence": {"type": "object"},
                "min_support_score": {"type": "number"},
                "top_k": {"type": "integer"},
                "threshold": {"type": "number"},
            },
        },
    },
    {
        "name": "create_claim_evaluation",
        "description": "Run and save a memory-backed claim verification evaluation dataset.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "claims": {"type": "array"},
                "dataset": {"type": "array"},
                "items": {"type": "array"},
                "filters": _FILTERS_PROPERTY,
                "min_support_score": {"type": "number"},
                "regression_threshold": {"type": "number"},
            },
        },
    },
    {
        "name": "create_summary",
        "description": "Create a drift-checked compressed summary from scoped memories.",
        "inputSchema": {
            "type": "object",
            "required": ["filters"],
            "properties": {
                "filters": _FILTERS_PROPERTY,
                "query": {"type": "string"},
                "budget_tokens": {"type": "integer"},
                "top_k": {"type": "integer"},
                "threshold": {"type": "number"},
                "rerank": {"type": "boolean"},
            },
        },
    },
    {
        "name": "list_summaries",
        "description": "List stored summaries for the current project.",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    },
    {
        "name": "get_summary",
        "description": "Retrieve one summary by summary_id.",
        "inputSchema": {
            "type": "object",
            "required": ["summary_id"],
            "properties": {"summary_id": {"type": "string"}},
        },
    },
    {
        "name": "get_memories",
        "description": "List memories with filters and pagination.",
        "inputSchema": {
            "type": "object",
            "required": ["filters"],
            "properties": {"filters": _FILTERS_PROPERTY, "page": {"type": "integer"}, "page_size": {"type": "integer"}},
        },
    },
    {
        "name": "list_memories",
        "description": "Browse everything stored in the user's long-term memory (OpenMemory-compatible alias). Use to review what is known about the user; to answer a specific question, prefer search_memories.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_memory",
        "description": "Retrieve one memory by memory_id.",
        "inputSchema": {
            "type": "object",
            "required": ["memory_id"],
            "properties": {"memory_id": {"type": "string"}},
        },
    },
    {
        "name": "update_memory",
        "description": "Overwrite a memory's text or metadata.",
        "inputSchema": {
            "type": "object",
            "required": ["memory_id"],
            "properties": {"memory_id": {"type": "string"}, "text": {"type": "string"}, "metadata": {"type": "object"}},
        },
    },
    {
        "name": "review_stale_candidates",
        "description": "Review inbox for stale memories: returns same-topic pairs whose timestamps are far apart, where the older one may be superseded by the newer. Adjudicate each pair yourself, then call supersede_memory for the obsolete ones. Hints only - false positives are expected.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "agent_id": {"type": "string"},
                "app_id": {"type": "string"},
                "run_id": {"type": "string"},
                "top_n": {"type": "integer"},
                "min_similarity": {"type": "number"},
                "min_days": {"type": "number"},
            },
        },
    },
    {
        "name": "confirm_memory",
        "description": "Close an open loop the honest way: a reported/unverified action claim turned out TRUE — attach the evidence and promote it to verified (green). Use this instead of supersede_memory when the claim was right: supersede means 'it was wrong', confirm means 'it was right, here is the receipt'. Evidence is required.",
        "inputSchema": {
            "type": "object",
            "required": ["memory_id", "evidence"],
            "properties": {
                "memory_id": {"type": "string"},
                "evidence": {"type": "string", "description": "What verifies the claim (observation, test result, user statement)"},
                "evidence_ref": {"type": "string", "description": "Optional pointer: commit hash, file path, event id"},
            },
        },
    },
    {
        "name": "supersede_memory",
        "description": "Mark a memory as superseded by a newer fact. Non-destructive: it stays retrievable but is demoted in every future search and annotated as superseded. Use when a stored fact is outdated (a completed todo, a changed decision). ALWAYS pass superseded_by to link the replacing memory — the link powers conflict-zone alerts. For a claim that was TRUE but unverified, use confirm_memory instead.",
        "inputSchema": {
            "type": "object",
            "required": ["memory_id"],
            "properties": {
                "memory_id": {"type": "string"},
                "superseded_by": {"type": "string", "description": "id of the memory that replaces it (optional)"},
                "reason": {"type": "string"},
            },
        },
    },
    {
        "name": "delete_memory",
        "description": "Delete a single memory by memory_id.",
        "inputSchema": {
            "type": "object",
            "required": ["memory_id"],
            "properties": {"memory_id": {"type": "string"}},
        },
    },
    {
        "name": "delete_memories",
        "description": "Delete specific memories by ID (OpenMemory-compatible alias). Destructive — use only when the user explicitly asks to forget something; to retire an outdated fact, prefer supersede_memory.",
        "inputSchema": {
            "type": "object",
            "required": ["memory_ids"],
            "properties": {"memory_ids": {"type": "array", "items": {"type": "string"}}},
        },
    },
    {
        "name": "delete_all_memories",
        "description": "Bulk delete memories matching a scope filter or the OpenMemory MCP path user and client.",
        "inputSchema": {
            "type": "object",
            "properties": {"filters": _FILTERS_PROPERTY},
        },
    },
    {
        "name": "delete_entities",
        "description": "Delete a user, agent, app, or run entity and all matching memories.",
        "inputSchema": {
            "type": "object",
            "required": ["entity_type", "entity_id"],
            "properties": {"entity_type": {"type": "string"}, "entity_id": {"type": "string"}},
        },
    },
    {
        "name": "list_entities",
        "description": "Enumerate users, agents, apps, and runs stored in memory.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_events",
        "description": "List memory operation events.",
        "inputSchema": {
            "type": "object",
            "properties": {"page": {"type": "integer"}, "page_size": {"type": "integer"}},
        },
    },
    {
        "name": "get_event_status",
        "description": "Check the status of an async memory operation by event_id.",
        "inputSchema": {
            "type": "object",
            "required": ["event_id"],
            "properties": {"event_id": {"type": "string"}},
        },
    },
]

# MCP tool annotations (readOnlyHint/destructiveHint) required by connector
# directory reviews. Tools that write memory/config/telemetry state are not
# read-only; only irreversible data removal is destructive.
_MUTATING_TOOLS = {
    "configure_provider",
    "add_memory",
    "add_memories",
    "judge_memory",
    "record_task_state",
    "record_context_observation",
    "record_context_outcome",
    "create_claim_evaluation",
    "create_summary",
    "update_memory",
}
_DESTRUCTIVE_TOOLS = {
    "delete_memory",
    "delete_memories",
    "delete_all_memories",
    "delete_entities",
}


def _tool_annotations(name: str) -> dict[str, bool]:
    if name in _DESTRUCTIVE_TOOLS:
        return {"readOnlyHint": False, "destructiveHint": True}
    if name in _MUTATING_TOOLS:
        return {"readOnlyHint": False, "destructiveHint": False}
    return {"readOnlyHint": True, "destructiveHint": False}


for _tool in TOOLS:
    _tool.setdefault("annotations", {}).update(_tool_annotations(str(_tool.get("name") or "")))


def _text_result(value: Any) -> dict[str, Any]:
    result = {"content": [{"type": "text", "text": value if isinstance(value, str) else _json(value)}]}
    if not isinstance(value, str):
        result["structuredContent"] = value
    return result


def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _entity_filter(entity_type: str, entity_id: str) -> dict[str, str]:
    field = entity_type[:-1] if entity_type.endswith("s") else entity_type
    if field not in {"user", "agent", "app", "run"}:
        raise HTTPException(status_code=400, detail="Unsupported entity_type")
    return {f"{field}_id": entity_id}


def _arg_bool(args: dict[str, Any], key: str, default: bool = False) -> bool:
    value = args.get(key, default)
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _arg_float(args: dict[str, Any], key: str, default: float) -> float:
    value = args.get(key, default)
    if value is None:
        return default
    return float(value)


def _arg_int(args: dict[str, Any], key: str, default: int) -> int:
    value = args.get(key, default)
    if value is None:
        return default
    return int(value)


def _validate_search_params(args: dict[str, Any]) -> None:
    threshold = args.get("threshold")
    top_k = args.get("top_k", args.get("limit"))
    if threshold is not None:
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise HTTPException(status_code=400, detail="threshold must be a valid number")
        if threshold < 0 or threshold > 1:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid threshold: {threshold}. Must be between 0 and 1 (inclusive).",
            )
    if top_k is not None:
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise HTTPException(status_code=400, detail="topK must be a valid integer")
        if top_k < 0:
            raise HTTPException(status_code=400, detail=f"Invalid topK: {top_k}. Must be a non-negative integer.")


def list_entities_payload() -> dict[str, list[dict[str, Any]]]:
    memories = list_memory_dicts()
    result: dict[str, list[dict[str, Any]]] = {"users": [], "agents": [], "apps": [], "runs": []}
    for field, bucket in [("user_id", "users"), ("agent_id", "agents"), ("app_id", "apps"), ("run_id", "runs")]:
        seen: dict[str, int] = {}
        for memory in memories:
            value = memory.get(field)
            if value:
                seen[value] = seen.get(value, 0) + 1
        result[bucket] = [{"id": key, "memory_count": count} for key, count in sorted(seen.items())]
    return result


def mem1_capabilities_payload() -> dict[str, Any]:
    return {
        "schema_version": "mem1-capabilities-v1",
        "service": "mem1",
        "preferred_namespace": "/v1/mem1",
        "compatibility_namespaces": ["/v1", "/v2", "/v3"],
        "control_plane": {
            "judgments": "/v1/mem1/judgments/",
            "judgment_audit": "/v1/mem1/judgments/audit/",
            "judgment_audit_reviews": "/v1/mem1/judgments/audit/{event_id}/reviews/",
            "self_improvement_status": "/v1/mem1/self-improvement/status/",
            "policy_presets": "/v1/mem1/policy/presets/",
            "policy_preset_apply": "/v1/mem1/policy/presets/{preset_id}/apply",
            "data_requests": "/v1/mem1/data-requests/",
            "provider_parity": "/v1/mem1/providers/",
            "provider_catalog": "/v1/mem1/providers/catalog/",
            "provider_health": "/v1/mem1/providers/health/",
            "provider_configure": "/v1/mem1/providers/configure/",
            "lora_readiness": "/v1/mem1/lora/readiness/",
            "lora_base_model_plan": "/v1/mem1/lora/base-model-plan/",
            "preflight": "/v1/mem1/preflight/",
            "platform_ping": "/v1/ping/",
            "readiness": "/ready",
            "context": "/v1/mem1/context/",
            "context_autopilot": "/v1/mem1/context/autopilot/",
            "context_verify": "/v1/mem1/context/verify",
            "context_trace": "/v1/mem1/context/traces/{trace_id}",
            "context_outcomes": "/v1/mem1/context/outcomes/",
            "context_observations": "/v1/mem1/context/observations/",
            "judgment_verify": "/v1/mem1/judgments/verify",
            "claim_verify": "/v1/mem1/claims/verify",
            "claim_evaluations": "/v1/mem1/claims/evaluations/",
            "context_evaluations": "/v1/mem1/context/evaluations/",
            "summaries": "/v1/mem1/summaries/",
            "proposals": "/v1/mem1/proposals/",
            "proposal_rollout": "/v1/mem1/proposals/rollout/",
            "proposal_reviews": "/v1/mem1/proposals/{proposal_id}/reviews/",
            "proposal_apply": "/v1/mem1/proposals/{proposal_id}/apply",
            "proposal_reject": "/v1/mem1/proposals/{proposal_id}/reject",
            "training_traces": "/v1/mem1/traces/training/",
            "trace_audit": "/v1/mem1/traces/audit/",
            "trace_export_approvals": "/v1/mem1/traces/export-approvals/",
            "trace_export_approval": "/v1/mem1/traces/export-approvals/{approval_id}/",
            "trace_export_approval_approve": "/v1/mem1/traces/export-approvals/{approval_id}/approve",
            "trace_export_approval_reject": "/v1/mem1/traces/export-approvals/{approval_id}/reject",
            "trace_export_dataset": "/v1/mem1/traces/export-approvals/{approval_id}/dataset/",
            "sft_dataset": "/v1/mem1/traces/export-approvals/{approval_id}/sft-dataset/",
            "fine_tuning_jobs": "/v1/mem1/fine-tuning/jobs/",
            "model_artifacts": "/v1/mem1/model-artifacts/",
            "model_artifact_deploy": "/v1/mem1/model-artifacts/{artifact_id}/deploy",
            "model_deployments": "/v1/mem1/model-deployments/",
            "model_deployment_activate": "/v1/mem1/model-deployments/{deployment_id}/activate",
            "model_activations": "/v1/mem1/model-activations/",
            "model_activation_health": "/v1/mem1/model-activations/{activation_id}/health",
            "model_activation_rollback": "/v1/mem1/model-activations/{activation_id}/rollback",
            "model_activation_rollback_overrides": "/v1/mem1/model-activations/rollback-overrides/",
            "model_adapter_evaluations": "/v1/mem1/model-adapters/evaluations/",
            "model_adapter_comparisons": "/v1/mem1/model-adapters/comparisons/",
            "promotion_report": "/v1/mem1/model-adapters/promotion-report/",
            "promotion_blocker_reviews": "/v1/mem1/model-adapters/promotion-blockers/{blocker_code}/reviews/",
            "promotion_activation": "/v1/mem1/model-adapters/promotion-activation/",
            "promotion_audit": "/v1/mem1/model-adapters/promotion-audit/",
        },
        "governance": {
            "promotion_audit_export": "/v1/mem1/model-adapters/promotion-audit/export",
            "promotion_audit_verify": "/v1/mem1/model-adapters/promotion-audit/verify",
            "retention": "/v1/mem1/model-adapters/promotion-audit/retention/",
            "retention_apply_requests": "/v1/mem1/model-adapters/promotion-audit/retention/apply-requests/",
            "retention_archive": "/v1/mem1/model-adapters/promotion-audit/retention/archive",
            "retention_archive_verify": "/v1/mem1/model-adapters/promotion-audit/retention/archive/verify",
            "retention_policy": "/v1/mem1/model-adapters/promotion-audit/retention/policy",
            "retention_policy_run": "/v1/mem1/model-adapters/promotion-audit/retention/policy/run",
            "retention_policy_run_due": "/v1/mem1/model-adapters/promotion-audit/retention/policy/run-due",
        },
        "contracts": {
            "working_memory": "mem1-working-memory-v1",
            "context_evidence": "mem1-context-evidence-v1",
            "context_trace": "mem1-context-trace-v1",
            "context_outcome": "mem1-context-outcome-v1",
            "context_observation": "mem1-context-observation-v0",
            "context_outcome_observed": "mem1-context-outcome-observed-v0",
            "context_outcome_inferred": "mem1-context-outcome-inferred-v0",
            "context_autopilot": "mem1-context-autopilot-v0",
            "context_capsule": "mem1-context-capsule-v0",
            "context_use_now": "mem1-context-use-now-v0",
            "context_status": "mem1-context-status-v0",
            "context_materialization": "mem1-context-materialization-v0",
            "context_evidence_verification": "mem1-context-evidence-verification-v1",
            "judgment_result": "mem1-judgment-result-v1",
            "judgment_evidence": "mem1-judgment-evidence-v1",
            "judgment_evidence_verification": "mem1-judgment-evidence-verification-v1",
            "claim_verification": "mem1-claim-verification-v1",
            "context_composer_request": "mem1-context-composer-request-v1",
            "shadow_adapter_request": "mem1-shadow-adapter-request-v1",
            "policy_adapter_input": "mem1-policy-adapter-input-v1",
            "policy_adapter_evidence": "mem1-policy-adapter-evidence-v1",
            "policy_sft_dataset": "mem1-policy-sft-v1",
            "fine_tuning_job": "mem1-fine-tuning-job-v1",
            "lora_base_model_plan": "mem1-lora-base-model-plan-v1",
            "model_artifact": "mem1-model-artifact-v1",
            "trainer_response": "mem1-trainer-artifact-v1",
            "model_adapter_promotion_report": "mem1-model-adapter-promotion-report-v1",
            "promotion_audit_bundle": "promotion-audit-bundle-v1",
            "promotion_audit_retention_archive": "promotion-audit-retention-archive-v1",
        },
        "mcp": {
            "endpoint": "/mcp",
            "scoped_endpoint": "/mcp/{app_id}/http/{user_id}",
            "transport": "streamable-http",
            "recommended_context_tool": "assemble_context",
            "recommended_autopilot_tool": "prepare_context_autopilot",
            "tools": [tool["name"] for tool in TOOLS],
        },
    }


def _openmemory_scope(args: dict[str, Any], context: dict[str, str] | None) -> dict[str, str]:
    user_id = str(args.get("user_id") or (context or {}).get("user_id") or "")
    app_id = str(args.get("app_id") or args.get("client_name") or (context or {}).get("client_name") or "")
    scope: dict[str, str] = {}
    if user_id:
        scope["user_id"] = user_id
    if app_id:
        scope["app_id"] = app_id
    return scope


def _mcp_default_scope(args: dict[str, Any], context: dict[str, str] | None) -> dict[str, str]:
    scope = _openmemory_scope(args, context)
    if not scope.get("user_id"):
        default_user_id = str(args.get("default_user_id") or MCP_DEFAULT_USER_ID).strip()
        if default_user_id:
            scope["user_id"] = default_user_id
    if not scope.get("app_id"):
        default_app_id = str(args.get("default_app_id") or MCP_DEFAULT_APP_ID).strip()
        if default_app_id:
            scope["app_id"] = default_app_id
    return scope


def _mcp_scoped_filters(args: dict[str, Any], context: dict[str, str] | None) -> dict[str, Any]:
    filters = args.get("filters")
    filters = dict(filters) if isinstance(filters, dict) else {}
    # Validate the caller's filters before merging defaults, so the error
    # names exactly what the client sent — every MCP tool that accepts
    # filters funnels through here, including ones whose store functions
    # ignore unrecognized keys instead of matching nothing.
    validate_filters(filters)
    if has_entity_filter(filters):
        return filters
    explicit_scope = _openmemory_scope(args, context)
    if explicit_scope:
        # The caller named an entity (user_id/app_id/client_name): scope to
        # exactly that. Injecting the default app_id alongside an explicit
        # user_id silently excludes every memory stored without an app_id —
        # this is what made assemble_context return empty capsules over MCP.
        return {**filters, **explicit_scope}
    return {**filters, **_mcp_default_scope(args, context)}


def _require_openmemory_scope(args: dict[str, Any], context: dict[str, str] | None) -> dict[str, str]:
    scope = _mcp_default_scope(args, context)
    if not scope.get("user_id"):
        raise HTTPException(status_code=400, detail="user_id is required for OpenMemory MCP compatibility tools")
    if not scope.get("app_id"):
        detail = "client_name or app_id is required for OpenMemory MCP compatibility tools"
        raise HTTPException(status_code=400, detail=detail)
    return scope


def _mcp_context_compact_requested(args: dict[str, Any]) -> bool:
    """Explicit args win; otherwise the server env decides the default.

    Production sets MEM1_MCP_COMPACT_CONTEXT=true so remote agents get the
    slim capsule by default, while local/dev (and the behavior test suite)
    keep the full diagnostic payload.
    """
    def _truthy(value: Any) -> bool:
        return str(value or "").lower() in {"1", "true", "yes"}

    if _truthy(args.get("debug")) or _truthy(args.get("verbose")):
        return False
    if "compact" in args:
        return _truthy(args.get("compact"))
    return _truthy(os.getenv("MEM1_MCP_COMPACT_CONTEXT"))


def _compact_context_capsule(assembled: dict[str, Any]) -> dict[str, Any]:
    """Slim the assemble_context payload for MCP consumers.

    The full capsule is ~8k tokens of which the usable context is ~3%
    (measured 2026-07-04); an agent reading the result pays that on every
    call. Keep what an agent acts on — context, memories, the trace id for
    record_context_outcome, status — and leave the full diagnostics to
    debug=true or the dashboard.
    """
    memories = [
        {"id": memory.get("id"), "memory": memory.get("memory"), "score": memory.get("score")}
        for memory in (assembled.get("memories") or [])
    ]
    next_actions = [
        {key: action.get(key) for key in ("action", "target", "purpose") if action.get(key)}
        for action in ((assembled.get("use_now") or {}).get("next_actions") or [])
        if isinstance(action, dict)
    ]
    status = assembled.get("context_status") or {}
    return {
        "context": assembled.get("context"),
        "capsule_text": assembled.get("context_capsule_text"),
        "memories": memories,
        "budgeted_count": assembled.get("budgeted_count"),
        "omitted_count": assembled.get("omitted_count"),
        "context_status": status.get("effective_status") or status.get("status"),
        "next_actions": next_actions,
        "context_trace_id": assembled.get("context_trace_id"),
        "hint": "record_context_outcome(trace_id, used_memory_ids/harmful_memory_ids) after acting; debug=true for full diagnostics",
    }


# Memory-read tools whose invocation means an external AI actually looked at the
# user's memory (the app's own console reads over HTTP, not MCP — so an MCP read
# is a connected client, e.g. Claude Desktop). We log a lightweight usage event so
# the app can surface "last referenced N minutes ago" — proof the wiring is live,
# not just configured.
_MEMORY_READ_OPS = frozenset(
    {"search_memories", "search_memory", "get_memories", "get_memory", "list_memories", "assemble_context"}
)

# MCP clients get no schema enforcement from the transport, so a misspelled or
# unsupported argument (e.g. max_results on search_memories) used to be dropped
# on the floor while the call "succeeded" with defaults. Warn instead of
# reject: rejecting would break agents mid-conversation over a cosmetic key.
# Accepted keys = declared inputSchema properties ∪ scope/context keys every
# scoped tool reads ∪ per-tool aliases the store handlers accept but the
# schema intentionally doesn't advertise.
_SCOPE_ARGS = frozenset({"user_id", "agent_id", "app_id", "run_id", "client_name", "project_id"})
_AS_OF_ARGS = frozenset({"memory_as_of", "memoryAsOf", "as_of", "asOf"})
_WORKSPACE_AS_OF_ARGS = frozenset(
    {"resume_workspace_as_of", "resumeWorkspaceAsOf", "workspace_as_of", "workspaceAsOf"}
)
_CONTEXT_ASSEMBLY_ARGS = (
    frozenset(
        {
            "limit",
            "budget",
            "slots",
            "scope_fallback",
            "temporal_rerank",
            "reference_date",
            "verify",
            "disable_resume_workspace",
            "disableResumeWorkspace",
            "compact",
            "debug",
            "verbose",
        }
    )
    | _AS_OF_ARGS
    | _WORKSPACE_AS_OF_ARGS
)
_EXTRA_ACCEPTED_ARGS: dict[str, frozenset[str]] = {
    "search_memories": frozenset(
        {"show_expired", "keyword_search", "filter_memories", "reference_date", "scope_fallback", "temporal_rerank"}
    )
    | _AS_OF_ARGS,
    "search_memory": frozenset({"top_k"}),
    "assemble_context": _CONTEXT_ASSEMBLY_ARGS,
    "prepare_context_autopilot": _CONTEXT_ASSEMBLY_ARGS,
    "create_summary": frozenset({"limit", "budget", "max_memories", "metadata"}),
    "get_task_state": _AS_OF_ARGS | _WORKSPACE_AS_OF_ARGS,
    "add_memory": frozenset({"created_at", "custom_timestamp", "timestamp"}),
    "add_memories": frozenset({"metadata"}),
    "create_claim_evaluation": frozenset(
        {"benchmark_family", "family", "metadata", "reference_date", "rerank", "threshold", "top_k", "limit"}
    ),
    "verify_memory_claims": frozenset({"context", "result"}),
    "record_task_state": frozenset({"sensitivity"}),
}
_TOOL_ARG_NAMES: dict[str, frozenset[str]] = {
    str(tool["name"]): frozenset((tool.get("inputSchema") or {}).get("properties") or {}) for tool in TOOLS
}


def _unknown_arg_notes(name: str, args: dict[str, Any]) -> list[str]:
    declared = _TOOL_ARG_NAMES.get(name)
    if declared is None:
        return []
    accepted = declared | _SCOPE_ARGS | _EXTRA_ACCEPTED_ARGS.get(name, frozenset())
    unknown = sorted(key for key in args if key not in accepted)
    if not unknown:
        return []
    import difflib

    notes = []
    for key in unknown:
        matches = difflib.get_close_matches(key, sorted(accepted), n=1)
        notes.append(f"{key} (did you mean '{matches[0]}'?)" if matches else key)
    return notes


def _reject_unknown_args(name: str, args: dict[str, Any]) -> None:
    """Search tools reject unknown top-level arguments outright.

    A warning appended after the results proved too quiet in practice: the
    first external user report showed callers never see it (issue #29).
    An unknown argument on a read path means the caller believes they are
    constraining the search when they are not — that must fail loudly.
    """
    notes = _unknown_arg_notes(name, args)
    if notes:
        raise HTTPException(
            status_code=400,
            detail=f"{name} got unknown argument(s): " + ", ".join(notes),
        )


def _unknown_args_warning(name: str, args: dict[str, Any]) -> str | None:
    notes = _unknown_arg_notes(name, args)
    if not notes:
        return None
    return f"warning: {name} ignored unknown argument(s): " + ", ".join(notes)


def call_tool(name: str, arguments: dict[str, Any] | None, context: dict[str, str] | None = None) -> dict[str, Any]:
    result = _dispatch_tool(name, arguments, context)
    if name in _MEMORY_READ_OPS:
        try:
            from .providers import record_usage

            record_usage(current_project_id(), f"mcp.{name}", metadata={"surface": "mcp", "tool": name})
        except Exception:
            pass  # telemetry must never break a tool call
    warning = _unknown_args_warning(name, arguments or {})
    if warning and isinstance(result.get("content"), list):
        result["content"].append({"type": "text", "text": warning})
    return result


def _dispatch_tool(name: str, arguments: dict[str, Any] | None, context: dict[str, str] | None = None) -> dict[str, Any]:
    args = dict(arguments or {})
    if name == "list_gate_log":
        return _text_result(list_gate_log({**args, "filters": _mcp_scoped_filters(args, context)}))
    if name == "recall_episode":
        from .episodes import recall_episodes_payload

        return _text_result(recall_episodes_payload(args))
    if name == "get_mem1_capabilities":
        return _text_result(mem1_capabilities_payload())
    if name == "get_provider_parity":
        return _text_result(provider_parity_payload())
    if name == "get_provider_catalog":
        return _text_result(provider_catalog_payload(project_id=str(args.get("project_id") or "proj_local")))
    if name == "get_provider_health":
        return _text_result(provider_health_payload(project_id=str(args.get("project_id") or "proj_local")))
    if name == "configure_provider":
        return _text_result(configure_provider_payload(dict(args), project_id=str(args.get("project_id") or "proj_local")))
    if name == "get_preflight_status":
        from .preflight import mem1_preflight_payload

        return _text_result(
            mem1_preflight_payload(
                project_id=str(args.get("project_id") or "proj_local"),
                limit=_arg_int(args, "limit", 100),
                min_adapter_accuracy=_arg_float(args, "min_adapter_accuracy", 0.9),
                min_benchmark_accuracy=_arg_float(args, "min_benchmark_accuracy", 1.0),
                min_claim_accuracy=_arg_float(args, "min_claim_accuracy", 1.0),
                min_context_accuracy=_arg_float(args, "min_context_accuracy", 1.0),
                min_shadow_precision=_arg_float(args, "min_shadow_precision", 0.9),
                min_shadow_reviews=_arg_int(args, "min_shadow_reviews", 1),
                require_self_improvement_ready=_arg_bool(args, "require_self_improvement_ready"),
                require_promotion_ready=_arg_bool(args, "require_promotion_ready"),
                require_lora_ready=_arg_bool(args, "require_lora_ready"),
                require_provider_ready=_arg_bool(args, "require_provider_ready"),
                include_details=_arg_bool(args, "include_details"),
            )
        )
    if name == "get_model_adapter_promotion_report":
        return _text_result(
            model_adapter_promotion_report(
                project_id=str(args.get("project_id") or "proj_local"),
                limit=_arg_int(args, "limit", 100),
                min_adapter_accuracy=_arg_float(args, "min_adapter_accuracy", 0.9),
                min_benchmark_accuracy=_arg_float(args, "min_benchmark_accuracy", 1.0),
                min_context_accuracy=_arg_float(args, "min_context_accuracy", 1.0),
                min_shadow_precision=_arg_float(args, "min_shadow_precision", 0.9),
                min_shadow_reviews=_arg_int(args, "min_shadow_reviews", 1),
                require_self_improvement_ready=_arg_bool(args, "require_self_improvement_ready"),
            )
        )
    if name == "get_self_improvement_status":
        return _text_result(
            self_improvement_status(
                project_id=str(args.get("project_id") or "proj_local"),
                min_context_accuracy=_arg_float(args, "min_context_accuracy", 1.0),
                min_adapter_accuracy=_arg_float(args, "min_adapter_accuracy", 0.9),
                min_claim_accuracy=_arg_float(args, "min_claim_accuracy", 1.0),
            )
        )
    if name == "get_lora_readiness":
        return _text_result(lora_training_readiness(project_id=str(args.get("project_id") or "proj_local")))
    if name == "get_lora_base_model_plan":
        return _text_result(lora_base_model_plan(dict(args), project_id=str(args.get("project_id") or "proj_local")))
    if name == "add_memory":
        payload = dict(args)
        if "messages" not in payload:
            text = payload.pop("text", None)
            if not text:
                raise HTTPException(status_code=400, detail="messages or text is required")
            # Role "user" is kept for extraction compatibility, but a text
            # save arrives through an agent-operated channel: unless the
            # caller explicitly vouches otherwise, its provenance is the
            # agent's own summary, not the user's words.
            payload["messages"] = [{"role": "user", "content": str(text)}]
            payload.setdefault("source_role", "assistant")
        scope_warning: str | None = None
        if not any(payload.get(field) for field in ("user_id", "agent_id", "run_id")):
            # app_id alone is client provenance, not ownership: an app_id-only
            # write would store user_id=NULL while default-scoped reads search
            # the session user_id — stored but never found by any search.
            defaults = _mcp_default_scope(args, context)
            for key, value in defaults.items():
                if not payload.get(key):
                    payload[key] = value
            explicit = _openmemory_scope(args, context)
            if defaults.get("user_id") and not explicit.get("user_id") and not args.get("default_user_id"):
                # The write is landing in the server-side fallback scope: say so
                # in-band, because a silently assumed owner is exactly how the
                # codex×codex ghost pool formed.
                described = " ".join(f"{key}='{value}'" for key, value in sorted(defaults.items()))
                scope_warning = (
                    f"warning: no user_id was given, stored under the server default scope {described}. "
                    "Pass user_id (and app_id) or connect via /mcp/{app_id}/http/{user_id} to pin the scope."
                )
        result = _text_result(add_memories(payload))
        if scope_warning:
            result["content"].append({"type": "text", "text": scope_warning})
        return result
    if name == "add_memories":
        scope = _require_openmemory_scope(args, context)
        text = args.get("text")
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        metadata = dict(args.get("metadata") or {})
        metadata.setdefault("source_app", "openmemory")
        metadata.setdefault("mcp_client", scope["app_id"])
        return _text_result(
            add_memories(
                {
                    "messages": [{"role": "user", "content": str(text)}],
                    "user_id": scope["user_id"],
                    "app_id": scope["app_id"],
                    "metadata": metadata,
                    "infer": args.get("infer", True),
                    "source_role": "assistant",
                }
            )
        )
    if name == "search_memories":
        _reject_unknown_args(name, args)
        _validate_search_params(args)
        return _text_result(search_memories({**args, "filters": _mcp_scoped_filters(args, context)}))
    if name == "search_memory":
        _reject_unknown_args(name, args)
        scope = _require_openmemory_scope(args, context)
        query = args.get("query")
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        _validate_search_params(args)
        return _text_result(
            search_memories(
                {
                    "query": str(query),
                    "filters": _mcp_scoped_filters({**args, "filters": scope}, context),
                    "top_k": args.get("limit") or args.get("top_k") or 10,
                    "threshold": args.get("threshold", 0),
                }
            )
        )
    if name == "judge_memory":
        payload = dict(args)
        if "messages" not in payload and "facts" not in payload:
            text = payload.pop("text", None)
            if not text:
                raise HTTPException(status_code=400, detail="messages, facts, or text is required")
            payload["messages"] = [{"role": "user", "content": str(text)}]
        return _text_result(judge_memories(payload))
    if name == "assemble_context":
        _validate_search_params(args)
        assembled = assemble_context({**args, "filters": _mcp_scoped_filters(args, context)})
        if _mcp_context_compact_requested(args):
            return _text_result(_compact_context_capsule(assembled))
        return _text_result(assembled)
    if name == "prepare_context_autopilot":
        _validate_search_params(args)
        return _text_result(prepare_context_autopilot({**args, "filters": _mcp_scoped_filters(args, context)}))
    if name == "record_task_state":
        payload = {**args, "filters": _mcp_scoped_filters(args, context)}
        return _text_result(record_task_state(payload))
    if name == "record_context_observation":
        return _text_result(record_context_observation(args))
    if name == "record_context_outcome":
        return _text_result(record_context_outcome(args))
    if name == "get_task_state":
        payload = {**args, "filters": _mcp_scoped_filters(args, context)}
        return _text_result(get_task_state(payload))
    if name == "verify_context_evidence":
        return _text_result(verify_context_evidence(args))
    if name == "verify_judgment_evidence":
        return _text_result(verify_judgment_evidence(args))
    if name == "verify_memory_claims":
        return _text_result(verify_memory_claims(args))
    if name == "create_claim_evaluation":
        return _text_result(create_claim_evaluation(args))
    if name == "create_summary":
        _validate_search_params(args)
        return _text_result(create_summary({**args, "filters": _mcp_scoped_filters(args, context)}))
    if name == "list_summaries":
        return _text_result(list_summaries(limit=args.get("limit", 100)))
    if name == "get_summary":
        return _text_result(get_summary(args["summary_id"]))
    if name == "get_memories":
        return _text_result(get_memories(_mcp_scoped_filters(args, context), args.get("page", 1), args.get("page_size", 100)))
    if name == "list_memories":
        scope = _require_openmemory_scope(args, context)
        return _text_result(get_memories(scope, args.get("page", 1), args.get("page_size", 100)))
    if name == "get_memory":
        return _text_result(get_memory(args["memory_id"]))
    if name == "update_memory":
        memory_id = args.pop("memory_id")
        return _text_result(update_memory(memory_id, args))
    if name == "review_stale_candidates":
        scoped = {k: args[k] for k in ("top_n", "min_similarity", "min_days") if k in args}
        scoped["filters"] = _mcp_scoped_filters(args, context)
        return _text_result(stale_candidate_pairs(scoped))
    if name == "confirm_memory":
        memory_id = str(args.get("memory_id") or "")
        if not memory_id:
            raise HTTPException(status_code=400, detail="memory_id is required")
        return _text_result(confirm_memory(memory_id, args))
    if name == "supersede_memory":
        memory_id = args.pop("memory_id")
        return _text_result(supersede_memory(memory_id, args))
    if name == "delete_memory":
        return _text_result(delete_memory(args["memory_id"]))
    if name == "delete_memories":
        memory_ids = args.get("memory_ids") or []
        if not isinstance(memory_ids, list) or not memory_ids:
            raise HTTPException(status_code=400, detail="memory_ids must be a non-empty list")
        deleted = [delete_memory(str(memory_id)) for memory_id in memory_ids]
        return _text_result({"deleted_count": len(deleted), "results": deleted})
    if name == "delete_all_memories":
        return _text_result(delete_memories(_mcp_scoped_filters(args, context)))
    if name == "delete_entities":
        return _text_result(delete_memories(_entity_filter(args["entity_type"], args["entity_id"])))
    if name == "list_entities":
        return _text_result(list_entities_payload())
    if name == "list_events":
        return _text_result(list_events(args.get("page", 1), args.get("page_size", 100)))
    if name == "get_event_status":
        return _text_result(get_event(args["event_id"]))
    raise HTTPException(status_code=404, detail=f"Unknown tool: {name}")


def rpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


# Everyday agent surface: memory CRUD, context assembly, the outcome loop,
# summaries, and the hook's task-state tools. The other ~18 tools (provider
# ops, LoRA plans, judgment/evidence internals, entities, events) cost every
# session ~2k tokens of schema for calls an agent almost never makes — they
# stay available under profile=full.
_CORE_TOOL_NAMES = {
    "get_mem1_capabilities",
    "add_memory",
    "add_memories",
    "search_memory",
    "search_memories",
    "get_memory",
    "get_memories",
    "list_memories",
    "update_memory",
    "supersede_memory",
    "confirm_memory",
    "review_stale_candidates",
    "delete_memory",
    "delete_memories",
    "delete_all_memories",
    "assemble_context",
    "prepare_context_autopilot",
    "record_context_outcome",
    "record_context_observation",
    "record_task_state",
    "get_task_state",
    "create_summary",
    "get_summary",
    "list_summaries",
}


def tools_for_profile(profile: str | None = None) -> list[dict[str, Any]]:
    resolved = str(profile or os.getenv("MEM1_MCP_TOOL_PROFILE") or "full").strip().lower()
    if resolved == "core":
        return [tool for tool in TOOLS if tool["name"] in _CORE_TOOL_NAMES]
    return TOOLS


def handle_mcp_rpc(payload: dict[str, Any], context: dict[str, str] | None = None) -> dict[str, Any] | None:
    method = payload.get("method")
    request_id = payload.get("id")
    params = payload.get("params") or {}
    try:
        if method == "initialize":
            return rpc_result(
                request_id,
                {
                    "protocolVersion": params.get("protocolVersion") or "2025-06-18",
                    "serverInfo": {"name": "forget-mcp", "version": __version__},
                    "capabilities": {"tools": {"listChanged": False}},
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return rpc_result(request_id, {})
        if method == "tools/list":
            return rpc_result(request_id, {"tools": tools_for_profile((context or {}).get("tool_profile"))})
        if method == "tools/call":
            return rpc_result(request_id, call_tool(params.get("name"), params.get("arguments") or {}, context=context))
        return rpc_error(request_id, -32601, f"Method not found: {method}")
    except HTTPException as exc:
        return rpc_error(request_id, -32000, str(exc.detail))
    except Exception as exc:
        return rpc_error(request_id, -32603, str(exc))
