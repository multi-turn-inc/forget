from __future__ import annotations

import difflib
import hashlib
import hmac
import importlib.util
import os
import re
import sqlite3
import shutil
import time
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote

import httpx
from fastapi import HTTPException, Request

from .ports import enforce_project_quota
from . import hybrid_workspace, scope_guard
from .db import get_db, json_dumps, json_loads
from .memory_engine import (
    categorize,
    cosine_similarity,
    deterministic_embedding,
    extract_linked_entities,
    keyword_overlap_score,
    low_value_memory_reason,
    normalize_entity,
    rerank_score,
    score_memory,
)
from .providers import (
    embed_text,
    extract_facts,
    generate_action_hint_targets,
    get_project_settings,
    record_usage,
    rerank_memory_results,
    token_estimate,
    update_project_settings,
    usage_summary,
)
from .policy_dataset import build_sft_dataset
from .ports import project_org_id, session_context_for_token, validate_csrf_for_cookie_request
from .utils import ENTITY_FIELDS, content_hash, decode_embedding, encode_embedding, new_id, parse_datetime, utc_now
from .vector_adapters import vector_delete_memory, vector_search_memories, vector_upsert_memory


CURRENT_PROJECT_ID: ContextVar[str] = ContextVar("mem1_project_id", default="proj_local")
CURRENT_AUTH_CONTEXT: ContextVar[dict[str, Any]] = ContextVar(
    "mem1_auth_context",
    default={"actor_type": "anonymous", "project_id": "proj_local", "org_id": "org_local", "is_operator": False},
)
FINE_TUNING_JOB_SCHEMA_VERSION = "mem1-fine-tuning-job-v1"
MODEL_ARTIFACT_SCHEMA_VERSION = "mem1-model-artifact-v1"
MODEL_ADAPTER_PROMOTION_REPORT_SCHEMA_VERSION = "mem1-model-adapter-promotion-report-v1"
MODEL_ADAPTER_COMPARISON_SCHEMA_VERSION = "mem1-model-adapter-comparison-v1"


def _server_version() -> str:
    try:
        from . import __version__

        return str(__version__)
    except Exception:
        return ""


def current_project_id() -> str:
    return CURRENT_PROJECT_ID.get() or "proj_local"


def set_current_project_id(project_id: str) -> None:
    CURRENT_PROJECT_ID.set(project_id or "proj_local")


def current_auth_context() -> dict[str, Any]:
    return CURRENT_AUTH_CONTEXT.get()


def _auth_cookie_tokens(request: Request) -> list[str]:
    tokens: list[str] = []
    for part in request.headers.get("cookie", "").split(";"):
        if "=" not in part:
            continue
        name, value = part.strip().split("=", 1)
        if name not in {"mem1_session", "mem1_access_token"} or not value:
            continue
        token = unquote(value.strip().strip('"'))
        if token and token not in tokens:
            tokens.append(token)
    for name in ("mem1_session", "mem1_access_token"):
        token = request.cookies.get(name)
        if token and token not in tokens:
            tokens.append(str(token))
    return tokens


def set_current_auth_context(context: dict[str, Any]) -> None:
    CURRENT_AUTH_CONTEXT.set(context)


def row_to_memory(row: Any, include_entities: bool = True, score: float | None = None) -> dict[str, Any]:
    metadata = json_loads(row["metadata"], {})
    item = {
        "id": row["id"],
        "memory": row["memory"],
        "metadata": metadata,
        "categories": json_loads(row["categories"], []),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "expiration_date": metadata.get("expiration_date"),
        "immutable": metadata.get("immutable") is True,
    }
    if include_entities:
        item.update(
            {
                "project_id": row["project_id"] if "project_id" in row.keys() else "proj_local",
                "user_id": row["user_id"],
                "agent_id": row["agent_id"],
                "app_id": row["app_id"],
                "run_id": row["run_id"],
                "hash": row["hash"],
            }
        )
    if score is not None:
        item["score"] = score
    if "embedding" in row.keys():
        item["_embedding"] = decode_embedding(row["embedding"])
    return item


def require_auth(request: Request) -> str:
    require = os.getenv("MEM1_REQUIRE_AUTH", "false").lower() in {"1", "true", "yes"}
    expected = os.getenv("MEM1_API_KEY", "m0-local-dev-key")
    header = request.headers.get("authorization", "")
    requested_project_id = request.path_params.get("project_id")
    requested_org_id = request.path_params.get("org_id")
    project_id = "proj_local"
    context: dict[str, Any] = {
        "actor_type": "anonymous",
        "project_id": project_id,
        "org_id": requested_org_id or "org_local",
        "is_operator": False,
    }
    if header.startswith("Token ") or header.startswith("Bearer "):
        token = header.split(" ", 1)[1].strip()
        if token == expected:
            project_id = str(requested_project_id or "proj_local")
            context = {
                "actor_type": "operator",
                "project_id": project_id,
                "org_id": requested_org_id or project_org_id(project_id) or "org_local",
                "role": "operator",
                "is_operator": True,
            }
        else:
            with get_db() as conn:
                row = conn.execute(
                    """
                    SELECT p.project_id, p.org_id, '' AS owner_user_id, 'project' AS credential_type
                      FROM projects p
                     WHERE p.api_key = ?
                    UNION ALL
                    SELECT ak.project_id, p.org_id, ak.owner_user_id, 'api_key' AS credential_type
                      FROM api_keys ak
                      JOIN projects p ON p.project_id = ak.project_id
                     WHERE ak.api_key = ?
                       AND ak.is_active = 1
                     LIMIT 1
                    """,
                    (token, token),
                ).fetchone()
            if row:
                project_id = row["project_id"]
                org_id = row["org_id"]
                if requested_project_id and requested_project_id != project_id:
                    raise HTTPException(status_code=403, detail="Project access denied")
                if requested_org_id and requested_org_id != org_id:
                    raise HTTPException(status_code=403, detail="Organization access denied")
                context = {
                    "actor_type": row["credential_type"],
                    "project_id": project_id,
                    "org_id": org_id,
                    "user_id": row["owner_user_id"] or None,
                    "role": "api_key",
                    "is_operator": False,
                }
            else:
                session_context = session_context_for_token(token, requested_project_id, requested_org_id)
                if session_context is None:
                    raise HTTPException(status_code=401, detail="Unauthorized")
                context = session_context
                project_id = str(context.get("project_id") or requested_project_id or "proj_local")
    else:
        cookie_tokens = _auth_cookie_tokens(request)
        if cookie_tokens:
            session_context = None
            for cookie_token in cookie_tokens:
                session_context = session_context_for_token(cookie_token, requested_project_id, requested_org_id)
                if session_context is not None:
                    break
            if session_context is None:
                raise HTTPException(status_code=401, detail="Unauthorized")
            validate_csrf_for_cookie_request(request)
            context = session_context
            project_id = str(context.get("project_id") or requested_project_id or "proj_local")
        elif require:
            raise HTTPException(status_code=401, detail="Unauthorized")
        else:
            if requested_project_id:
                project_id = str(requested_project_id)
            context = {
                "actor_type": "anonymous",
                "project_id": project_id,
                "org_id": requested_org_id or project_org_id(project_id) or "org_local",
                "is_operator": False,
            }
    set_current_project_id(project_id)
    set_current_auth_context(context)
    request.state.auth_context = context
    request.state.project_id = project_id
    request.state.org_id = context.get("org_id")
    request.state.user_id = context.get("user_id")
    request.state.actor_type = context.get("actor_type")
    return project_id


def api_key_payload(row: Any, include_key: bool = False) -> dict[str, Any]:
    item = {
        "id": row["id"],
        "project_id": row["project_id"],
        "owner_user_id": row["owner_user_id"] if "owner_user_id" in row.keys() else "",
        "name": row["name"],
        "label": row["name"],
        "key_prefix": row["key_prefix"],
        "masked_key": f"{row['key_prefix']}...",
        "scopes": json_loads(row["scopes"], []) if "scopes" in row.keys() else [],
        "created_by_role": row["created_by_role"] if "created_by_role" in row.keys() else "operator",
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
        "revoked_at": row["revoked_at"],
    }
    if include_key:
        item["api_key"] = row["api_key"]
        item["key"] = row["api_key"]
    return item


def list_api_keys(project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM api_keys
             WHERE project_id = ?
             ORDER BY created_at DESC
            """,
            (project_id,),
        ).fetchall()
    return {"project_id": project_id, "count": len(rows), "results": [api_key_payload(row) for row in rows]}


def create_api_key(
    payload: dict[str, Any],
    project_id: str | None = None,
    owner_user_id: str | None = None,
    created_by_role: str = "operator",
) -> dict[str, Any]:
    project_id = payload.get("project_id") or project_id or current_project_id()
    key = f"m0sk_{str(new_id()).replace('-', '')}"
    scopes = payload.get("scopes") if isinstance(payload.get("scopes"), list) else ["project:read", "memory:read", "memory:write"]
    item = {
        "id": str(new_id("key")),
        "project_id": project_id,
        "owner_user_id": owner_user_id or str(payload.get("owner_user_id") or ""),
        "name": str(payload.get("name") or payload.get("label") or "API key"),
        "api_key": key,
        "key_prefix": key[:12],
        "scopes": scopes,
        "created_by_role": created_by_role,
        "is_active": 1,
        "created_at": utc_now(),
        "revoked_at": None,
    }
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO api_keys (
                id, project_id, owner_user_id, name, api_key, key_prefix, scopes,
                created_by_role, is_active, created_at, revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                item["project_id"],
                item["owner_user_id"],
                item["name"],
                item["api_key"],
                item["key_prefix"],
                json_dumps(item["scopes"]),
                item["created_by_role"],
                item["is_active"],
                item["created_at"],
                item["revoked_at"],
            ),
        )
        row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (item["id"],)).fetchone()
    return api_key_payload(row, include_key=True)


def revoke_api_key(key_id: str, project_id: str | None = None) -> dict[str, str]:
    project_id = project_id or current_project_id()
    now = utc_now()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM api_keys WHERE id = ? AND project_id = ?", (key_id, project_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="API key not found")
        conn.execute(
            "UPDATE api_keys SET is_active = 0, revoked_at = ? WHERE id = ? AND project_id = ?",
            (now, key_id, project_id),
        )
    return {"message": "API key revoked successfully!"}


def has_entity_filter(filters: Any) -> bool:
    if not isinstance(filters, dict):
        return False
    for key, value in filters.items():
        if key in ENTITY_FIELDS:
            return True
        if key in {"AND", "OR"} and isinstance(value, list) and any(has_entity_filter(v) for v in value):
            return True
        if key == "NOT":
            if isinstance(value, list) and any(has_entity_filter(v) for v in value):
                return True
            if isinstance(value, dict) and has_entity_filter(value):
                return True
    return False


FILTER_LOGICAL_KEYS = ("AND", "OR", "NOT")
# Task-state routing keys read from filters by get_task_state / workspace paths.
FILTER_TASK_KEYS = ("task_id", "goal_id", "task_phase", "phase")
# Directly queryable memory fields (see row_to_memory / _value_for_field).
FILTER_FIELD_KEYS = (
    "id",
    "memory",
    "hash",
    "categories",
    "created_at",
    "updated_at",
    "expiration_date",
    "immutable",
    "project_id",
    "metadata",
)
ALLOWED_FILTER_KEYS = frozenset(ENTITY_FIELDS) | frozenset(FILTER_TASK_KEYS) | frozenset(FILTER_FIELD_KEYS)
FILTER_COMPARE_OPS = ("in", "contains", "icontains", "ne", "gte", "lte", "gt", "lt")
FILTER_CONTRACT_SUMMARY = (
    "valid keys: "
    + ", ".join(sorted(ALLOWED_FILTER_KEYS))
    + ", metadata.<path>; logical operators: "
    + ", ".join(FILTER_LOGICAL_KEYS)
)


def _filter_key_hint(key: str) -> str:
    if key == "scope":
        return " 'scope' is not a filter key; scope by entity id instead (user_id, agent_id, app_id, run_id)."
    normalized = key.lower().replace("_", "")
    for allowed in sorted(ALLOWED_FILTER_KEYS):
        if allowed.replace("_", "") == normalized:
            return f" Did you mean '{allowed}'?"
    close = difflib.get_close_matches(key.lower(), sorted(ALLOWED_FILTER_KEYS), n=1, cutoff=0.8)
    if close:
        return f" Did you mean '{close[0]}'?"
    return ""


def validate_filters(filters: Any, _path: str = "filters") -> None:
    """Reject unknown filter keys/operators instead of silently matching nothing.

    An unrecognized key falls through to a memory-field lookup that no row
    satisfies, so the primary scope quietly matches zero memories and — with
    scope_fallback enabled — every result degrades to discounted fallback hits
    (observed 2026-07-04 over MCP with filters={"scope": "user"}).
    """
    if filters is None:
        return
    if not isinstance(filters, dict):
        raise HTTPException(status_code=400, detail=f"{_path} must be an object")
    for key, value in filters.items():
        if key in {"AND", "OR"}:
            if not isinstance(value, list) or not value:
                raise HTTPException(
                    status_code=400,
                    detail=f"{_path}.{key} must be a non-empty list of filter objects",
                )
            for index, part in enumerate(value):
                validate_filters(part, f"{_path}.{key}[{index}]")
            continue
        if key == "NOT":
            parts = value if isinstance(value, list) else [value]
            for index, part in enumerate(parts):
                validate_filters(part, f"{_path}.NOT[{index}]")
            continue
        if key not in ALLOWED_FILTER_KEYS and not key.startswith("metadata."):
            raise HTTPException(
                status_code=400,
                detail=f"Unknown filter key '{key}' in {_path}.{_filter_key_hint(key)} {FILTER_CONTRACT_SUMMARY}",
            )
        if isinstance(value, dict):
            for op in value:
                if op in FILTER_COMPARE_OPS:
                    continue
                if key == "metadata":
                    detail = (
                        f"Unknown operator '{op}' for {_path}.metadata. Filter nested fields with dotted"
                        f" paths (e.g. metadata.{op}) or use operators: {', '.join(FILTER_COMPARE_OPS)}"
                    )
                else:
                    detail = f"Unknown operator '{op}' for {_path}.{key}. Valid operators: {', '.join(FILTER_COMPARE_OPS)}"
                raise HTTPException(status_code=400, detail=detail)
        elif isinstance(value, list):
            raise HTTPException(
                status_code=400,
                detail=f"{_path}.{key} takes a scalar, '*', or an operator object; to match any of several values use {{\"in\": [...]}}",
            )


def _value_for_field(memory: dict[str, Any], field: str) -> Any:
    if field.startswith("metadata."):
        value: Any = memory.get("metadata", {})
        for part in field.split(".")[1:]:
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value
    return memory.get(field)


def _list_payload_value(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _metadata_from_add_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_metadata = payload.get("metadata") or {}
    metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
    categories = _list_payload_value(payload.get("categories") or payload.get("category_ids"))
    if categories and not metadata.get("categories"):
        metadata["categories"] = categories
    if "immutable" in payload and "immutable" not in metadata:
        metadata["immutable"] = bool(payload.get("immutable"))
    expiration = payload.get("expiration_date") or payload.get("expires")
    if expiration and "expiration_date" not in metadata:
        metadata["expiration_date"] = str(expiration)
    return metadata


def memory_is_expired(memory: dict[str, Any]) -> bool:
    metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
    expiration = memory.get("expiration_date") or metadata.get("expiration_date")
    expiration_at = parse_datetime(expiration)
    now = parse_datetime(utc_now())
    return bool(expiration_at and now and expiration_at <= now)


def _compare(actual: Any, expected: Any) -> bool:
    if expected == "*":
        return actual not in (None, "", [])
    if isinstance(expected, dict):
        for op, value in expected.items():
            if op == "in":
                values = value if isinstance(value, list) else [value]
                if isinstance(actual, list):
                    if not any(item in values for item in actual):
                        return False
                elif actual not in values:
                    return False
            elif op in {"contains", "icontains"}:
                needle = str(value)
                if isinstance(actual, list):
                    haystack = [str(v) for v in actual]
                    if op == "icontains":
                        needle = needle.lower()
                        haystack = [v.lower() for v in haystack]
                    if not any(needle in v for v in haystack):
                        return False
                else:
                    haystack = str(actual or "")
                    if op == "icontains":
                        needle = needle.lower()
                        haystack = haystack.lower()
                    if needle not in haystack:
                        return False
            elif op == "ne":
                if actual == value:
                    return False
            elif op in {"gte", "lte", "gt", "lt"}:
                left_dt = parse_datetime(actual)
                right_dt = parse_datetime(value)
                if left_dt and right_dt:
                    left, right = left_dt, right_dt
                else:
                    left, right = actual, value
                try:
                    if op == "gte" and not (left >= right):
                        return False
                    if op == "lte" and not (left <= right):
                        return False
                    if op == "gt" and not (left > right):
                        return False
                    if op == "lt" and not (left < right):
                        return False
                except TypeError:
                    return False
            else:
                return False
        return True
    if isinstance(actual, list):
        return expected in actual
    return actual == expected


def matches_filters(memory: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    for key, expected in filters.items():
        if key == "AND":
            if not isinstance(expected, list) or not all(matches_filters(memory, part) for part in expected):
                return False
        elif key == "OR":
            if not isinstance(expected, list) or not any(matches_filters(memory, part) for part in expected):
                return False
        elif key == "NOT":
            if isinstance(expected, list):
                if any(matches_filters(memory, part) for part in expected):
                    return False
            elif matches_filters(memory, expected):
                return False
        else:
            if not _compare(_value_for_field(memory, key), expected):
                return False
    return True


def list_memory_dicts(
    include_deleted: bool = False,
    project_id: str | None = None,
    include_expired: bool = False,
    entity_prefilter: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        sql = "SELECT * FROM memories WHERE project_id = ?"
        params: list[Any] = [project_id]
        if not include_deleted:
            sql += " AND deleted = 0"
        if entity_prefilter:
            # Candidate-narrowing superset of (primary match ∪ scope-fallback
            # eligibility): rows matching every requested entity, plus shared
            # rows (no user_id) which fallback may surface. Final filtering
            # stays in Python (matches_filters / _scope_fallback_eligible),
            # so this only prunes rows that could never qualify.
            equality = " AND ".join(f"{field} = ?" for field in entity_prefilter)
            sql += f" AND (({equality}) OR user_id IS NULL OR user_id = '')"
            params.extend(entity_prefilter.values())
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, params).fetchall()
    memories = [row_to_memory(row) for row in rows]
    if include_expired:
        return memories
    return [memory for memory in memories if not memory_is_expired(memory)]


def _batch_cosine_scores(query_embedding: list[float], candidates: list[dict[str, Any]]) -> dict[str, float]:
    """Vectorized cosine over stored embeddings of the same dimension as the
    query. Produces bit-for-bit the same rounded score as cosine_similarity
    ((cos + 1) / 2, rounded to 4, clamped); rows without a matching-dimension
    embedding are left out so the caller falls back to the scalar path."""
    try:
        import numpy as np
    except ImportError:
        return {}
    if not query_embedding or len(candidates) < 64:
        return {}
    dim = len(query_embedding)
    ids: list[str] = []
    rows: list[list[float]] = []
    for memory in candidates:
        embedding = memory.get("_embedding")
        if isinstance(embedding, list) and len(embedding) == dim:
            ids.append(memory["id"])
            rows.append(embedding)
    if not rows:
        return {}
    matrix = np.asarray(rows, dtype=np.float64)
    query = np.asarray(query_embedding, dtype=np.float64)
    query_norm = float(np.linalg.norm(query)) or 1.0
    norms = np.linalg.norm(matrix, axis=1)
    norms[norms == 0.0] = 1.0
    cosines = (matrix @ query) / (norms * query_norm)
    scores = np.clip(np.round((cosines + 1.0) / 2.0, 4), 0.0, 1.0)
    return dict(zip(ids, scores.tolist()))


def _simple_entity_prefilter(filters: dict[str, Any] | None) -> dict[str, str] | None:
    """Return an entity->value map when filters use only flat entity
    equality (the overwhelmingly common shape), else None to keep the
    unpruned full-project scan for complex filter trees."""
    if not isinstance(filters, dict) or not filters:
        return None
    prefilter: dict[str, str] = {}
    for key, value in filters.items():
        if key not in ENTITY_FIELDS or not isinstance(value, str) or not value:
            return None
        prefilter[key] = value
    return prefilter or None


def _scope_variants(payload: dict[str, Any]) -> list[dict[str, str | None]]:
    # 결합 스코프는 결합된 채로 저장한다 (#6): user_id와 agent_id를 함께 준 add는
    # 한 레코드가 양쪽 ID를 다 갖는다 — 같은 payload로 한 conjunctive 검색이
    # 그 레코드를 되찾는다. (참가자 이름 기반 분기는 _message_scope_variants 소관.)
    base = {field: payload.get(field) for field in ENTITY_FIELDS}
    if base.get("user_id") or base.get("agent_id"):
        variant: dict[str, str | None] = {field: None for field in ENTITY_FIELDS}
        variant["user_id"] = base.get("user_id")
        variant["agent_id"] = base.get("agent_id")
        variant["app_id"] = base.get("app_id")
        variant["run_id"] = base.get("run_id")
        return [variant]
    variants: list[dict[str, str | None]] = []
    for primary in ("app_id", "run_id"):
        if base.get(primary):
            variant = {field: None for field in ENTITY_FIELDS}
            variant[primary] = base[primary]
            variants.append(variant)
    return variants


def _participant_entity_id(name: Any) -> str | None:
    normalized = re.sub(r"\s+", "_", str(name or "").strip().lower())
    return normalized or None


def _message_scope_variants(payload: dict[str, Any], message: dict[str, Any]) -> list[dict[str, str | None]]:
    name = str(message.get("name") or "").strip()
    if not name:
        return _scope_variants(payload)

    entity_id = _participant_entity_id(name)
    if not entity_id:
        return _scope_variants(payload)

    role = str(message.get("role", "user")).lower()
    scope: dict[str, str | None] = {field: None for field in ENTITY_FIELDS}
    if role in {"assistant", "agent"}:
        scope["agent_id"] = entity_id
    else:
        scope["user_id"] = entity_id
    scope["app_id"] = payload.get("app_id")
    scope["run_id"] = payload.get("run_id")
    return [scope]


def _fact_records(
    payload: dict[str, Any],
    project_id: str,
    infer: bool,
    gate_log: list[dict[str, Any]] | None = None,
    accounting: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    messages = payload["messages"]
    custom_instructions = payload.get("custom_instructions")
    extraction_policy = payload.get("extraction_policy")
    # an add scoped to an agent entity records that agent's own voice, so
    # assistant messages are the observation subject, not answer-model noise
    assistant_is_subject = bool(payload.get("agent_id"))
    if not any(isinstance(message, dict) and str(message.get("name") or "").strip() for message in messages):
        scopes = _scope_variants(payload)
        return [
            {"fact": fact, "scopes": scopes, "input": messages, "source_role": payload.get("source_role")}
            for fact in extract_facts(
                messages,
                infer=infer,
                project_id=project_id,
                custom_instructions=custom_instructions,
                extraction_policy=extraction_policy,
                assistant_is_subject=assistant_is_subject,
                gate_log=gate_log,
                accounting=accounting,
            )
        ]

    records: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[tuple[str | None, ...], ...]]] = set()
    for message in messages:
        if not isinstance(message, dict):
            continue
        scopes = _message_scope_variants(payload, message)
        for fact in extract_facts(
            [message],
            infer=infer,
            project_id=project_id,
            custom_instructions=custom_instructions,
            extraction_policy=extraction_policy,
            assistant_is_subject=assistant_is_subject,
            gate_log=gate_log,
            accounting=accounting,
        ):
            scope_key = tuple(tuple(scope.get(field) for field in ENTITY_FIELDS) for scope in scopes)
            key = (fact.lower(), scope_key)
            if key in seen:
                if accounting is not None:
                    accounting["scope_deduped"] = accounting.get("scope_deduped", 0) + 1
                continue
            seen.add(key)
            records.append({"fact": fact, "scopes": scopes, "input": [message], "source_role": payload.get("source_role")})
    return records


RELATION_RE = re.compile(
    r"^(?P<subject>[A-Za-z][A-Za-z0-9_' -]{0,80}?)\s+"
    r"(?P<predicate>prefers|likes|loves|avoids|uses|wants|needs|works|lives|has|teaches|moved|is)\s+"
    r"(?P<detail>.+?)\.?$",
    re.IGNORECASE,
)
# Korean negation has no word boundaries usable by \b, so those patterns
# match bare. Found via incident #1's retro-scoring: "발송된 적 없음" was
# stored polarity="positive" because this regex was English-only.
NEGATION_RE = re.compile(
    r"\b(no longer|not|does not|doesn't|stopped|changed|instead)\b"
    r"|않|없(?:다|음|는|었|어|고)|아니(?:다|야|었|고|며)|못\s|안\s|말았",
    re.IGNORECASE,
)
DELETE_INTENT_RE = re.compile(r"\b(forget|delete|remove|erase)\b", re.IGNORECASE)
MERGE_PREDICATES = {"prefers", "likes", "loves", "avoids", "uses", "wants", "needs", "has"}
UPDATE_PREDICATES = {"lives", "works", "teaches", "moved", "is"}

# A claim that an action was *completed* is the dangerous class: agents act on
# it in the real world (send the follow-up, skip the "already done" step). When
# such a claim comes from an agent-side summary rather than the user or a tool,
# it must not read as settled fact — plans routinely get recorded as done.
ACTION_COMPLETION_RE = re.compile(
    r"(?:발송|전송|제출|송부|배포|출시|런칭|등록|생성|작성|삭제|머지|커밋|푸시|결제|예약|신청|완료)(?:했|됐|함|됨|\b)"
    r"|(?:보냈|보냄|마쳤|끝냈|올렸|만들었|지웠|고쳤|합쳤)"
    r"|\b(?:sent|submitted|shipped|deployed|launched|merged|committed|pushed|filed|emailed|paid|booked|completed|finished|done)\b",
    re.IGNORECASE,
)


def _action_completion(fact: str) -> bool:
    return bool(ACTION_COMPLETION_RE.search(str(fact or "")))


def _memory_trust(source_role: str, fact: str) -> dict[str, str]:
    light = "green" if source_role in ("user", "tool") else "yellow"
    kind = "action_report" if _action_completion(fact) else "fact"
    trust = {"light": light, "source": source_role, "kind": kind}
    if light == "yellow" and kind == "action_report":
        trust["note"] = "unverified action claim from an agent-side summary — confirm with the user before acting on it"
    return trust


def _fact_relation(text: str) -> dict[str, str] | None:
    match = RELATION_RE.match(str(text or "").strip())
    if not match:
        return None
    return {
        "subject": re.sub(r"\s+", " ", match.group("subject").strip()).lower(),
        "predicate": match.group("predicate").strip().lower(),
        "detail": match.group("detail").strip(" ."),
    }


def _claim_scope(scope: dict[str, Any]) -> dict[str, Any]:
    return {field: scope.get(field) for field in ENTITY_FIELDS}


def _claim_source_role(record: dict[str, Any]) -> str:
    # An explicit declaration wins: MCP text-writes are agent-authored even
    # though they arrive wrapped as role "user" for extraction compatibility.
    declared = str(record.get("source_role") or "").strip().lower() if isinstance(record, dict) else ""
    if declared in {"user", "assistant", "tool", "system", "imported"}:
        return declared
    messages = record.get("input") if isinstance(record, dict) else []
    roles = {
        str(message.get("role") or "").strip().lower()
        for message in messages
        if isinstance(message, dict)
    }
    roles.discard("")
    if not roles:
        return "inferred"
    if roles <= {"user", "human"}:
        return "user"
    if roles <= {"assistant", "agent"}:
        return "assistant"
    if roles.intersection({"tool", "function"}):
        return "tool"
    if roles == {"system"}:
        return "system"
    if roles.intersection({"user", "human"}):
        return "user"
    return "mixed"


def _claim_authority(source_role: str) -> str:
    return {
        "user": "explicit_user",
        "assistant": "assistant_action",
        "tool": "authoritative_tool_state",
        "system": "operator_approved",
        "imported": "inferred",
    }.get(source_role, "inferred")


def _claim_confidence(source_role: str) -> float:
    return {
        "user": 0.9,
        "tool": 0.92,
        "assistant": 0.78,
        "system": 0.8,
    }.get(source_role, 0.7)


def _claim_actor(scope: dict[str, Any]) -> tuple[str, str]:
    for field, actor_type in (
        ("user_id", "user"),
        ("agent_id", "agent"),
        ("app_id", "app"),
        ("run_id", "run"),
    ):
        if scope.get(field):
            return str(scope[field]), actor_type
    return "", ""


def _claim_shape(fact: str, scope: dict[str, Any]) -> dict[str, Any]:
    relation = _fact_relation(fact)
    if relation:
        predicate = relation["predicate"]
        if predicate in {"prefers", "likes", "loves", "avoids"}:
            assertion_kind = "preference"
        elif predicate in {"wants", "needs"}:
            assertion_kind = "intent"
        elif predicate in UPDATE_PREDICATES:
            assertion_kind = "state"
        else:
            assertion_kind = "fact"
        return {
            "subject_key": normalize_entity(relation["subject"]) or "memory",
            "predicate_key": predicate,
            "object_value": {"text": fact, "detail": relation["detail"]},
            "assertion_kind": assertion_kind,
        }
    subject = next((str(scope.get(field)) for field in ENTITY_FIELDS if scope.get(field)), "memory")
    return {
        "subject_key": subject,
        "predicate_key": "memory",
        "object_value": {"text": fact},
        "assertion_kind": "fact",
    }


def _write_observation_and_claim(
    conn: Any,
    *,
    project_id: str,
    source_event_id: str,
    memory_id: str,
    fact: str,
    record: dict[str, Any],
    scope: dict[str, Any],
    metadata: dict[str, Any],
    now: str,
) -> None:
    source_role = _claim_source_role(record)
    authority = _claim_authority(source_role)
    actor_id, actor_type = _claim_actor(scope)
    claim_scope = _claim_scope(scope)
    observation_id = str(new_id())
    payload = {
        "input": record.get("input", []),
        "metadata": metadata,
        "scope": claim_scope,
    }
    source_hash = hashlib.sha256(
        json_dumps(
            {
                "source_event_id": source_event_id,
                "memory_id": memory_id,
                "content": fact,
                "payload": payload,
            }
        ).encode("utf-8")
    ).hexdigest()
    conn.execute(
        """
        INSERT INTO observation_events (
            id, project_id, tenant_id, source_event_id, memory_id, source_role,
            actor_id, actor_type, scope, content, payload, source_hash,
            observed_at, recorded_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            observation_id,
            project_id,
            "local",
            source_event_id,
            memory_id,
            source_role,
            actor_id,
            actor_type,
            json_dumps(claim_scope),
            fact,
            json_dumps(payload),
            source_hash,
            now,
            utc_now(),
            now,
        ),
    )
    shape = _claim_shape(fact, scope)
    # "asserted" is reserved for claims whose source can vouch for them (the
    # user said it, a tool observed it). An agent-side report that an action
    # was completed is testimony, not observation — it stays "reported" until
    # evidence closes it.
    modality = "reported" if source_role not in ("user", "tool") and _action_completion(fact) else "asserted"
    conn.execute(
        """
        INSERT INTO claims (
            id, project_id, tenant_id, memory_id, claim_text, scope,
            subject_key, predicate_key, object_value, assertion_kind,
            polarity, modality, valid_from, valid_to, observed_at,
            recorded_at, retired_at, status, supersedes_claim_ids,
            contradicts_claim_ids, source_event_ids, source_hashes,
            source_role, authority, confidence, sensitivity,
            retention_policy, policy_version, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(new_id()),
            project_id,
            "local",
            memory_id,
            fact,
            json_dumps(claim_scope),
            shape["subject_key"],
            shape["predicate_key"],
            json_dumps(shape["object_value"]),
            shape["assertion_kind"],
            "negative" if NEGATION_RE.search(fact) else "positive",
            modality,
            now,
            None,
            now,
            utc_now(),
            None,
            "active",
            "[]",
            "[]",
            json_dumps([observation_id]),
            json_dumps([source_hash]),
            source_role,
            authority,
            _claim_confidence(source_role),
            str(metadata.get("sensitivity") or "normal"),
            str(metadata.get("retention_policy") or "default"),
            "claim-model-v1",
            now,
            now,
        ),
    )


def _requested_project(payload: dict[str, Any], filters: dict[str, Any]) -> str:
    """The project key a task-state call carries, if any.

    Accepted as a top-level `project` arg, `metadata.project`, or a scalar
    metadata.project filter. The layered OR that memory recall uses is
    deliberately NOT parsed here — its compat branches (untagged, global)
    have memory-recall semantics; task calls say `project` explicitly.
    """
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    value = payload.get("project") or metadata.get("project") or filters.get("metadata.project")
    return str(value).strip() if isinstance(value, str) and value.strip() else ""


def _task_state_scope(payload: dict[str, Any]) -> dict[str, Any]:
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    scope = {field: filters.get(field) or payload.get(field) for field in ENTITY_FIELDS}
    scope = {field: value for field, value in scope.items() if value not in (None, "")}
    # Project rides in the scope blob (a free-form JSON column) so BOTH
    # storage paths — claims and workspace epochs — carry it without schema
    # surgery. It is a content boundary, not an entity: matching rules live
    # in _task_claim_scope_matches_filters.
    project = _requested_project(payload, filters)
    if project:
        scope["project"] = project
    return scope


def _task_state_id(payload: dict[str, Any]) -> str:
    raw = payload.get("task_id") or payload.get("goal_id") or payload.get("id") or "current"
    value = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", str(raw).strip().lower()).strip("-")
    return value or "current"


_TASK_ID_NAMESPACE_PREFIXES = (
    "multi-turn-memory",
    "multi-turn",
    "enacta",
    "mem1",
    "mem0",
)

_GENERIC_TASK_IDS = {"current", "default", "general", "misc", "unknown"}


def _task_state_id_aliases(task_id: str | None) -> set[str]:
    raw = str(task_id or "").strip()
    if not raw:
        return set()
    normalized = _task_state_id({"task_id": raw})
    aliases = {normalized}
    for prefix in _TASK_ID_NAMESPACE_PREFIXES:
        marker = f"{prefix}-"
        if normalized.startswith(marker):
            stripped = normalized[len(marker) :].strip("-")
            if stripped:
                aliases.add(stripped)
    return aliases


def _task_state_ids_match(expected_task_id: str | None, actual_task_id: str | None) -> bool:
    expected_aliases = _task_state_id_aliases(expected_task_id)
    actual_aliases = _task_state_id_aliases(actual_task_id)
    return bool(expected_aliases and actual_aliases and expected_aliases.intersection(actual_aliases))


def _task_state_id_is_generic(task_id: str | None) -> bool:
    normalized = _task_state_id({"task_id": task_id}) if task_id not in (None, "") else ""
    return normalized in _GENERIC_TASK_IDS


def _task_state_normalized_id(value: Any) -> str:
    return _task_state_id({"task_id": value})


def _task_state_related_ids(value: Any) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for item in _task_state_list(value):
        normalized = _task_state_normalized_id(item)
        if normalized and normalized not in seen:
            seen.add(normalized)
            ids.append(normalized)
    return ids


def _task_state_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _compact_context_list(label: str, items: list[str], max_items: int = 2) -> str:
    if len(items) <= max_items:
        return f"{label}: " + "; ".join(items)
    visible = items[:max_items] + [f"+{len(items) - max_items} more"]
    return f"{label} ({len(items)}): " + "; ".join(visible)


def _task_state_payload(payload: dict[str, Any], task_id: str, scope: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or payload.get("state") or "in_progress").strip().lower()
    status = re.sub(r"\s+", "_", status)
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    goal_id = payload.get("goal_id") or evidence.get("goal_id")
    parent_goal_id = (
        payload.get("parent_goal_id")
        or payload.get("parent_task_id")
        or evidence.get("parent_goal_id")
        or evidence.get("parent_task_id")
    )
    related_task_ids = _task_state_related_ids(
        payload.get("related_task_ids")
        or payload.get("related_tasks")
        or payload.get("related_task_id")
        or evidence.get("related_task_ids")
        or evidence.get("related_tasks")
        or evidence.get("related_task_id")
    )
    return {
        "task_id": task_id,
        "status": status or "in_progress",
        "summary": str(payload.get("summary") or payload.get("description") or payload.get("text") or "").strip(),
        "next_actions": _task_state_list(payload.get("next_actions") or payload.get("next")),
        "blockers": _task_state_list(payload.get("blockers") or payload.get("blocked_by")),
        "evidence": payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {},
        "evidence_files": _task_state_list(payload.get("evidence_files") or payload.get("files")),
        "commands": _task_state_list(payload.get("commands")),
        "scope": scope,
        "goal_id": _task_state_normalized_id(goal_id) if goal_id not in (None, "") else "",
        "parent_goal_id": _task_state_normalized_id(parent_goal_id) if parent_goal_id not in (None, "") else "",
        "related_task_ids": related_task_ids,
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }


def _task_state_claim_text(item: dict[str, Any]) -> str:
    parts = [f"Task {item['task_id']} is {item['status']}."]
    if item.get("summary"):
        parts.append(str(item["summary"]))
    if item.get("next_actions"):
        parts.append(_compact_context_list("Next", item["next_actions"]))
    if item.get("blockers"):
        parts.append("Blockers: " + "; ".join(item["blockers"]))
    if item.get("related_task_ids"):
        parts.append(_compact_context_list("Related tasks", item["related_task_ids"]))
    if item.get("evidence_files"):
        parts.append(_workspace_evidence_context(item["evidence_files"]))
    if item.get("terminal_evidence_refs"):
        parts.append(_terminal_evidence_context(item["terminal_evidence_refs"]))
    return " ".join(part for part in parts if part).strip()


def _task_claim_scope_matches_filters(scope: dict[str, Any], filters: dict[str, Any]) -> bool:
    for field in ENTITY_FIELDS:
        expected = filters.get(field)
        if expected not in (None, "") and scope.get(field) != expected:
            return False
    # Project layering, same compat rule as memory recall: a project-scoped
    # read hides only rows TAGGED with a different project. Untagged rows
    # (everything before 2026-08-01) stay visible everywhere, and a read with
    # no project sees everything — that is the explicit cross-project view.
    requested = filters.get("project")
    stored = scope.get("project")
    if requested not in (None, "") and stored not in (None, "") and stored != requested:
        return False
    return True


def _task_state_row_payload(row: Any) -> dict[str, Any]:
    item = json_loads(row["object_value"], {})
    if not isinstance(item, dict):
        item = {}
    item.setdefault("task_id", str(row["subject_key"]).removeprefix("task:"))
    item.setdefault("status", "unknown")
    item.setdefault("summary", row["claim_text"])
    item.setdefault("scope", json_loads(row["scope"], {}))
    return item


def _task_state_result_from_row(row: Any, score: float | None = None) -> dict[str, Any]:
    item = _task_state_row_payload(row)
    scope = item.get("scope") if isinstance(item.get("scope"), dict) else json_loads(row["scope"], {})
    claim_lifecycle = str(item.get("claim_lifecycle") or row["modality"] or "provisional").upper()
    memory = {
        "id": f"claim:{row['id']}",
        "claim_id": row["id"],
        "memory_id": row["memory_id"],
        "memory": _task_state_claim_text(item),
        "metadata": {
            "source": "claim_ledger",
            "assertion_kind": "task_state",
            "task_state": item,
            "claim_lifecycle": claim_lifecycle,
            "source_event_ids": json_loads(row["source_event_ids"], []),
            "source_hashes": json_loads(row["source_hashes"], []),
        },
        "categories": ["task_state", "work"],
        # Task states are agent-authored self-summaries; the traffic-light
        # contract says unlabeled reads as yellow, but relying on the default
        # makes ledger rows look like an oversight next to labeled memories.
        "trust": {
            "light": "yellow",
            "source": "assistant",
            "kind": "task_state",
            "note": "agent-recorded task ledger — verify completion claims against evidence",
        },
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "expiration_date": None,
        "immutable": True,
        "user_id": scope.get("user_id"),
        "agent_id": scope.get("agent_id"),
        "app_id": scope.get("app_id"),
        "run_id": scope.get("run_id"),
    }
    if score is not None:
        memory["score"] = score
    return memory


def _task_state_feedback_map(project_id: str) -> dict[str, dict[str, Any]]:
    """Return outcome feedback keyed by the public claim-backed result ID."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT f.memory_id, f.feedback, f.feedback_reason, f.created_at, f.metadata
              FROM feedback f
              JOIN claims c ON f.memory_id = ('claim:' || c.id)
             WHERE c.project_id = ?
            """,
            (project_id,),
        ).fetchall()
    feedbacks: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        metadata = json_loads(item.get("metadata"), {})
        item["metadata"] = metadata if isinstance(metadata, dict) else {}
        feedbacks[str(row["memory_id"])] = item
    return feedbacks


def _task_state_search_results(
    query: str,
    filters: dict[str, Any],
    project_id: str,
    top_k: int,
    threshold: float,
    as_of: str = "",
) -> list[dict[str, Any]]:
    params: list[Any] = [project_id]
    if as_of:
        where = """
             WHERE project_id = ?
               AND assertion_kind = 'task_state'
               AND recorded_at <= ?
               AND (retired_at IS NULL OR retired_at > ?)
               AND (valid_to IS NULL OR valid_to > ?)
        """
        params.extend([as_of, as_of, as_of])
    else:
        where = """
             WHERE project_id = ?
               AND assertion_kind = 'task_state'
               AND status = 'active'
        """
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM claims
            {where}
             ORDER BY updated_at DESC
             LIMIT 100
            """,
            params,
        ).fetchall()
    feedbacks = _task_state_feedback_map(project_id)
    results: list[dict[str, Any]] = []
    for row in rows:
        scope = json_loads(row["scope"], {})
        if not _task_claim_scope_matches_filters(scope, filters):
            continue
        item = _task_state_result_from_row(row)
        # No flat activeness boost: being in_progress already earns the
        # recency bonus inside score_memory, and a second additive let
        # off-topic active states ride free score over recall gates
        # (friction F2 — the Quant task shadowing devloop turns).
        # Activeness is the capsule's job; search ranks by topic.
        score = score_memory(query, item, reference_date=as_of or None)
        score = feedback_adjusted_score(score, feedbacks.get(str(item["id"])))
        if score >= threshold:
            item["score"] = score
            results.append(item)
    results.sort(key=lambda item: (item.get("score", 0), item["updated_at"]), reverse=True)
    return results[:top_k]


def record_task_state(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    project_id = payload.get("project_id") or project_id or current_project_id()
    task_id = _task_state_id(payload)
    scope = _task_state_scope(payload)
    item = _task_state_payload(payload, task_id, scope)
    if not item["summary"] and not item["next_actions"] and not item["blockers"]:
        raise HTTPException(status_code=400, detail="summary, next_actions, or blockers is required")
    source_role = str(payload.get("source_role") or "assistant").strip().lower()
    if source_role not in {"user", "assistant", "tool", "operator", "system", "imported", "mixed", "inferred"}:
        source_role = "assistant"
    authority = str(payload.get("authority") or _claim_authority(source_role))
    claim_lifecycle, terminal_evidence_refs = hybrid_workspace.task_claim_lifecycle(payload, item)
    item = {**item, "claim_lifecycle": claim_lifecycle, "terminal_evidence_refs": terminal_evidence_refs}
    now = utc_now()
    event_payload = {**payload, "task_id": task_id, "filters": scope}
    event_id = create_event("TASK_STATE", event_payload, {"task_id": task_id, "status": item["status"]}, project_id=project_id)
    started_at = now
    start_time = time.perf_counter()
    observation_id = str(new_id())
    claim_id = str(new_id())
    content = _task_state_claim_text(item)
    source_hash = hashlib.sha256(
        json_dumps({"event_id": event_id, "task_id": task_id, "content": content, "payload": item}).encode("utf-8")
    ).hexdigest()
    actor_id, actor_type = _claim_actor(scope)
    model_settings = get_project_settings(project_id)
    with get_db() as conn:
        previous = conn.execute(
            """
            SELECT id FROM claims
             WHERE project_id = ?
               AND subject_key = ?
               AND predicate_key = 'task_state'
               AND assertion_kind = 'task_state'
               AND status = 'active'
            """,
            (project_id, f"task:{task_id}"),
        ).fetchall()
        previous_ids = [row["id"] for row in previous]
        if previous_ids:
            conn.execute(
                f"""
                UPDATE claims
                   SET status = 'superseded',
                       modality = 'superseded',
                       retired_at = ?,
                       valid_to = ?,
                       updated_at = ?
                 WHERE id IN ({','.join('?' for _ in previous_ids)})
                   AND project_id = ?
                """,
                [now, now, now, *previous_ids, project_id],
            )
        conn.execute(
            """
            INSERT INTO observation_events (
                id, project_id, tenant_id, source_event_id, memory_id, source_role,
                actor_id, actor_type, scope, content, payload, source_hash,
                observed_at, recorded_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                project_id,
                "local",
                event_id,
                None,
                source_role,
                actor_id,
                actor_type,
                json_dumps(scope),
                content,
                json_dumps(item),
                source_hash,
                now,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO claims (
                id, project_id, tenant_id, memory_id, claim_text, scope,
                subject_key, predicate_key, object_value, assertion_kind,
                polarity, modality, valid_from, valid_to, observed_at,
                recorded_at, retired_at, status, supersedes_claim_ids,
                contradicts_claim_ids, source_event_ids, source_hashes,
                source_role, authority, confidence, sensitivity,
                retention_policy, policy_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim_id,
                project_id,
                "local",
                None,
                content,
                json_dumps(scope),
                f"task:{task_id}",
                "task_state",
                json_dumps(item),
                "task_state",
                "positive",
                claim_lifecycle.lower(),
                now,
                None,
                now,
                now,
                None,
                "active",
                json_dumps(previous_ids),
                "[]",
                json_dumps([observation_id]),
                json_dumps([source_hash]),
                source_role,
                authority,
                _float_or(payload.get("confidence"), _claim_confidence(source_role)),
                str(payload.get("sensitivity") or "normal"),
                str(payload.get("retention_policy") or "default"),
                "claim-model-v1",
                now,
                now,
            ),
        )
        hybrid_result = hybrid_workspace.record_task_observation(
            conn,
            project_id=project_id,
            task_id=task_id,
            scope=scope,
            payload=payload,
            item=item,
            actor_id=actor_id,
            source_role=source_role,
            authority=authority,
            claim_id=claim_id,
            event_id=event_id,
            legacy_observation_id=observation_id,
            source_hash=source_hash,
            claim_lifecycle=claim_lifecycle,
            terminal_evidence_refs=terminal_evidence_refs,
            now=now,
            model_settings=model_settings,
        )
    result = {
        "schema_version": "mem1-task-state-v1",
        "project_id": project_id,
        "task_id": task_id,
        "status": item["status"],
        "summary": item["summary"],
        "next_actions": item["next_actions"],
        "blockers": item["blockers"],
        "claim_id": claim_id,
        "observation_id": observation_id,
        "event_id": event_id,
        "superseded_claim_ids": previous_ids,
        "source_hash": source_hash,
        "scope": scope,
        "claim_lifecycle": claim_lifecycle,
        "terminal_evidence_refs": terminal_evidence_refs,
        "goal_id": item.get("goal_id", ""),
        "parent_goal_id": item.get("parent_goal_id", ""),
        "related_task_ids": item.get("related_task_ids", []),
        "hybrid_workspace": hybrid_result,
    }
    complete_event(event_id, "SUCCEEDED", [result], started_at, start_time)
    record_usage(
        project_id,
        "task_state_record",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate(result),
        event_id=event_id,
        metadata={"task_id": task_id, "status": item["status"], "superseded_count": len(previous_ids)},
    )
    return result


def get_task_state(payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    payload = dict(payload or {})
    project_id = payload.get("project_id") or project_id or current_project_id()
    task_id = payload.get("task_id") or payload.get("goal_id")
    as_of = str(
        payload.get("as_of")
        or payload.get("asOf")
        or payload.get("memory_as_of")
        or payload.get("memoryAsOf")
        or payload.get("resume_workspace_as_of")
        or payload.get("resumeWorkspaceAsOf")
        or ""
    ).strip()
    filters = _task_state_scope(payload)
    limit = min(max(_int_or(payload.get("limit", 20), 20), 1), 100)
    epoch_params: list[Any] = [project_id]
    if as_of:
        epoch_where = """
         WHERE project_id = ?
           AND valid_from <= ?
           AND (valid_to IS NULL OR valid_to > ?)
        """
        epoch_params.extend([as_of, as_of])
    else:
        epoch_where = """
         WHERE project_id = ?
           AND valid_to IS NULL
        """
    if task_id:
        epoch_where += " AND task_id = ?"
        epoch_params.append(_task_state_id({"task_id": task_id}))
    status_rank_sql = """
            CASE LOWER(COALESCE(current_status, ''))
                WHEN 'in_progress' THEN 0
                WHEN 'running' THEN 0
                WHEN 'active' THEN 0
                WHEN 'blocked' THEN 1
                WHEN 'pending' THEN 1
                WHEN 'complete' THEN 2
                WHEN 'completed' THEN 2
                WHEN 'done' THEN 2
                WHEN 'cancelled' THEN 3
                WHEN 'canceled' THEN 3
                ELSE 4
            END
    """
    with get_db() as conn:
        epoch_rows = conn.execute(
            f"""
            SELECT * FROM workspace_epochs
            {epoch_where}
             ORDER BY {status_rank_sql}, valid_from DESC
             LIMIT 100
            """,
            epoch_params,
        ).fetchall()
    epoch_results = []
    for row in epoch_rows:
        scope = json_loads(row["scope_json"], {})
        if filters and not _task_claim_scope_matches_filters(scope, filters):
            continue
        result = hybrid_workspace.workspace_epoch_result(row)
        if as_of:
            result["replay_as_of"] = as_of
        epoch_results.append(result)
        if len(epoch_results) >= limit:
            break
    if epoch_results:
        return {
            "schema_version": "mem1-task-state-list-v1",
            "project_id": project_id,
            "replay_as_of": as_of,
            "count": len(epoch_results),
            "results": epoch_results,
            "current": epoch_results[0],
            "state_source": "workspace_epoch_as_of" if as_of else "workspace_epoch",
        }
    params: list[Any] = [project_id]
    where = """
     WHERE project_id = ?
       AND assertion_kind = 'task_state'
    """
    if as_of:
        where += """
       AND recorded_at <= ?
       AND (retired_at IS NULL OR retired_at > ?)
       AND (valid_to IS NULL OR valid_to > ?)
        """
        params.extend([as_of, as_of, as_of])
    else:
        where += """
       AND status = 'active'
        """
    if task_id:
        where += " AND subject_key = ?"
        params.append(f"task:{_task_state_id({'task_id': task_id})}")
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM claims
            {where}
             ORDER BY updated_at DESC
             LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    results = []
    for row in rows:
        scope = json_loads(row["scope"], {})
        if filters and not _task_claim_scope_matches_filters(scope, filters):
            continue
        item = _task_state_row_payload(row)
        results.append(
            {
                "task_id": item["task_id"],
                "status": item["status"],
                "summary": item.get("summary", ""),
                "next_actions": item.get("next_actions", []),
                "blockers": item.get("blockers", []),
                "claim_lifecycle": str(item.get("claim_lifecycle") or row["modality"] or "provisional").upper(),
                "terminal_evidence_refs": item.get("terminal_evidence_refs", []),
                "evidence": item.get("evidence", {}),
                "evidence_files": item.get("evidence_files", []),
                "commands": item.get("commands", []),
                "goal_id": item.get("goal_id", ""),
                "parent_goal_id": item.get("parent_goal_id", ""),
                "related_task_ids": item.get("related_task_ids", []),
                "claim_id": row["id"],
                "source_event_ids": json_loads(row["source_event_ids"], []),
                "source_hashes": json_loads(row["source_hashes"], []),
                "supersedes_claim_ids": json_loads(row["supersedes_claim_ids"], []),
                "scope": scope,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "replay_as_of": as_of,
            }
        )
    return {
        "schema_version": "mem1-task-state-list-v1",
        "project_id": project_id,
        "replay_as_of": as_of,
        "count": len(results),
        "results": results,
        "current": results[0] if results else None,
        "state_source": "claim_ledger_as_of" if as_of else "claim_ledger",
    }


def _exact_scope_filter(scope: dict[str, Any]) -> dict[str, Any]:
    return {field: scope.get(field) for field in ENTITY_FIELDS}


def _matches_exact_scope(memory: dict[str, Any], scope: dict[str, Any]) -> bool:
    for field in ENTITY_FIELDS:
        if (memory.get(field) or None) != (scope.get(field) or None):
            return False
    return True


def _split_detail(detail: str) -> list[str]:
    parts = re.split(r"\s*,\s*|\s+and\s+", detail.strip(" ."))
    return [part.strip() for part in parts if part.strip()]


def _merge_fact(existing: str, candidate: str) -> str:
    existing_rel = _fact_relation(existing)
    candidate_rel = _fact_relation(candidate)
    if not existing_rel or not candidate_rel:
        return candidate
    details: list[str] = []
    seen: set[str] = set()
    for detail in [*_split_detail(existing_rel["detail"]), *_split_detail(candidate_rel["detail"])]:
        key = detail.lower()
        if key not in seen:
            seen.add(key)
            details.append(detail)
    subject = existing_rel["subject"]
    subject = "User" if subject == "user" else subject[:1].upper() + subject[1:]
    return f"{subject} {existing_rel['predicate']} {' and '.join(details)}."


def _related_memory(candidate: str, memories: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not memories:
        return None
    scored = [(score_memory(candidate, memory), memory) for memory in memories]
    scored.sort(key=lambda item: item[0], reverse=True)
    score, memory = scored[0]
    return memory if score >= 0.18 else None


def _shadow_mode_enabled(payload: dict[str, Any], project_id: str) -> bool:
    if "shadow" in payload:
        return bool(payload.get("shadow"))
    if "shadow_mode" in payload:
        return bool(payload.get("shadow_mode"))
    return bool(get_project_settings(project_id).get("shadow_mode_enabled", False))


def _shadow_settings(project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    settings = get_project_settings(project_id)
    timeout = payload.get("shadow_timeout") or settings.get("shadow_timeout") or os.getenv("MEM1_SHADOW_TIMEOUT") or 5
    try:
        timeout_value = float(timeout)
    except (TypeError, ValueError):
        timeout_value = 5.0
    return {
        "adapter": payload.get("shadow_provider") or settings.get("shadow_provider") or os.getenv("MEM1_SHADOW_PROVIDER") or "local",
        "model": payload.get("shadow_model") or settings.get("shadow_model") or os.getenv("MEM1_SHADOW_MODEL") or "deterministic-shadow-v1",
        "adapter_url": payload.get("shadow_adapter_url") or settings.get("shadow_adapter_url") or os.getenv("MEM1_SHADOW_ADAPTER_URL") or "",
        "timeout": timeout_value,
    }


def _shadow_public_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return {"adapter": settings.get("adapter") or "local", "model": settings.get("model") or "deterministic-shadow-v1"}


def _shadow_external_enabled(settings: dict[str, Any]) -> bool:
    adapter = str(settings.get("adapter") or "").lower()
    return adapter in {"http", "external", "api"} and bool(settings.get("adapter_url"))


def _call_shadow_adapter(task: str, request: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any] | None:
    if not _shadow_external_enabled(settings):
        return None
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("MEM1_SHADOW_ADAPTER_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        with httpx.Client(timeout=float(settings.get("timeout") or 5)) as client:
            response = client.post(
                str(settings["adapter_url"]),
                headers=headers,
                json={"task": task, "model": settings.get("model"), **request},
            )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("shadow adapter response must be a JSON object")
        data["external"] = True
        return data
    except Exception as exc:
        return {"external": True, "fallback": True, "error": str(exc)}


def _float_or(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool_or(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _int_or(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _validated_search_top_k_value(raw: Any, default: int = 10) -> int:
    if raw is None:
        raw = default
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise HTTPException(status_code=400, detail="topK must be a valid integer")
    if raw < 0:
        raise HTTPException(status_code=400, detail=f"Invalid topK: {raw}. Must be a non-negative integer.")
    return min(max(raw, 1), 1000)


def _validated_search_top_k(payload: dict[str, Any], default: int = 10) -> int:
    # "limit" is the OpenMemory-compatible alias of "top_k"; every other
    # search-shaped entry point (assemble_context, create_summary, the MCP
    # validator) already coalesces the two — dropping it here silently
    # returned the default 10 to clients that asked for limit=N.
    raw = payload.get("top_k")
    if raw is None:
        raw = payload.get("limit")
    return _validated_search_top_k_value(raw, default=default)


def _validated_search_threshold_value(raw: Any) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise HTTPException(status_code=400, detail="threshold must be a valid number")
    threshold = float(raw)
    if threshold != threshold:
        raise HTTPException(status_code=400, detail="threshold must be a valid number")
    if threshold < 0 or threshold > 1:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid threshold: {raw}. Must be between 0 and 1 (inclusive).",
        )
    return threshold


def _validated_search_threshold(payload: dict[str, Any], default: float = 0.1) -> float:
    raw = payload.get("threshold", default)
    return _validated_search_threshold_value(raw)


def _validated_bounded_int_value(raw: Any, field_name: str, minimum: int = 1, maximum: int = 1000) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a valid integer")
    if raw < minimum:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}: {raw}. Must be at least {minimum}.")
    return min(raw, maximum)


def _local_shadow_judgment(
    candidate: str,
    scope: dict[str, Any],
    memories: list[dict[str, Any]],
    baseline: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    related = _related_memory(candidate, [memory for memory in memories if _matches_exact_scope(memory, scope)])
    relation = _fact_relation(candidate)
    if related and relation and _fact_relation(related["memory"]):
        shadow_decision = "MERGE" if relation["predicate"] in MERGE_PREDICATES else "UPDATE"
        confidence = 0.74
        reason = "shadow_relation_match"
    elif related:
        shadow_decision = "SKIP" if score_memory(candidate, related) >= 0.72 else "ADD"
        confidence = 0.62
        reason = "shadow_similarity_match"
    else:
        shadow_decision = "ADD"
        confidence = 0.58
        reason = "shadow_new_fact"
    return {
        **_shadow_public_settings(settings),
        "decision": shadow_decision,
        "confidence": confidence,
        "reason": reason,
        "agrees_with_baseline": shadow_decision == baseline.get("decision"),
        "baseline_decision": baseline.get("decision"),
    }


def _normalize_shadow_judgment(data: dict[str, Any], baseline: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    decision = str(data.get("decision") or data.get("memory_decision") or baseline.get("decision") or "ADD").upper()
    if decision not in {"ADD", "SKIP", "MERGE", "UPDATE", "DELETE"}:
        decision = str(baseline.get("decision") or "ADD")
    if isinstance(data.get("target_memory_ids"), list):
        target_memory_ids = [str(memory_id) for memory_id in data["target_memory_ids"] if str(memory_id).strip()]
    elif data.get("target_memory_id"):
        target_memory_ids = [str(data["target_memory_id"])]
    else:
        target_memory_ids = []
    baseline_evidence = baseline.get("evidence") if isinstance(baseline.get("evidence"), dict) else {}
    allowed_memory_ids = {str(memory_id) for memory_id in baseline_evidence.get("memory_ids", [])}
    unknown_target_memory_ids = [memory_id for memory_id in target_memory_ids if memory_id not in allowed_memory_ids]
    if unknown_target_memory_ids:
        return {
            **_shadow_public_settings(settings),
            "external": True,
            "fallback": True,
            "error": f"shadow adapter returned unknown target memory ids: {', '.join(unknown_target_memory_ids)}",
            "decision": str(baseline.get("decision") or "ADD"),
            "confidence": 0.0,
            "reason": "unknown_target_memory_id",
            "agrees_with_baseline": True,
            "baseline_decision": baseline.get("decision"),
        }
    result = {
        **_shadow_public_settings(settings),
        "external": True,
        "decision": decision,
        "confidence": _float_or(data.get("confidence"), 0.5),
        "reason": str(data.get("reason") or "external_shadow_adapter"),
        "agrees_with_baseline": decision == baseline.get("decision"),
        "baseline_decision": baseline.get("decision"),
    }
    if data.get("output_memory") is not None:
        result["output_memory"] = str(data["output_memory"])
    if target_memory_ids:
        result["target_memory_ids"] = target_memory_ids
    if isinstance(data.get("risk_flags"), list):
        result["risk_flags"] = [str(flag) for flag in data["risk_flags"] if str(flag).strip()]
    if data.get("requires_review") is not None:
        result["requires_review"] = _bool_or(data.get("requires_review"))
    if isinstance(data.get("evidence"), dict):
        result["evidence"] = data["evidence"]
    return result


def _memory_policy_adapter_input(
    candidate: str,
    scope: dict[str, Any],
    memories: list[dict[str, Any]],
    baseline: dict[str, Any],
    project_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    settings = get_project_settings(project_id)
    scoped_memories = [strip_internal(memory) for memory in memories if _matches_exact_scope(memory, scope)]
    source_hashes = {
        str(memory["id"]): _compression_source_hash(memory)
        for memory in memories
        if memory.get("id") and _matches_exact_scope(memory, scope)
    }
    context_budget_tokens = _int_or(payload.get("context_budget_tokens", payload.get("budget_tokens", 800)), 800)
    return {
        "schema_version": "mem1-policy-adapter-input-v1",
        "task": "memory_judgment",
        "scope": {field: scope.get(field) for field in ENTITY_FIELDS if scope.get(field) is not None},
        "messages": payload.get("messages") if isinstance(payload.get("messages"), list) else [],
        "candidate_facts": [candidate],
        "retrieved_memories": scoped_memories,
        "baseline": baseline,
        "policy": {
            "review_required_for_delete": True,
            "proposal_required_reviews": max(1, _int_or(settings.get("proposal_required_reviews"), 1)),
            "redaction_policy": settings.get("trace_redaction_policy") or TRACE_REDACTION_POLICY,
            "policy_preset": settings.get("policy_preset") or "balanced",
            "risk_tolerance": settings.get("policy_risk_tolerance") or "balanced",
            "shadow_promotion_enabled": bool(settings.get("shadow_promotion_enabled")),
            "shadow_canary_enabled": bool(settings.get("shadow_canary_enabled")),
        },
        "context_budget_tokens": context_budget_tokens,
        "evidence": {
            "schema_version": "mem1-policy-adapter-evidence-v1",
            "memory_ids": list(source_hashes),
            "source_hashes": source_hashes,
        },
    }


def _shadow_judgment(
    candidate: str,
    scope: dict[str, Any],
    memories: list[dict[str, Any]],
    baseline: dict[str, Any],
    project_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = _shadow_settings(project_id, payload)
    scoped_memories = [strip_internal(memory) for memory in memories if _matches_exact_scope(memory, scope)]
    policy_input = _memory_policy_adapter_input(candidate, scope, memories, baseline, project_id, payload)
    external = _call_shadow_adapter(
        "judgment",
        {
            "schema_version": "mem1-shadow-adapter-request-v1",
            "candidate": candidate,
            "scope": policy_input["scope"],
            "memories": scoped_memories,
            "retrieved_memories": policy_input["retrieved_memories"],
            "baseline": baseline,
            "policy": policy_input["policy"],
            "context_budget_tokens": policy_input["context_budget_tokens"],
            "evidence": policy_input["evidence"],
            "policy_input": policy_input,
        },
        settings,
    )
    if external and not external.get("fallback"):
        return _normalize_shadow_judgment(external, baseline, settings)
    local = _local_shadow_judgment(candidate, scope, memories, baseline, settings)
    if external and external.get("fallback"):
        local["fallback"] = True
        local["external_error"] = str(external.get("error") or "shadow adapter failed")
    return local


def _local_shadow_compression(result: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    ratio = result["drift_check"]["compression_ratio"]
    return {
        **_shadow_public_settings(settings),
        "action": "COMPRESS_MEMORIES",
        "output_memory": result["output_memory"],
        "confidence": 0.78 if ratio < 1 else 0.52,
        "reason": "shadow_same_relation_compression",
        "agrees_with_baseline": True,
        "baseline_output_memory": result["output_memory"],
    }


def _normalize_shadow_compression(data: dict[str, Any], result: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    output_memory = str(data.get("output_memory") or data.get("summary") or result["output_memory"])
    return {
        **_shadow_public_settings(settings),
        "external": True,
        "action": str(data.get("action") or "COMPRESS_MEMORIES"),
        "output_memory": output_memory,
        "confidence": _float_or(data.get("confidence"), 0.5),
        "reason": str(data.get("reason") or "external_shadow_adapter"),
        "agrees_with_baseline": output_memory == result["output_memory"],
        "baseline_output_memory": result["output_memory"],
    }


def _shadow_compression(payload: dict[str, Any], result: dict[str, Any], project_id: str) -> dict[str, Any]:
    settings = _shadow_settings(project_id)
    external = _call_shadow_adapter(
        "compression",
        {
            "payload": payload,
            "source_memories": result["source_memories"],
            "drift_check": result["drift_check"],
            "baseline": {"output_memory": result["output_memory"], "action": result["action"]},
        },
        settings,
    )
    if external and not external.get("fallback"):
        return _normalize_shadow_compression(external, result, settings)
    local = _local_shadow_compression(result, settings)
    if external and external.get("fallback"):
        local["fallback"] = True
        local["external_error"] = str(external.get("error") or "shadow adapter failed")
    return local


def _shadow_promotion_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    return {
        "enabled": bool(settings.get("shadow_promotion_enabled", False)),
        "gate_passed": bool(settings.get("shadow_promotion_gate_passed", False)),
        "min_confidence": _float_or(settings.get("shadow_promotion_min_confidence"), 0.8),
    }


def _shadow_promotion_allowed(project_id: str) -> bool:
    settings = _shadow_promotion_settings(project_id)
    return bool(settings["enabled"] and settings["gate_passed"])


def _shadow_canary_settings(project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    return {
        "enabled": bool(settings.get("shadow_canary_enabled", False)),
        "min_reviews": max(1, _int_or(settings.get("shadow_canary_min_reviews"), 5)),
        "min_precision": _float_or(settings.get("shadow_canary_min_precision"), 0.9),
        "min_confidence": _float_or(settings.get("shadow_canary_min_confidence"), 0.95),
    }


def _shadow_canary_stats(project_id: str) -> dict[str, Any]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT status FROM proposals
            WHERE project_id = ?
              AND proposal_type = 'memory_judgment'
              AND review_reason LIKE 'shadow_promotion:%'
              AND status IN ('APPLIED', 'REJECTED')
            """,
            (project_id,),
        ).fetchall()
    applied = sum(1 for row in rows if row["status"] == "APPLIED")
    rejected = sum(1 for row in rows if row["status"] == "REJECTED")
    reviewed = applied + rejected
    precision = round(applied / reviewed, 4) if reviewed else 0.0
    return {"reviewed": reviewed, "applied": applied, "rejected": rejected, "precision": precision}


def _route_shadow_canary(proposal: dict[str, Any], project_id: str) -> dict[str, Any]:
    settings = _shadow_canary_settings(project_id)
    stats = _shadow_canary_stats(project_id)
    metadata = proposal.get("payload", {}).get("metadata", {}) if isinstance(proposal.get("payload"), dict) else {}
    confidence = _float_or(metadata.get("shadow_confidence"), 0.0)
    canary = {
        "eligible": False,
        "routed": False,
        "applied": False,
        "reason": "disabled",
        "stats": stats,
        "settings": settings,
    }
    if not settings["enabled"]:
        proposal["shadow_canary"] = canary
        return proposal
    activation_rollback = _activation_rollback_gate(project_id)
    canary["activation_rollback"] = activation_rollback
    if activation_rollback and activation_rollback.get("blocked"):
        canary["reason"] = "activation_rollback"
        proposal["shadow_canary"] = canary
        return proposal
    activation_health = _active_activation_health(project_id)
    canary["activation_health"] = activation_health
    if activation_health and not activation_health.get("healthy"):
        canary["reason"] = "activation_unhealthy"
        proposal["shadow_canary"] = canary
        return proposal
    if stats["reviewed"] < settings["min_reviews"]:
        canary["reason"] = "insufficient_review_data"
        proposal["shadow_canary"] = canary
        return proposal
    if stats["precision"] < settings["min_precision"]:
        canary["reason"] = "precision_below_threshold"
        proposal["shadow_canary"] = canary
        return proposal
    if confidence < settings["min_confidence"]:
        canary["reason"] = "confidence_below_threshold"
        proposal["shadow_canary"] = canary
        return proposal
    canary.update({"eligible": True, "routed": True, "reason": "precision_gate_passed"})
    review_proposal(
        proposal["id"],
        {
            "decision": "APPROVE",
            "reviewer_id": "shadow_canary",
            "reason": f"precision:{stats['precision']}:reviewed:{stats['reviewed']}",
        },
        project_id=project_id,
    )
    refreshed = get_proposal(proposal["id"], project_id=project_id)
    review_state = refreshed.get("review_state", {})
    if review_state.get("can_apply") and not review_state.get("blocked"):
        refreshed = apply_proposal(proposal["id"], project_id=project_id)
        canary["applied"] = True
    refreshed["shadow_canary"] = canary
    return refreshed


def _pending_shadow_promotion_exists(project_id: str, fact: str, scope: dict[str, Any]) -> bool:
    normalized_fact = re.sub(r"\s+", " ", fact.strip()).lower()
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT payload, review_reason FROM proposals
            WHERE project_id = ? AND proposal_type = 'memory_judgment' AND status = 'PENDING'
            """,
            (project_id,),
        ).fetchall()
    for row in rows:
        if not str(row["review_reason"] or "").startswith("shadow_promotion:"):
            continue
        payload = json_loads(row["payload"], {})
        raw_facts = payload.get("facts") or []
        payload_facts = list(raw_facts) if isinstance(raw_facts, list) else [raw_facts]
        if "messages" in payload and isinstance(payload["messages"], list):
            payload_facts.extend(message.get("content", "") for message in payload["messages"] if isinstance(message, dict))
        if not any(re.sub(r"\s+", " ", str(item).strip()).lower() == normalized_fact for item in payload_facts):
            continue
        if all(payload.get(field) == scope.get(field) for field in ENTITY_FIELDS):
            return True
    return False


def _create_shadow_promotion_proposals(
    decisions: list[dict[str, Any]],
    project_id: str,
) -> list[dict[str, Any]]:
    if not _shadow_promotion_allowed(project_id):
        return []
    settings = _shadow_promotion_settings(project_id)
    proposals: list[dict[str, Any]] = []
    for item in decisions:
        shadow = item.get("shadow") if isinstance(item.get("shadow"), dict) else None
        if not shadow:
            continue
        if not shadow.get("external") or shadow.get("fallback"):
            continue
        if shadow.get("agrees_with_baseline", True):
            continue
        if str(shadow.get("decision") or "").upper() != "ADD":
            continue
        if _float_or(shadow.get("confidence"), 0.0) < settings["min_confidence"]:
            continue
        fact = str(shadow.get("output_memory") or item.get("candidate") or "").strip()
        if not fact:
            continue
        scope = item.get("scope") if isinstance(item.get("scope"), dict) else {}
        if _pending_shadow_promotion_exists(project_id, fact, scope):
            continue
        proposal = create_proposal(
            {
                "proposal_type": "memory_judgment",
                "payload": {
                    "facts": [fact],
                    "infer": False,
                    "shadow": False,
                    "metadata": {
                        "source": "shadow_promotion",
                        "shadow_adapter": shadow.get("adapter"),
                        "shadow_model": shadow.get("model"),
                        "shadow_confidence": shadow.get("confidence"),
                        "shadow_reason": shadow.get("reason"),
                        "baseline_decision": shadow.get("baseline_decision"),
                        "shadow_decision": shadow.get("decision"),
                    },
                    **{field: scope[field] for field in ENTITY_FIELDS if scope.get(field) is not None},
                },
                "review_reason": (
                    f"shadow_promotion:{shadow.get('baseline_decision')}->{shadow.get('decision')}:"
                    f"{shadow.get('reason') or 'external_shadow_adapter'}"
                ),
            },
            project_id=project_id,
        )
        proposal["shadow_promotion"] = True
        proposal = _route_shadow_canary(proposal, project_id)
        proposals.append(proposal)
    return proposals


JUDGMENT_CONFIDENCE_BY_REASON = {
    "duplicate_memory": 0.98,
    "covered_by_existing_memory": 0.92,
    "explicit_delete_intent": 0.82,
    "same_slot_replacement": 0.86,
    "same_subject_predicate_merge": 0.84,
    "new_scoped_fact": 0.72,
}


def _judgment_target_memory_ids(judgment: dict[str, Any]) -> list[str]:
    target_memory_id = str(judgment.get("target_memory_id") or "").strip()
    return [target_memory_id] if target_memory_id else []


def _judgment_confidence(judgment: dict[str, Any]) -> float:
    reason = str(judgment.get("reason") or "")
    return JUDGMENT_CONFIDENCE_BY_REASON.get(reason, 0.6)


def _judgment_risk_flags(judgment: dict[str, Any], confidence: float) -> list[str]:
    flags = []
    decision = str(judgment.get("decision") or "").upper()
    if decision in {"MERGE", "UPDATE", "DELETE"}:
        flags.append("mutating_decision")
    if decision == "DELETE":
        flags.append("destructive_delete")
    if confidence < 0.6:
        flags.append("low_confidence")
    return flags


def _judgment_evidence(
    candidate: str,
    scope: dict[str, Any],
    memories: list[dict[str, Any]],
    judgment: dict[str, Any],
) -> dict[str, Any]:
    source_hashes = {
        str(memory["id"]): _compression_source_hash(memory)
        for memory in memories
        if memory.get("id") and _matches_exact_scope(memory, scope)
    }
    target_memory_ids = _judgment_target_memory_ids(judgment)
    return {
        "schema_version": "mem1-judgment-evidence-v1",
        "candidate_hash": content_hash(candidate),
        "scope": {field: scope.get(field) for field in ENTITY_FIELDS if scope.get(field) is not None},
        "memory_ids": list(source_hashes),
        "target_memory_ids": target_memory_ids,
        "source_hashes": source_hashes,
        "target_source_hashes": {
            memory_id: source_hashes[memory_id] for memory_id in target_memory_ids if memory_id in source_hashes
        },
    }


def _enrich_judgment(
    candidate: str,
    scope: dict[str, Any],
    memories: list[dict[str, Any]],
    judgment: dict[str, Any],
) -> dict[str, Any]:
    confidence = _judgment_confidence(judgment)
    risk_flags = _judgment_risk_flags(judgment, confidence)
    return {
        **judgment,
        "confidence": confidence,
        "target_memory_ids": _judgment_target_memory_ids(judgment),
        "risk_flags": risk_flags,
        "requires_review": bool(risk_flags),
        "evidence": _judgment_evidence(candidate, scope, memories, judgment),
    }


def _judge_fact(candidate: str, scope: dict[str, Any], memories: list[dict[str, Any]]) -> dict[str, Any]:
    scoped = [memory for memory in memories if _matches_exact_scope(memory, scope)]
    normalized_candidate = re.sub(r"\s+", " ", candidate.strip()).lower()
    for memory in scoped:
        if re.sub(r"\s+", " ", memory["memory"].strip()).lower() == normalized_candidate:
            return {
                "decision": "SKIP",
                "reason": "duplicate_memory",
                "target_memory_id": memory["id"],
                "target_memory": memory["memory"],
                "output_memory": memory["memory"],
            }

    related = _related_memory(candidate, scoped)
    if DELETE_INTENT_RE.search(candidate) and related:
        return {
            "decision": "DELETE",
            "reason": "explicit_delete_intent",
            "target_memory_id": related["id"],
            "target_memory": related["memory"],
            "output_memory": None,
        }

    candidate_rel = _fact_relation(candidate)
    if candidate_rel:
        for memory in scoped:
            memory_rel = _fact_relation(memory["memory"])
            if not memory_rel:
                continue
            same_slot = (
                candidate_rel["subject"] == memory_rel["subject"]
                and candidate_rel["predicate"] == memory_rel["predicate"]
            )
            if not same_slot:
                continue
            candidate_details = {item.lower() for item in _split_detail(candidate_rel["detail"])}
            memory_details = {item.lower() for item in _split_detail(memory_rel["detail"])}
            if candidate_details and candidate_details.issubset(memory_details):
                return {
                    "decision": "SKIP",
                    "reason": "covered_by_existing_memory",
                    "target_memory_id": memory["id"],
                    "target_memory": memory["memory"],
                    "output_memory": memory["memory"],
                }
            if NEGATION_RE.search(candidate) or candidate_rel["predicate"] in UPDATE_PREDICATES:
                return {
                    "decision": "UPDATE",
                    "reason": "same_slot_replacement",
                    "target_memory_id": memory["id"],
                    "target_memory": memory["memory"],
                    "output_memory": candidate,
                }
            if candidate_rel["predicate"] in MERGE_PREDICATES:
                merged = _merge_fact(memory["memory"], candidate)
                if merged.lower() != memory["memory"].lower():
                    return {
                        "decision": "MERGE",
                        "reason": "same_subject_predicate_merge",
                        "target_memory_id": memory["id"],
                        "target_memory": memory["memory"],
                        "output_memory": merged,
                    }

    return {
        "decision": "ADD",
        "reason": "new_scoped_fact",
        "target_memory_id": None,
        "target_memory": None,
        "output_memory": candidate,
    }


def judge_memories(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    project_id = payload.get("project_id") or project_id or current_project_id()
    if payload.get("facts") and "messages" not in payload:
        payload = {
            **payload,
            "messages": [{"role": "user", "content": str(fact)} for fact in payload.get("facts") or []],
            "infer": False,
        }
    if not payload.get("messages") or not isinstance(payload["messages"], list):
        raise HTTPException(status_code=400, detail="messages or facts is required")
    if not any(payload.get(field) for field in ENTITY_FIELDS):
        raise HTTPException(status_code=400, detail="At least one entity ID is required")

    apply_changes = bool(payload.get("apply", False))
    shadow_enabled = _shadow_mode_enabled(payload, project_id)
    infer = bool(payload.get("infer", True))
    metadata = payload.get("metadata") or {}
    fact_records = _fact_records(payload, project_id=project_id, infer=infer)
    memories = list_memory_dicts(project_id=project_id)
    decisions: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    started_at = utc_now()
    start_time = time.perf_counter()
    event_id = create_event("JUDGMENT", payload, {"apply": apply_changes}, project_id=project_id)

    for record in fact_records:
        for scope in record["scopes"]:
            judgment = _judge_fact(record["fact"], scope, memories)
            baseline_judgment = _enrich_judgment(record["fact"], scope, memories, judgment)
            item = {
                "candidate": record["fact"],
                "scope": {field: scope.get(field) for field in ENTITY_FIELDS if scope.get(field) is not None},
                **baseline_judgment,
            }
            if shadow_enabled:
                item["shadow"] = _shadow_judgment(record["fact"], scope, memories, baseline_judgment, project_id, payload)
            decisions.append(item)
            if not apply_changes:
                continue
            if item["decision"] == "ADD":
                add_payload = {
                    "messages": [{"role": "user", "content": item["output_memory"]}],
                    "infer": False,
                    "metadata": metadata,
                    **item["scope"],
                }
                result = add_memories(add_payload, project_id=project_id)
                event = get_event(result["event_id"], project_id=project_id)
                created = event.get("results", [])
                results.extend({"decision": "ADD", **memory} for memory in created)
                memories = list_memory_dicts(project_id=project_id)
            elif item["decision"] in {"MERGE", "UPDATE"} and item.get("target_memory_id"):
                updated = update_memory(str(item["target_memory_id"]), {"text": item["output_memory"], "metadata": metadata})
                results.append({"decision": item["decision"], **updated})
                memories = list_memory_dicts(project_id=project_id)
            elif item["decision"] == "DELETE" and item.get("target_memory_id"):
                deleted = delete_memory(str(item["target_memory_id"]), project_id=project_id)
                results.append({"decision": "DELETE", "id": item["target_memory_id"], **deleted})
                memories = list_memory_dicts(project_id=project_id)

    complete_event(event_id, "SUCCEEDED", decisions, started_at, start_time)
    counts: dict[str, int] = {}
    for item in decisions:
        counts[item["decision"]] = counts.get(item["decision"], 0) + 1
    shadow_proposals = _create_shadow_promotion_proposals(decisions, project_id) if shadow_enabled and not apply_changes else []
    record_usage(
        project_id,
        "memory_judgment",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate({"decisions": decisions, "shadow_proposals": shadow_proposals}),
        event_id=event_id,
        metadata={
            "apply": apply_changes,
            "decision_counts": counts,
            "shadow": shadow_enabled,
            "shadow_proposal_count": len(shadow_proposals),
        },
    )
    return {
        "schema_version": "mem1-judgment-result-v1",
        "project_id": project_id,
        "event_id": event_id,
        "status": "SUCCEEDED",
        "apply": apply_changes,
        "shadow": shadow_enabled,
        "shadow_proposal_count": len(shadow_proposals),
        "shadow_proposals": shadow_proposals,
        "decision_counts": counts,
        "decisions": decisions,
        "results": results,
    }


def judgment_review_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "event_id": row["event_id"],
        "reviewer_id": row["reviewer_id"],
        "decision": row["decision"],
        "reason": row["reason"] or "",
        "risk_flags": json_loads(row["risk_flags"], []),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _judgment_review_state(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    latest = reviews[0] if reviews else None
    status = latest["decision"] if latest else "OPEN"
    resolved = status in {"ACKNOWLEDGED", "RESOLVED"}
    return {
        "status": status,
        "resolved": resolved,
        "review_count": len(reviews),
        "latest_review": latest,
        "reviews": reviews,
    }


def _judgment_reviews_for_events(project_id: str, event_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not event_ids:
        return {}
    placeholders = ", ".join("?" for _ in event_ids)
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM judgment_reviews
            WHERE project_id = ? AND event_id IN ({placeholders})
            ORDER BY updated_at DESC
            """,
            [project_id, *event_ids],
        ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["event_id"], []).append(judgment_review_row(row))
    return grouped


def _normalize_judgment_review_decision(value: Any) -> str:
    decision = str(value or "ACKNOWLEDGE").strip().upper()
    if decision in {"ACK", "ACKNOWLEDGE", "ACKNOWLEDGED"}:
        return "ACKNOWLEDGED"
    if decision in {"RESOLVE", "RESOLVED"}:
        return "RESOLVED"
    if decision in {"REOPEN", "REOPENED"}:
        return "REOPENED"
    raise HTTPException(status_code=400, detail="decision must be ACKNOWLEDGE, RESOLVE, or REOPEN")


def _judgment_audit_item(event: dict[str, Any], reviews: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    decisions = [item for item in event.get("results", []) if isinstance(item, dict)]
    counts: dict[str, int] = {}
    scope_counts: dict[str, int] = {}
    missing_reason_count = 0
    shadow_count = 0
    shadow_disagreement_count = 0
    shadow_fallback_count = 0
    review_worthy_count = 0
    sample_candidates: list[str] = []
    decision_risk_flags: set[str] = set()
    for decision in decisions:
        label = str(decision.get("decision") or "UNKNOWN")
        counts[label] = counts.get(label, 0) + 1
        if not str(decision.get("reason") or "").strip():
            missing_reason_count += 1
        for flag in decision.get("risk_flags") or []:
            if str(flag).strip():
                decision_risk_flags.add(str(flag))
        if label in {"UPDATE", "DELETE"}:
            review_worthy_count += 1
        scope = decision.get("scope") if isinstance(decision.get("scope"), dict) else {}
        for field, value in scope.items():
            if value is not None:
                scope_counts[field] = scope_counts.get(field, 0) + 1
        candidate = str(decision.get("candidate") or "").strip()
        if candidate and len(sample_candidates) < 3:
            sample_candidates.append(candidate)
        shadow = decision.get("shadow") if isinstance(decision.get("shadow"), dict) else None
        if shadow:
            shadow_count += 1
            if shadow.get("fallback"):
                shadow_fallback_count += 1
            if not shadow.get("agrees_with_baseline", True):
                shadow_disagreement_count += 1
                review_worthy_count += 1
    risk_flags = []
    if not decisions:
        risk_flags.append("no_decisions")
    if missing_reason_count:
        risk_flags.append("missing_reason")
    if shadow_disagreement_count:
        risk_flags.append("shadow_disagreement")
    if shadow_fallback_count:
        risk_flags.append("shadow_fallback")
    for flag in sorted(decision_risk_flags):
        if flag not in risk_flags:
            risk_flags.append(flag)
    if any(label in counts for label in {"UPDATE", "DELETE"}):
        if "mutating_decision" not in risk_flags:
            risk_flags.append("mutating_decision")
    reason_coverage = round((len(decisions) - missing_reason_count) / max(len(decisions), 1), 4)
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    review_state = _judgment_review_state(reviews or [])
    needs_review = bool(risk_flags) and not review_state["resolved"]
    return {
        "event_id": event["id"],
        "project_id": event["project_id"],
        "created_at": event["created_at"],
        "latency": event["latency"],
        "apply": bool(metadata.get("apply", False)),
        "shadow": bool(metadata.get("shadow", False)),
        "decision_count": len(decisions),
        "decision_counts": counts,
        "scope_counts": scope_counts,
        "reason_coverage": reason_coverage,
        "shadow_count": shadow_count,
        "shadow_disagreement_count": shadow_disagreement_count,
        "shadow_fallback_count": shadow_fallback_count,
        "review_worthy_count": review_worthy_count,
        "risk_flags": risk_flags,
        "needs_review": needs_review,
        "review_state": review_state,
        "sample_candidates": sample_candidates,
    }


def memory_judgment_audit(limit: int = 100, project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(limit, 1), 500)
    with get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM events WHERE project_id = ? AND event_type = 'JUDGMENT'",
            (project_id,),
        ).fetchone()["c"]
        rows = conn.execute(
            """
            SELECT * FROM events
            WHERE project_id = ? AND event_type = 'JUDGMENT'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
    events = [event_row(row) for row in rows]
    reviews_by_event = _judgment_reviews_for_events(project_id, [event["id"] for event in events])
    results = [_judgment_audit_item(event, reviews_by_event.get(event["id"], [])) for event in events]
    aggregate_flags = sorted({flag for item in results for flag in item["risk_flags"]})
    aggregate_open_flags = sorted({flag for item in results if item["needs_review"] for flag in item["risk_flags"]})
    return {
        "project_id": project_id,
        "count": len(results),
        "total": count,
        "needs_review_count": sum(1 for item in results if item["needs_review"]),
        "reviewed_risk_count": sum(1 for item in results if item["risk_flags"] and not item["needs_review"]),
        "aggregate_risk_flags": aggregate_flags,
        "aggregate_open_risk_flags": aggregate_open_flags,
        "results": results,
    }


def review_judgment_audit(
    event_id: str,
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    payload = payload or {}
    with get_db() as conn:
        event_row_data = conn.execute(
            "SELECT * FROM events WHERE id = ? AND project_id = ? AND event_type = 'JUDGMENT'",
            (event_id, project_id),
        ).fetchone()
    if not event_row_data:
        raise HTTPException(status_code=404, detail="Judgment event not found")
    event = event_row(event_row_data)
    current_audit = _judgment_audit_item(event, [])
    decision = _normalize_judgment_review_decision(payload.get("decision"))
    reviewer_id = str(payload.get("reviewer_id") or payload.get("reviewer") or "local_reviewer").strip()
    if not reviewer_id:
        raise HTTPException(status_code=400, detail="reviewer_id is required")
    reason = str(payload.get("reason") or payload.get("review_reason") or "")
    risk_flags = payload.get("risk_flags")
    if not isinstance(risk_flags, list):
        risk_flags = current_audit["risk_flags"]
    risk_flags = [str(flag) for flag in risk_flags if str(flag).strip()]
    now = utc_now()
    with get_db() as conn:
        existing = conn.execute(
            """
            SELECT id FROM judgment_reviews
            WHERE project_id = ? AND event_id = ? AND reviewer_id = ?
            """,
            (project_id, event_id, reviewer_id),
        ).fetchone()
        if existing:
            review_id = existing["id"]
            conn.execute(
                """
                UPDATE judgment_reviews
                   SET decision = ?, reason = ?, risk_flags = ?, updated_at = ?
                 WHERE id = ? AND project_id = ?
                """,
                (decision, reason, json_dumps(risk_flags), now, review_id, project_id),
            )
        else:
            review_id = str(new_id("judgment_review"))
            conn.execute(
                """
                INSERT INTO judgment_reviews (
                    id, project_id, event_id, reviewer_id, decision, reason,
                    risk_flags, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (review_id, project_id, event_id, reviewer_id, decision, reason, json_dumps(risk_flags), now, now),
            )
        row = conn.execute("SELECT * FROM judgment_reviews WHERE id = ? AND project_id = ?", (review_id, project_id)).fetchone()
    reviews = _judgment_reviews_for_events(project_id, [event_id]).get(event_id, [])
    audit = _judgment_audit_item(event, reviews)
    review = judgment_review_row(row)
    record_usage(
        project_id,
        "judgment_audit_review",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate(audit),
        metadata={"event_id": event_id, "decision": decision, "reviewer_id": reviewer_id, "risk_flags": risk_flags},
    )
    return {"event_id": event_id, "review": review, "review_state": audit["review_state"], "audit": audit}


def _latest_evaluation_for_family(project_id: str, family: str) -> dict[str, Any] | None:
    evaluations = list_evaluations(project_id=project_id, limit=1, family=family)
    results = evaluations.get("results") or []
    return results[0] if results else None


def self_improvement_status(
    project_id: str | None = None,
    min_context_accuracy: float = 1.0,
    min_adapter_accuracy: float = 0.9,
    min_claim_accuracy: float = 1.0,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    judgment = memory_judgment_audit(limit=50, project_id=project_id)
    context_eval = _latest_evaluation_for_family(project_id, "context_composer")
    claim_eval = _latest_evaluation_for_family(project_id, "claim_verification")
    adapter_eval = _latest_model_adapter_eval(project_id)
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if judgment["needs_review_count"]:
        blockers.append(
            {
                "code": "judgment_audit_needs_review",
                "message": "Recent judgment audit contains review-worthy risk flags.",
                "value": judgment["needs_review_count"],
            }
        )

    if not context_eval:
        blockers.append({"code": "missing_context_composer_eval", "message": "No context-composer evaluation has run."})
        context_component = None
    else:
        context_metrics = context_eval.get("metrics", {})
        context_accuracy = _float_or(context_metrics.get("accuracy"), 0.0)
        if context_accuracy < min_context_accuracy:
            blockers.append(
                {
                    "code": "context_accuracy_below_threshold",
                    "message": "Latest context-composer evaluation is below threshold.",
                    "value": context_accuracy,
                    "threshold": min_context_accuracy,
                }
            )
        fallback_count = int(context_metrics.get("composer_fallback_count") or 0)
        unexpected_fallback_count = int(context_metrics.get("unexpected_composer_fallback_count", fallback_count) or 0)
        if unexpected_fallback_count:
            blockers.append(
                {
                    "code": "context_composer_fallback",
                    "message": "Latest context-composer evaluation used unexpected fallback output.",
                    "value": unexpected_fallback_count,
                    "total_fallback_count": fallback_count,
                }
            )
        grounding_missing_count = int(context_metrics.get("context_grounding_missing_count") or 0)
        grounding_unsupported_count = int(context_metrics.get("context_grounding_unsupported_count") or 0)
        if grounding_missing_count:
            blockers.append(
                {
                    "code": "context_grounding_missing",
                    "message": "Latest external context-composer evaluation did not include claim-grounding verification.",
                    "value": grounding_missing_count,
                }
            )
        if grounding_unsupported_count:
            blockers.append(
                {
                    "code": "context_grounding_unsupported",
                    "message": "Latest external context-composer evaluation produced unsupported grounded claims.",
                    "value": grounding_unsupported_count,
                }
            )
        context_component = {
            "id": context_eval["id"],
            "name": context_eval["name"],
            "created_at": context_eval["created_at"],
            "metrics": context_metrics,
        }

    if not claim_eval:
        warnings.append(
            {
                "code": "missing_claim_verification_eval",
                "message": "No claim-verification evaluation has run.",
            }
        )
        claim_component = None
    else:
        claim_metrics = claim_eval.get("metrics", {})
        claim_accuracy = _float_or(claim_metrics.get("accuracy"), 0.0)
        if claim_accuracy < min_claim_accuracy:
            warnings.append(
                {
                    "code": "claim_verification_accuracy_below_threshold",
                    "message": "Latest claim-verification evaluation is below the guardrail threshold.",
                    "value": claim_accuracy,
                    "threshold": min_claim_accuracy,
                }
            )
        claim_component = {
            "id": claim_eval["id"],
            "name": claim_eval["name"],
            "created_at": claim_eval["created_at"],
            "metrics": claim_metrics,
        }

    if not adapter_eval:
        blockers.append({"code": "missing_model_adapter_eval", "message": "No model-adapter evaluation has run."})
        adapter_component = None
    else:
        adapter_metrics = adapter_eval.get("metrics", {})
        adapter_accuracy = _float_or(adapter_metrics.get("accuracy"), 0.0)
        if adapter_accuracy < min_adapter_accuracy:
            blockers.append(
                {
                    "code": "adapter_accuracy_below_threshold",
                    "message": "Latest model-adapter evaluation is below threshold.",
                    "value": adapter_accuracy,
                    "threshold": min_adapter_accuracy,
                }
            )
        adapter_component = {
            "id": adapter_eval["id"],
            "created_at": adapter_eval["created_at"],
            "metrics": adapter_metrics,
            "fine_tuning_job_id": adapter_eval.get("fine_tuning_job_id"),
        }

    return {
        "schema_version": "mem1-self-improvement-status-v1",
        "project_id": project_id,
        "ready": not blockers,
        "blockers": blockers,
        "blocker_codes": [blocker["code"] for blocker in blockers],
        "warnings": warnings,
        "warning_codes": [warning["code"] for warning in warnings],
        "thresholds": {
            "min_context_accuracy": min_context_accuracy,
            "min_adapter_accuracy": min_adapter_accuracy,
            "min_claim_accuracy": min_claim_accuracy,
        },
        "components": {
            "judgment_audit": {
                "count": judgment["count"],
                "needs_review_count": judgment["needs_review_count"],
                "aggregate_risk_flags": judgment["aggregate_risk_flags"],
            },
            "context_composer_eval": context_component,
            "claim_verification_eval": claim_component,
            "model_adapter_eval": adapter_component,
        },
    }


def _proposal_required_reviews(project_id: str) -> int:
    try:
        return max(1, int(get_project_settings(project_id).get("proposal_required_reviews") or 1))
    except (TypeError, ValueError):
        return 1


def proposal_review_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "proposal_id": row["proposal_id"],
        "reviewer_id": row["reviewer_id"],
        "decision": row["decision"],
        "reason": row["reason"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def proposal_review_summary(proposal_id: str, project_id: str) -> dict[str, Any]:
    required = _proposal_required_reviews(project_id)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM proposal_reviews
            WHERE project_id = ? AND proposal_id = ?
            ORDER BY updated_at DESC
            """,
            (project_id, proposal_id),
        ).fetchall()
    reviews = [proposal_review_row(row) for row in rows]
    approve_count = sum(1 for review in reviews if review["decision"] == "APPROVE")
    reject_count = sum(1 for review in reviews if review["decision"] == "REJECT")
    can_apply = reject_count == 0 and (required <= 1 or approve_count >= required)
    return {
        "required": required,
        "approve_count": approve_count,
        "reject_count": reject_count,
        "remaining": max(required - approve_count, 0) if required > 1 else 0,
        "blocked": reject_count > 0,
        "can_apply": can_apply,
        "reviews": reviews,
    }


def proposal_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "proposal_type": row["proposal_type"],
        "status": row["status"],
        "payload": json_loads(row["payload"], {}),
        "result": json_loads(row["result"], {}),
        "review_reason": row["review_reason"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "reviewed_at": row["reviewed_at"],
        "review_state": proposal_review_summary(row["id"], row["project_id"]),
    }


def _proposal_payload(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    proposal_type = str(payload.get("proposal_type") or payload.get("type") or "memory_judgment")
    if isinstance(payload.get("payload"), dict):
        proposal_payload = dict(payload["payload"])
    elif isinstance(payload.get("judgment"), dict):
        proposal_payload = dict(payload["judgment"])
    else:
        reserved = {"proposal_type", "type", "payload", "judgment", "status", "review_reason"}
        proposal_payload = {key: value for key, value in payload.items() if key not in reserved}
    if not proposal_payload:
        raise HTTPException(status_code=400, detail="proposal payload is required")
    if proposal_type == "memory_judgment":
        proposal_payload["apply"] = False
        return proposal_type, proposal_payload
    if proposal_type == "entity_alias":
        entity = str(proposal_payload.get("entity") or proposal_payload.get("canonical") or "").strip()
        alias = str(proposal_payload.get("alias") or "").strip()
        if not entity or not alias:
            raise HTTPException(status_code=400, detail="entity and alias are required")
        normalized_entity = normalize_entity(entity)
        normalized_alias = normalize_entity(alias)
        if not normalized_entity or not normalized_alias:
            raise HTTPException(status_code=400, detail="entity and alias are required")
        if normalized_entity == normalized_alias:
            raise HTTPException(status_code=400, detail="alias must differ from entity")
        result = {
            "entity": entity,
            "alias": alias,
            "entity_type": proposal_payload.get("entity_type") or proposal_payload.get("entityType") or "concept",
        }
        evidence = proposal_payload.get("evidence") or proposal_payload.get("metadata")
        if isinstance(evidence, dict):
            result["evidence"] = evidence
        return proposal_type, result
    if proposal_type in {"memory_compression", "compression"}:
        memory_ids = proposal_payload.get("memory_ids") or proposal_payload.get("source_memory_ids") or []
        if not isinstance(memory_ids, list):
            raise HTTPException(status_code=400, detail="memory_ids must be a list")
        ids = []
        seen = set()
        for memory_id in memory_ids:
            value = str(memory_id).strip()
            if value and value not in seen:
                seen.add(value)
                ids.append(value)
        if len(ids) < 2:
            raise HTTPException(status_code=400, detail="at least two memory_ids are required")
        return "memory_compression", {
            "memory_ids": ids,
            "strategy": proposal_payload.get("strategy") or "same_subject_predicate_merge",
        }
    if proposal_type in {"activation_rollback_override", "rollback_override"}:
        activation_id = str(proposal_payload.get("activation_id") or "").strip()
        reason = str(proposal_payload.get("reason") or proposal_payload.get("override_reason") or "").strip()
        requested_by = str(proposal_payload.get("requested_by") or proposal_payload.get("requester") or "operator").strip()
        if not activation_id:
            raise HTTPException(status_code=400, detail="activation_id is required")
        return "activation_rollback_override", {
            "activation_id": activation_id,
            "reason": reason,
            "requested_by": requested_by,
        }
    if proposal_type in {"promotion_audit_retention_apply", "audit_retention_apply"}:
        try:
            older_than_days = int(proposal_payload.get("older_than_days", proposal_payload.get("olderThanDays", 30)))
            limit = int(proposal_payload.get("limit", 500))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="older_than_days and limit must be integers") from exc
        return "promotion_audit_retention_apply", {
            "older_than_days": max(older_than_days, 0),
            "limit": min(max(limit, 1), 5000),
            "requested_by": str(proposal_payload.get("requested_by") or proposal_payload.get("requestedBy") or "operator"),
        }
    raise HTTPException(status_code=400, detail="Unsupported proposal type")


def _memory_scope(memory: dict[str, Any]) -> dict[str, Any]:
    return {field: memory.get(field) for field in ENTITY_FIELDS}


def _compression_source_hash(memory: dict[str, Any]) -> str:
    return content_hash(memory.get("memory", ""), memory.get("updated_at"), memory.get("id"))


def _compression_proposal_result(payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    memory_ids = [str(memory_id) for memory_id in payload.get("memory_ids", [])]
    memories = [get_memory(memory_id, project_id=project_id) for memory_id in memory_ids]
    first_scope = _memory_scope(memories[0])
    if not all(_matches_exact_scope(memory, first_scope) for memory in memories):
        raise HTTPException(status_code=400, detail="compression sources must share the same scope")
    relations = [_fact_relation(memory["memory"]) for memory in memories]
    if not all(relations):
        raise HTTPException(status_code=400, detail="compression sources must be relation-shaped memories")
    first_relation = relations[0] or {}
    if not all(
        relation
        and relation["subject"] == first_relation["subject"]
        and relation["predicate"] == first_relation["predicate"]
        for relation in relations
    ):
        raise HTTPException(status_code=400, detail="compression sources must share subject and predicate")

    output_memory = memories[0]["memory"]
    for memory in memories[1:]:
        output_memory = _merge_fact(output_memory, memory["memory"])
    source_tokens = sum(token_estimate(memory["memory"]) for memory in memories)
    output_tokens = token_estimate(output_memory)
    source_hashes = {memory["id"]: _compression_source_hash(memory) for memory in memories}
    warnings = []
    if output_tokens >= source_tokens:
        warnings.append("no_token_savings")
    result = {
        "action": "COMPRESS_MEMORIES",
        "primary_memory_id": memories[0]["id"],
        "source_memory_ids": memory_ids,
        "source_memories": [{"id": memory["id"], "memory": memory["memory"]} for memory in memories],
        "output_memory": output_memory,
        "strategy": payload.get("strategy") or "same_subject_predicate_merge",
        "scope": {field: value for field, value in first_scope.items() if value is not None},
        "drift_check": {
            "scope_consistent": True,
            "relation_consistent": True,
            "source_hashes": source_hashes,
            "source_tokens": source_tokens,
            "output_tokens": output_tokens,
            "compression_ratio": round(output_tokens / max(source_tokens, 1), 4),
            "warnings": warnings,
        },
    }
    if _shadow_mode_enabled(payload, project_id):
        result["shadow"] = _shadow_compression(payload, result, project_id)
    return result


def _apply_compression_proposal(payload: dict[str, Any], preview: dict[str, Any], project_id: str) -> dict[str, Any]:
    primary_id = preview["primary_memory_id"]
    source_ids = [str(memory_id) for memory_id in preview["source_memory_ids"]]
    primary = get_memory(primary_id, project_id=project_id)
    compressed_at = utc_now()
    compression = {
        "source_memory_ids": source_ids,
        "strategy": preview["strategy"],
        "compressed_at": compressed_at,
        "source_memories": preview["source_memories"],
    }
    metadata = dict(primary.get("metadata") or {})
    metadata["compression"] = compression
    updated = update_memory(
        primary_id,
        {
            "project_id": project_id,
            "text": preview["output_memory"],
            "metadata": metadata,
        },
    )
    deleted_ids = []
    for memory_id in source_ids[1:]:
        delete_memory(memory_id, project_id=project_id)
        deleted_ids.append(memory_id)
    return {
        "action": "COMPRESS_MEMORIES",
        "primary_memory": updated,
        "deleted_source_memory_ids": deleted_ids,
        "compression": compression,
        "drift_check": preview["drift_check"],
    }


def _activation_rollback_override_preview(payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    gate = _activation_rollback_gate(project_id)
    if not gate or not gate.get("blocked"):
        raise HTTPException(status_code=409, detail="No activation rollback gate is blocking promotion")
    activation_id = str(payload.get("activation_id") or "")
    if activation_id != gate.get("activation_id"):
        raise HTTPException(status_code=409, detail="Activation rollback gate changed; create a new override request")
    return {
        "action": "OVERRIDE_ACTIVATION_ROLLBACK_GATE",
        "activation_id": activation_id,
        "deployment_id": gate.get("deployment_id"),
        "artifact_id": gate.get("artifact_id"),
        "reason": payload.get("reason") or "",
        "requested_by": payload.get("requested_by") or "operator",
        "gate": gate,
    }


def _apply_activation_rollback_override(payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    preview = _activation_rollback_override_preview(payload, project_id)
    return {
        **preview,
        "override_applied_at": utc_now(),
    }


def request_activation_rollback_override(
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    project_id = project_id or current_project_id()
    gate = _activation_rollback_gate(project_id)
    if not gate or not gate.get("blocked"):
        raise HTTPException(status_code=409, detail="No activation rollback gate is blocking promotion")
    activation_id = str(payload.get("activation_id") or gate.get("activation_id") or "")
    reason = str(payload.get("reason") or payload.get("override_reason") or "").strip()
    return create_proposal(
        {
            "proposal_type": "activation_rollback_override",
            "activation_id": activation_id,
            "reason": reason,
            "requested_by": payload.get("requested_by") or payload.get("requester") or "operator",
            "review_reason": f"activation_rollback_override:{activation_id}:{reason}",
        },
        project_id=project_id,
    )


def create_proposal(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    project_id = payload.get("project_id") or project_id or current_project_id()
    proposal_type, proposal_payload = _proposal_payload(payload)
    review_reason = str(payload.get("review_reason") or payload.get("reason") or "")
    if proposal_type == "memory_judgment":
        result = _memory_judgment_proposal_preview(proposal_payload, project_id)
    elif proposal_type == "entity_alias":
        result = {
            "entity": proposal_payload["entity"],
            "normalized_entity": normalize_entity(proposal_payload["entity"]),
            "alias": proposal_payload["alias"],
            "normalized_alias": normalize_entity(proposal_payload["alias"]),
            "entity_type": proposal_payload["entity_type"],
            "action": "CREATE_ENTITY_ALIAS",
        }
    elif proposal_type == "memory_compression":
        result = _compression_proposal_result(proposal_payload, project_id)
    elif proposal_type == "activation_rollback_override":
        result = _activation_rollback_override_preview(proposal_payload, project_id)
    elif proposal_type == "promotion_audit_retention_apply":
        result = _promotion_audit_retention_preview(proposal_payload, project_id)
    else:
        raise HTTPException(status_code=400, detail="Unsupported proposal type")
    proposal_id = str(new_id("proposal"))
    now = utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO proposals (
                id, project_id, proposal_type, status, payload, result,
                review_reason, created_at, updated_at, reviewed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal_id,
                project_id,
                proposal_type,
                "PENDING",
                json_dumps(proposal_payload),
                json_dumps(result),
                review_reason,
                now,
                now,
                None,
            ),
        )
        row = conn.execute("SELECT * FROM proposals WHERE id = ? AND project_id = ?", (proposal_id, project_id)).fetchone()
    record_usage(
        project_id,
        "proposal_create",
        input_tokens=token_estimate(proposal_payload),
        output_tokens=token_estimate(result),
        metadata={"proposal_id": proposal_id, "proposal_type": proposal_type},
    )
    return proposal_row(row)


def get_proposal(proposal_id: str, project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM proposals WHERE id = ? AND project_id = ?", (proposal_id, project_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal_row(row)


def _proposal_evidence_source(proposal: dict[str, Any]) -> str:
    payload = proposal.get("payload") if isinstance(proposal.get("payload"), dict) else {}
    result = proposal.get("result") if isinstance(proposal.get("result"), dict) else {}
    evidence = payload.get("evidence") or result.get("evidence")
    if not isinstance(evidence, dict):
        evidence = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return str(evidence.get("source") or "").strip().lower()


def list_proposals(
    status: str | None = None,
    limit: int = 100,
    project_id: str | None = None,
    proposal_type: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(limit, 1), 1000)
    params: list[Any] = [project_id]
    where = "WHERE project_id = ?"
    if status:
        where += " AND status = ?"
        params.append(status.upper())
    if proposal_type:
        where += " AND proposal_type = ?"
        params.append(str(proposal_type))
    sql_limit = limit if not source else min(max(limit * 5, 100), 1000)
    params.append(sql_limit)
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM proposals {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
    results = [proposal_row(row) for row in rows]
    if source:
        expected_source = str(source).strip().lower()
        results = [proposal for proposal in results if _proposal_evidence_source(proposal) == expected_source][:limit]
    return {"project_id": project_id, "count": len(results), "results": results}


def shadow_rollout_summary(project_id: str | None = None, limit: int = 1000) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(limit, 1), 5000)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM proposals
            WHERE project_id = ?
              AND proposal_type = 'memory_judgment'
              AND review_reason LIKE 'shadow_promotion:%'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
    proposals = [proposal_row(row) for row in rows]
    status_counts: dict[str, int] = {"PENDING": 0, "APPLIED": 0, "REJECTED": 0}
    canary_count = 0
    canary_applied = 0
    blocked_count = 0
    rollback_events: list[dict[str, Any]] = []
    for proposal in proposals:
        status = proposal["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        reviews = proposal.get("review_state", {}).get("reviews", [])
        canary_routed = any(review.get("reviewer_id") == "shadow_canary" for review in reviews)
        if canary_routed:
            canary_count += 1
            canary_applied += 1 if status == "APPLIED" else 0
        blocked_count += 1 if proposal.get("review_state", {}).get("blocked") else 0
        if status != "APPLIED" or not canary_routed:
            continue
        for result in proposal.get("result", {}).get("results", []):
            memory_id = result.get("id") if isinstance(result, dict) else None
            if not memory_id:
                continue
            with get_db() as conn:
                memory = conn.execute(
                    "SELECT id, memory, deleted, updated_at FROM memories WHERE id = ? AND project_id = ?",
                    (memory_id, project_id),
                ).fetchone()
            if memory and memory["deleted"]:
                rollback_events.append(
                    {
                        "proposal_id": proposal["id"],
                        "memory_id": memory["id"],
                        "memory": memory["memory"],
                        "deleted_at": memory["updated_at"],
                    }
                )
    reviewed = status_counts.get("APPLIED", 0) + status_counts.get("REJECTED", 0)
    precision = round(status_counts.get("APPLIED", 0) / reviewed, 4) if reviewed else 0.0
    canary_precision = round(canary_applied / canary_count, 4) if canary_count else 0.0
    return {
        "project_id": project_id,
        "total": len(proposals),
        "status_counts": status_counts,
        "reviewed": reviewed,
        "precision": precision,
        "pending_count": status_counts.get("PENDING", 0),
        "blocked_count": blocked_count,
        "canary_count": canary_count,
        "canary_applied_count": canary_applied,
        "canary_precision": canary_precision,
        "rollback_count": len(rollback_events),
        "rollback_events": rollback_events[:50],
    }


def review_proposal(proposal_id: str, payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    payload = payload or {}
    proposal = get_proposal(proposal_id, project_id=project_id)
    if proposal["status"] != "PENDING":
        raise HTTPException(status_code=409, detail="Only pending proposals can be reviewed")
    decision = str(payload.get("decision") or "APPROVE").strip().upper()
    if decision not in {"APPROVE", "REJECT"}:
        raise HTTPException(status_code=400, detail="decision must be APPROVE or REJECT")
    reviewer_id = str(payload.get("reviewer_id") or payload.get("reviewer") or "local_reviewer").strip()
    if not reviewer_id:
        raise HTTPException(status_code=400, detail="reviewer_id is required")
    reason = str(payload.get("reason") or payload.get("review_reason") or "")
    now = utc_now()
    with get_db() as conn:
        existing = conn.execute(
            """
            SELECT id FROM proposal_reviews
            WHERE project_id = ? AND proposal_id = ? AND reviewer_id = ?
            """,
            (project_id, proposal_id, reviewer_id),
        ).fetchone()
        if existing:
            review_id = existing["id"]
            conn.execute(
                """
                UPDATE proposal_reviews
                   SET decision = ?, reason = ?, updated_at = ?
                 WHERE id = ? AND project_id = ?
                """,
                (decision, reason, now, review_id, project_id),
            )
        else:
            review_id = str(new_id("review"))
            conn.execute(
                """
                INSERT INTO proposal_reviews (
                    id, project_id, proposal_id, reviewer_id, decision, reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (review_id, project_id, proposal_id, reviewer_id, decision, reason, now, now),
            )
        row = conn.execute("SELECT * FROM proposal_reviews WHERE id = ? AND project_id = ?", (review_id, project_id)).fetchone()
    summary = proposal_review_summary(proposal_id, project_id)
    record_usage(
        project_id,
        "proposal_review",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate(summary),
        metadata={"proposal_id": proposal_id, "decision": decision, "reviewer_id": reviewer_id},
    )
    return {"proposal_id": proposal_id, "review": proposal_review_row(row), "review_state": summary}


def _memory_judgment_proposal_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("facts") and "messages" not in payload:
        return {
            **payload,
            "messages": [{"role": "user", "content": str(fact)} for fact in payload.get("facts") or []],
            "infer": False,
        }
    return dict(payload)


def _memory_judgment_decision_signature(decision: dict[str, Any]) -> dict[str, Any]:
    scope = decision.get("scope") if isinstance(decision.get("scope"), dict) else {}
    target_ids = decision.get("target_memory_ids")
    if not isinstance(target_ids, list):
        target_ids = [decision["target_memory_id"]] if decision.get("target_memory_id") else []
    return {
        "candidate": str(decision.get("candidate") or ""),
        "scope": {field: scope.get(field) for field in ENTITY_FIELDS if scope.get(field) is not None},
        "decision": str(decision.get("decision") or ""),
        "target_memory_ids": [str(memory_id) for memory_id in target_ids],
        "output_memory": decision.get("output_memory"),
    }


def _memory_judgment_proposal_preview(payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    payload = _memory_judgment_proposal_payload(payload)
    if not payload.get("messages") or not isinstance(payload["messages"], list):
        raise HTTPException(status_code=400, detail="messages or facts is required")
    if not any(payload.get(field) for field in ENTITY_FIELDS):
        raise HTTPException(status_code=400, detail="At least one entity ID is required")
    infer = bool(payload.get("infer", True))
    fact_records = _fact_records(payload, project_id=project_id, infer=infer)
    memories = list_memory_dicts(project_id=project_id)
    decisions: list[dict[str, Any]] = []
    for record in fact_records:
        for scope in record["scopes"]:
            judgment = _judge_fact(record["fact"], scope, memories)
            enriched = _enrich_judgment(record["fact"], scope, memories, judgment)
            if _shadow_mode_enabled(payload, project_id):
                enriched["shadow"] = _shadow_judgment(record["fact"], scope, memories, judgment, project_id, payload)
            decisions.append(
                {
                    "candidate": record["fact"],
                    "scope": {field: scope.get(field) for field in ENTITY_FIELDS if scope.get(field) is not None},
                    **enriched,
                }
            )
    counts: dict[str, int] = {}
    for item in decisions:
        counts[item["decision"]] = counts.get(item["decision"], 0) + 1
    result = {
        "schema_version": "mem1-judgment-result-v1",
        "project_id": project_id,
        "status": "SUCCEEDED",
        "apply": False,
        "decisions": decisions,
        "decision_counts": counts,
    }
    if "shadow" in payload or "shadow_mode" in payload:
        result["shadow"] = bool(payload.get("shadow", payload.get("shadow_mode")))
    return result


def _verify_memory_judgment_proposal_not_drifted(proposal: dict[str, Any], project_id: str) -> None:
    verification = verify_judgment_evidence({"judgment_result": proposal.get("result", {})}, project_id=project_id)
    if not verification.get("valid"):
        raise HTTPException(status_code=409, detail="Memory judgment proposal drifted; create a new proposal")
    current = _memory_judgment_proposal_preview(proposal["payload"], project_id)
    expected_signatures = [
        _memory_judgment_decision_signature(decision)
        for decision in proposal.get("result", {}).get("decisions", [])
        if isinstance(decision, dict)
    ]
    current_signatures = [
        _memory_judgment_decision_signature(decision)
        for decision in current.get("decisions", [])
        if isinstance(decision, dict)
    ]
    if expected_signatures != current_signatures:
        raise HTTPException(status_code=409, detail="Memory judgment proposal changed; create a new proposal")


def apply_proposal(proposal_id: str, project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    proposal = get_proposal(proposal_id, project_id=project_id)
    if proposal["status"] != "PENDING":
        raise HTTPException(status_code=409, detail="Only pending proposals can be applied")
    review_state = proposal.get("review_state") or proposal_review_summary(proposal_id, project_id)
    if review_state.get("blocked"):
        raise HTTPException(status_code=409, detail="Proposal has a rejecting review")
    if not review_state.get("can_apply", True):
        remaining = review_state.get("remaining") or 1
        raise HTTPException(status_code=409, detail=f"Proposal requires {remaining} more approval(s)")
    if proposal["proposal_type"] == "promotion_audit_retention_apply":
        required = max(int(review_state.get("required") or 1), 1)
        approve_count = int(review_state.get("approve_count") or 0)
        if approve_count < required:
            raise HTTPException(status_code=409, detail=f"Retention apply requires {required - approve_count} more approval(s)")
    if proposal["proposal_type"] == "memory_judgment":
        _verify_memory_judgment_proposal_not_drifted(proposal, project_id)
        apply_payload = {**proposal["payload"], "apply": True}
        result = judge_memories(apply_payload, project_id=project_id)
    elif proposal["proposal_type"] == "entity_alias":
        apply_payload = proposal["payload"]
        result = create_entity_alias(apply_payload, project_id=project_id)
    elif proposal["proposal_type"] == "memory_compression":
        apply_payload = proposal["payload"]
        current_preview = _compression_proposal_result(apply_payload, project_id)
        previous_drift = proposal.get("result", {}).get("drift_check", {})
        if (
            current_preview.get("output_memory") != proposal.get("result", {}).get("output_memory")
            or current_preview.get("drift_check", {}).get("source_hashes") != previous_drift.get("source_hashes")
        ):
            raise HTTPException(status_code=409, detail="Compression proposal drifted; create a new proposal")
        result = _apply_compression_proposal(apply_payload, current_preview, project_id)
    elif proposal["proposal_type"] == "activation_rollback_override":
        apply_payload = proposal["payload"]
        result = _apply_activation_rollback_override(apply_payload, project_id)
    elif proposal["proposal_type"] == "promotion_audit_retention_apply":
        apply_payload = proposal["payload"]
        result = _apply_promotion_audit_retention(apply_payload, proposal.get("result", {}), project_id)
    else:
        raise HTTPException(status_code=400, detail="Unsupported proposal type")
    now = utc_now()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE proposals
               SET status = ?, result = ?, updated_at = ?, reviewed_at = ?
             WHERE id = ? AND project_id = ?
            """,
            ("APPLIED", json_dumps(result), now, now, proposal_id, project_id),
        )
        row = conn.execute("SELECT * FROM proposals WHERE id = ? AND project_id = ?", (proposal_id, project_id)).fetchone()
    record_usage(
        project_id,
        "proposal_apply",
        input_tokens=token_estimate(apply_payload),
        output_tokens=token_estimate(result),
        metadata={"proposal_id": proposal_id, "proposal_type": proposal["proposal_type"]},
    )
    return proposal_row(row)


def reject_proposal(proposal_id: str, payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    proposal = get_proposal(proposal_id, project_id=project_id)
    if proposal["status"] != "PENDING":
        raise HTTPException(status_code=409, detail="Only pending proposals can be rejected")
    reason = str((payload or {}).get("reason") or (payload or {}).get("review_reason") or "")
    now = utc_now()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE proposals
               SET status = ?, review_reason = ?, updated_at = ?, reviewed_at = ?
             WHERE id = ? AND project_id = ?
            """,
            ("REJECTED", reason, now, now, proposal_id, project_id),
        )
        row = conn.execute("SELECT * FROM proposals WHERE id = ? AND project_id = ?", (proposal_id, project_id)).fetchone()
    record_usage(
        project_id,
        "proposal_reject",
        input_tokens=token_estimate(payload or {}),
        metadata={"proposal_id": proposal_id, "proposal_type": proposal["proposal_type"]},
    )
    return proposal_row(row)


def create_event(event_type: str, payload: dict[str, Any], metadata: dict[str, Any] | None = None, project_id: str | None = None) -> str:
    project_id = project_id or current_project_id()
    event_id = str(new_id())
    now = utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO events (
                id, project_id, event_type, status, payload, metadata, results,
                created_at, updated_at, started_at, completed_at, latency
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                project_id,
                event_type,
                "PENDING",
                json_dumps(payload),
                json_dumps(metadata or {}),
                "[]",
                now,
                now,
                None,
                None,
                0,
            ),
        )
    return event_id


def complete_event(event_id: str, status: str, results: list[Any], started_at: str, start_time: float) -> None:
    now = utc_now()
    latency = round((time.perf_counter() - start_time) * 1000, 3)
    with get_db() as conn:
        conn.execute(
            """
            UPDATE events
               SET status = ?, results = ?, updated_at = ?, started_at = ?,
                   completed_at = ?, latency = ?
             WHERE id = ?
            """,
            (status, json_dumps(results), now, started_at, now, latency, event_id),
        )


def _record_gate_drops(
    drops: list[dict[str, Any]],
    payload: dict[str, Any],
    *,
    project_id: str,
    event_id: str | None = None,
) -> None:
    """Persist what the gate refused, so forgetting stays auditable.

    The gate is an editor and editors are power; a memory product whose
    forgetting leaves no trace asks for blind trust. The log itself must
    forget too: MEM1_GATE_LOG_DAYS (default 30, "0" disables logging).
    """
    if not drops:
        return
    days = float(os.environ.get("MEM1_GATE_LOG_DAYS", "30") or 0)
    if days <= 0:
        return
    now = utc_now()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    scope = {field: payload.get(field) for field in ENTITY_FIELDS}
    try:
        with get_db() as conn:
            for drop in drops[:50]:
                conn.execute(
                    """INSERT INTO gate_log (id, project_id, user_id, agent_id, app_id, run_id,
                                             dropped_text, role, reason, source_event_id, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (new_id("gate"), project_id, scope.get("user_id"), scope.get("agent_id"),
                     scope.get("app_id"), scope.get("run_id"), str(drop.get("text") or "")[:300],
                     str(drop.get("role") or ""), str(drop.get("reason") or "unknown"),
                     event_id, now),
                )
            conn.execute("DELETE FROM gate_log WHERE created_at < ?", (cutoff,))
    except sqlite3.Error:
        pass  # the log must never block the write path


def list_gate_log(payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    """What the observation gate dropped recently, newest first."""
    payload = payload or {}
    project_id = payload.get("project_id") or project_id or current_project_id()
    limit = max(1, min(int(payload.get("limit") or 20), 100))
    days = payload.get("days")
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    where = ["project_id = ?"]
    params: list[Any] = [project_id]
    for field in ENTITY_FIELDS:
        value = filters.get(field)
        if value:
            where.append(f"{field} = ?")
            params.append(value)
    if days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=float(days))).strftime("%Y-%m-%dT%H:%M:%SZ")
        where.append("created_at >= ?")
        params.append(cutoff)
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT dropped_text, role, reason, created_at FROM gate_log
                WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ?""",
            (*params, limit),
        ).fetchall()
    return {
        "results": [
            {"text": row["dropped_text"], "role": row["role"],
             "reason": row["reason"], "created_at": row["created_at"]}
            for row in rows
        ],
        "note": "what the gate refused to remember, and why — retention "
                + os.environ.get("MEM1_GATE_LOG_DAYS", "30") + " days",
    }


def add_accounting_violations(accounting: dict[str, Any]) -> list[str]:
    """F5 침묵 잊음 — stage-wise conservation checks for one ADD event.

    Every unit entering the pipeline must exit as a stored memory, a logged
    refusal, or a counted drop; a violation means some path loses input
    without a number. gate_log rows are sampled (50/event), so the counters,
    not the rows, are the authoritative denominator. Remote-provider
    extraction is sentence-opaque (provider_extractions marker) — for those
    events only the storage-side equations are checked.
    """
    def n(key: str) -> int:
        return int(accounting.get(key) or 0)

    violations: list[str] = []
    if not n("provider_extractions"):
        if n("facts_raw") != n("facts_extracted") + n("batch_deduped"):
            violations.append("extraction: facts_raw != facts_extracted + batch_deduped")
        if n("facts_out") != n("facts_extracted") - n("instruction_filtered"):
            violations.append("instruction: facts_out != facts_extracted - instruction_filtered")
    if n("facts_out") - n("scope_deduped") - n("sanitize_dropped") != n("records_kept"):
        violations.append("records: facts_out - scope_deduped - sanitize_dropped != records_kept")
    if n("fact_scope_pairs") != n("memories_created") + n("duplicate_skipped"):
        violations.append("storage: fact_scope_pairs != memories_created + duplicate_skipped")
    return violations


def _merge_event_metadata(event_id: str, extra: dict[str, Any]) -> None:
    try:
        with get_db() as conn:
            row = conn.execute("SELECT metadata FROM events WHERE id = ?", (event_id,)).fetchone()
            if not row:
                return
            metadata = json_loads(row["metadata"], {})
            metadata.update(extra)
            conn.execute(
                "UPDATE events SET metadata = ?, updated_at = ? WHERE id = ?",
                (json_dumps(metadata), utc_now(), event_id),
            )
    except sqlite3.Error:
        pass  # accounting must never block the write path


def add_memories(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    project_id = payload.get("project_id") or project_id or current_project_id()
    if not payload.get("messages") or not isinstance(payload["messages"], list):
        raise HTTPException(status_code=400, detail="messages is required")
    if not any(payload.get(field) for field in ENTITY_FIELDS):
        raise HTTPException(status_code=400, detail="At least one entity ID is required")
    # Every write path (MCP tools, REST /v1/memories) converges here — the one
    # place a foreign (user_id, app_id) pool cannot slip past (F4 class).
    scope_guard_warning = scope_guard.evaluate_write_scope(
        payload.get("user_id"), payload.get("app_id")
    )
    if scope_guard_warning and scope_guard.guard_mode() == "enforce":
        raise HTTPException(status_code=400, detail=scope_guard_warning)
    enforce_project_quota(project_id, "memory_write", current_auth_context())

    metadata = _metadata_from_add_payload(payload)
    if scope_guard_warning:
        metadata["scope_guard"] = "foreign"
    payload = {**payload, "metadata": metadata}
    event_id = create_event("ADD", payload, metadata, project_id=project_id)
    started_at = utc_now()
    start_time = time.perf_counter()
    infer = bool(payload.get("infer", True))
    sanitize = _add_sanitize_enabled(payload)
    gate_drops: list[dict[str, Any]] = []
    accounting: dict[str, Any] = {}
    fact_records = _fact_records(payload, project_id=project_id, infer=infer, gate_log=gate_drops, accounting=accounting)
    skipped_junk: dict[str, int] = {}
    skipped_duplicate = 0
    if sanitize:
        kept_records: list[dict[str, Any]] = []
        for record in fact_records:
            reason = low_value_memory_reason(str(record.get("fact") or ""))
            if reason:
                skipped_junk[reason] = skipped_junk.get(reason, 0) + 1
                gate_drops.append({"text": str(record.get("fact") or "")[:300],
                                   "role": "fact", "reason": f"sanitize:{reason}"})
            else:
                kept_records.append(record)
        fact_records = kept_records
    accounting["sanitize_dropped"] = sum(skipped_junk.values())
    accounting["records_kept"] = len(fact_records)
    accounting["fact_scope_pairs"] = sum(len(record["scopes"]) for record in fact_records)
    _record_gate_drops(gate_drops, payload, project_id=project_id, event_id=event_id)
    created: list[dict[str, Any]] = []
    vector_upserts: list[tuple[dict[str, Any], list[float]]] = []
    # Normalize client-supplied timestamps (mem0 v3 clients send unix ints) to
    # ISO strings — stored timestamps are compared lexicographically elsewhere.
    now_raw = payload.get("created_at") or payload.get("timestamp") or payload.get("custom_timestamp") or utc_now()
    now_parsed = parse_datetime(now_raw)
    now = now_parsed.isoformat() if now_parsed else utc_now()

    with get_db() as conn:
        for record in fact_records:
            fact = record["fact"]
            source_role = _claim_source_role(record)
            record_metadata = {**metadata, "trust": _memory_trust(source_role, fact)}
            categories = categorize(fact, metadata)
            for scope in record["scopes"]:
                primary_type = next((field for field in ("user_id", "agent_id", "app_id", "run_id") if scope.get(field)), None)
                memory_id = str(new_id())
                digest = content_hash(fact, scope.get("user_id"), scope.get("agent_id"), scope.get("app_id"), scope.get("run_id"))
                if sanitize:
                    existing = conn.execute(
                        "SELECT 1 FROM memories WHERE project_id = ? AND hash = ? AND deleted = 0 LIMIT 1",
                        (project_id, digest),
                    ).fetchone()
                    if existing:
                        skipped_duplicate += 1
                        continue
                embedding = embed_text(fact, project_id=project_id)
                conn.execute(
                    """
                    INSERT INTO memories (
                        id, project_id, memory, user_id, agent_id, app_id, run_id,
                        primary_entity_type, primary_entity_id, metadata,
                        categories, embedding, hash, created_at, updated_at, deleted
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        memory_id,
                        project_id,
                        fact,
                        scope.get("user_id"),
                        scope.get("agent_id"),
                        scope.get("app_id"),
                        scope.get("run_id"),
                        primary_type,
                        scope.get(primary_type) if primary_type else None,
                        json_dumps(record_metadata),
                        json_dumps(categories),
                        encode_embedding(embedding),
                        digest,
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO memory_history (
                        id, memory_id, project_id, event, input, old_memory, new_memory,
                        user_id, agent_id, app_id, run_id, metadata, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(new_id()),
                        memory_id,
                        project_id,
                        "ADD",
                        json_dumps(record["input"]),
                        None,
                        fact,
                        scope.get("user_id"),
                        scope.get("agent_id"),
                        scope.get("app_id"),
                        scope.get("run_id"),
                        json_dumps(record_metadata),
                        now,
                        now,
                    ),
                )
                _write_observation_and_claim(
                    conn,
                    project_id=project_id,
                    source_event_id=event_id,
                    memory_id=memory_id,
                    fact=fact,
                    record=record,
                    scope=scope,
                    metadata=record_metadata,
                    now=now,
                )
                entities = link_memory_entities(memory_id, fact, project_id, conn=conn)
                memory_record = {
                    "id": memory_id,
                    "memory": fact,
                    "project_id": project_id,
                    **scope,
                    "metadata": record_metadata,
                    "categories": categories,
                    "expiration_date": metadata.get("expiration_date"),
                    "immutable": metadata.get("immutable") is True,
                    "entities": entities,
                    "created_at": now,
                    "updated_at": now,
                }
                created.append(memory_record)
                vector_upserts.append((memory_record, embedding))

    for memory_record, embedding in vector_upserts:
        vector_upsert_memory(memory_record, embedding, project_id)
    accounting["duplicate_skipped"] = skipped_duplicate
    accounting["memories_created"] = len(created)
    violations = add_accounting_violations(accounting)
    if violations:
        accounting["identity_violations"] = violations
    _merge_event_metadata(event_id, {"accounting": accounting})
    elapsed = round((time.perf_counter() - start_time) * 1000, 3)
    complete_event(event_id, "SUCCEEDED", created, started_at, start_time)
    record_usage(
        project_id,
        "memory_add",
        input_tokens=token_estimate(payload["messages"]),
        output_tokens=token_estimate(created),
        latency=elapsed,
        event_id=event_id,
        metadata={"count": len(created)},
    )
    for memory in created:
        emit_webhook_event("memory_add", {"id": memory["id"], "data": {"memory": memory["memory"]}}, project_id=project_id)
        if memory.get("categories"):
            emit_webhook_event(
                "memory_categorize",
                {"memory_id": memory["id"], "categories": memory.get("categories", [])},
                project_id=project_id,
            )
    response = {
        "message": "Memory processing has been queued for background execution",
        "status": "PENDING",
        "event_id": event_id,
        "accounting": accounting,
    }
    if sanitize:
        response["sanitized"] = True
        response["skipped"] = {
            "junk": skipped_junk,
            "junk_total": sum(skipped_junk.values()),
            "duplicate": skipped_duplicate,
        }
    if scope_guard_warning:
        response["scope_guard"] = {"verdict": "foreign", "warning": scope_guard_warning}
    return response


def _add_sanitize_enabled(payload: dict[str, Any]) -> bool:
    value = payload.get("sanitize")
    if value is not None:
        return bool(value)
    return os.getenv("MEM1_INPUT_SANITIZE_DEFAULT", "").lower() in {"1", "true", "yes"}


def get_memories(
    filters: dict[str, Any],
    page: int = 1,
    page_size: int = 100,
    project_id: str | None = None,
    show_expired: bool = False,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    validate_filters(filters)
    if not has_entity_filter(filters):
        raise HTTPException(status_code=400, detail="filters must include at least one entity ID")
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    items = [m for m in list_memory_dicts(project_id=project_id, include_expired=show_expired) if matches_filters(m, filters)]
    count = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    next_url = f"/v3/memories/?page={page + 1}&page_size={page_size}" if end < count else None
    previous_url = f"/v3/memories/?page={page - 1}&page_size={page_size}" if page > 1 else None
    return {
        "count": count,
        "next": next_url,
        "previous": previous_url,
        "results": [strip_internal(m) for m in items[start:end]],
    }


def strip_internal(memory: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": memory["id"],
        "memory": memory["memory"],
        "user_id": memory.get("user_id"),
        "agent_id": memory.get("agent_id"),
        "app_id": memory.get("app_id"),
        "run_id": memory.get("run_id"),
        "metadata": memory.get("metadata", {}),
        "categories": memory.get("categories", []),
        "created_at": memory["created_at"],
        "updated_at": memory["updated_at"],
        "expiration_date": memory.get("expiration_date"),
        "immutable": memory.get("immutable") is True,
        **({"score": memory["score"]} if "score" in memory else {}),
    }


ENTITY_LINK_NEGATIVE_REASON_TERMS = ("entity", "link", "wrong", "noisy", "noise")


def link_memory_entities(memory_id: str, text: str, project_id: str, conn: Any | None = None) -> list[dict[str, Any]]:
    entities = extract_linked_entities(text)
    now = utc_now()
    if conn is not None:
        return _write_memory_entities(conn, memory_id, project_id, entities, now)
    with get_db() as db:
        return _write_memory_entities(db, memory_id, project_id, entities, now)


def _entity_alias_map(project_id: str, conn: Any | None = None) -> dict[str, dict[str, Any]]:
    if conn is not None:
        rows = conn.execute(
            "SELECT * FROM entity_aliases WHERE project_id = ?",
            (project_id,),
        ).fetchall()
    else:
        with get_db() as db:
            rows = db.execute(
                "SELECT * FROM entity_aliases WHERE project_id = ?",
                (project_id,),
            ).fetchall()
    aliases: dict[str, dict[str, Any]] = {}
    for row in rows:
        aliases[row["normalized_alias"]] = {
            "entity": row["entity"],
            "normalized_entity": row["normalized_entity"],
            "alias": row["alias"],
            "normalized_alias": row["normalized_alias"],
            "entity_type": row["entity_type"],
        }
    return aliases


def _canonical_entity(normalized_entity: str, aliases: dict[str, dict[str, Any]]) -> str:
    return aliases.get(normalized_entity, {}).get("normalized_entity", normalized_entity)


def _entity_family(project_id: str, entity: str) -> set[str]:
    normalized = normalize_entity(entity)
    aliases = _entity_alias_map(project_id)
    canonical = _canonical_entity(normalized, aliases)
    values = {normalized, canonical}
    values.update(alias for alias, row in aliases.items() if row["normalized_entity"] == canonical)
    return values


def alias_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "entity": row["entity"],
        "normalized_entity": row["normalized_entity"],
        "alias": row["alias"],
        "normalized_alias": row["normalized_alias"],
        "entity_type": row["entity_type"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_entity_alias(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    project_id = payload.get("project_id") or project_id or current_project_id()
    entity = str(payload.get("entity") or payload.get("canonical") or "").strip()
    alias = str(payload.get("alias") or "").strip()
    if not entity or not alias:
        raise HTTPException(status_code=400, detail="entity and alias are required")
    normalized_entity = normalize_entity(entity)
    normalized_alias = normalize_entity(alias)
    if not normalized_entity or not normalized_alias:
        raise HTTPException(status_code=400, detail="entity and alias are required")
    if normalized_entity == normalized_alias:
        raise HTTPException(status_code=400, detail="alias must differ from entity")
    now = utc_now()
    alias_id = str(new_id("alias"))
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO entity_aliases (
                id, project_id, entity, normalized_entity, alias, normalized_alias,
                entity_type, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, normalized_alias) DO UPDATE SET
                entity = excluded.entity,
                normalized_entity = excluded.normalized_entity,
                alias = excluded.alias,
                entity_type = excluded.entity_type,
                updated_at = excluded.updated_at
            """,
            (
                alias_id,
                project_id,
                entity,
                normalized_entity,
                alias,
                normalized_alias,
                payload.get("entity_type") or "concept",
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM entity_aliases WHERE project_id = ? AND normalized_alias = ?",
            (project_id, normalized_alias),
        ).fetchone()
    return alias_row(row)


def list_entity_aliases(
    project_id: str | None = None,
    entity: str | None = None,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    params: list[Any] = [project_id]
    where = "WHERE project_id = ?"
    if entity:
        family = sorted(_entity_family(project_id, entity))
        where += f" AND (normalized_entity IN ({','.join('?' for _ in family)}) OR normalized_alias IN ({','.join('?' for _ in family)}))"
        params.extend(family)
        params.extend(family)
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM entity_aliases {where} ORDER BY updated_at DESC",
            params,
        ).fetchall()
    return {"project_id": project_id, "count": len(rows), "results": [alias_row(row) for row in rows]}


def delete_entity_alias(alias_id: str, project_id: str | None = None) -> dict[str, str]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        row = conn.execute("SELECT 1 FROM entity_aliases WHERE id = ? AND project_id = ?", (alias_id, project_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Entity alias not found")
        conn.execute("DELETE FROM entity_aliases WHERE id = ? AND project_id = ?", (alias_id, project_id))
    return {"message": "Entity alias deleted successfully!"}


def _entity_link_negative_feedback(feedback: str | None, reason: str | None) -> bool:
    value = str(feedback or "").upper()
    if value not in {"NEGATIVE", "VERY_NEGATIVE"}:
        return False
    reason_tokens = str(reason or "").lower()
    return value == "VERY_NEGATIVE" or any(term in reason_tokens for term in ENTITY_LINK_NEGATIVE_REASON_TERMS)


_ENTITY_PRUNE_STATS_TTL_SECONDS = 2.0
_entity_prune_stats_cache: dict[str, tuple[float, dict[str, dict[str, int]]]] = {}


def _entity_link_prune_stats(project_id: str, aliases: dict[str, dict[str, Any]], conn: Any) -> dict[str, dict[str, int]]:
    # Called once per stored fact on the add hot path. Feedback rows are rare
    # while memory_entities grows unbounded, so (a) force the join to start
    # from the small feedback table (CROSS JOIN pins SQLite's join order) and
    # (b) cache per project for a couple of seconds so a multi-fact add pays
    # the query once. Pruning is a statistical suppressor; a 2s-stale view is
    # harmless.
    cached = _entity_prune_stats_cache.get(project_id)
    if cached and (time.monotonic() - cached[0]) < _ENTITY_PRUNE_STATS_TTL_SECONDS:
        return cached[1]
    rows = conn.execute(
        """
        SELECT me.normalized_entity, f.feedback, f.feedback_reason
          FROM feedback f CROSS JOIN memory_entities me
         WHERE me.memory_id = f.memory_id
           AND me.project_id = ?
        """,
        (project_id,),
    ).fetchall()
    stats: dict[str, dict[str, int]] = {}
    for row in rows:
        normalized = _canonical_entity(row["normalized_entity"], aliases)
        bucket = stats.setdefault(normalized, {"negative": 0, "positive": 0})
        feedback = str(row["feedback"] or "").upper()
        if feedback == "POSITIVE":
            bucket["positive"] += 1
        elif _entity_link_negative_feedback(feedback, row["feedback_reason"]):
            bucket["negative"] += 1
    _entity_prune_stats_cache[project_id] = (time.monotonic(), stats)
    return stats


def _should_prune_entity_link(normalized_entity: str, stats: dict[str, dict[str, int]], settings: dict[str, Any]) -> bool:
    if not settings.get("entity_link_prune_enabled", True):
        return False
    bucket = stats.get(normalized_entity, {})
    negative = int(bucket.get("negative", 0))
    positive = int(bucket.get("positive", 0))
    min_negative = max(int(settings.get("entity_link_prune_min_negative_feedback") or 2), 1)
    negative_ratio = float(settings.get("entity_link_prune_negative_ratio") or 0.67)
    total = negative + positive
    return negative >= min_negative and (total == 0 or (negative / total) >= negative_ratio)


def _write_memory_entities(conn: Any, memory_id: str, project_id: str, entities: list[dict[str, Any]], now: str) -> list[dict[str, Any]]:
    conn.execute("DELETE FROM memory_entities WHERE memory_id = ? AND project_id = ?", (memory_id, project_id))
    aliases = _entity_alias_map(project_id, conn=conn)
    settings = get_project_settings(project_id)
    prune_stats = _entity_link_prune_stats(project_id, aliases, conn)
    written: list[dict[str, Any]] = []
    for entity in entities:
        alias = aliases.get(entity["normalized_entity"], {})
        normalized_entity = _canonical_entity(entity["normalized_entity"], aliases)
        if _should_prune_entity_link(normalized_entity, prune_stats, settings):
            continue
        stored_entity = {
            **entity,
            "entity": alias.get("entity", entity["entity"]),
            "normalized_entity": normalized_entity,
            "entity_type": alias.get("entity_type", entity["entity_type"]),
        }
        conn.execute(
            """
            INSERT INTO memory_entities (
                id, project_id, memory_id, entity, normalized_entity,
                entity_type, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(new_id()),
                project_id,
                memory_id,
                stored_entity["entity"],
                stored_entity["normalized_entity"],
                stored_entity["entity_type"],
                entity["confidence"],
                now,
                now,
            )
        )
        written.append(stored_entity)
    return written


def feedback_quality_weight(feedback: dict[str, Any] | None) -> float:
    if not feedback:
        return 1.0
    value = str(feedback.get("feedback") or "").upper()
    if value == "POSITIVE":
        return 1.05
    if value == "NEGATIVE":
        return 0.65
    if value == "VERY_NEGATIVE":
        return 0.35
    return 1.0


def feedback_is_negative(feedback: dict[str, Any] | None) -> bool:
    return str((feedback or {}).get("feedback") or "").upper() in {"NEGATIVE", "VERY_NEGATIVE"}


def memory_entity_map(
    project_id: str,
    feedbacks: dict[str, dict[str, Any]] | None = None,
    suppress_negative: bool = False,
) -> dict[str, set[str]]:
    aliases = _entity_alias_map(project_id)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT memory_id, normalized_entity FROM memory_entities WHERE project_id = ?",
            (project_id,),
        ).fetchall()
    mapping: dict[str, set[str]] = {}
    feedbacks = feedbacks or {}
    for row in rows:
        if suppress_negative and feedback_is_negative(feedbacks.get(row["memory_id"])):
            continue
        mapping.setdefault(row["memory_id"], set()).add(_canonical_entity(row["normalized_entity"], aliases))
    return mapping


def list_entity_links(
    project_id: str | None = None,
    entity: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(limit, 1), 1000)
    params: list[Any] = [project_id]
    where = "WHERE me.project_id = ?"
    if entity:
        family = sorted(_entity_family(project_id, entity))
        where += f" AND me.normalized_entity IN ({','.join('?' for _ in family)})"
        params.extend(family)
    params.append(limit)
    aliases = _entity_alias_map(project_id)
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT me.normalized_entity, me.entity, me.entity_type, me.confidence, me.memory_id,
                   me.created_at, me.updated_at, f.feedback, f.feedback_reason
              FROM memory_entities me
              LEFT JOIN feedback f ON f.memory_id = me.memory_id
              {where}
             ORDER BY me.updated_at DESC
             LIMIT ?
            """,
            params,
        ).fetchall()
    links = []
    for row in rows:
        feedback = {"feedback": row["feedback"], "feedback_reason": row["feedback_reason"] or ""} if row["feedback"] else None
        quality_weight = feedback_quality_weight(feedback)
        confidence = float(row["confidence"])
        links.append(
            {
                "entity": row["entity"],
                "normalized_entity": _canonical_entity(row["normalized_entity"], aliases),
                "raw_normalized_entity": row["normalized_entity"],
                "entity_type": row["entity_type"],
                "confidence": confidence,
                "effective_confidence": round(confidence * quality_weight, 4),
                "quality_weight": quality_weight,
                "feedback": row["feedback"],
                "feedback_reason": row["feedback_reason"] or "",
                "memory_id": row["memory_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
    grouped: dict[str, dict[str, Any]] = {}
    for link in links:
        key = link["normalized_entity"]
        bucket = grouped.setdefault(
            key,
            {
                "entity": link["entity"],
                "normalized_entity": key,
                "entity_type": link["entity_type"],
                "memory_count": 0,
                "memory_ids": [],
                "positive_memory_count": 0,
                "negative_memory_count": 0,
                "max_confidence": 0.0,
                "max_effective_confidence": 0.0,
                "average_quality_weight": 0.0,
                "_quality_total": 0.0,
            },
        )
        bucket["memory_count"] += 1
        bucket["memory_ids"].append(link["memory_id"])
        if link["feedback"] == "POSITIVE":
            bucket["positive_memory_count"] += 1
        if link["feedback"] in {"NEGATIVE", "VERY_NEGATIVE"}:
            bucket["negative_memory_count"] += 1
        bucket["max_confidence"] = max(bucket["max_confidence"], link["confidence"])
        bucket["max_effective_confidence"] = max(bucket["max_effective_confidence"], link["effective_confidence"])
        bucket["_quality_total"] += link["quality_weight"]
    entities = list(grouped.values())
    for bucket in entities:
        bucket["average_quality_weight"] = round(bucket.pop("_quality_total") / max(bucket["memory_count"], 1), 4)
    return {"project_id": project_id, "count": len(grouped), "entities": entities, "links": links}


def _project_retrieval_criteria(project_id: str) -> list[dict[str, Any]]:
    """Validated project-level retrieval criteria used for weighted search scoring."""
    settings = get_project_settings(project_id)
    raw = settings.get("retrieval_criterias")
    criteria: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        description = str(item.get("description") or "").strip()
        if not name and not description:
            continue
        try:
            weight = float(item.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 1.0
        if weight <= 0:
            continue
        criteria.append({"name": name or description, "description": description or name, "weight": weight})
    return criteria


def _criteria_weighted_score(
    memory: dict[str, Any],
    criteria: list[dict[str, Any]],
    reference_date: Any = None,
) -> tuple[float, dict[str, Any]]:
    total_weight = sum(item["weight"] for item in criteria)
    if total_weight <= 0:
        return 0.0, {}
    breakdown: dict[str, Any] = {}
    weighted_total = 0.0
    for item in criteria:
        criterion_query = f"{item['name']} {item['description']}".strip()
        criterion_score = score_memory(criterion_query, memory, reference_date=reference_date)
        breakdown[item["name"]] = {"score": criterion_score, "weight": item["weight"]}
        weighted_total += criterion_score * item["weight"]
    return round(weighted_total / total_weight, 4), breakdown


def memory_relations(memories: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Deterministic graph relations extracted from memory facts for enable_graph responses."""
    relations: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for memory in memories:
        relation = _fact_relation(str(memory.get("memory") or ""))
        if not relation:
            continue
        key = (relation["subject"], relation["predicate"], relation["detail"])
        if key in seen:
            continue
        seen.add(key)
        relations.append(
            {
                "source": relation["subject"],
                "relationship": relation["predicate"],
                "target": relation["detail"],
            }
        )
    return relations


def _reflex_angles(query: str) -> list[str]:
    """Multi-angle query expansion without an LLM (Recall v2, reflex layer).

    The store is personal-scale, so extra scans are nearly free. Angles:
    the query itself, its salient-term digest, and up to three individual
    salient terms — different angles sample different embedding
    neighborhoods and different keyword hits.
    """
    from .utils import tokenize

    tokens = tokenize(query)
    seen: set[str] = set()
    unique = [t for t in tokens if not (t in seen or seen.add(t))]
    # Longer tokens carry more signal ("payments" over "did"); generic verbs
    # survive tokenize's stopword list but rarely survive a length sort.
    salient = sorted((t for t in unique if len(t) >= 4), key=len, reverse=True)
    angles = [query]
    if len(salient) >= 2:
        angles.append(" ".join(salient[:8]))
    angles.extend(salient[:3])
    deduped: list[str] = []
    for angle in angles:
        if angle and angle.lower() not in {a.lower() for a in deduped}:
            deduped.append(angle)
    return deduped[:5]


def _reflex_mmr(candidates: list[dict[str, Any]], k: int, diversity: float = 0.35) -> list[dict[str, Any]]:
    """Greedy MMR on token overlap — 'k different pieces of evidence', not
    'k neighbors of the same moment'. Embedding-free: Jaccard on token sets
    is enough to stop near-duplicates from monopolizing the budget."""
    from .utils import tokenize

    token_sets = [set(tokenize(str(c.get("memory") or ""))) for c in candidates]
    picked: list[int] = []
    while candidates and len(picked) < k:
        best_i, best_val = None, None
        for i, candidate in enumerate(candidates):
            if i in picked:
                continue
            relevance = float(candidate.get("_rrf") or 0.0)
            redundancy = max(
                (len(token_sets[i] & token_sets[j]) / max(len(token_sets[i] | token_sets[j]), 1) for j in picked),
                default=0.0,
            )
            value = (1 - diversity) * relevance - diversity * redundancy
            if best_val is None or value > best_val:
                best_i, best_val = i, value
        picked.append(best_i)
    return [candidates[i] for i in picked]


def _search_memories_reflex(payload: dict[str, Any], project_id: str | None) -> dict[str, Any]:
    """Recall v2 reflex layer: multi-angle → RRF merge → MMR selection.

    Opt-in (MEM1_RECALL_V2=reflex or payload recall="reflex"); each angle
    reuses the v1 scoring pipeline unchanged, so this wraps rather than
    forks the ranking logic. RRF merges by rank (score scales across
    different queries are not comparable); MMR spends the final budget on
    diverse evidence.
    """
    query = str(payload.get("query") or "").strip()
    top_k = int(payload.get("top_k") or 10)
    wide_k = max(top_k * 4, 24)
    base = {key: value for key, value in payload.items() if key not in {"recall"}}
    merged: dict[str, dict[str, Any]] = {}
    for angle in _reflex_angles(query):
        try:
            outcome = search_memories({**base, "query": angle, "top_k": wide_k, "recall": "v1"}, project_id)
        except HTTPException:
            continue
        for rank, memory in enumerate(outcome.get("results") or [], 1):
            memory_id = str(memory.get("id") or "")
            entry = merged.setdefault(memory_id, dict(memory))
            entry["_rrf"] = float(entry.get("_rrf") or 0.0) + 1.0 / (60 + rank)
    candidates = sorted(merged.values(), key=lambda m: float(m.get("_rrf") or 0.0), reverse=True)[: wide_k]
    selected = _reflex_mmr(candidates, top_k)
    for memory in selected:
        memory.pop("_rrf", None)
    return {"results": selected, "recall_layer": "reflex-v2"}


_RECALL_LLM_CACHE: dict[str, Any] = {"at": 0.0, "value": None}


def _pick_local_model(models: list[Any]) -> str | None:
    names = [str(m) for m in models if m]
    for preference in ("qwen", "llama", "gemma", "mistral", "phi"):
        for name in names:
            if preference in name.lower() and "embed" not in name.lower():
                return name
    return names[0] if names else None


def _detect_local_llm() -> dict[str, Any] | None:
    """Attach to a local runtime if one is already running — never install.
    An absent runtime is a product surface, not an error: deep recall simply
    stays off until the user brings a local LLM or a hosted plan."""
    import urllib.request as _urllib

    probes = [
        ("http://127.0.0.1:11434", "/api/tags", "models", "name", "ollama"),
        ("http://127.0.0.1:1234", "/v1/models", "data", "id", "lm-studio"),
    ]
    for origin, path, list_key, name_key, token in probes:
        try:
            with _urllib.urlopen(f"{origin}{path}", timeout=0.5) as response:
                body = json_loads(response.read().decode("utf-8"), {})
            model = _pick_local_model([m.get(name_key) for m in body.get(list_key) or []])
            if model:
                return {"base_url": f"{origin}/v1", "model": model, "api_key": token, "source": token}
        except Exception:
            continue
    return None


def _resolve_recall_llm() -> dict[str, Any] | None:
    """The recall gears' LLM, resolved down a ladder: env override →
    stored settings → auto-detected local runtime → None (v1 fallback)."""
    base_url = os.getenv("MEM1_GATE_BASE_URL", "").rstrip("/")
    model = os.getenv("MEM1_GATE_MODEL", "")
    if base_url and model:
        api_key = os.environ.get(os.getenv("MEM1_GATE_API_KEY_ENV", "MEM1_GATE_API_KEY"), "")
        if not api_key:
            key_file = os.getenv("MEM1_GATE_API_KEY_FILE", "")
            if key_file and os.path.exists(key_file):
                api_key = open(key_file).read().strip()
        return {"base_url": base_url, "model": model, "api_key": api_key, "source": "env"}
    from .providers import get_project_settings

    stored = get_project_settings().get("recall_llm") or {}
    if stored.get("base_url") and stored.get("model"):
        api_key = str(stored.get("api_key") or "")
        key_file = str(stored.get("api_key_file") or "")
        if not api_key and key_file and os.path.exists(key_file):
            api_key = open(key_file).read().strip()
        return {
            "base_url": str(stored["base_url"]).rstrip("/"),
            "model": str(stored["model"]),
            "api_key": api_key,
            "source": "settings",
        }
    now = time.time()
    if now - float(_RECALL_LLM_CACHE["at"]) < 300:
        return _RECALL_LLM_CACHE["value"]
    detected = _detect_local_llm()
    _RECALL_LLM_CACHE.update({"at": now, "value": detected})
    return detected


def _search_memories_gate(payload: dict[str, Any], project_id: str | None, wide_k: int = 40, snippet_chars: int = 280, layer: str = "gate-v2") -> dict[str, Any]:
    """Recall v2 'high' gear: wide hybrid retrieval, then a small LLM reads
    the candidates and keeps only what the question actually needs.

    The measured prize (2026-08-04, stratified V1 eval): gold sits in ranks
    7-40 for +7.5pp of questions — a selector's job, not a retriever's.
    Config via env (experimental): MEM1_GATE_BASE_URL, MEM1_GATE_MODEL,
    MEM1_GATE_API_KEY_ENV. Any failure degrades to the v1 top-k.
    """
    import urllib.request as _urllib

    query = str(payload.get("query") or "").strip()
    top_k = int(payload.get("top_k") or 10)
    base = {key: value for key, value in payload.items() if key != "recall"}
    wide = search_memories({**base, "top_k": wide_k, "recall": "v1"}, project_id)
    candidates = list(wide.get("results") or [])
    if len(candidates) <= top_k:
        return {"results": candidates, "recall_layer": f"{layer}(passthrough)"}
    llm = _resolve_recall_llm()
    if not llm:
        return {"results": candidates[:top_k], "recall_layer": f"{layer}(unconfigured→v1)"}
    base_url, model, api_key = llm["base_url"], llm["model"], llm["api_key"]
    numbered = "\n".join(
        f"[{i}] {str(c.get('memory') or '')[:snippet_chars]}" for i, c in enumerate(candidates)
    )
    prompt = (
        "Question: " + query + "\n\nCandidate memories:\n" + numbered +
        f"\n\nReturn ONLY a JSON array of up to {top_k} candidate indices that contain "
        "information needed to answer the question, most useful first. Example: [3,17,0]"
    )
    try:
        request = _urllib.Request(
            f"{base_url}/chat/completions",
            data=json_dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 256,
                "temperature": 0,
                "chat_template_kwargs": {"enable_thinking": False},
            }).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        )
        with _urllib.urlopen(request, timeout=60) as response:
            body = json_loads(response.read().decode("utf-8"), {})
            content = str(((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        match = re.search(r"\[[\d,\s]*\]", content)
        parsed = json_loads(match.group(0), []) if match else []
        indices = [i for i in parsed if isinstance(i, int) and 0 <= i < len(candidates)]
    except Exception:
        indices = []
    if not indices:
        return {"results": candidates[:top_k], "recall_layer": f"{layer}(fallback→v1)"}
    seen: set[int] = set()
    ordered = [i for i in indices if not (i in seen or seen.add(i))][:top_k]
    for i in range(len(candidates)):
        if len(ordered) >= top_k:
            break
        if i not in seen:
            ordered.append(i)
            seen.add(i)
    return {"results": [candidates[i] for i in ordered], "recall_layer": layer}


def search_memories(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    project_id = payload.get("project_id") or project_id or current_project_id()
    recall_mode = str(payload.get("recall") or os.getenv("MEM1_RECALL_V2") or "").strip().lower()
    if not recall_mode:
        from .providers import get_project_settings

        recall_mode = str(get_project_settings(project_id).get("recall_default") or "").strip().lower()
    # Dial names are the stable contract (docs/recall-v2.md); mechanisms are
    # disposable incumbents. Measured 2026-08-04 (stratified V1 eval):
    # v1 0.892 / gate 0.950 / reader 0.967, ceiling@100 0.992.
    recall_mode = {"low": "", "medium": "", "high": "gate", "extra": "reader"}.get(recall_mode, recall_mode)
    if recall_mode == "reflex":
        return _search_memories_reflex(payload, project_id)
    if recall_mode == "gate":
        return _search_memories_gate(payload, project_id)
    if recall_mode == "reader":
        # 'extra' gear: one decade up from gate — the LLM reads ~100
        # candidates at near-full text instead of 40 keyhole snippets.
        # Measured prize (2026-08-04): gold recall@100 = 0.992 vs @40 0.967.
        return _search_memories_gate(payload, project_id, wide_k=100, snippet_chars=500, layer="reader-v2")
    started_at = utc_now()
    start_time = time.perf_counter()
    query = str(payload.get("query") or "").strip()
    filters = payload.get("filters") or {}
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    validate_filters(filters)
    if not has_entity_filter(filters):
        raise HTTPException(status_code=400, detail="filters must include at least one entity ID")
    enforce_project_quota(project_id, "memory_search", current_auth_context())
    top_k = _validated_search_top_k(payload)
    threshold = _validated_search_threshold(payload)
    rerank = bool(payload.get("rerank", False))
    show_expired = bool(payload.get("show_expired", False))
    keyword_search = bool(payload.get("keyword_search", False))
    filter_memories_enabled = bool(payload.get("filter_memories", False))
    retrieval_criteria = _project_retrieval_criteria(project_id)
    memory_as_of = str(
        payload.get("memory_as_of")
        or payload.get("memoryAsOf")
        or payload.get("as_of")
        or payload.get("asOf")
        or ""
    ).strip()
    reference_date = payload.get("reference_date") or memory_as_of or None
    scope_fallback = _scope_fallback_enabled(payload)
    query_embedding = embed_text(query, project_id=project_id, role="query")
    vector_hits = vector_search_memories(query_embedding, filters, top_k, project_id)
    vector_scores = {hit["id"]: float(hit.get("score") or 0.0) for hit in vector_hits}
    aliases = _entity_alias_map(project_id)
    query_entities = {_canonical_entity(entity["normalized_entity"], aliases) for entity in extract_linked_entities(query)}
    feedbacks = memory_feedback_map(project_id)
    entity_links = memory_entity_map(project_id, feedbacks=feedbacks, suppress_negative=True)
    scored: list[dict[str, Any]] = []
    candidates = list_memory_dicts(
        project_id=project_id,
        include_expired=show_expired,
        entity_prefilter=_simple_entity_prefilter(filters),
    )
    batch_vector_scores = _batch_cosine_scores(query_embedding, candidates)
    temporal_rerank = _temporal_rerank_enabled(payload, project_id)
    scored_embeddings: dict[str, list[float] | None] = {}
    superseded_ids: set[str] = set()
    for memory in candidates:
        if memory_as_of and (
            str(memory.get("created_at") or "") > memory_as_of
            or str(memory.get("updated_at") or "") > memory_as_of
        ):
            continue
        in_primary_scope = matches_filters(memory, filters)
        if not in_primary_scope and not (scope_fallback and _scope_fallback_eligible(memory, filters)):
            continue
        rule_score = score_memory(query, memory, reference_date=reference_date)
        vector_score = vector_scores.get(memory["id"])
        if vector_score is None:
            vector_score = batch_vector_scores.get(memory["id"])
        if vector_score is None:
            memory_embedding = memory.get("_embedding") or deterministic_embedding(memory.get("memory", ""))
            vector_score = cosine_similarity(query_embedding, memory_embedding)
        rule_weight, vector_weight = _search_score_weights()
        score = round((rule_score * rule_weight) + (vector_score * vector_weight), 4)
        score_breakdown: dict[str, Any] = {"rule": rule_score, "vector": round(float(vector_score), 4)}
        entity_overlap = query_entities.intersection(entity_links.get(memory["id"], set()))
        if entity_overlap:
            score = min(1.0, round(score + min(0.14, 0.06 * len(entity_overlap)), 4))
            score_breakdown["entity_boost"] = min(0.14, 0.06 * len(entity_overlap))
        keyword_score_value = 0.0
        if keyword_search or filter_memories_enabled:
            keyword_score_value = keyword_overlap_score(query, memory.get("memory", ""))
        if keyword_search and keyword_score_value:
            score = min(1.0, round(score + (0.3 * keyword_score_value), 4))
            score_breakdown["keyword"] = keyword_score_value
        if retrieval_criteria:
            criteria_score, criteria_breakdown = _criteria_weighted_score(memory, retrieval_criteria, reference_date=reference_date)
            score = round(min(1.0, (score * 0.6) + (criteria_score * 0.4)), 4)
            score_breakdown["criteria"] = criteria_breakdown
        if rerank:
            score = rerank_score(query, memory, score, reference_date=reference_date)
        score = feedback_adjusted_score(score, feedbacks.get(memory["id"]))
        if (memory.get("metadata") or {}).get("superseded_at"):
            # Supersession is a deterministic, agent-issued staleness signal
            # (unlike the inferred harmful penalty), so demote hard — but
            # never remove: "did X change?" questions still need the old
            # fact retrievable, annotated as superseded.
            score = round(score * _superseded_score_multiplier(), 4)
            score_breakdown["superseded"] = True
            superseded_ids.add(memory["id"])
        if (memory.get("metadata") or {}).get("hook"):
            # Session-capture entries are pointers for rehydration, not facts.
            # They quote user utterances verbatim (green/tool), so left at full
            # weight they outrank real memories for the very queries those
            # utterances asked about. Demote; lexical match still surfaces
            # them when the session itself is what's being hunted.
            score = round(score * 0.5, 4)
            score_breakdown["session_capture"] = True
        if not in_primary_scope:
            # Shared-scope knowledge blends in slightly discounted, so a
            # strong primary-scope hit always outranks an equal fallback one.
            score = round(score * 0.88, 4)
        if filter_memories_enabled and rule_score < 0.18 and keyword_score_value < 0.34 and not entity_overlap:
            continue
        if score >= threshold:
            item = strip_internal(memory)
            item["score"] = score
            memory_meta = memory.get("metadata") or {}
            trust = memory_meta.get("trust")
            if memory_meta.get("superseded_at"):
                trust = {**(trust or {}), "light": "red", "note": "superseded — reference only, prefer the newer fact"}
            if trust:
                item["trust"] = trust
            if not in_primary_scope:
                item["scope"] = "fallback"
                item["scope_source"] = next(
                    (f"{field}:{memory.get(field)}" for field in ENTITY_FIELDS if memory.get(field)),
                    "project",
                )
            if keyword_search or filter_memories_enabled or retrieval_criteria:
                item["score_breakdown"] = score_breakdown
            if temporal_rerank:
                scored_embeddings[memory["id"]] = memory.get("_embedding")
            scored.append(item)
    scored.extend(_task_state_search_results(query, filters, project_id, top_k, threshold, as_of=memory_as_of))
    if rerank:
        scored = rerank_memory_results(query, scored, project_id=project_id, top_n=top_k)
    scored.sort(key=lambda item: (item["score"], item["updated_at"]), reverse=True)
    if temporal_rerank:
        adjusted = _promote_newer_siblings(scored, scored_embeddings, superseded_ids, project_id)
        adjusted += _demote_stale_siblings(scored, scored_embeddings, superseded_ids, project_id)
        if adjusted:
            scored.sort(key=lambda item: (item["score"], item["updated_at"]), reverse=True)
    event_id = create_event("SEARCH", payload, {"top_k": top_k, "threshold": threshold}, project_id=project_id)
    complete_event(event_id, "SUCCEEDED", scored[:top_k], started_at, start_time)
    record_usage(
        project_id,
        "memory_search",
        input_tokens=token_estimate(query),
        output_tokens=token_estimate(scored[:top_k]),
        latency=round((time.perf_counter() - start_time) * 1000, 3),
        event_id=event_id,
        metadata={"top_k": top_k, "result_count": len(scored[:top_k])},
    )
    return {"results": scored[:top_k]}


def _scope_fallback_enabled(payload: dict[str, Any]) -> bool:
    value = payload.get("scope_fallback")
    if value is not None:
        return bool(value)
    return os.getenv("MEM1_SCOPE_FALLBACK_DEFAULT", "").lower() in {"1", "true", "yes"}


def _scope_fallback_requested_user_id(filters: dict[str, Any] | None) -> str | None:
    if not isinstance(filters, dict):
        return None
    requested = filters.get("user_id")
    if isinstance(requested, str) and requested:
        return requested
    for part in filters.get("AND") or []:
        found = _scope_fallback_requested_user_id(part if isinstance(part, dict) else None)
        if found:
            return found
    return None


def _strip_entity_conditions(filters: Any) -> Any:
    """The non-entity remainder of a filter tree — what fallback must still honor.

    Scope fallback exists to relax WHO may see a row (entity scope: user_id,
    agent_id, app_id, run_id). Every other condition — metadata layers, dates,
    categories — is a content boundary the caller asked for, and fallback
    re-admitting rows past it is a leak (found 2026-08-01 while layering
    project scope: another project's rows re-entered as discounted hits).
    """
    if not isinstance(filters, dict):
        return filters
    stripped: dict[str, Any] = {}
    for key, value in filters.items():
        if key in ENTITY_FIELDS:
            continue
        if key in {"AND", "OR"} and isinstance(value, list):
            parts = [_strip_entity_conditions(part) for part in value]
            parts = [part for part in parts if part]
            if parts:
                stripped[key] = parts
            continue
        if key == "NOT":
            parts = value if isinstance(value, list) else [value]
            kept = [part for part in (_strip_entity_conditions(p) for p in parts) if part]
            if kept:
                stripped[key] = kept
            continue
        stripped[key] = value
    return stripped


def _scope_fallback_eligible(memory: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    # user_id is a privacy boundary between the customer's end users:
    # fallback may only surface shared rows (no user_id — agent/app/run
    # scoped knowledge) or rows belonging to the requesting user. Another
    # user's personal memories never enter through fallback.
    memory_user = memory.get("user_id")
    if memory_user not in (None, "") and memory_user != _scope_fallback_requested_user_id(filters):
        return False
    # Fallback relaxes entity scope only; content conditions still bind.
    return matches_filters(memory, _strip_entity_conditions(filters))


def _semantic_embedding_active() -> bool:
    provider = (os.getenv("MEM1_EMBEDDING_PROVIDER") or "").strip().lower()
    return bool(provider) and provider not in {"local", "deterministic"}


def _search_score_weights() -> tuple[float, float]:
    # The legacy 0.72/0.28 rule/vector split dates from the deterministic
    # hash-bag fallback era, when the vector channel carried almost no
    # meaning. With a real semantic model the vector becomes the stronger
    # signal (2026-07-04 real-corpus eval: 3/6 queries ranked strictly
    # better in pure semantic order, 0/6 worse), so rebalance toward it —
    # but only when a semantic provider is actually active.
    if _semantic_embedding_active():
        return 0.45, 0.55
    return 0.72, 0.28


def memory_feedback_map(project_id: str) -> dict[str, dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT f.memory_id, f.feedback, f.feedback_reason, f.created_at, f.metadata
              FROM feedback f
              JOIN memories m ON m.id = f.memory_id
             WHERE m.project_id = ? AND m.deleted = 0
            """,
            (project_id,),
        ).fetchall()
    feedback_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        metadata = json_loads(item.get("metadata"), {})
        item["metadata"] = metadata if isinstance(metadata, dict) else {}
        feedback_map[row["memory_id"]] = item
    return feedback_map


def _superseded_score_multiplier() -> float:
    return _float_or(os.getenv("MEM1_SUPERSEDED_SCORE_MULT"), 0.45)


def _temporal_rerank_enabled(payload: dict[str, Any], project_id: str | None = None) -> bool:
    """Payload wins, then the env kill/force switch, then the project setting.

    The project setting is how a tenant opts in durably (dogfood first);
    the payload override keeps benchmark arms independent of it."""
    value = payload.get("temporal_rerank")
    if value is not None:
        return bool(value)
    env = (os.getenv("MEM1_TEMPORAL_RERANK") or "").strip().lower()
    if env in {"1", "true", "yes"}:
        return True
    if env in {"0", "false", "no"}:
        return False
    if project_id:
        return bool(get_project_settings(project_id).get("temporal_rerank"))
    return False


def _stale_sibling_params(project_id: str | None = None) -> tuple[float, float, float, int]:
    mult = _float_or(os.getenv("MEM1_STALE_SIBLING_SCORE_MULT"), 0.55)
    # same floor as stale-candidates: "same fact, different wording" pairs
    # sit at ~0.80+ on the production embedding's (cos+1)/2 scale
    min_similarity = _float_or(os.getenv("MEM1_STALE_SIBLING_MIN_SIMILARITY"), 0.80)
    min_days = _temporal_min_days(project_id)
    window = int(_float_or(os.getenv("MEM1_STALE_SIBLING_WINDOW"), 400))
    return mult, min_similarity, min_days, window


def _temporal_min_days(project_id: str | None = None) -> float:
    """Tenant timescale for "meaningfully newer".

    STALE-style archives span years (default 14d is safe there), but a young
    dogfood corpus goes stale in days — a fixed global floor makes the whole
    temporal machinery inert for exactly the tenants who feel staleness most
    (measured 2026-07-07: an 8-day-old corpus produced zero rerank activity).
    Project setting `temporal_min_days` wins; env keeps the global fallback."""
    if project_id:
        configured = get_project_settings(project_id).get("temporal_min_days")
        if configured is not None:
            try:
                return max(0.25, float(configured))
            except (TypeError, ValueError):
                pass
    return _float_or(os.getenv("MEM1_STALE_SIBLING_MIN_DAYS"), 14.0)


def _sibling_promotion_params() -> tuple[float, float, float, int, int]:
    # replacement facts live in a similarity BAND around their anchor:
    # worded differently than the state they replace, so they sit below
    # near-duplicate echoes but above unrelated noise (STALE diag1 measured
    # anchor→replacement at 0.73–0.85 on bge-m3's scaled cosine, while
    # templated chat echoes cluster at 0.9+)
    min_similarity = _float_or(os.getenv("MEM1_TEMPORAL_PROMOTE_MIN_SIMILARITY"), 0.73)
    max_similarity = _float_or(os.getenv("MEM1_TEMPORAL_PROMOTE_MAX_SIMILARITY"), 0.92)
    score_mult = _float_or(os.getenv("MEM1_TEMPORAL_PROMOTE_SCORE_MULT"), 0.92)
    anchors = int(_float_or(os.getenv("MEM1_TEMPORAL_PROMOTE_ANCHORS"), 25))
    max_promotions = int(_float_or(os.getenv("MEM1_TEMPORAL_PROMOTE_MAX"), 4))
    return min_similarity, max_similarity, score_mult, anchors, max_promotions


def _promote_newer_siblings(
    scored: list[dict[str, Any]],
    embeddings_by_id: dict[str, list[float] | None],
    superseded_ids: set[str],
    project_id: str | None = None,
) -> int:
    """The recall half of temporal rerank: each strong hit acts as an anchor
    that pulls its newest sufficiently-similar sibling up next to itself.

    A query phrased around an outdated state ranks the old rows high while
    the replacement fact — worded differently — can sit hundreds of ranks
    deep (STALE diag1: median ~160 of ~7,000, some beyond 1,000). Demotion
    alone cannot recover it: the rows above the replacement are mostly
    unrelated, so clearing a stale copy or two moves it a place or two.
    Following the anchor's embedding neighborhood forward in time surfaces
    the replacement regardless of its own query score; the answerer then
    sees both states with their timestamps. Superseded rows never get
    promoted — supersession says they lost to a successor already.
    """
    min_similarity, max_similarity, score_mult, anchor_count, max_promotions = _sibling_promotion_params()
    _, _, min_days, _ = _stale_sibling_params(project_id)
    pool = [
        item
        for item in scored
        if isinstance(embeddings_by_id.get(item.get("id")), list) and embeddings_by_id[item["id"]]
    ]
    if len(pool) < 2:
        return 0
    dims = {len(embeddings_by_id[item["id"]]) for item in pool}
    if len(dims) > 1:
        majority = max(dims, key=lambda d: sum(1 for item in pool if len(embeddings_by_id[item["id"]]) == d))
        pool = [item for item in pool if len(embeddings_by_id[item["id"]]) == majority]
        if len(pool) < 2:
            return 0
    try:
        import numpy as np
    except ImportError:
        np = None
    if np is not None:
        matrix = np.asarray([embeddings_by_id[item["id"]] for item in pool], dtype=np.float64)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        unit = matrix / norms
    else:
        unit = _unit_rows([embeddings_by_id[item["id"]] for item in pool])
    epochs: list[float | None] = []
    for item in pool:
        created = parse_datetime(item.get("created_at")) or parse_datetime(item.get("updated_at"))
        epochs.append(created.timestamp() if created is not None else None)
    promotable = [item.get("id") not in superseded_ids for item in pool]
    index_by_id = {item["id"]: i for i, item in enumerate(pool)}
    promotions = 0
    for anchor in scored[: max(anchor_count, 0)]:
        if promotions >= max_promotions:
            break
        anchor_index = index_by_id.get(anchor.get("id"))
        if anchor_index is None or epochs[anchor_index] is None:
            continue
        if np is not None:
            similarities = ((unit @ unit[anchor_index] + 1.0) / 2.0).tolist()
        else:
            anchor_row = unit[anchor_index]
            similarities = [
                (sum(a * b for a, b in zip(row, anchor_row)) + 1.0) / 2.0
                for row in unit
            ]
        # band-pass: above the ceiling is a near-duplicate echo of the anchor
        # (same stale content, no news value — templated chat rows especially),
        # below the floor is a different topic; the replacement register the
        # diag1 A/B was after lives in between
        newer_floor = epochs[anchor_index] + min_days * 86400.0
        # most-similar-in-band wins (stay on the anchor's topic), newest
        # breaks ties — newest-first let any recent above-floor row hijack
        # the slot in a large noisy corpus (caught by the diag1 A/B)
        chosen, chosen_key = None, None
        for j, similarity in enumerate(similarities):
            if j == anchor_index or not promotable[j] or epochs[j] is None:
                continue
            if epochs[j] <= newer_floor:
                continue
            if not (min_similarity <= similarity <= max_similarity):
                continue
            key = (similarity, epochs[j])
            if chosen_key is None or key > chosen_key:
                chosen, chosen_key = j, key
        if chosen is None:
            continue
        sibling = pool[chosen]
        target_score = round(float(anchor["score"]) * score_mult, 4)
        if sibling["score"] >= target_score:
            continue
        sibling["score"] = target_score
        breakdown = sibling.get("score_breakdown")
        if not isinstance(breakdown, dict):
            breakdown = {}
            sibling["score_breakdown"] = breakdown
        breakdown["temporal_sibling_of"] = {
            "anchor_id": anchor["id"],
            "similarity": round(float(similarities[chosen]), 4),
        }
        promotions += 1
    return promotions


def _demote_stale_siblings(
    scored: list[dict[str, Any]],
    embeddings_by_id: dict[str, list[float] | None],
    superseded_ids: set[str],
    project_id: str | None = None,
) -> int:
    """Query-time staleness: within the head of the ranking, a memory yields
    to a sufficiently similar, meaningfully newer one.

    This is the soft counterpart of supersede_memory. Supersession only
    demotes the exact row the loop adjudicated, but stale facts usually
    exist as several near-duplicate rows — and semantic search favors them
    because a query phrased around the old state ("do I still live in
    Seattle?") embeds closer to the old fact than to its replacement. The
    newest similar row wins; older siblings keep their content but drop
    below fresher, unrelated hits. Already-superseded rows are skipped:
    they carry the harder deterministic penalty.
    """
    mult, min_similarity, min_days, window = _stale_sibling_params(project_id)
    head = [
        item
        for item in scored[:window]
        if isinstance(embeddings_by_id.get(item.get("id")), list) and embeddings_by_id[item["id"]]
    ]
    if len(head) < 2:
        return 0
    dims = {len(embeddings_by_id[item["id"]]) for item in head}
    if len(dims) > 1:
        majority = max(dims, key=lambda d: sum(1 for item in head if len(embeddings_by_id[item["id"]]) == d))
        head = [item for item in head if len(embeddings_by_id[item["id"]]) == majority]
        if len(head) < 2:
            return 0
    similarity_matrix = _pairwise_cosine_matrix([embeddings_by_id[item["id"]] for item in head])
    if similarity_matrix is None:
        return 0
    timestamps = [
        parse_datetime(item.get("created_at")) or parse_datetime(item.get("updated_at"))
        for item in head
    ]
    demoted = 0
    for i, item in enumerate(head):
        if item.get("id") in superseded_ids or timestamps[i] is None:
            continue
        newer_index, newer_similarity = None, 0.0
        for j in range(len(head)):
            if j == i or timestamps[j] is None:
                continue
            gap_days = (timestamps[j] - timestamps[i]).total_seconds() / 86400.0
            if gap_days < min_days:
                continue
            similarity = float(similarity_matrix[i][j])
            if similarity >= min_similarity and similarity > newer_similarity:
                newer_index, newer_similarity = j, similarity
        if newer_index is None:
            continue
        item["score"] = round(item["score"] * mult, 4)
        breakdown = item.get("score_breakdown")
        if not isinstance(breakdown, dict):
            breakdown = {}
            item["score_breakdown"] = breakdown
        breakdown["stale_sibling"] = {
            "newer_id": head[newer_index]["id"],
            "similarity": round(newer_similarity, 4),
        }
        demoted += 1
    return demoted


def _unit_rows(rows: list[list[float]]) -> list[list[float]]:
    unit = []
    for row in rows:
        norm = sum(value * value for value in row) ** 0.5 or 1.0
        unit.append([value / norm for value in row])
    return unit


def _pairwise_cosine_matrix(embeddings: list[list[float]]) -> Any:
    """(cos+1)/2-scaled pairwise similarity matrix — numpy when available,
    pure-Python fallback otherwise. Temporal rerank and consolidation are
    headline behavior; they must not silently turn off on a minimal
    install. Callers only index the result, so nested lists interchange
    with an ndarray."""
    try:
        import numpy as np
    except ImportError:
        unit = _unit_rows(embeddings)
        return [
            [(sum(a * b for a, b in zip(left, right)) + 1.0) / 2.0 for right in unit]
            for left in unit
        ]
    matrix = np.asarray(embeddings, dtype=np.float64)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    unit = matrix / norms
    return (unit @ unit.T + 1.0) / 2.0


def stale_candidate_pairs(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    """Review inbox for the verification loop: same-topic memory pairs whose
    timestamps are far apart — the older one is a supersession candidate.

    Deliberately a *hint* generator: precision is tuned for triage, recall is
    secondary, and false positives are acceptable because the agent (not the
    server) adjudicates each pair before calling supersede_memory. Pairs where
    either side is already superseded are skipped.
    """
    payload = payload or {}
    project_id = payload.get("project_id") or project_id or current_project_id()
    filters = payload.get("filters") or {}
    validate_filters(filters)
    if not has_entity_filter(filters):
        raise HTTPException(status_code=400, detail="filters must include at least one entity ID")
    top_n = max(1, min(int(_float_or(payload.get("top_n"), 20)), 100))
    min_similarity = _float_or(payload.get("min_similarity"), 0.80)
    min_days = _float_or(payload.get("min_days"), 7.0)
    scan_limit = 800  # newest-first cap so huge scopes stay tractable

    candidates = [
        memory
        for memory in list_memory_dicts(project_id=project_id, entity_prefilter=_simple_entity_prefilter(filters))
        if matches_filters(memory, filters)
        and not (memory.get("metadata") or {}).get("superseded_at")
        and isinstance(memory.get("_embedding"), list)
        and memory.get("_embedding")
    ][:scan_limit]

    dims = {len(memory["_embedding"]) for memory in candidates}
    if len(dims) > 1:
        majority = max(dims, key=lambda d: sum(1 for m in candidates if len(m["_embedding"]) == d))
        candidates = [m for m in candidates if len(m["_embedding"]) == majority]

    pairs: list[dict[str, Any]] = []
    similarity_matrix = _pairwise_cosine_matrix([m["_embedding"] for m in candidates]) if len(candidates) >= 2 else None
    if similarity_matrix is not None:
        timestamps = [parse_datetime(m.get("created_at")) for m in candidates]
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                if timestamps[i] is None or timestamps[j] is None:
                    continue
                gap_days = abs((timestamps[i] - timestamps[j]).total_seconds()) / 86400.0
                similarity = float(similarity_matrix[i][j])
                if similarity < min_similarity or gap_days < min_days:
                    continue
                older, newer = (i, j) if timestamps[i] <= timestamps[j] else (j, i)
                pairs.append(
                    {
                        "similarity": round(similarity, 4),
                        "gap_days": round(gap_days, 1),
                        "older": {
                            "id": candidates[older]["id"],
                            "memory": candidates[older]["memory"],
                            "created_at": candidates[older].get("created_at"),
                        },
                        "newer": {
                            "id": candidates[newer]["id"],
                            "memory": candidates[newer]["memory"],
                            "created_at": candidates[newer].get("created_at"),
                        },
                    }
                )
    pairs.sort(key=lambda item: item["similarity"], reverse=True)
    return {
        "schema_version": "mem1-stale-candidates-v1",
        "scanned": len(candidates),
        "pair_count": len(pairs[:top_n]),
        "min_similarity": min_similarity,
        "min_days": min_days,
        "pairs": pairs[:top_n],
        "hint": "Adjudicate each pair; when the older fact is obsolete, call supersede_memory(older_id, superseded_by=newer_id).",
    }


def feedback_adjusted_score(score: float, feedback: dict[str, Any] | None) -> float:
    if not feedback:
        return score
    metadata = feedback.get("metadata")
    a1 = metadata.get("a1") if isinstance(metadata, dict) else None
    if isinstance(a1, dict) and "adjust" in a1:
        # outcome-derived rows carry the A1 aggregate (single label ⇒ flat ±)
        score += _float_or(a1.get("adjust"), 0.0)
        return max(0.0, min(1.0, round(score, 4)))
    value = str(feedback.get("feedback") or "").upper()
    if value == "POSITIVE":
        score += 0.05
    elif value == "NEGATIVE":
        score -= 0.15
    elif value == "VERY_NEGATIVE":
        score -= 0.35
    return max(0.0, min(1.0, round(score, 4)))


def _context_composer_settings(payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    timeout = payload.get("composer_timeout") or payload.get("context_composer_timeout")
    timeout = timeout or settings.get("context_composer_timeout") or os.getenv("MEM1_CONTEXT_COMPOSER_TIMEOUT") or 10
    return {
        "provider": payload.get("composer_provider") or settings.get("context_composer_provider") or os.getenv("MEM1_CONTEXT_COMPOSER_PROVIDER") or "local",
        "model": payload.get("composer_model") or settings.get("context_composer_model") or os.getenv("MEM1_CONTEXT_COMPOSER_MODEL") or "deterministic-context-v1",
        "url": payload.get("composer_url") or payload.get("context_composer_url") or settings.get("context_composer_url") or os.getenv("MEM1_CONTEXT_COMPOSER_URL") or "",
        "api_key": payload.get("composer_api_key") or payload.get("context_composer_api_key") or os.getenv("MEM1_CONTEXT_COMPOSER_API_KEY") or "",
        "timeout": _float_or(timeout, 10.0),
    }


def _external_context_composer(
    payload: dict[str, Any],
    result: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any] | None:
    url = str(settings.get("url") or "").strip()
    if not url:
        return None

    headers = {"Content-Type": "application/json"}
    if settings.get("api_key"):
        headers["Authorization"] = f"Bearer {settings['api_key']}"
    evidence = _context_evidence(result)
    request_payload = {
        "schema_version": "mem1-context-composer-request-v1",
        "task": "context_compose",
        "model": settings.get("model"),
        "project_id": result.get("project_id"),
        "query": result.get("query"),
        "filters": result.get("filters"),
        "budget_tokens": result.get("budget_tokens"),
        "constraints": {
            "budget_tokens": result.get("budget_tokens"),
            "selected_count": result.get("selected_count"),
            "omitted_count": result.get("omitted_count"),
            "working_memory_slots": (result.get("working_memory") or {}).get("slot_capacity"),
        },
        "deterministic_context": result.get("context"),
        "memories": result.get("memories", []),
        "working_memory": result.get("working_memory") or {},
        "evidence": evidence,
        "omitted_memory_ids": result.get("omitted_memory_ids", []),
        "metadata": payload.get("metadata") or {},
    }
    with httpx.Client(timeout=float(settings.get("timeout") or 10.0)) as client:
        response = client.post(url, headers=headers, json=request_payload)
        response.raise_for_status()
        data = response.json()

    _validate_external_context_evidence(data, evidence)

    context = str(data.get("context") or data.get("text") or data.get("output") or "").strip()
    if not context:
        raise ValueError("context composer returned empty context")

    selected_ids = {str(memory.get("id")) for memory in result.get("memories", [])}
    returned_ids = [str(value) for value in data.get("memory_ids") or data.get("selected_memory_ids") or []]
    unknown_ids = [memory_id for memory_id in returned_ids if memory_id not in selected_ids]
    if unknown_ids:
        raise ValueError(f"context composer returned unknown memory ids: {', '.join(unknown_ids)}")

    used_tokens = token_estimate(context)
    budget_tokens = int(result.get("budget_tokens") or 0)
    if used_tokens > budget_tokens:
        raise ValueError("context composer exceeded budget_tokens")

    draft = dict(result)
    draft.update({"context": context, "used_tokens": used_tokens})
    draft["composer"] = {"external": True, "fallback": False}
    draft["evidence"] = _context_evidence(draft)
    grounding = _verify_external_context_grounding(payload, draft, project_id=str(result.get("project_id") or current_project_id()))

    drift = _summary_drift(result.get("memories", []), context)
    updated = dict(result)
    updated.update(
        {
            "context": context,
            "used_tokens": used_tokens,
            "composer": {
                "external": True,
                "fallback": False,
                "provider": settings.get("provider"),
                "model": data.get("model") or settings.get("model"),
                "url": url,
                "reason": data.get("reason") or "external_context_composer",
                "coverage": drift["coverage"],
                "warnings": drift["warnings"],
                "memory_ids": returned_ids or list(selected_ids),
                "claim_verification": {
                    "schema_version": grounding["schema_version"],
                    "status": grounding["status"],
                    "supported_count": grounding["supported_count"],
                    "unsupported_count": grounding["unsupported_count"],
                    "coverage": grounding["coverage"],
                    "min_support_score": grounding["min_support_score"],
                },
            },
        }
    )
    return updated


def _context_claim_texts(context: str) -> list[str]:
    claims: list[str] = []
    for raw_part in re.split(r"(?<=[.!?])\s+|\n+|;\s+", context):
        text = re.sub(r"^\s*[-*]\s*", "", raw_part).strip()
        if text:
            claims.append(text)
    return claims


def _verify_external_context_grounding(
    payload: dict[str, Any],
    context_result: dict[str, Any],
    project_id: str,
) -> dict[str, Any]:
    claims = _context_claim_texts(str(context_result.get("context") or ""))
    if not claims:
        raise ValueError("context composer returned no verifiable claims")
    min_support_score = min(
        max(
            _float_or(
                payload.get("composer_min_support_score", payload.get("context_composer_min_support_score")),
                0.5,
            ),
            0.0,
        ),
        1.0,
    )
    grounding = verify_memory_claims(
        {
            "claims": claims,
            "context_result": context_result,
            "min_support_score": min_support_score,
        },
        project_id=project_id,
    )
    if not grounding.get("valid"):
        unsupported = [
            str(item.get("claim") or "")
            for item in grounding.get("results", [])
            if isinstance(item, dict) and not item.get("supported")
        ]
        sample = "; ".join(claim for claim in unsupported[:3] if claim)
        suffix = f": {sample}" if sample else ""
        raise ValueError(f"context composer returned unsupported claims{suffix}")
    return grounding


def _validate_external_context_evidence(data: dict[str, Any], request_evidence: dict[str, Any]) -> None:
    response_evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
    top_level_hashes = data.get("source_hashes") if isinstance(data.get("source_hashes"), dict) else {}
    evidence_hashes = (
        response_evidence.get("source_hashes") if isinstance(response_evidence.get("source_hashes"), dict) else {}
    )
    if not response_evidence and not top_level_hashes:
        return

    request_ids = {str(memory_id) for memory_id in request_evidence.get("memory_ids") or []}
    request_hashes = {
        str(memory_id): str(source_hash)
        for memory_id, source_hash in (request_evidence.get("source_hashes") or {}).items()
    }
    response_ids = [str(memory_id) for memory_id in response_evidence.get("memory_ids") or []]
    response_hashes = {str(memory_id): str(source_hash) for memory_id, source_hash in evidence_hashes.items()}
    response_hashes.update({str(memory_id): str(source_hash) for memory_id, source_hash in top_level_hashes.items()})
    if not response_ids:
        response_ids = list(response_hashes)
    unknown_ids = sorted(
        {memory_id for memory_id in response_ids + list(response_hashes) if memory_id not in request_ids}
    )
    if unknown_ids:
        raise ValueError(f"context composer returned evidence for unknown memory ids: {', '.join(unknown_ids)}")

    if response_evidence and response_evidence.get("schema_version") not in {None, "mem1-context-evidence-v1"}:
        raise ValueError("context composer returned invalid evidence schema_version")
    if response_ids and response_hashes and not set(response_ids).issubset(set(response_hashes)):
        raise ValueError("context composer evidence source_hashes must cover response memory_ids")
    mismatches = sorted(
        memory_id for memory_id, source_hash in response_hashes.items() if request_hashes.get(memory_id) != source_hash
    )
    if mismatches:
        raise ValueError(f"context composer returned stale source hashes: {', '.join(mismatches)}")


def _context_evidence(result: dict[str, Any]) -> dict[str, Any]:
    memories = result.get("memories") or []
    memory_ids = [str(memory.get("id")) for memory in memories if memory.get("id")]
    source_hashes = {
        str(memory.get("id")): _context_item_source_hash(memory)
        for memory in memories
        if memory.get("id")
    }
    working_memory = result.get("working_memory") or {}
    composer = result.get("composer") or {}
    fallback_memory_ids = _context_fallback_memory_ids_from_cascade(result.get("fallback_cascade"))
    return {
        "schema_version": "mem1-context-evidence-v1",
        "memory_ids": memory_ids,
        "fallback_memory_ids": fallback_memory_ids,
        "fallback_selected_stage": str((result.get("fallback_cascade") or {}).get("selected_stage") or ""),
        "fallback_used_stages": [
            str(stage)
            for stage in ((result.get("fallback_cascade") or {}).get("used_stages") or [])
            if str(stage)
        ],
        "source_hashes": source_hashes,
        "context_sha256": hashlib.sha256(str(result.get("context") or "").encode("utf-8")).hexdigest(),
        "budget_tokens": int(result.get("budget_tokens") or 0),
        "used_tokens": int(result.get("used_tokens") or 0),
        "omitted_memory_ids": [str(memory_id) for memory_id in result.get("omitted_memory_ids") or []],
        "working_memory_pressure": working_memory.get("pressure"),
        "composer_external": bool(composer.get("external")),
        "composer_fallback": bool(composer.get("fallback")),
    }


def _context_fallback_memory_ids_from_cascade(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    memory_ids: list[str] = []
    seen: set[str] = set()
    for stage in value.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        for candidate in stage.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            memory_id = str(candidate.get("memory_id") or "").strip()
            if not memory_id or memory_id in seen:
                continue
            seen.add(memory_id)
            memory_ids.append(memory_id)
    return memory_ids


def _context_item_source_hash(memory: dict[str, Any]) -> str:
    metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
    source_hashes = metadata.get("source_hashes") if isinstance(metadata, dict) else None
    if isinstance(source_hashes, list) and source_hashes:
        return str(source_hashes[0])
    return _compression_source_hash(memory)


def _current_context_source_hash(memory_id: str, project_id: str) -> str:
    if memory_id.startswith("claim:"):
        claim_id = memory_id.split(":", 1)[1]
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM claims WHERE id = ? AND project_id = ?",
                (claim_id, project_id),
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Claim not found")
        source_hashes = json_loads(row["source_hashes"], [])
        if source_hashes:
            return str(source_hashes[0])
        return hashlib.sha256(
            json_dumps(
                {
                    "id": row["id"],
                    "claim_text": row["claim_text"],
                    "object_value": row["object_value"],
                    "updated_at": row["updated_at"],
                }
            ).encode("utf-8")
        ).hexdigest()
    memory = get_memory(memory_id, project_id=project_id)
    return _compression_source_hash(memory)


def verify_context_evidence(payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    payload = payload or {}
    project_id = payload.get("project_id") or project_id or current_project_id()
    context_result = payload.get("context_result") or payload.get("result") or {}
    if not isinstance(context_result, dict):
        context_result = {}
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else context_result.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    context_text = str(payload.get("context", context_result.get("context", "")) or "")
    evidence_memory_ids = [str(memory_id) for memory_id in evidence.get("memory_ids") or []]
    raw_source_hashes = evidence.get("source_hashes") if isinstance(evidence.get("source_hashes"), dict) else {}
    expected_source_hashes = {str(memory_id): str(source_hash) for memory_id, source_hash in raw_source_hashes.items()}
    expected_memory_ids = list(dict.fromkeys(evidence_memory_ids or list(expected_source_hashes)))
    current_source_hashes: dict[str, str] = {}
    missing_memory_ids: list[str] = []
    hash_mismatches: list[str] = []
    for memory_id in expected_memory_ids:
        try:
            current_hash = _current_context_source_hash(memory_id, project_id)
        except HTTPException as exc:
            if exc.status_code == 404:
                missing_memory_ids.append(memory_id)
                continue
            raise
        current_source_hashes[memory_id] = current_hash
        if expected_source_hashes.get(memory_id) != current_hash:
            hash_mismatches.append(memory_id)
    context_sha256 = hashlib.sha256(context_text.encode("utf-8")).hexdigest()
    expected_context_sha256 = str(evidence.get("context_sha256") or "")
    selected_memory_ids = [
        str(memory.get("id"))
        for memory in context_result.get("memories") or []
        if isinstance(memory, dict) and memory.get("id")
    ]
    source_hash_keys_ok = set(expected_source_hashes) == set(evidence_memory_ids)
    selected_memory_ids_ok = not selected_memory_ids or selected_memory_ids == evidence_memory_ids
    checks = {
        "schema_version": evidence.get("schema_version") == "mem1-context-evidence-v1",
        "context_hash": len(expected_context_sha256) == 64 and expected_context_sha256 == context_sha256,
        "source_hash_keys": source_hash_keys_ok,
        "source_hash_drift": not missing_memory_ids and not hash_mismatches,
        "selected_memory_ids": selected_memory_ids_ok,
    }
    valid = all(checks.values())
    result = {
        "schema_version": "mem1-context-evidence-verification-v1",
        "project_id": project_id,
        "valid": valid,
        "status": "VERIFIED" if valid else "DRIFTED",
        "checks": checks,
        "evidence_schema_version": evidence.get("schema_version"),
        "memory_ids": expected_memory_ids,
        "selected_memory_ids": selected_memory_ids,
        "missing_memory_ids": missing_memory_ids,
        "hash_mismatches": hash_mismatches,
        "expected_context_sha256": expected_context_sha256 or None,
        "current_context_sha256": context_sha256,
        "expected_source_hashes": expected_source_hashes,
        "current_source_hashes": current_source_hashes,
    }
    record_usage(
        project_id,
        "context_evidence_verify",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate(result),
        metadata={
            "valid": valid,
            "missing_memory_count": len(missing_memory_ids),
            "hash_mismatch_count": len(hash_mismatches),
        },
    )
    return result


def _verify_judgment_evidence_item(evidence: dict[str, Any], project_id: str) -> dict[str, Any]:
    evidence_memory_ids = [str(memory_id) for memory_id in evidence.get("memory_ids") or []]
    raw_source_hashes = evidence.get("source_hashes") if isinstance(evidence.get("source_hashes"), dict) else {}
    expected_source_hashes = {str(memory_id): str(source_hash) for memory_id, source_hash in raw_source_hashes.items()}
    expected_memory_ids = list(dict.fromkeys(evidence_memory_ids or list(expected_source_hashes)))
    target_memory_ids = [str(memory_id) for memory_id in evidence.get("target_memory_ids") or []]
    current_source_hashes: dict[str, str] = {}
    missing_memory_ids: list[str] = []
    hash_mismatches: list[str] = []
    for memory_id in expected_memory_ids:
        try:
            memory = get_memory(memory_id, project_id=project_id)
        except HTTPException as exc:
            if exc.status_code == 404:
                missing_memory_ids.append(memory_id)
                continue
            raise
        current_hash = _compression_source_hash(memory)
        current_source_hashes[memory_id] = current_hash
        if expected_source_hashes.get(memory_id) != current_hash:
            hash_mismatches.append(memory_id)
    source_hash_keys_ok = set(expected_source_hashes) == set(evidence_memory_ids)
    target_memory_ids_ok = set(target_memory_ids).issubset(set(evidence_memory_ids))
    checks = {
        "schema_version": evidence.get("schema_version") == "mem1-judgment-evidence-v1",
        "candidate_hash": len(str(evidence.get("candidate_hash") or "")) == 64,
        "source_hash_keys": source_hash_keys_ok,
        "source_hash_drift": not missing_memory_ids and not hash_mismatches,
        "target_memory_ids": target_memory_ids_ok,
    }
    valid = all(checks.values())
    return {
        "valid": valid,
        "status": "VERIFIED" if valid else "DRIFTED",
        "checks": checks,
        "evidence_schema_version": evidence.get("schema_version"),
        "memory_ids": expected_memory_ids,
        "target_memory_ids": target_memory_ids,
        "missing_memory_ids": missing_memory_ids,
        "hash_mismatches": hash_mismatches,
        "expected_source_hashes": expected_source_hashes,
        "current_source_hashes": current_source_hashes,
    }


def verify_judgment_evidence(payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    payload = payload or {}
    project_id = payload.get("project_id") or project_id or current_project_id()
    judgment_result = payload.get("judgment_result") or payload.get("result") or {}
    if not isinstance(judgment_result, dict):
        judgment_result = {}
    evidence_items: list[dict[str, Any]] = []
    if isinstance(payload.get("evidence"), dict):
        evidence_items.append(payload["evidence"])
    for decision in judgment_result.get("decisions") or []:
        if isinstance(decision, dict) and isinstance(decision.get("evidence"), dict):
            evidence_items.append(decision["evidence"])
    if not evidence_items:
        evidence_items.append({})
    item_results = [_verify_judgment_evidence_item(evidence, project_id) for evidence in evidence_items]
    valid = all(item["valid"] for item in item_results)
    result = {
        "schema_version": "mem1-judgment-evidence-verification-v1",
        "project_id": project_id,
        "valid": valid,
        "status": "VERIFIED" if valid else "DRIFTED",
        "evidence_count": len(item_results),
        "results": item_results,
    }
    if len(item_results) == 1:
        result.update(item_results[0])
        result["schema_version"] = "mem1-judgment-evidence-verification-v1"
        result["project_id"] = project_id
        result["evidence_count"] = 1
        result["results"] = item_results
    record_usage(
        project_id,
        "judgment_evidence_verify",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate(result),
        metadata={
            "valid": valid,
            "evidence_count": len(item_results),
            "missing_memory_count": sum(len(item["missing_memory_ids"]) for item in item_results),
            "hash_mismatch_count": sum(len(item["hash_mismatches"]) for item in item_results),
        },
    )
    return result


_CLAIM_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "user",
    "with",
}


_CURRENT_CLAIM_MARKERS = {
    "current",
    "currently",
    "now",
    "today",
    "still",
}
_FAILURE_STATE_TERMS = {
    "blocked",
    "broken",
    "denied",
    "error",
    "failed",
    "failing",
    "unavailable",
    "unreliable",
}
_RESOLVED_STATE_TERMS = {
    "fixed",
    "green",
    "healthy",
    "pass",
    "passed",
    "passes",
    "resolved",
    "succeeds",
    "working",
}
_SUPERSEDED_STATE_MARKERS = {
    "historical",
    "obsolete",
    "previously",
    "superseded",
}
_CONTEXT_INTENT_TERMS = {
    "blocked",
    "blocker",
    "blockers",
    "deferred",
    "followup",
    "gap",
    "gaps",
    "hardening",
    "next",
    "remaining",
    "task",
    "tasks",
    "todo",
    "todos",
}


def _claim_texts(payload: dict[str, Any]) -> list[str]:
    claims = payload.get("claims")
    if isinstance(claims, list):
        texts = []
        for claim in claims:
            if isinstance(claim, dict):
                text = str(claim.get("claim") or claim.get("text") or "").strip()
            else:
                text = str(claim or "").strip()
            if text:
                texts.append(text)
        return texts
    text = str(payload.get("answer") or payload.get("text") or payload.get("response") or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _claim_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z0-9가-힣_]+", text.lower())
        if len(token) > 1 and token not in _CLAIM_STOPWORDS
    }


def _has_negated_state(text: str, terms: set[str]) -> bool:
    lowered = text.lower()
    for term in terms:
        if re.search(rf"\b(?:not|no longer|never|without|isn't|isnt|wasn't|wasnt|doesn't|doesnt)\b(?:\W+\w+){{0,3}}\W+{re.escape(term)}\b", lowered):
            return True
    return False


def _claim_temporal_state_conflict(claim: str, memory_text: str) -> bool:
    claim_tokens = _claim_tokens(claim)
    memory_tokens = _claim_tokens(memory_text)
    if not claim_tokens or not memory_tokens or not (claim_tokens & _CURRENT_CLAIM_MARKERS):
        return False

    claim_failure = bool(claim_tokens & _FAILURE_STATE_TERMS)
    claim_resolved = bool(claim_tokens & _RESOLVED_STATE_TERMS)
    memory_failure = bool(memory_tokens & _FAILURE_STATE_TERMS)
    memory_resolved = bool(memory_tokens & _RESOLVED_STATE_TERMS)
    memory_superseded = bool(memory_tokens & _SUPERSEDED_STATE_MARKERS)

    if claim_failure and (
        memory_resolved
        or _has_negated_state(memory_text, _FAILURE_STATE_TERMS)
        or (memory_superseded and memory_failure)
    ):
        return True
    if claim_resolved and memory_failure and not memory_resolved and not _has_negated_state(memory_text, _FAILURE_STATE_TERMS):
        return True
    return False


def _claim_support_score(claim: str, memory_text: str) -> float:
    if _claim_temporal_state_conflict(claim, memory_text):
        return 0.0
    claim_tokens = _claim_tokens(claim)
    if not claim_tokens:
        return 0.0
    memory_tokens = _claim_tokens(memory_text)
    if not memory_tokens:
        return 0.0
    return round(len(claim_tokens & memory_tokens) / len(claim_tokens), 4)


def _candidate_memories_for_claim(
    claim: str,
    payload: dict[str, Any],
    context_result: dict[str, Any],
    project_id: str,
) -> list[dict[str, Any]]:
    context_memories = context_result.get("memories") if isinstance(context_result.get("memories"), list) else []
    if context_memories:
        return [dict(memory) for memory in context_memories if isinstance(memory, dict)]
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    search = search_memories(
        {
            "query": claim,
            "filters": filters,
            "top_k": payload.get("top_k", payload.get("limit", 5)),
            "threshold": payload.get("threshold", 0),
            "rerank": payload.get("rerank", False),
            "reference_date": payload.get("reference_date"),
        },
        project_id=project_id,
    )
    return [dict(memory) for memory in search.get("results") or [] if isinstance(memory, dict)]


def verify_memory_claims(payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    payload = payload or {}
    project_id = payload.get("project_id") or project_id or current_project_id()
    context_result = payload.get("context_result") or payload.get("result") or {}
    if not isinstance(context_result, dict):
        context_result = {}
    claims = _claim_texts(payload)
    if not claims:
        raise HTTPException(status_code=400, detail="claims, answer, text, or response is required")
    min_support_score = _float_or(payload.get("min_support_score"), 0.5)
    min_support_score = min(max(min_support_score, 0.0), 1.0)
    evidence_verification = None
    if context_result or isinstance(payload.get("evidence"), dict):
        evidence_payload = {
            "context_result": context_result,
            "evidence": payload.get("evidence"),
            "project_id": project_id,
        }
        if payload.get("context") is not None:
            evidence_payload["context"] = payload.get("context")
        evidence_verification = verify_context_evidence(
            evidence_payload,
            project_id=project_id,
        )

    results = []
    for claim in claims:
        candidates = _candidate_memories_for_claim(claim, payload, context_result, project_id)
        scored = []
        for memory in candidates:
            score = _claim_support_score(claim, str(memory.get("memory") or memory.get("text") or ""))
            if score > 0:
                scored.append(
                    {
                        "id": memory.get("id"),
                        "memory": memory.get("memory") or memory.get("text"),
                        "support_score": score,
                    }
                )
        scored.sort(key=lambda item: item["support_score"], reverse=True)
        supporting = [item for item in scored if item["support_score"] >= min_support_score]
        results.append(
            {
                "claim": claim,
                "status": "SUPPORTED" if supporting else "UNSUPPORTED",
                "supported": bool(supporting),
                "support_score": supporting[0]["support_score"] if supporting else (scored[0]["support_score"] if scored else 0.0),
                "supporting_memory_ids": [str(item["id"]) for item in supporting if item.get("id")],
                "supporting_memories": supporting[:3],
                "candidate_count": len(candidates),
            }
        )

    supported_count = sum(1 for item in results if item["supported"])
    unsupported_count = len(results) - supported_count
    evidence_valid = evidence_verification is None or bool(evidence_verification.get("valid"))
    valid = unsupported_count == 0 and evidence_valid
    status = "VERIFIED" if valid else ("DRIFTED" if not evidence_valid else "UNSUPPORTED")
    result = {
        "schema_version": "mem1-claim-verification-v1",
        "project_id": project_id,
        "valid": valid,
        "status": status,
        "claim_count": len(results),
        "supported_count": supported_count,
        "unsupported_count": unsupported_count,
        "coverage": round(supported_count / max(len(results), 1), 4),
        "min_support_score": min_support_score,
        "checks": {
            "all_claims_supported": unsupported_count == 0,
            "context_evidence_valid": evidence_valid,
        },
        "results": results,
    }
    if evidence_verification is not None:
        result["evidence_verification"] = evidence_verification
    record_usage(
        project_id,
        "memory_claims_verify",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate(result),
        metadata={
            "valid": valid,
            "claim_count": len(results),
            "unsupported_count": unsupported_count,
            "evidence_valid": evidence_valid,
        },
    )
    return result


def _claim_eval_matched(item: dict[str, Any], verification: dict[str, Any]) -> bool:
    if "expected_valid" in item:
        return bool(item.get("expected_valid")) == bool(verification.get("valid"))
    expected_status = item.get("expected_status")
    if expected_status:
        return str(expected_status).upper() == str(verification.get("status"))
    expected_supported = item.get("expected_supported_count")
    if expected_supported is not None and int(expected_supported) != int(verification.get("supported_count") or 0):
        return False
    expected_unsupported = item.get("expected_unsupported_count")
    if expected_unsupported is not None and int(expected_unsupported) != int(verification.get("unsupported_count") or 0):
        return False
    return bool(verification.get("valid"))


def create_claim_evaluation(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    project_id = payload.get("project_id") or project_id or current_project_id()
    dataset = payload.get("claims") or payload.get("dataset") or payload.get("items") or []
    if isinstance(dataset, (str, dict)):
        dataset = [dataset]
    if not isinstance(dataset, list) or not dataset:
        raise HTTPException(status_code=400, detail="claims dataset is required")
    name = payload.get("name") or "Claim Verification Evaluation"
    metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata") or {}, dict) else {}
    family = payload.get("family") or payload.get("benchmark_family") or metadata.get("family") or "claim_verification"
    metadata["family"] = str(family)
    metadata["evaluation_type"] = "claims"
    eval_id = str(new_id())
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    hits = 0
    total = 0
    total_latency = 0.0
    total_claims = 0
    supported_claims = 0
    unsupported_claims = 0
    for index, raw_item in enumerate(dataset):
        item = dict(raw_item) if isinstance(raw_item, dict) else {"claims": [str(raw_item)]}
        item_payload = {
            **item,
            "filters": item.get("filters", payload.get("filters")),
            "top_k": item.get("top_k", payload.get("top_k", payload.get("limit"))),
            "threshold": item.get("threshold", payload.get("threshold", 0)),
            "rerank": item.get("rerank", payload.get("rerank", False)),
            "min_support_score": item.get("min_support_score", payload.get("min_support_score")),
            "reference_date": item.get("reference_date", payload.get("reference_date")),
        }
        item_payload = {key: value for key, value in item_payload.items() if value is not None}
        item_started = time.perf_counter()
        try:
            verification = verify_memory_claims(item_payload, project_id=project_id)
            latency = round((time.perf_counter() - item_started) * 1000, 3)
            matched = _claim_eval_matched(item, verification)
            hits += 1 if matched else 0
            total += 1
            total_latency += latency
            total_claims += int(verification.get("claim_count") or 0)
            supported_claims += int(verification.get("supported_count") or 0)
            unsupported_claims += int(verification.get("unsupported_count") or 0)
            results.append(
                {
                    "index": index,
                    "matched": matched,
                    "latency": latency,
                    "expected_status": item.get("expected_status"),
                    "expected_valid": item.get("expected_valid"),
                    "expected_supported_count": item.get("expected_supported_count"),
                    "expected_unsupported_count": item.get("expected_unsupported_count"),
                    "verification": verification,
                }
            )
        except HTTPException:
            raise
        except Exception as exc:
            total += 1
            results.append({"index": index, "matched": False, "error": str(exc), "verification": {}})

    elapsed = round((time.perf_counter() - started) * 1000, 3)
    metrics = {
        "accuracy": round(hits / total, 4) if total else 0,
        "hit_count": hits,
        "item_count": total,
        "claim_count": total_claims,
        "supported_claim_count": supported_claims,
        "unsupported_claim_count": unsupported_claims,
        "avg_latency": round(total_latency / total, 3) if total else 0,
        "total_latency": elapsed,
        "token_efficiency": round((hits / max(token_estimate(results), 1)) * 1000, 4) if hits else 0,
    }
    regression_threshold = max(0.0, float(payload.get("regression_threshold") or 0))
    now = utc_now()
    data = {"items": results}
    with get_db() as conn:
        previous = conn.execute(
            """
            SELECT id, metrics FROM evaluations
            WHERE project_id = ? AND name = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (project_id, name),
        ).fetchone()
        previous_accuracy: float | None = None
        previous_evaluation_id = previous["id"] if previous else None
        if previous:
            try:
                previous_accuracy = float(json_loads(previous["metrics"], {}).get("accuracy"))
            except (TypeError, ValueError):
                previous_accuracy = None
        accuracy_delta = round(metrics["accuracy"] - previous_accuracy, 4) if previous_accuracy is not None else None
        metrics.update(
            {
                "previous_evaluation_id": previous_evaluation_id,
                "previous_accuracy": round(previous_accuracy, 4) if previous_accuracy is not None else None,
                "accuracy_delta": accuracy_delta,
                "regression_threshold": regression_threshold,
                "regression": bool(accuracy_delta is not None and accuracy_delta < -regression_threshold),
            }
        )
        conn.execute(
            """
            INSERT INTO evaluations (
                id, project_id, name, status, dataset, results, metrics, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eval_id,
                project_id,
                name,
                "SUCCEEDED",
                json_dumps(dataset),
                json_dumps(data),
                json_dumps(metrics),
                json_dumps(metadata),
                now,
                now,
            ),
        )
    record_usage(
        project_id,
        "claim_verification_evaluation",
        input_tokens=token_estimate(dataset),
        output_tokens=token_estimate(data),
        latency=elapsed,
        metadata={"evaluation_id": eval_id, "family": metadata.get("family"), **metrics},
    )
    return {
        "id": eval_id,
        "project_id": project_id,
        "name": name,
        "status": "SUCCEEDED",
        "metrics": metrics,
        "metadata": metadata,
        "family": _evaluation_item_family({"name": name, "metadata": metadata}),
        "results": data,
        "created_at": now,
        "updated_at": now,
    }


_WORKING_MEMORY_ROLE_ORDER = ["current_workspace", "task_state", "evidence", "architecture", "product", "general"]
_CONTEXT_SELECTOR_POLICY_VERSION = "selector-policy-v1.1"
_CONTEXT_SELECTOR_ROLE_SCORE_FLOORS = {
    "evidence": 0.0,
    "architecture": 0.0,
    "product": 0.0,
    "general": 0.3,
}
_CONTEXT_SELECTOR_ROLE_PRIORITY = {
    "evidence": 3,
    "architecture": 3,
    "product": 2,
    "general": 1,
}
_CONTEXT_SELECTOR_TRADEOFF_GAP_TOLERANCE = 0.05
_CONTEXT_SELECTOR_SOFT_ROLE_QUOTAS = {
    "evidence": 1,
    "product": 1,
}
_CONTEXT_SELECTOR_SOFT_QUOTA_SCORE_FLOORS = {
    "evidence": 0.25,
    "product": 0.25,
}
CONTEXT_TRACE_SCHEMA_VERSION = "mem1-context-trace-v1"
CONTEXT_OUTCOME_SCHEMA_VERSION = "mem1-context-outcome-v1"
CONTEXT_OBSERVATION_SCHEMA_VERSION = "mem1-context-observation-v0"
CONTEXT_CAPSULE_SCHEMA_VERSION = "mem1-context-capsule-v0"
CONTEXT_AUTOPILOT_SCHEMA_VERSION = "mem1-context-autopilot-v0"
CONTEXT_AUTOPILOT_DEBUG_SCHEMA_VERSION = "mem1-context-autopilot-debug-v0"
CONTEXT_USE_NOW_SCHEMA_VERSION = "mem1-context-use-now-v0"
CONTEXT_ACTION_HINTS_SCHEMA_VERSION = "mem1-context-action-hints-v0"
CONTEXT_ACTION_PLAN_SCHEMA_VERSION = "mem1-context-action-plan-v0"
CONTEXT_SOURCE_ROUTE_SCHEMA_VERSION = "mem1-context-source-route-v0"
CONTEXT_STATUS_SCHEMA_VERSION = "mem1-context-status-v0"
CONTEXT_MATERIALIZATION_SCHEMA_VERSION = "mem1-context-materialization-v0"
CONTEXT_FALLBACK_CASCADE_SCHEMA_VERSION = "mem1-context-fallback-cascade-v0"
CONTEXT_OUTCOME_OBSERVED_SCHEMA_VERSION = "mem1-context-outcome-observed-v0"
CONTEXT_OUTCOME_INFERRED_SCHEMA_VERSION = "mem1-context-outcome-inferred-v0"
CONTEXT_CAPSULE_TOKEN_BUDGET = 400
CONTEXT_UTILITY_FAILURE_STAGES = {
    "none",
    "write_failure",
    "retrieval_failure",
    "selection_failure",
    "packing_failure",
    "reasoning_failure",
    "unknown",
}


def _working_memory_state(
    selected: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    budget_tokens: int,
    used_tokens: int,
    slot_capacity: int,
    workspace_current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    slot_capacity = min(max(slot_capacity, 1), 32)
    selected_ids = {str(memory.get("id")) for memory in selected}
    slots = [
        {
            "index": index,
            "memory_id": memory.get("id"),
            "role": _working_memory_role(memory),
            "reason": memory.get("reason"),
            "tokens": memory.get("context_tokens", 0),
            "score": memory.get("score"),
        }
        for index, memory in enumerate(selected[:slot_capacity], start=1)
    ]
    overflow_selected_ids = [str(memory.get("id")) for memory in selected[slot_capacity:] if memory.get("id")]
    omitted_ids = [str(memory.get("id")) for memory in candidates if str(memory.get("id")) not in selected_ids]
    overflow_count = len(overflow_selected_ids) + len(omitted_ids)
    budget_ratio = round(used_tokens / max(budget_tokens, 1), 4)
    if overflow_count or budget_ratio >= 0.9:
        pressure = "high"
    elif budget_ratio >= 0.6 or len(slots) >= slot_capacity:
        pressure = "medium"
    else:
        pressure = "low"
    return {
        "schema_version": "mem1-working-memory-v1",
        "slot_capacity": slot_capacity,
        "slot_count": len(slots),
        "pressure": pressure,
        "budget_ratio": budget_ratio,
        "overflow_count": overflow_count,
        "overflow_memory_ids": overflow_selected_ids + omitted_ids,
        "slots": slots,
        "role_schema_version": "mem1-working-memory-roles-v1",
        "role_order": list(_WORKING_MEMORY_ROLE_ORDER),
        "roles": _working_memory_roles(selected[:slot_capacity], candidates, workspace_current),
    }


def _working_memory_role(memory: dict[str, Any]) -> str:
    metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
    categories = {
        str(category).lower()
        for category in list(memory.get("categories") or []) + list(metadata.get("categories") or [])
        if str(category).strip()
    }
    if (
        metadata.get("assertion_kind") == "task_state"
        or metadata.get("kind") == "task_state"
        or isinstance(metadata.get("task_state"), dict)
    ):
        return "task_state"
    if categories.intersection({"evidence", "report", "eval", "test", "runtime", "trace"}):
        return "evidence"
    if categories.intersection({"architecture", "system", "engine", "hybrid_workspace", "alpha_kernel"}):
        return "architecture"
    if categories.intersection({"product", "ui", "ux", "pricing", "onboarding", "brand"}):
        return "product"
    return "general"


def _working_memory_role_bucket() -> dict[str, Any]:
    return {
        "selected_count": 0,
        "overflow_count": 0,
        "memory_ids": [],
        "overflow_memory_ids": [],
    }


def _working_memory_roles(
    selected: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    workspace_current: dict[str, Any] | None,
) -> dict[str, Any]:
    roles = {
        "current_workspace": {
            "selected_count": 1 if isinstance(workspace_current, dict) else 0,
            "overflow_count": 0,
            "memory_ids": [],
            "overflow_memory_ids": [],
        },
        "task_state": _working_memory_role_bucket(),
        "evidence": _working_memory_role_bucket(),
        "architecture": _working_memory_role_bucket(),
        "product": _working_memory_role_bucket(),
        "general": _working_memory_role_bucket(),
    }
    if isinstance(workspace_current, dict):
        roles["current_workspace"].update(
            {
                "task_id": workspace_current.get("task_id"),
                "status": workspace_current.get("status"),
                "claim_lifecycle": workspace_current.get("claim_lifecycle"),
                "terminal_evidence_count": len(workspace_current.get("terminal_evidence_refs") or []),
                "claim_id": workspace_current.get("claim_id"),
                "workspace_epoch_id": workspace_current.get("workspace_epoch_id"),
            }
        )
    selected_ids = {str(memory.get("id")) for memory in selected if memory.get("id")}
    for memory in selected:
        role = _working_memory_role(memory)
        memory_id = str(memory.get("id") or "")
        if memory_id:
            roles[role]["memory_ids"].append(memory_id)
        roles[role]["selected_count"] += 1
    for memory in candidates:
        memory_id = str(memory.get("id") or "")
        if not memory_id or memory_id in selected_ids:
            continue
        role = _working_memory_role(memory)
        roles[role]["overflow_memory_ids"].append(memory_id)
        roles[role]["overflow_count"] += 1
    return roles


def _working_memory_role_counts(
    selected: list[dict[str, Any]],
    workspace_current: dict[str, Any] | None,
) -> dict[str, int]:
    counts = {role: 0 for role in _WORKING_MEMORY_ROLE_ORDER}
    if isinstance(workspace_current, dict):
        counts["current_workspace"] = 1
    for memory in selected:
        role = _working_memory_role(memory)
        counts[role] = counts.get(role, 0) + 1
    return counts


def _working_memory_role_balance(selected_role_counts: dict[str, int]) -> dict[str, Any]:
    query_counts = {
        role: int(selected_role_counts.get(role) or 0)
        for role in _WORKING_MEMORY_ROLE_ORDER
        if role != "current_workspace"
    }
    non_workspace_selected_count = sum(query_counts.values())
    active_query_roles = {role: count for role, count in query_counts.items() if count > 0}
    dominant_role = None
    dominant_count = 0
    if active_query_roles:
        dominant_role, dominant_count = max(active_query_roles.items(), key=lambda item: item[1])
    return {
        "selected_role_counts": {role: int(selected_role_counts.get(role) or 0) for role in _WORKING_MEMORY_ROLE_ORDER},
        "active_roles": {
            role: int(selected_role_counts.get(role) or 0)
            for role in _WORKING_MEMORY_ROLE_ORDER
            if int(selected_role_counts.get(role) or 0) > 0
        },
        "non_workspace_selected_count": non_workspace_selected_count,
        "query_evidence_role_count": len(active_query_roles),
        "dominant_role": dominant_role,
        "dominant_count": dominant_count,
        "dominant_ratio": round(dominant_count / max(non_workspace_selected_count, 1), 4)
        if dominant_role
        else 0.0,
    }


def _select_working_memory_slots(
    budgeted: list[dict[str, Any]],
    slot_capacity: int,
    query: str,
) -> list[dict[str, Any]]:
    selected = list(budgeted[:slot_capacity])
    if len(budgeted) <= len(selected):
        return selected

    intent_terms = _claim_tokens(query).intersection(_CONTEXT_INTENT_TERMS)
    if not intent_terms:
        return selected

    selected_ids = {str(memory.get("id")) for memory in selected}
    intent_candidates = []
    for memory in budgeted:
        if str(memory.get("id")) in selected_ids:
            continue
        memory_tokens = _claim_tokens(str(memory.get("memory") or ""))
        overlap = memory_tokens.intersection(intent_terms)
        if overlap:
            intent_candidates.append((len(overlap), float(memory.get("score") or 0.0), str(memory.get("updated_at") or ""), memory))
    if not intent_candidates:
        return selected

    intent_memory = max(intent_candidates, key=lambda item: (item[0], item[1], item[2]))[3]
    if len(selected) >= slot_capacity and selected:
        selected[-1] = intent_memory
    else:
        selected.append(intent_memory)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for memory in selected:
        memory_id = str(memory.get("id"))
        if memory_id and memory_id in seen:
            continue
        if memory_id:
            seen.add(memory_id)
        deduped.append(memory)
    return deduped


def _workspace_context_line(state: dict[str, Any]) -> str:
    parts = [f"Current workspace: task {state.get('task_id') or 'current'} is {state.get('status') or 'unknown'}."]
    summary = str(state.get("current_goal") or state.get("summary") or "").strip()
    if summary:
        parts.append(f"Goal: {summary}")
    blockers = [str(item) for item in state.get("blockers") or [] if str(item).strip()]
    if blockers:
        parts.append("Blockers: " + "; ".join(blockers))
    next_actions = [str(item) for item in state.get("next_actions") or [] if str(item).strip()]
    if next_actions:
        parts.append(_compact_context_list("Next", next_actions))
    evidence_files = [str(item) for item in state.get("evidence_files") or [] if str(item).strip()]
    if evidence_files:
        parts.append(_workspace_evidence_context(evidence_files))
    if state.get("terminal_evidence_refs"):
        parts.append(_terminal_evidence_context(state["terminal_evidence_refs"]))
    return " ".join(parts).strip()


def _terminal_evidence_context(evidence_refs: list[dict[str, Any]]) -> str:
    labels = []
    for ref in evidence_refs:
        if not isinstance(ref, dict):
            continue
        ref_id = str(ref.get("id") or "").strip()
        ref_kind = str(ref.get("kind") or "").strip()
        if ref_id:
            labels.append(ref_id)
        elif ref_kind:
            labels.append(ref_kind)
    labels = list(dict.fromkeys(label for label in labels if label))
    if not labels:
        return ""
    total = len(labels)
    if len(labels) > 3:
        labels = labels[:2] + [f"+{total - 2} more"]
    return f"Terminal evidence ({total}): " + "; ".join(labels)


def _workspace_evidence_context(evidence_files: list[str]) -> str:
    visible_files: list[str] = []
    redacted_count = 0
    for path in evidence_files:
        if _context_sensitive_target_reason(path):
            redacted_count += 1
            continue
        visible_files.append(path)
    labels = [os.path.basename(path.rstrip("/")) or path for path in visible_files]
    if len(labels) > 3:
        labels = labels[:2] + [f"+{len(visible_files) - 2} more"]
    if not redacted_count:
        return f"Evidence files ({len(visible_files)}): " + "; ".join(labels)
    if redacted_count:
        labels.append(f"{redacted_count} sensitive redacted")
    return f"Evidence files ({len(visible_files)} visible): " + "; ".join(labels)


def _resume_workspace_for_context(payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    override = payload.get("resume_workspace_override") or payload.get("resumeWorkspaceOverride")
    if isinstance(override, dict):
        current = override.get("current") if isinstance(override.get("current"), dict) else None
        if current is None and override.get("task_id"):
            current = dict(override)
        if isinstance(current, dict):
            state_source = str(override.get("state_source") or override.get("stateSource") or "replay_workspace_fixture")
            fixture = override.get("fixture") if isinstance(override.get("fixture"), dict) else {}
            return {
                "schema_version": "mem1-task-state-list-v1",
                "project_id": project_id,
                "count": 1,
                "results": [current],
                "current": current,
                "state_source": state_source,
                "replay_fixture": fixture,
            }
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    workspace_payload: dict[str, Any] = {
        "filters": filters,
        "limit": 1,
    }
    for key in ("task_id", "goal_id", "user_id", "agent_id", "app_id", "run_id", "project"):
        if payload.get(key):
            workspace_payload[key] = payload[key]
        elif filters.get(key):
            workspace_payload[key] = filters[key]
    replay_as_of = (
        payload.get("resume_workspace_as_of")
        or payload.get("resumeWorkspaceAsOf")
        or payload.get("workspace_as_of")
        or payload.get("workspaceAsOf")
        or payload.get("memory_as_of")
        or payload.get("memoryAsOf")
        or payload.get("as_of")
        or payload.get("asOf")
    )
    if replay_as_of:
        workspace_payload["as_of"] = replay_as_of
    result = get_task_state(workspace_payload, project_id=project_id)
    if result.get("current") or not workspace_payload.get("task_id"):
        return result

    relaxed_payload = dict(workspace_payload)
    relaxed_task_id = str(relaxed_payload.pop("task_id", "") or "")
    relaxed_result = get_task_state(relaxed_payload, project_id=project_id)
    if not relaxed_result.get("current"):
        return result
    relaxed_result = dict(relaxed_result)
    relaxed_result["state_source"] = f"{relaxed_result.get('state_source') or 'task_state'}_relaxed_task"
    relaxed_result["fallback_reason"] = "requested_task_state_not_found"
    relaxed_result["requested_task_id"] = _task_state_id({"task_id": relaxed_task_id})
    return relaxed_result


def _context_requested_task_id(payload: dict[str, Any]) -> str | None:
    task_id = payload.get("task_id") or payload.get("goal_id")
    if task_id in (None, "") and isinstance(payload.get("filters"), dict):
        filters = payload["filters"]
        task_id = filters.get("task_id") or filters.get("goal_id")
    if task_id in (None, ""):
        return None
    return _task_state_id({"task_id": task_id})


def _context_memory_task_state_id(memory: dict[str, Any]) -> str | None:
    metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
    is_task_state_memory = (
        metadata.get("assertion_kind") == "task_state"
        or metadata.get("kind") == "task_state"
        or isinstance(metadata.get("task_state"), dict)
    )
    if not is_task_state_memory:
        return None
    task_state = metadata.get("task_state") if isinstance(metadata.get("task_state"), dict) else {}
    task_id = task_state.get("task_id") or metadata.get("task_id")
    if task_id in (None, ""):
        return ""
    return _task_state_id({"task_id": task_id})


def _context_memory_task_tag_id(memory: dict[str, Any]) -> str | None:
    metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
    task_id = metadata.get("task_id") or metadata.get("goal_id")
    if task_id in (None, ""):
        return None
    return _task_state_id({"task_id": task_id})


def _context_memory_has_generic_task_id(memory: dict[str, Any]) -> bool:
    for task_id in (_context_memory_task_state_id(memory), _context_memory_task_tag_id(memory)):
        if task_id and _task_state_id_is_generic(task_id):
            return True
    return False


def _context_related_task_ids_from_source(source: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("related_task_ids", "related_tasks", "related_task_id"):
        ids.extend(_task_state_related_ids(source.get(key)))
    relations = source.get("task_relations") if isinstance(source.get("task_relations"), dict) else {}
    for key in ("related_task_ids", "related_tasks", "related_task_id"):
        ids.extend(_task_state_related_ids(relations.get(key)))
    deduped: list[str] = []
    seen: set[str] = set()
    for task_id in ids:
        if task_id and task_id not in seen:
            seen.add(task_id)
            deduped.append(task_id)
    return deduped


def _context_requested_related_task_ids(
    payload: dict[str, Any],
    workspace_current: dict[str, Any] | None = None,
) -> list[str]:
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    ids: list[str] = []
    for source in (payload, filters, workspace_current if isinstance(workspace_current, dict) else {}):
        ids.extend(_context_related_task_ids_from_source(source))
    deduped: list[str] = []
    seen: set[str] = set()
    for task_id in ids:
        if task_id and task_id not in seen:
            seen.add(task_id)
            deduped.append(task_id)
    return deduped


def _context_requested_task_scope_ids(
    requested_task_id: str | None,
    related_task_ids: list[str] | None = None,
) -> set[str]:
    ids: set[str] = set()
    if requested_task_id:
        ids.add(requested_task_id)
    for related_id in related_task_ids or []:
        normalized = _task_state_normalized_id(related_id)
        if normalized:
            ids.add(normalized)
    return ids


def _task_state_id_matches_any(task_id: str | None, task_ids: set[str]) -> bool:
    return any(_task_state_ids_match(task_id, candidate) for candidate in task_ids)


def _context_memory_related_task_ids(memory: dict[str, Any]) -> set[str]:
    metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
    task_state = metadata.get("task_state") if isinstance(metadata.get("task_state"), dict) else {}
    scope = task_state.get("scope") if isinstance(task_state.get("scope"), dict) else {}
    ids: set[str] = set()
    for source in (task_state, scope, metadata):
        for related_id in _context_related_task_ids_from_source(source):
            ids.add(related_id)
    return ids


def _context_memory_links_requested_task(memory: dict[str, Any], requested_task_id: str | None) -> bool:
    if not requested_task_id:
        return False
    return any(_task_state_ids_match(related_id, requested_task_id) for related_id in _context_memory_related_task_ids(memory))


def _context_task_scope_match_reason(
    memory: dict[str, Any],
    requested_task_id: str | None,
    requested_task_scope_ids: set[str],
) -> str:
    memory_task_id = _context_memory_task_state_id(memory)
    memory_task_tag_id = _context_memory_task_tag_id(memory)
    for candidate_task_id in (memory_task_id, memory_task_tag_id):
        if candidate_task_id is None:
            continue
        if _task_state_ids_match(candidate_task_id, requested_task_id):
            return "selected_exact_task"
        if _task_state_id_matches_any(candidate_task_id, requested_task_scope_ids):
            return "selected_related_task"
    if _context_memory_links_requested_task(memory, requested_task_id):
        return "selected_reverse_related_task"
    return "selected_task_scope"


def _context_matches_requested_task(
    memory: dict[str, Any],
    requested_task_id: str | None,
    requested_task_scope_ids: set[str] | None = None,
) -> bool:
    if not requested_task_id:
        return True
    task_scope_ids = requested_task_scope_ids or {requested_task_id}
    memory_task_id = _context_memory_task_state_id(memory)
    if memory_task_id is not None:
        return _task_state_id_matches_any(memory_task_id, task_scope_ids) or _context_memory_links_requested_task(
            memory,
            requested_task_id,
        )
    memory_task_tag_id = _context_memory_task_tag_id(memory)
    if memory_task_tag_id is not None:
        return _task_state_id_matches_any(memory_task_tag_id, task_scope_ids) or _context_memory_links_requested_task(
            memory,
            requested_task_id,
        )
    return True


def _context_backfill_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in filters.items()
        if key not in {"task_id", "goal_id"}
    }


def _context_memory_score(memory: dict[str, Any]) -> float:
    try:
        return float(memory.get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _context_trace_candidate_snapshot(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
    return {
        "id": str(memory.get("id") or ""),
        "memory": str(memory.get("memory") or ""),
        "score": round(_context_memory_score(memory), 4),
        "role": _working_memory_role(memory),
        "reason": memory.get("reason") or _context_reason(memory),
        "context_tokens": int(memory.get("context_tokens") or 0),
        "categories": list(memory.get("categories") or []),
        "metadata": metadata,
        "created_at": memory.get("created_at"),
        "updated_at": memory.get("updated_at"),
    }


def _context_selector_rejection_sample(
    memory: dict[str, Any],
    *,
    reason: str,
    threshold: float | None = None,
    competing_memory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sample = {
        "memory_id": str(memory.get("id") or ""),
        "role": _working_memory_role(memory),
        "score": round(_context_memory_score(memory), 4),
        "reason": reason,
    }
    if threshold is not None:
        sample["threshold"] = round(threshold, 4)
    if isinstance(competing_memory, dict):
        sample.update(
            {
                "competing_memory_id": str(competing_memory.get("id") or ""),
                "competing_role": _working_memory_role(competing_memory),
                "competing_score": round(_context_memory_score(competing_memory), 4),
                "score_gap": round(_context_memory_score(competing_memory) - _context_memory_score(memory), 4),
            }
        )
    return sample


def _context_selector_rejection_counts(samples: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"score_floor": 0, "tradeoff_gap": 0}
    for sample in samples:
        reason = str(sample.get("reason") or "")
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _context_selector_selected_role_count(selected: list[dict[str, Any]], role: str) -> int:
    return sum(1 for memory in selected if _working_memory_role(memory) == role)


def _context_selector_stronger_skipped(
    memory: dict[str, Any],
    *,
    diversity_skipped: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    role = _working_memory_role(memory)
    role_priority = _CONTEXT_SELECTOR_ROLE_PRIORITY.get(role, 0)
    score = _context_memory_score(memory)
    return [
        skipped
        for skipped in diversity_skipped
        if _CONTEXT_SELECTOR_ROLE_PRIORITY.get(_working_memory_role(skipped), 0) >= role_priority
        and _context_memory_score(skipped) - score > _CONTEXT_SELECTOR_TRADEOFF_GAP_TOLERANCE
    ]


def _context_selector_soft_quota_sample(
    memory: dict[str, Any],
    *,
    selected: list[dict[str, Any]],
    diversity_skipped: list[dict[str, Any]],
) -> dict[str, Any] | None:
    role = _working_memory_role(memory)
    quota = int(_CONTEXT_SELECTOR_SOFT_ROLE_QUOTAS.get(role) or 0)
    if quota <= 0 or _context_selector_selected_role_count(selected, role) >= quota:
        return None
    score_floor = _CONTEXT_SELECTOR_SOFT_QUOTA_SCORE_FLOORS.get(role, 0.0)
    score = _context_memory_score(memory)
    if score < score_floor:
        return None
    stronger_skipped = _context_selector_stronger_skipped(memory, diversity_skipped=diversity_skipped)
    if not stronger_skipped:
        return None
    competing = max(stronger_skipped, key=_context_memory_score)
    return {
        "memory_id": str(memory.get("id") or ""),
        "role": role,
        "score": round(score, 4),
        "quota": quota,
        "score_floor": round(score_floor, 4),
        "competing_memory_id": str(competing.get("id") or ""),
        "competing_role": _working_memory_role(competing),
        "competing_score": round(_context_memory_score(competing), 4),
        "score_gap": round(_context_memory_score(competing) - score, 4),
    }


def _context_selector_tradeoff_rejection(
    memory: dict[str, Any],
    *,
    diversity_skipped: list[dict[str, Any]],
) -> dict[str, Any] | None:
    stronger_skipped = _context_selector_stronger_skipped(memory, diversity_skipped=diversity_skipped)
    if not stronger_skipped:
        return None
    competing = max(stronger_skipped, key=_context_memory_score)
    return _context_selector_rejection_sample(
        memory,
        reason="tradeoff_gap",
        threshold=_CONTEXT_SELECTOR_TRADEOFF_GAP_TOLERANCE,
        competing_memory=competing,
    )


def _context_diversity_tradeoffs(
    *,
    diversity_skipped: list[dict[str, Any]],
    selected: list[dict[str, Any]],
) -> dict[str, Any]:
    selected_ids = {str(memory.get("id")) for memory in selected if memory.get("id")}
    tradeoffs: list[dict[str, Any]] = []
    max_gap = 0.0
    for skipped in diversity_skipped:
        skipped_id = str(skipped.get("id") or "")
        if not skipped_id or skipped_id in selected_ids:
            continue
        skipped_role = _working_memory_role(skipped)
        skipped_score = _context_memory_score(skipped)
        lower_selected = [
            memory
            for memory in selected
            if _working_memory_role(memory) != skipped_role
            and _context_memory_score(memory) < skipped_score
            and str(memory.get("id") or "")
        ]
        if not lower_selected:
            continue
        selected_lower = min(lower_selected, key=_context_memory_score)
        selected_score = _context_memory_score(selected_lower)
        score_gap = round(max(skipped_score - selected_score, 0.0), 4)
        max_gap = max(max_gap, score_gap)
        tradeoff = {
            "skipped_memory_id": skipped_id,
            "skipped_role": skipped_role,
            "skipped_score": round(skipped_score, 4),
            "selected_memory_id": str(selected_lower.get("id")),
            "selected_role": _working_memory_role(selected_lower),
            "selected_score": round(selected_score, 4),
            "score_gap": score_gap,
        }
        tradeoffs.append(tradeoff)
    return {
        "diversity_tradeoff_count": len(tradeoffs),
        "diversity_tradeoff_max_score_gap": round(max_gap, 4),
        "diversity_tradeoff_samples": tradeoffs[:5],
    }


def _context_memory_is_superseded(memory: dict[str, Any]) -> bool:
    # Search keeps superseded memories retrievable (red label, history and
    # audit queries need them); assembled ACTION context must not — a struck-
    # through fact re-entering the acting prompt defeats the supersede
    # contract. Found via dogfood repro on 0.2.0 (issue #3).
    return bool((memory.get("metadata") or {}).get("superseded_at"))


def _context_role_backfill_candidates(
    *,
    search_payload: dict[str, Any],
    project_id: str,
    requested_task_id: str | None,
    requested_task_scope_ids: set[str],
    existing_memory_ids: set[str],
    workspace_duplicate_memory_id: str | None,
    max_backfill: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    backfill_state = {
        "applied": False,
        "reason": "not_task_scoped",
        "selector_policy_version": _CONTEXT_SELECTOR_POLICY_VERSION,
        "score_floors": dict(_CONTEXT_SELECTOR_ROLE_SCORE_FLOORS),
        "tradeoff_gap_tolerance": _CONTEXT_SELECTOR_TRADEOFF_GAP_TOLERANCE,
        "soft_quotas": dict(_CONTEXT_SELECTOR_SOFT_ROLE_QUOTAS),
        "soft_quota_score_floors": dict(_CONTEXT_SELECTOR_SOFT_QUOTA_SCORE_FLOORS),
        "soft_quota_applied_count": 0,
        "soft_quota_samples": [],
        "candidate_ids": [],
        "candidate_snapshots": [],
        "eligible_memory_ids": [],
        "admissible_memory_ids": [],
        "raw_candidate_count": 0,
        "eligible_count": 0,
        "admissible_count": 0,
        "selected_count": 0,
        "memory_ids": [],
        "selected_role_counts": {role: 0 for role in _WORKING_MEMORY_ROLE_ORDER if role != "current_workspace"},
        "diversity_first_pass": False,
        "diversity_tradeoff_count": 0,
        "diversity_tradeoff_max_score_gap": 0.0,
        "diversity_tradeoff_samples": [],
        "rejected_count": 0,
        "rejection_counts": {"score_floor": 0, "tradeoff_gap": 0},
        "rejected_samples": [],
        "filters": {},
    }
    if not requested_task_id or max_backfill <= 0:
        return [], backfill_state
    filters = search_payload.get("filters") if isinstance(search_payload.get("filters"), dict) else {}
    backfill_filters = _context_backfill_filters(filters)
    backfill_state["filters"] = backfill_filters
    if backfill_filters == filters:
        backfill_state["reason"] = "no_task_scope_filter_to_relax"
        return [], backfill_state
    if not has_entity_filter(backfill_filters):
        backfill_state["reason"] = "missing_entity_filter_after_task_scope_relaxation"
        return [], backfill_state

    payload = dict(search_payload)
    payload["filters"] = backfill_filters
    payload["top_k"] = max(_int_or(search_payload.get("top_k"), 10), max_backfill * 4, 12)
    search = search_memories(payload, project_id=project_id)
    raw_candidates = search.get("results") or []
    current_candidates = [memory for memory in raw_candidates if not _context_memory_is_superseded(memory)]
    backfill_state["applied"] = True
    backfill_state["reason"] = "relaxed_task_scope_for_non_task_state_roles"
    backfill_state["raw_candidate_count"] = len(raw_candidates)
    backfill_state["candidate_ids"] = [str(memory.get("id")) for memory in raw_candidates if memory.get("id")]
    backfill_state["candidate_snapshots"] = [
        _context_trace_candidate_snapshot(memory) for memory in raw_candidates if memory.get("id")
    ]

    eligible: list[dict[str, Any]] = []
    for memory in current_candidates:
        memory_id = str(memory.get("id") or "")
        if not memory_id or memory_id in existing_memory_ids:
            continue
        if workspace_duplicate_memory_id and memory_id == workspace_duplicate_memory_id:
            continue
        if _context_memory_task_state_id(memory) is not None:
            continue
        memory_task_tag_id = _context_memory_task_tag_id(memory)
        if (
            memory_task_tag_id is not None
            and not _task_state_id_matches_any(memory_task_tag_id, requested_task_scope_ids)
            and not _context_memory_links_requested_task(memory, requested_task_id)
        ):
            continue
        if _working_memory_role(memory) == "task_state":
            continue
        eligible.append(memory)
    backfill_state["eligible_count"] = len(eligible)
    backfill_state["eligible_memory_ids"] = [str(memory.get("id")) for memory in eligible if memory.get("id")]

    rejected_samples: list[dict[str, Any]] = []
    admissible: list[dict[str, Any]] = []
    for memory in eligible:
        role = _working_memory_role(memory)
        score_floor = _CONTEXT_SELECTOR_ROLE_SCORE_FLOORS.get(role, 0.0)
        if _context_memory_score(memory) < score_floor:
            rejected_samples.append(
                _context_selector_rejection_sample(
                    memory,
                    reason="score_floor",
                    threshold=score_floor,
                )
            )
            continue
        admissible.append(memory)
    backfill_state["admissible_count"] = len(admissible)
    backfill_state["admissible_memory_ids"] = [str(memory.get("id")) for memory in admissible if memory.get("id")]

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    rejected_ids: set[str] = set()
    selected_roles: set[str] = set()
    diversity_skipped: list[dict[str, Any]] = []
    soft_quota_samples: list[dict[str, Any]] = []
    for memory in admissible:
        memory_id = str(memory.get("id") or "")
        role = _working_memory_role(memory)
        if role in selected_roles:
            diversity_skipped.append(memory)
            continue
        soft_quota_sample = _context_selector_soft_quota_sample(
            memory,
            selected=selected,
            diversity_skipped=diversity_skipped,
        )
        tradeoff_rejection = _context_selector_tradeoff_rejection(
            memory,
            diversity_skipped=diversity_skipped,
        ) if soft_quota_sample is None else None
        if tradeoff_rejection:
            rejected_samples.append(tradeoff_rejection)
            rejected_ids.add(memory_id)
            continue
        if soft_quota_sample:
            soft_quota_samples.append(soft_quota_sample)
        selected.append(memory)
        selected_ids.add(memory_id)
        selected_roles.add(role)
        existing_memory_ids.add(memory_id)
        if len(selected) >= max_backfill:
            break
    if len(selected) < max_backfill:
        for memory in admissible:
            memory_id = str(memory.get("id") or "")
            if memory_id in selected_ids or memory_id in rejected_ids:
                continue
            selected.append(memory)
            selected_ids.add(memory_id)
            existing_memory_ids.add(memory_id)
            if len(selected) >= max_backfill:
                break

    backfill_state["selected_count"] = len(selected)
    backfill_state["memory_ids"] = [str(memory.get("id")) for memory in selected if memory.get("id")]
    role_counts = {role: 0 for role in _WORKING_MEMORY_ROLE_ORDER if role != "current_workspace"}
    for memory in selected:
        role = _working_memory_role(memory)
        role_counts[role] = role_counts.get(role, 0) + 1
    backfill_state["selected_role_counts"] = role_counts
    backfill_state["diversity_first_pass"] = True
    backfill_state.update(
        _context_diversity_tradeoffs(diversity_skipped=diversity_skipped, selected=selected)
    )
    backfill_state["rejected_count"] = len(rejected_samples)
    backfill_state["rejection_counts"] = _context_selector_rejection_counts(rejected_samples)
    backfill_state["rejected_samples"] = rejected_samples[:5]
    backfill_state["soft_quota_applied_count"] = len(soft_quota_samples)
    backfill_state["soft_quota_samples"] = soft_quota_samples[:5]
    return selected, backfill_state


def _context_workspace_duplicate_memory_id(
    workspace_current: dict[str, Any] | None,
    requested_task_id: str | None,
) -> str | None:
    if not requested_task_id or not isinstance(workspace_current, dict):
        return None
    current_task_id = workspace_current.get("task_id")
    if current_task_id in (None, ""):
        return None
    if not _task_state_ids_match(requested_task_id, str(current_task_id)):
        return None
    claim_id = workspace_current.get("claim_id")
    if claim_id in (None, ""):
        return None
    return f"claim:{claim_id}"


def _context_hygiene_summary(
    *,
    raw_candidate_count: int,
    task_scoped_candidate_count: int,
    selected_count: int,
    omitted_count: int,
    requested_task_id: str | None,
    requested_related_task_ids: list[str] | None,
    task_scope_filtered_memory_ids: list[str],
    workspace_duplicate_filtered_memory_ids: list[str],
    workspace_current: dict[str, Any] | None,
    selected_memories: list[dict[str, Any]] | None = None,
    role_backfill: dict[str, Any] | None = None,
) -> dict[str, Any]:
    next_actions = []
    evidence_files = []
    terminal_evidence_refs = []
    workspace_summary_drift: list[dict[str, Any]] = []
    if isinstance(workspace_current, dict):
        next_actions = [str(item) for item in workspace_current.get("next_actions") or [] if str(item).strip()]
        evidence_files = [str(item) for item in workspace_current.get("evidence_files") or [] if str(item).strip()]
        terminal_evidence_refs = [
            ref for ref in workspace_current.get("terminal_evidence_refs") or [] if isinstance(ref, dict)
        ]
        summary_text = " ".join(
            str(workspace_current.get(field) or "")
            for field in ("summary", "current_goal", "active_hypothesis")
        )
        actual_terminal_count = len(terminal_evidence_refs)
        seen_drift: set[tuple[str, int, int]] = set()
        for match in re.finditer(r"(?:terminal[_\s-]*evidence(?:[_\s-]*count)?|Terminal evidence)\s*[(:=]\s*(\d+)", summary_text):
            mentioned_count = int(match.group(1))
            if mentioned_count != actual_terminal_count:
                drift_key = ("terminal_evidence_count", mentioned_count, actual_terminal_count)
                if drift_key in seen_drift:
                    continue
                seen_drift.add(drift_key)
                workspace_summary_drift.append(
                    {
                        "field": "terminal_evidence_count",
                        "mentioned_count": mentioned_count,
                        "actual_count": actual_terminal_count,
                    }
                )
    role_counts = _working_memory_role_counts(selected_memories or [], workspace_current)
    role_balance = _working_memory_role_balance(role_counts)
    role_backfill = role_backfill if isinstance(role_backfill, dict) else {}
    requested_task_aliases = sorted(_task_state_id_aliases(requested_task_id))
    requested_related_task_ids = list(requested_related_task_ids or [])
    diagnostics = []
    if requested_task_id:
        diagnostics.append(
            {
                "code": "task_scope_filter",
                "severity": "info",
                "message": (
                    f"Filtered {len(task_scope_filtered_memory_ids)} task-state candidate(s) "
                    f"outside requested task {requested_task_id}."
                ),
            }
        )
        if len(requested_task_aliases) > 1:
            diagnostics.append(
                {
                    "code": "task_scope_alias_family",
                    "severity": "info",
                    "message": (
                        "Task scope accepts namespace aliases: "
                        + ", ".join(requested_task_aliases[:5])
                        + ("." if len(requested_task_aliases) <= 5 else "; +more.")
                    ),
                }
            )
        if requested_related_task_ids:
            diagnostics.append(
                {
                    "code": "task_scope_related_family",
                    "severity": "info",
                    "message": (
                        "Task scope accepts explicit related tasks: "
                        + ", ".join(requested_related_task_ids[:5])
                        + ("." if len(requested_related_task_ids) <= 5 else "; +more.")
                    ),
                }
            )
    else:
        diagnostics.append(
            {
                "code": "task_scope_filter_skipped",
                "severity": "info",
                "message": "No task_id or goal_id was provided, so task-scope filtering was not applied.",
            }
        )
    if workspace_duplicate_filtered_memory_ids:
        diagnostics.append(
            {
                "code": "workspace_duplicate_filter",
                "severity": "info",
                "message": (
                    f"Removed {len(workspace_duplicate_filtered_memory_ids)} current-workspace claim duplicate(s) "
                    "from query evidence."
                ),
            }
        )
    if selected_count == 0 and raw_candidate_count > 0:
        diagnostics.append(
            {
                "code": "query_evidence_empty",
                "severity": "info",
                "message": "No query evidence remains after filtering; context contains only the current workspace.",
            }
        )
    if role_backfill.get("applied"):
        diagnostics.append(
            {
                "code": "role_aware_backfill",
                "severity": "info",
                "message": (
                    f"Backfilled {int(role_backfill.get('selected_count') or 0)} non-task-state memory "
                    f"candidate(s) after relaxing task scope with role diversity."
                ),
            }
        )
        diversity_tradeoff_count = int(role_backfill.get("diversity_tradeoff_count") or 0)
        if diversity_tradeoff_count:
            diagnostics.append(
                {
                    "code": "role_diversity_tradeoff",
                    "severity": "info",
                    "message": (
                        "Role-aware backfill skipped "
                        f"{diversity_tradeoff_count} higher-scoring same-role candidate(s) "
                        "while preserving role diversity."
                    ),
                }
            )
        selector_rejected_count = int(role_backfill.get("rejected_count") or 0)
        if selector_rejected_count:
            diagnostics.append(
                {
                    "code": "role_selector_rejections",
                    "severity": "info",
                    "message": (
                        f"Selector policy rejected {selector_rejected_count} role-aware backfill "
                        "candidate(s) by score floor or tradeoff gap."
                    ),
                }
            )
        soft_quota_applied_count = int(role_backfill.get("soft_quota_applied_count") or 0)
        if soft_quota_applied_count:
            diagnostics.append(
                {
                    "code": "role_soft_quota",
                    "severity": "info",
                    "message": (
                        f"Selector policy preserved {soft_quota_applied_count} evidence/product "
                        "candidate(s) through soft role quota."
                    ),
                }
            )
    if len(next_actions) > 2:
        diagnostics.append(
            {
                "code": "next_actions_compacted",
                "severity": "info",
                "message": f"Compacted {len(next_actions)} next action(s) in context text; full list remains structured.",
            }
        )
    if len(evidence_files) > 3:
        diagnostics.append(
            {
                "code": "evidence_files_compacted",
                "severity": "info",
                "message": f"Compacted {len(evidence_files)} evidence file path(s) in context text; full list remains structured.",
            }
        )
    if terminal_evidence_refs:
        diagnostics.append(
            {
                "code": "terminal_evidence_visible",
                "severity": "info",
                "message": f"Rendered {len(terminal_evidence_refs)} terminal evidence ref(s) in context text.",
            }
        )
    if role_balance["active_roles"]:
        role_summary = ", ".join(
            f"{role}={count}" for role, count in role_balance["active_roles"].items()
        )
        diagnostics.append(
            {
                "code": "role_distribution",
                "severity": "info",
                "message": f"Selected context roles: {role_summary}.",
            }
        )
    if (
        role_balance["non_workspace_selected_count"] >= 2
        and role_balance["dominant_role"]
        and role_balance["dominant_ratio"] >= 0.8
    ):
        diagnostics.append(
            {
                "code": "role_concentration",
                "severity": "info",
                "message": (
                    f"Query evidence is concentrated in {role_balance['dominant_role']} "
                    f"({role_balance['dominant_count']}/{role_balance['non_workspace_selected_count']})."
                ),
            }
        )
    for drift in workspace_summary_drift:
        diagnostics.append(
            {
                "code": "workspace_summary_drift",
                "severity": "warning",
                "message": (
                    f"Workspace summary mentions {drift['field']}={drift['mentioned_count']}, "
                    f"but structured state has {drift['actual_count']}."
                ),
            }
        )
    summary_parts = [f"selected {selected_count}/{raw_candidate_count} raw candidate(s)"]
    if requested_task_id:
        summary_parts.append(f"task-scope filtered {len(task_scope_filtered_memory_ids)}")
    if len(requested_task_aliases) > 1:
        summary_parts.append(f"task aliases {len(requested_task_aliases)}")
    if requested_related_task_ids:
        summary_parts.append(f"related task scope {len(requested_related_task_ids)}")
    if workspace_duplicate_filtered_memory_ids:
        summary_parts.append(f"workspace-duplicate filtered {len(workspace_duplicate_filtered_memory_ids)}")
    if omitted_count:
        summary_parts.append(f"omitted {omitted_count}")
    if len(next_actions) > 2:
        summary_parts.append("compacted next actions")
    if len(evidence_files) > 3:
        summary_parts.append("compacted evidence files")
    if terminal_evidence_refs:
        summary_parts.append(f"terminal evidence {len(terminal_evidence_refs)}")
    if workspace_summary_drift:
        summary_parts.append("workspace summary drift")
    if selected_count == 0 and raw_candidate_count > 0:
        summary_parts.append("query evidence empty")
    if role_backfill.get("applied"):
        summary_parts.append(f"role-aware backfill {int(role_backfill.get('selected_count') or 0)}")
        diversity_tradeoff_count = int(role_backfill.get("diversity_tradeoff_count") or 0)
        if diversity_tradeoff_count:
            summary_parts.append(f"diversity tradeoff {diversity_tradeoff_count}")
        selector_rejected_count = int(role_backfill.get("rejected_count") or 0)
        if selector_rejected_count:
            summary_parts.append(f"selector rejected {selector_rejected_count}")
        soft_quota_applied_count = int(role_backfill.get("soft_quota_applied_count") or 0)
        if soft_quota_applied_count:
            summary_parts.append(f"soft quota {soft_quota_applied_count}")
    if role_balance["active_roles"]:
        role_summary = ", ".join(
            f"{role}={count}" for role, count in role_balance["active_roles"].items()
        )
        summary_parts.append(f"roles {role_summary}")
    return {
        "schema_version": "mem1-context-hygiene-v1",
        "summary": "; ".join(summary_parts),
        "diagnostics": diagnostics,
        "workspace_summary_drift": workspace_summary_drift,
        "selected_role_counts": role_balance["selected_role_counts"],
        "role_balance": role_balance,
        "role_aware_backfill": {
            "applied": bool(role_backfill.get("applied")),
            "reason": role_backfill.get("reason") or "not_applied",
            "selector_policy_version": role_backfill.get("selector_policy_version")
            or _CONTEXT_SELECTOR_POLICY_VERSION,
            "score_floors": (
                role_backfill.get("score_floors")
                if isinstance(role_backfill.get("score_floors"), dict)
                else dict(_CONTEXT_SELECTOR_ROLE_SCORE_FLOORS)
            ),
            "soft_quotas": (
                role_backfill.get("soft_quotas")
                if isinstance(role_backfill.get("soft_quotas"), dict)
                else dict(_CONTEXT_SELECTOR_SOFT_ROLE_QUOTAS)
            ),
            "soft_quota_score_floors": (
                role_backfill.get("soft_quota_score_floors")
                if isinstance(role_backfill.get("soft_quota_score_floors"), dict)
                else dict(_CONTEXT_SELECTOR_SOFT_QUOTA_SCORE_FLOORS)
            ),
            "soft_quota_applied_count": int(role_backfill.get("soft_quota_applied_count") or 0),
            "soft_quota_samples": (
                list(role_backfill.get("soft_quota_samples") or [])
                if isinstance(role_backfill.get("soft_quota_samples"), list)
                else []
            ),
            "tradeoff_gap_tolerance": round(
                _float_or(role_backfill.get("tradeoff_gap_tolerance"), _CONTEXT_SELECTOR_TRADEOFF_GAP_TOLERANCE),
                4,
            ),
            "raw_candidate_count": int(role_backfill.get("raw_candidate_count") or 0),
            "eligible_count": int(role_backfill.get("eligible_count") or 0),
            "admissible_count": int(role_backfill.get("admissible_count") or 0),
            "selected_count": int(role_backfill.get("selected_count") or 0),
            "memory_ids": list(role_backfill.get("memory_ids") or []),
            "selected_role_counts": (
                role_backfill.get("selected_role_counts")
                if isinstance(role_backfill.get("selected_role_counts"), dict)
                else {role: 0 for role in _WORKING_MEMORY_ROLE_ORDER if role != "current_workspace"}
            ),
            "diversity_first_pass": bool(role_backfill.get("diversity_first_pass")),
            "diversity_tradeoff_count": int(role_backfill.get("diversity_tradeoff_count") or 0),
            "diversity_tradeoff_max_score_gap": round(
                _float_or(role_backfill.get("diversity_tradeoff_max_score_gap"), 0.0),
                4,
            ),
            "diversity_tradeoff_samples": (
                list(role_backfill.get("diversity_tradeoff_samples") or [])
                if isinstance(role_backfill.get("diversity_tradeoff_samples"), list)
                else []
            ),
            "rejected_count": int(role_backfill.get("rejected_count") or 0),
            "rejection_counts": (
                role_backfill.get("rejection_counts")
                if isinstance(role_backfill.get("rejection_counts"), dict)
                else {"score_floor": 0, "tradeoff_gap": 0}
            ),
            "rejected_samples": (
                list(role_backfill.get("rejected_samples") or [])
                if isinstance(role_backfill.get("rejected_samples"), list)
                else []
            ),
            "filters": role_backfill.get("filters") if isinstance(role_backfill.get("filters"), dict) else {},
        },
        "raw_candidate_count": raw_candidate_count,
        "task_scoped_candidate_count": task_scoped_candidate_count,
        "selected_count": selected_count,
        "omitted_count": omitted_count,
        "task_scope_filter": {
            "applied": bool(requested_task_id),
            "requested_task_id": requested_task_id,
            "requested_task_aliases": requested_task_aliases,
            "requested_related_task_ids": requested_related_task_ids,
            "filtered_count": len(task_scope_filtered_memory_ids),
            "reason": "excluded_task_state_from_other_tasks" if requested_task_id else "not_task_scoped",
            "memory_ids": task_scope_filtered_memory_ids,
        },
        "workspace_duplicate_filter": {
            "applied": bool(requested_task_id and workspace_duplicate_filtered_memory_ids),
            "filtered_count": len(workspace_duplicate_filtered_memory_ids),
            "reason": "current_workspace_claim_already_rendered",
            "memory_ids": workspace_duplicate_filtered_memory_ids,
        },
        "workspace_context_compaction": {
            "next_actions_compacted": len(next_actions) > 2,
            "next_actions_count": len(next_actions),
            "evidence_files_compacted": len(evidence_files) > 3,
            "evidence_files_count": len(evidence_files),
            "terminal_evidence_compacted": len(terminal_evidence_refs) > 3,
            "terminal_evidence_count": len(terminal_evidence_refs),
        },
    }


def _autopilot_short_text(value: Any, max_chars: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _autopilot_list(value: Any, limit: int = 3, max_chars: int = 180) -> list[str]:
    if value in (None, ""):
        return []
    raw_items = value if isinstance(value, list) else [value]
    items: list[str] = []
    for item in raw_items:
        text = _autopilot_short_text(item, max_chars=max_chars)
        if text:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def _context_memory_task_state_payload(memory: dict[str, Any]) -> dict[str, Any]:
    metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
    task_state = metadata.get("task_state") if isinstance(metadata.get("task_state"), dict) else {}
    return task_state


def _context_list_from_nested(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple) or isinstance(value, set):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict):
        items: list[str] = []
        for key, nested in value.items():
            if str(key).lower() in {"file", "files", "path", "paths", "target", "artifact", "artifacts", "evidence_file", "evidence_files"}:
                items.extend(_context_list_from_nested(nested))
        return items
    return [str(value).strip()]


def _context_memory_artifacts(memory: dict[str, Any]) -> list[str]:
    metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
    task_state = _context_memory_task_state_payload(memory)
    artifacts: list[str] = []
    for key in ("evidence_files", "files", "relevant_artifacts", "artifacts"):
        artifacts.extend(_context_list_from_nested(task_state.get(key)))
        artifacts.extend(_context_list_from_nested(metadata.get(key)))
    for key in ("file", "path", "target", "evidence_file"):
        artifacts.extend(_context_list_from_nested(metadata.get(key)))
    evidence = task_state.get("evidence") if isinstance(task_state.get("evidence"), dict) else {}
    artifacts.extend(_context_list_from_nested(evidence))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in artifacts:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _context_artifact_keys(paths: list[str]) -> set[str]:
    keys: set[str] = set()
    for path in paths:
        text = str(path or "").strip()
        if not text:
            continue
        normalized = os.path.normpath(text).lower()
        keys.add(normalized)
        basename = os.path.basename(normalized.rstrip("/"))
        if basename:
            keys.add(f"basename:{basename}")
    return keys


def _context_artifact_match(workspace_paths: list[str], candidate_paths: list[str]) -> tuple[int, list[str]]:
    best_strength = 0
    labels: list[str] = []
    for workspace_path in workspace_paths:
        workspace_text = str(workspace_path or "").strip()
        if not workspace_text:
            continue
        workspace_norm = os.path.normpath(workspace_text).lower()
        workspace_base = os.path.basename(workspace_norm.rstrip("/"))
        for candidate_path in candidate_paths:
            candidate_text = str(candidate_path or "").strip()
            if not candidate_text:
                continue
            candidate_norm = os.path.normpath(candidate_text).lower()
            candidate_base = os.path.basename(candidate_norm.rstrip("/"))
            strength = 0
            label = ""
            if workspace_norm == candidate_norm:
                strength = 3
                label = f"exact:{workspace_text}"
            elif workspace_norm.endswith(f"/{candidate_norm}") or candidate_norm.endswith(f"/{workspace_norm}"):
                strength = 2
                label = f"suffix:{workspace_text}"
            elif workspace_base and workspace_base == candidate_base:
                strength = 1
                label = f"basename:{workspace_base}"
            if strength <= 0:
                continue
            if strength > best_strength:
                best_strength = strength
                labels = [label]
            elif strength == best_strength and label not in labels:
                labels.append(label)
    return best_strength, labels[:5]


def _context_fallback_candidate(
    memory: dict[str, Any],
    *,
    match_reason: str = "",
    matched_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
    task_state = _context_memory_task_state_payload(memory)
    lifecycle = str(task_state.get("claim_lifecycle") or metadata.get("claim_lifecycle") or "").upper()
    terminal_refs = task_state.get("terminal_evidence_refs") or []
    artifacts = [
        artifact
        for artifact in _context_memory_artifacts(memory)
        if not _context_sensitive_target_reason(artifact)
    ]
    visible_matched_artifacts = [
        artifact
        for artifact in list(matched_artifacts or [])
        if not _context_sensitive_target_reason(artifact)
    ]
    return {
        "memory_id": str(memory.get("id") or ""),
        "role": _working_memory_role(memory),
        "score": round(_context_memory_score(memory), 4),
        "task_id": _context_memory_task_state_id(memory) or _context_memory_task_tag_id(memory) or "",
        "claim_lifecycle": lifecycle,
        "terminal_evidence_count": len(terminal_refs) if isinstance(terminal_refs, list) else 0,
        "updated_at": memory.get("updated_at"),
        "summary": _autopilot_short_text(memory.get("memory"), max_chars=180),
        "artifacts": artifacts[:3],
        "match_reason": match_reason,
        "matched_artifacts": visible_matched_artifacts[:3],
    }


def _context_fallback_stage(
    name: str,
    *,
    status: str,
    reason: str,
    candidates: list[dict[str, Any]] | None = None,
    candidate_count: int | None = None,
) -> dict[str, Any]:
    candidates = list(candidates or [])
    memory_ids = [str(candidate.get("memory_id")) for candidate in candidates if candidate.get("memory_id")]
    stage = {
        "name": name,
        "status": status,
        "reason": reason,
        "candidate_count": len(candidates) if candidate_count is None else int(candidate_count),
        "memory_ids": memory_ids[:5],
    }
    if candidates:
        stage["candidates"] = candidates[:3]
    return stage


def _context_parent_goal_ids(
    payload: dict[str, Any],
    workspace_current: dict[str, Any] | None = None,
) -> set[str]:
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    parent_ids: set[str] = set()
    for source in (payload, filters, workspace_current if isinstance(workspace_current, dict) else {}):
        for key in ("goal_id", "parent_goal_id", "parent_task_id"):
            value = source.get(key) if isinstance(source, dict) else None
            if value not in (None, ""):
                parent_ids.add(_task_state_id({"task_id": value}))
    return parent_ids


def _context_memory_parent_goal_id(memory: dict[str, Any]) -> str | None:
    metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
    task_state = _context_memory_task_state_payload(memory)
    scope = task_state.get("scope") if isinstance(task_state.get("scope"), dict) else {}
    for source in (task_state, scope, metadata):
        for key in ("goal_id", "parent_goal_id", "parent_task_id"):
            value = source.get(key) if isinstance(source, dict) else None
            if value not in (None, ""):
                return _task_state_id({"task_id": value})
    return None


def _context_memory_is_verified_task_state(memory: dict[str, Any]) -> bool:
    task_state = _context_memory_task_state_payload(memory)
    metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
    lifecycle = str(task_state.get("claim_lifecycle") or metadata.get("claim_lifecycle") or "").upper()
    terminal_refs = task_state.get("terminal_evidence_refs") or []
    return lifecycle in {"CONFIRMED", "VERIFIED", "SUPPORTED"} or bool(terminal_refs)


def _context_fallback_cascade(
    *,
    payload: dict[str, Any],
    requested_task_id: str | None,
    requested_task_scope_ids: set[str],
    raw_candidates: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    task_scope_filtered_memory_ids: list[str],
    workspace_duplicate_filtered_memory_ids: list[str],
    workspace_current: dict[str, Any] | None,
    role_backfill: dict[str, Any],
) -> dict[str, Any]:
    raw_by_id = {str(memory.get("id")): memory for memory in raw_candidates if memory.get("id")}
    task_scope_filtered = [
        raw_by_id[memory_id]
        for memory_id in task_scope_filtered_memory_ids
        if memory_id in raw_by_id
    ]
    workspace_paths_raw = (
        _context_list_from_nested(workspace_current.get("evidence_files"))
        if isinstance(workspace_current, dict)
        else []
    )
    workspace_paths: list[str] = []
    sensitive_workspace_artifact_count = 0
    for path in workspace_paths_raw:
        if _context_sensitive_target_reason(path):
            sensitive_workspace_artifact_count += 1
            continue
        workspace_paths.append(path)
    workspace_keys = _context_artifact_keys(workspace_paths)

    exact_candidates = [
        _context_fallback_candidate(
            memory,
            match_reason=_context_task_scope_match_reason(memory, requested_task_id, requested_task_scope_ids),
        )
        for memory in selected
        if not requested_task_id
        or _task_state_id_matches_any(_context_memory_task_state_id(memory), requested_task_scope_ids)
        or _task_state_id_matches_any(_context_memory_task_tag_id(memory), requested_task_scope_ids)
        or _context_memory_links_requested_task(memory, requested_task_id)
    ]
    parent_goal_ids = _context_parent_goal_ids(payload, workspace_current)
    parent_goal_candidates = [
        _context_fallback_candidate(memory, match_reason="same_parent_goal")
        for memory in task_scope_filtered
        if parent_goal_ids
        and not _context_memory_has_generic_task_id(memory)
        and _task_state_id_matches_any(_context_memory_parent_goal_id(memory), parent_goal_ids)
    ]

    same_artifact_candidates: list[dict[str, Any]] = []
    if workspace_keys:
        for memory in task_scope_filtered:
            if _context_memory_has_generic_task_id(memory):
                continue
            memory_artifacts = _context_memory_artifacts(memory)
            match_strength, matched_artifacts = _context_artifact_match(workspace_paths, memory_artifacts)
            if match_strength <= 0:
                continue
            candidate = _context_fallback_candidate(
                memory,
                match_reason="same_artifact",
                matched_artifacts=matched_artifacts,
            )
            candidate["artifact_match_strength"] = match_strength
            same_artifact_candidates.append(candidate)
    same_artifact_candidates.sort(
        key=lambda item: (
            int(item.get("artifact_match_strength") or 0),
            float(item.get("score") or 0.0),
            str(item.get("updated_at") or ""),
        ),
        reverse=True,
    )
    suggested_related_task_ids: list[str] = []
    suggested_related_task_details: list[dict[str, Any]] = []
    seen_suggested_related_task_ids: set[str] = set()
    if requested_task_id:
        for candidate in same_artifact_candidates:
            task_id = str(candidate.get("task_id") or "").strip()
            if not task_id:
                continue
            if _task_state_id_is_generic(task_id):
                continue
            if _task_state_ids_match(task_id, requested_task_id):
                continue
            if _task_state_id_matches_any(task_id, requested_task_scope_ids):
                continue
            if task_id in seen_suggested_related_task_ids:
                continue
            seen_suggested_related_task_ids.add(task_id)
            suggested_related_task_ids.append(task_id)
            suggested_related_task_details.append(
                {
                    "task_id": task_id,
                    "memory_id": str(candidate.get("memory_id") or ""),
                    "source_stage": "same_artifact",
                    "artifact_match_strength": int(candidate.get("artifact_match_strength") or 0),
                    "score": float(candidate.get("score") or 0.0),
                }
            )
            if len(suggested_related_task_ids) >= 3:
                break

    recent_verified_candidates = [
        _context_fallback_candidate(memory, match_reason="recent_verified_state")
        for memory in task_scope_filtered
        if _context_memory_is_verified_task_state(memory)
        and not _context_memory_has_generic_task_id(memory)
    ]
    recent_verified_candidates.sort(
        key=lambda item: (str(item.get("updated_at") or ""), float(item.get("score") or 0.0)),
        reverse=True,
    )

    stages = [
        _context_fallback_stage(
            "exact_task",
            status="used" if exact_candidates else "empty",
            reason="selected_query_evidence_for_requested_task" if exact_candidates else "no_selected_exact_task_query_evidence",
            candidates=exact_candidates,
        ),
        _context_fallback_stage(
            "parent_goal",
            status="available" if parent_goal_candidates else ("not_applicable" if not parent_goal_ids else "empty"),
            reason="candidate_task_state_shares_parent_goal"
            if parent_goal_candidates
            else ("no_parent_goal_requested" if not parent_goal_ids else "no_filtered_candidate_matches_parent_goal"),
            candidates=parent_goal_candidates,
        ),
        _context_fallback_stage(
            "same_artifact",
            status="available" if same_artifact_candidates else ("not_applicable" if not workspace_keys else "empty"),
            reason="filtered_candidate_touches_current_workspace_artifact"
            if same_artifact_candidates
            else ("current_workspace_has_no_artifacts" if not workspace_keys else "no_filtered_candidate_shares_artifact"),
            candidates=same_artifact_candidates,
        ),
        _context_fallback_stage(
            "current_workspace",
            status="used" if isinstance(workspace_current, dict) else "empty",
            reason="current_workspace_snapshot_rendered" if isinstance(workspace_current, dict) else "no_current_workspace_snapshot",
            candidate_count=1 if isinstance(workspace_current, dict) else 0,
        ),
        _context_fallback_stage(
            "recent_verified_state",
            status="available" if recent_verified_candidates else "empty",
            reason="filtered_candidate_has_terminal_evidence"
            if recent_verified_candidates
            else "no_filtered_verified_task_state_candidate",
            candidates=recent_verified_candidates,
        ),
    ]
    selected_stage = ""
    for stage in stages:
        if stage["status"] in {"used", "available"} and int(stage.get("candidate_count") or 0) > 0:
            selected_stage = str(stage["name"])
            break

    suggestions: list[dict[str, Any]] = []
    stage_by_name = {str(stage["name"]): stage for stage in stages}
    if selected_stage in {"parent_goal", "same_artifact", "recent_verified_state"}:
        candidate = (stage_by_name.get(selected_stage, {}).get("candidates") or [{}])[0]
        target = ""
        artifacts = candidate.get("artifacts") if isinstance(candidate, dict) else []
        if artifacts:
            target = next(
                (
                    str(artifact)
                    for artifact in artifacts
                    if not _context_sensitive_target_reason(artifact)
                ),
                "",
            )
        elif candidate.get("memory_id"):
            target = str(candidate["memory_id"])
        if target and _context_sensitive_target_reason(target):
            target = ""
        suggestions.append(
            {
                "action": f"inspect_{selected_stage}",
                "target": target,
                "memory_id": str(candidate.get("memory_id") or ""),
                "purpose": "Use bounded fallback evidence because task-scoped query evidence is empty.",
                "source": "context_fallback_cascade",
            }
        )
        if suggested_related_task_ids:
            suggestions.append(
                {
                    "action": "record_related_task_scope",
                    "target": ",".join(suggested_related_task_ids),
                    "related_task_ids": suggested_related_task_ids,
                    "purpose": (
                        "Persist these as related_task_ids if this same-artifact fallback is useful, "
                        "so future context can select it directly without broad task-scope relaxation."
                    ),
                    "source": "context_fallback_cascade",
                }
            )
    elif selected_stage == "current_workspace":
        suggestions.append(
            {
                "action": "continue_current_workspace",
                "target": str(workspace_current.get("task_id") or "") if isinstance(workspace_current, dict) else "",
                "purpose": "Use the current workspace snapshot because no query evidence survived filtering.",
                "source": "context_fallback_cascade",
            }
        )

    role_backfill_count = int(role_backfill.get("selected_count") or 0) if isinstance(role_backfill, dict) else 0
    return {
        "schema_version": CONTEXT_FALLBACK_CASCADE_SCHEMA_VERSION,
        "requested_task_id": requested_task_id or "",
        "selected_stage": selected_stage,
        "used_stages": [
            str(stage["name"])
            for stage in stages
            if stage["status"] in {"used", "available"} and int(stage.get("candidate_count") or 0) > 0
        ],
        "stages": stages,
        "suggestions": suggestions,
        "suggested_related_task_ids": suggested_related_task_ids,
        "suggested_related_task_details": suggested_related_task_details,
        "workspace_artifacts": workspace_paths[:5],
        "sensitive_workspace_artifact_count": sensitive_workspace_artifact_count,
        "task_scope_filtered_count": len(task_scope_filtered_memory_ids),
        "workspace_duplicate_filtered_count": len(workspace_duplicate_filtered_memory_ids),
        "role_aware_backfill_count": role_backfill_count,
    }


def _context_status_for_autopilot(
    *,
    raw_candidate_count: int,
    selected_count: int,
    task_scope_filtered_memory_ids: list[str],
    workspace_duplicate_filtered_memory_ids: list[str],
    workspace_current: dict[str, Any] | None,
    role_backfill: dict[str, Any],
    fallback_cascade: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fallback_used: list[str] = []
    if isinstance(workspace_current, dict):
        fallback_used.append("current_workspace")
    if int(role_backfill.get("selected_count") or 0) > 0:
        fallback_used.append("role_aware_backfill")
    if isinstance(fallback_cascade, dict):
        for stage in fallback_cascade.get("used_stages") or []:
            stage_name = str(stage)
            if stage_name and stage_name not in fallback_used:
                fallback_used.append(stage_name)
    excluded_count = len(task_scope_filtered_memory_ids) + len(workspace_duplicate_filtered_memory_ids)
    if selected_count > 0:
        status = "sufficient"
        primary_reason = "selected_memory"
        missing: list[str] = []
    elif raw_candidate_count > 0:
        status = "degraded" if fallback_used else "insufficient"
        if task_scope_filtered_memory_ids:
            primary_reason = "task_scope_filter"
        elif workspace_duplicate_filtered_memory_ids:
            primary_reason = "workspace_duplicate_filter"
        else:
            primary_reason = "candidate_filtering"
        missing = ["query_evidence"]
    else:
        status = "degraded" if fallback_used else "insufficient"
        primary_reason = "no_candidates"
        missing = ["candidate_memories"]
    selected_stage = ""
    if isinstance(fallback_cascade, dict):
        selected_stage = str(fallback_cascade.get("selected_stage") or "")
    fallback_actionable = bool(
        fallback_used
        and (
            isinstance(workspace_current, dict)
            or int(role_backfill.get("selected_count") or 0) > 0
            or selected_stage in {"same_artifact", "recent_verified_state", "current_workspace"}
        )
    )
    fallback_recovered = status == "degraded" and fallback_actionable
    if status == "sufficient":
        effective_status = "sufficient"
        issue_kind = "none"
        severity = "ok"
    elif fallback_recovered:
        effective_status = "fallback_ready"
        issue_kind = "normal_fallback"
        severity = "info"
    elif status == "degraded":
        effective_status = "degraded"
        issue_kind = "true_gap"
        severity = "warning"
    else:
        effective_status = "insufficient"
        issue_kind = "true_gap"
        severity = "blocker"
    recommendations = []
    if primary_reason == "task_scope_filter":
        recommendations.append("relax_task_scope_or_fix_task_id_alias")
    if isinstance(fallback_cascade, dict):
        for suggestion in fallback_cascade.get("suggestions") or []:
            if isinstance(suggestion, dict) and suggestion.get("action"):
                recommendations.append(str(suggestion["action"]))
    if "current_workspace" not in fallback_used:
        recommendations.append("record_task_state")
    status_result = {
        "schema_version": CONTEXT_STATUS_SCHEMA_VERSION,
        "status": status,
        "effective_status": effective_status,
        "primary_reason": primary_reason,
        "issue_kind": issue_kind,
        "severity": severity,
        "fallback_recovered": fallback_recovered,
        "excluded_candidate_count": excluded_count,
        "fallback_used": fallback_used,
        "missing": missing,
        "recommendations": list(dict.fromkeys(recommendations)),
    }
    if isinstance(fallback_cascade, dict):
        status_result["fallback_cascade"] = {
            "schema_version": fallback_cascade.get("schema_version"),
            "selected_stage": fallback_cascade.get("selected_stage") or "",
            "used_stages": fallback_cascade.get("used_stages") or [],
            "suggestions": fallback_cascade.get("suggestions") or [],
            "suggested_related_task_ids": fallback_cascade.get("suggested_related_task_ids") or [],
        }
    return status_result



def _context_relevant_targets(
    workspace_current: dict[str, Any] | None,
    selected: list[dict[str, Any]],
    fallback_cascade: dict[str, Any] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []

    def append_target(target: Any, source: str) -> bool:
        target_text = _autopilot_short_text(target, max_chars=240)
        if not target_text or _context_sensitive_target_reason(target_text):
            return False
        targets.append({"target": target_text, "source": source})
        return True

    if isinstance(workspace_current, dict):
        for path in _autopilot_list(workspace_current.get("evidence_files"), limit=3, max_chars=240):
            append_target(path, "current_workspace.evidence_files")
    for memory in selected:
        memory_id = str(memory.get("id") or "")
        metadata = memory.get("metadata") if isinstance(memory.get("metadata"), dict) else {}
        for key in ("file", "path", "target", "evidence_file"):
            if metadata.get(key):
                if append_target(
                    metadata.get(key),
                    f"memory:{memory_id}:{key}" if memory_id else f"memory:{key}",
                ):
                    break
        if len(targets) >= limit:
            break
    if isinstance(fallback_cascade, dict):
        for suggestion in fallback_cascade.get("suggestions") or []:
            if not isinstance(suggestion, dict) or not suggestion.get("target"):
                continue
            append_target(
                suggestion.get("target"),
                str(suggestion.get("source") or "context_fallback_cascade"),
            )
            if len(targets) >= limit:
                break
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for target in targets:
        key = str(target.get("target") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(target)
        if len(deduped) >= limit:
            break
    return deduped


def _context_action_key(text: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))


_CONTEXT_COMPLETION_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "before",
    "but",
    "by",
    "context",
    "current",
    "do",
    "does",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "next",
    "of",
    "on",
    "or",
    "so",
    "that",
    "the",
    "then",
    "this",
    "to",
    "use",
    "using",
    "with",
    "work",
}


def _context_completion_tokens(text: Any) -> set[str]:
    return {
        token
        for token in _context_action_key(text).split()
        if len(token) >= 3 and token not in _CONTEXT_COMPLETION_STOPWORDS
    }


_RECURRING_ACTION_RE = re.compile(
    r"\b(monitor|watch|poll|wait|track|observe|keep an eye|check back|follow up)\b"
    r"|모니터|감시|주시|추적|대기|지켜보",
    re.IGNORECASE,
)

# 반복성 액션의 암시적 완료를 허용하는 상태 변화/종결 신호. "확인했다"는 신호가 아니다 —
# 외부 상태가 실제로 움직였다는 증거만 통과한다 (#14).
_STATE_CHANGE_RE = re.compile(
    r"\b(merged|closed|approved|declined|rejected|resolved|landed|released|published"
    r"|replied|responded|commented|answered"
    r"|new (comment|review|reply|feedback|commit|check|response)s?"
    r"|changes requested|review posted|feedback received"
    r"|completed|finished|done|terminal)\b"
    r"|머지됨|종료됨|완료됨|응답이? 왔|새 (댓글|리뷰|피드백)|변경됨",
    re.IGNORECASE,
)


def _context_recurring_action(action_text: str) -> bool:
    return bool(_RECURRING_ACTION_RE.search(action_text or ""))


def _context_state_change_signal(observed_text: str) -> bool:
    return bool(_STATE_CHANGE_RE.search(observed_text or ""))


def _context_completion_match(
    *,
    action_text: str,
    row: Any,
    observed: dict[str, Any],
    trace_payload: dict[str, Any],
) -> dict[str, Any]:
    action_key = _context_action_key(action_text)
    if not action_key:
        return {
            "schema_version": "mem1-context-next-action-completion-match-v0",
            "matched": False,
            "reason": "next action text is empty",
        }

    explicit_key = str(observed.get("completed_next_action_key") or "").strip()
    explicit_text = str(observed.get("completed_next_action") or "").strip()
    if explicit_key and explicit_key == action_key:
        return {
            "schema_version": "mem1-context-next-action-completion-match-v0",
            "matched": True,
            "reason": "caller explicitly marked the completed next action key",
            "mode": "explicit_key",
        }
    if explicit_text and _context_action_key(explicit_text) == action_key:
        return {
            "schema_version": "mem1-context-next-action-completion-match-v0",
            "matched": True,
            "reason": "caller explicitly marked the completed next action text",
            "mode": "explicit_text",
        }

    first_tool_call = observed.get("first_tool_call") if isinstance(observed.get("first_tool_call"), dict) else {}
    observed_parts = [
        observed.get("first_action"),
        row["first_action"] if "first_action" in row.keys() else "",
        row["notes"] if "notes" in row.keys() else "",
        _context_tool_call_text(first_tool_call) if first_tool_call else "",
    ]
    observed_text = " ".join(str(part or "") for part in observed_parts).strip()
    observed_key = _context_action_key(observed_text)
    if not observed_key:
        return {
            "schema_version": "mem1-context-next-action-completion-match-v0",
            "matched": False,
            "reason": "outcome has no first-action or first-tool text to compare",
        }

    if _context_recurring_action(action_text) and not _context_state_change_signal(observed_text):
        # 감시의 성공은 감시의 종료가 아니다: 반복성 액션은 외부 상태가 움직였다는
        # 증거(또는 caller의 explicit 마킹) 없이는 열린 채로 남는다 (#14).
        return {
            "schema_version": "mem1-context-next-action-completion-match-v0",
            "matched": False,
            "reason": "recurring action stays open — observation reports no state change",
            "mode": "recurring_no_state_change",
        }

    if action_key == observed_key or action_key in observed_key:
        return {
            "schema_version": "mem1-context-next-action-completion-match-v0",
            "matched": True,
            "reason": "observed first action contains the next action text",
            "mode": "text_containment",
        }

    action_tokens = _context_completion_tokens(action_text)
    observed_tokens = _context_completion_tokens(observed_text)
    overlap = sorted(action_tokens & observed_tokens)
    overlap_count = len(overlap)
    ratio = round(overlap_count / max(len(action_tokens), 1), 4)
    lexical_match = (
        bool(action_tokens)
        and (
            (len(action_tokens) <= 4 and overlap_count >= max(2, len(action_tokens) - 1))
            or (len(action_tokens) > 4 and overlap_count >= 3 and ratio >= 0.35)
        )
    )
    if lexical_match:
        return {
            "schema_version": "mem1-context-next-action-completion-match-v0",
            "matched": True,
            "reason": "observed first action overlaps the next action with enough specific tokens",
            "mode": "lexical_overlap",
            "overlap_tokens": overlap[:8],
            "overlap_ratio": ratio,
        }

    if first_tool_call:
        for alignment in _context_tool_hint_alignments(first_tool_call=first_tool_call, trace_payload=trace_payload):
            hint = alignment.get("hint") if isinstance(alignment.get("hint"), dict) else {}
            hint_text = " ".join(
                str(part or "")
                for part in [
                    hint.get("purpose"),
                    hint.get("target"),
                    _context_hint_command(hint),
                ]
            )
            hint_tokens = _context_completion_tokens(hint_text)
            hint_overlap = sorted(action_tokens & hint_tokens)
            if alignment.get("aligned") and len(hint_overlap) >= 2:
                return {
                    "schema_version": "mem1-context-next-action-completion-match-v0",
                    "matched": True,
                    "reason": "first tool matched an action hint whose purpose overlaps the next action",
                    "mode": "tool_hint_alignment",
                    "overlap_tokens": hint_overlap[:8],
                }

    return {
        "schema_version": "mem1-context-next-action-completion-match-v0",
        "matched": False,
        "reason": "productive outcome did not specifically match the next action",
        "overlap_tokens": overlap[:8],
        "overlap_ratio": ratio,
    }


def _context_safe_action_command(command: Any) -> str:
    text = re.sub(r"\s+", " ", str(command or "")).strip()
    if not text:
        return ""
    lowered = text.lower()
    if re.search(r"\b(rm|mv|cp|scp|kill|pkill|nohup|setsid|sudo|chmod|chown)\b", lowered):
        return ""
    if re.search(r"(?i)(api[_-]?key|authorization|bearer|password|secret|token)\s*[:=]\s*(?!<redacted>)", text):
        return ""
    safe_prefixes = (
        "rg ",
        "sed ",
        "ls ",
        "find ",
        "cat ",
        "curl -s",
        "python -m py_compile ",
        "python -m pytest ",
        ".venv",
        "/home/",
        "ssh ",
    )
    if lowered.startswith(safe_prefixes):
        return text
    if " -m pytest " in lowered or " -m py_compile " in lowered:
        return text
    return ""


def _context_sensitive_target_reason(target: Any) -> str:
    text = str(target or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    normalized = os.path.normpath(lowered)
    parts = [part for part in normalized.split(os.sep) if part]
    basename = os.path.basename(normalized)
    if ".secrets" in parts or "secrets" in parts:
        return "secret_directory"
    if basename in {".env", ".env.local", ".env.production", ".env.development"}:
        return "env_file"
    if basename.endswith(".env") or ".env." in basename:
        return "env_file"
    if basename in {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "known_hosts"}:
        return "ssh_secret_file"
    if os.path.splitext(basename)[1] in {".pem", ".key", ".p12", ".pfx", ".crt", ".cer"}:
        return "credential_file"
    if re.search(r"(?i)(secret|credential|credentials|token|api[_-]?key|private[_-]?key)", basename):
        return "secret_named_file"
    return ""


def _context_action_hint_workdir_info(payload: dict[str, Any]) -> tuple[str, str]:
    for key in ("client_workdir", "workdir", "cwd", "workspace"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value), f"payload.{key}"
    if os.getenv("MEM1_HINT_EXPOSE_SERVER_WORKDIR", "").lower() in {"1", "true", "yes"}:
        try:
            return os.getcwd(), "server_cwd"
        except Exception:
            return "", "unknown"
    # A remote client cannot use this server's filesystem path, and exposing
    # it leaks server layout; "." keeps the suggested command runnable in
    # the client's own workspace.
    return ".", "server_cwd"


def _context_action_hint_workdir(payload: dict[str, Any]) -> str:
    workdir, _source = _context_action_hint_workdir_info(payload)
    return workdir


def _context_workspace_alias_target(target: Any, *, workdir: str) -> str:
    text = str(target or "").strip()
    workdir_text = str(workdir or "").strip()
    if not text or not workdir_text or not os.path.isabs(os.path.expanduser(text)):
        return text

    expanded = os.path.normpath(os.path.abspath(os.path.expanduser(text)))
    workdir_expanded = os.path.normpath(os.path.abspath(os.path.expanduser(workdir_text)))
    parts = [part for part in expanded.split(os.sep) if part]
    repo_roots = {"mem1"}
    repo_top_levels = {"app", "scripts", "tests", "docs", "static", "integrations", "output"}
    for index, part in enumerate(parts):
        if part.lower() not in repo_roots:
            continue
        if index == len(parts) - 1:
            return workdir_expanded
        if parts[index + 1] not in repo_top_levels:
            continue
        relative = os.path.join(*parts[index + 1 :])
        return os.path.join(workdir_expanded, relative)
    return text


def _context_target_inspect_command(target: Any) -> str:
    text = str(target or "").strip()
    if not text:
        return ""
    if re.search(r"(?i)(^https?://|^ssh:|[;&|`$<>])", text):
        return ""
    if _context_sensitive_target_reason(text):
        return ""
    if os.path.isdir(text):
        return f"find {text} -maxdepth 2 -type f"
    suffix = os.path.splitext(text)[1].lower()
    readable_suffixes = {
        ".py",
        ".md",
        ".txt",
        ".json",
        ".jsonl",
        ".html",
        ".css",
        ".js",
        ".ts",
        ".tsx",
        ".yml",
        ".yaml",
        ".toml",
        ".sh",
    }
    if not suffix:
        return ""
    if suffix and suffix not in readable_suffixes:
        return ""
    return f"sed -n '1,260p' {text}"


def _context_rg_hint_command(*texts: Any) -> str:
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "context",
        "current",
        "workspace",
        "next",
        "action",
        "continue",
        "inspect",
    }
    terms: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for token in re.findall(r"[A-Za-z0-9_가-힣-]{3,}", str(text or "").lower()):
            if token in stopwords or token in seen:
                continue
            seen.add(token)
            terms.append(token)
            if len(terms) >= 4:
                break
        if len(terms) >= 4:
            break
    if not terms:
        return ""
    pattern = "|".join(re.escape(term) for term in terms)
    return f'rg -n "{pattern}" .'


def _context_action_hint_target_key(target: Any) -> str:
    text = str(target or "").strip()
    if not text:
        return ""
    normalized = os.path.normpath(text)
    parts = [part for part in normalized.split(os.sep) if part]
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return normalized


def _context_source_route_workdir(payload: dict[str, Any]) -> str:
    workdir = str(payload.get("workdir") or payload.get("cwd") or payload.get("workspace") or "").strip()
    if not workdir:
        workdir = os.getcwd()
    return os.path.abspath(os.path.expanduser(workdir))


def _context_source_route_target_class(target: Any, *, payload: dict[str, Any], source: Any = "") -> str:
    target_text = str(target or "").strip()
    source_text = str(source or "").strip()
    lowered = " ".join([target_text.lower(), source_text.lower()])
    workdir = _context_source_route_workdir(payload)
    expanded = os.path.abspath(os.path.expanduser(target_text)) if target_text.startswith(("~", "/")) else target_text
    repo_markers = (
        "/documents/mem1/app/",
        "/documents/mem1/scripts/",
        "/documents/mem1/tests/",
        "/documents/mem1/docs/",
        "/documents/mem1/static/",
        "/documents/mem1/integrations/",
        "/documents/mem1/output/",
        "/mem1/app/",
        "/mem1/scripts/",
        "/mem1/tests/",
        "/mem1/docs/",
        "/mem1/static/",
        "/mem1/integrations/",
        "/mem1/output/",
    )
    if ".codex/memories" in lowered or "memory_summary.md" in lowered or re.search(r"(^|/)memory\.md\b", lowered):
        return "codex_memory"
    if "skill.md" in lowered or ".codex/skills" in lowered or "/skills/" in lowered:
        return "skill_doc"
    if re.search(r"(github\.com|git clone|git ls-remote|pull request|issue_read|search_repositories)", lowered):
        return "web_or_github"
    if source_text == "query.file_reference" and (
        "file://" in lowered
        or "/downloads/" in lowered
        or "/attachments/" in lowered
        or "in app browser" in lowered
        or "browser" in lowered
    ):
        return "browser_or_file_view"
    if any(marker in expanded.lower() for marker in repo_markers):
        return "repo_inspection"
    if re.search(r"(ssh\s|4090|155\.230\.107\.59|/home/dilab|remote_start_mem1_api|/ready|/health)", lowered):
        return "remote_4090_runtime"
    if target_text and os.path.isabs(expanded) and not expanded.startswith(workdir):
        return "browser_or_file_view"
    if source_text.startswith("memory:") or source_text == "current_workspace.evidence_files":
        return "repo_inspection"
    if target_text.startswith(("app/", "scripts/", "tests/", "docs/", "static/", "integrations/", "output/")):
        return "repo_inspection"
    return "unknown"


def _context_source_route_runtime_location(payload: dict[str, Any]) -> dict[str, Any]:
    query_text = str(payload.get("query") or "")
    workdir = _context_source_route_workdir(payload)
    lowered = " ".join([query_text.lower(), workdir.lower()])
    if re.search(r"(4090|155\.230\.107\.59|/home/dilab|remote_start_mem1_api)", lowered):
        return {
            "kind": "remote_4090_runtime",
            "reason": "query or workdir references the 4090 runtime",
            "workdir": workdir,
        }
    if workdir:
        return {
            "kind": "local_workspace",
            "reason": "using the provided local workspace directory",
            "workdir": workdir,
        }
    return {"kind": "unknown", "reason": "no runtime workdir provided", "workdir": ""}


def _context_source_route_for_text(
    *,
    payload: dict[str, Any],
    next_action_text: str,
    relevant_targets: list[dict[str, Any]],
    context_status: dict[str, Any],
) -> tuple[str, str, float]:
    query_text = str(payload.get("query") or "")
    combined = " ".join([query_text, next_action_text]).lower()
    for target in _context_query_referenced_targets({"trace_query": query_text}):
        source_class = _context_source_route_target_class(
            target,
            payload=payload,
            source="query.file_reference",
        )
        if source_class != "unknown":
            return source_class, f"query explicitly references {target}", 0.86
    if re.search(
        r"(\bgithub(?:\.com)?\b|\bgit clone\b|\bgit ls-remote\b|\bpull request\b|\bissue\b|\bpr\s*#?\d+\b)",
        combined,
    ):
        return "web_or_github", "query or next action references web or GitHub", 0.68
    for target in relevant_targets:
        if not isinstance(target, dict):
            continue
        source_class = _context_source_route_target_class(
            target.get("target"),
            payload=payload,
            source=target.get("source"),
        )
        if source_class != "unknown":
            return source_class, f"relevant target {target.get('target')} maps to {source_class}", 0.72
    if ".codex/memories" in combined or "memory_summary.md" in combined or re.search(r"(^|/)memory\.md\b", combined):
        return "codex_memory", "query or next action references Codex memory files", 0.82
    if re.search(r"\b(goal|set_goal|get_goal|milestone|objective)\b", combined):
        return "goal_state", "query or next action references goal state", 0.72
    if re.search(r"(ssh\s|4090|/home/dilab|155\.230\.107\.59|/ready|/health)", combined):
        return "remote_4090_runtime", "query or next action references 4090/runtime verification", 0.78
    if re.search(r"(skill\.md|\.codex/skills|/skills/)", combined):
        return "skill_doc", "query or next action references skill instructions", 0.7
    if re.search(r"(file://|browser|screenshot|/downloads/|/attachments/)", combined):
        return "browser_or_file_view", "query or next action references browser or file-view state", 0.7
    if context_status.get("status") == "insufficient":
        return "enacta_memory", "context status is insufficient, so memory/context inspection should come first", 0.58
    return "repo_inspection", "default route for code/workspace continuation", 0.58


def _context_source_route_required_tools(source_class: str) -> list[str]:
    return {
        "enacta_memory": ["mcp__enacta.prepare_context_autopilot", "mcp__enacta.search_memory"],
        "codex_memory": ["functions.exec_command"],
        "repo_inspection": ["functions.exec_command", "functions.apply_patch"],
        "remote_4090_runtime": ["functions.exec_command"],
        "browser_or_file_view": ["functions.exec_command", "browser"],
        "goal_state": ["functions.get_goal"],
        "skill_doc": ["functions.exec_command"],
        "web_or_github": ["web", "mcp__github"],
        "user_input": ["user"],
    }.get(source_class, ["functions.exec_command"])


def _context_source_route_availability(source_class: str, *, payload: dict[str, Any], relevant_targets: list[dict[str, Any]]) -> dict[str, Any]:
    workdir = _context_source_route_workdir(payload)
    if source_class == "repo_inspection":
        workdir_supplied = any(payload.get(key) not in (None, "") for key in ("client_workdir", "workdir", "cwd", "workspace"))
        if os.path.isdir(workdir):
            return {
                "status": "available",
                "reason": "workspace directory is readable",
                "evidence": {"workdir": workdir},
            }
        if workdir_supplied:
            return {
                "status": "not_checked",
                "reason": "client-provided workspace is not readable from this context server",
                "evidence": {"workdir": workdir},
            }
        return {
            "status": "unavailable",
            "reason": "workspace directory is not readable",
            "evidence": {"workdir": workdir},
        }
    if source_class == "enacta_memory":
        return {"status": "available", "reason": "current process can assemble Forget context", "evidence": {}}
    if source_class == "codex_memory":
        memory_root = os.path.expanduser("~/.codex/memories")
        registry = os.path.join(memory_root, "MEMORY.md")
        summary = os.path.join(memory_root, "memory_summary.md")
        available = os.path.isfile(registry) and os.path.isfile(summary)
        return {
            "status": "available" if available else "unavailable",
            "reason": "Codex memory registry is readable" if available else "Codex memory registry is not readable from this runtime",
            "evidence": {"registry": registry, "summary": summary},
        }
    if source_class == "browser_or_file_view":
        existing = []
        for target in _context_query_referenced_targets({"trace_query": payload.get("query")}):
            expanded = os.path.abspath(os.path.expanduser(str(target)))
            if os.path.exists(expanded):
                existing.append(expanded)
        return {
            "status": "available" if existing else "not_checked",
            "reason": "explicit file target is readable" if existing else "browser/file source depends on app-provided state not checked here",
            "evidence": {"files": existing},
        }
    if source_class == "skill_doc":
        skill_targets = [
            str(target.get("target") or "")
            for target in relevant_targets
            if isinstance(target, dict) and str(target.get("target") or "").endswith("SKILL.md")
        ]
        readable = [target for target in skill_targets if os.path.isfile(os.path.expanduser(target))]
        return {
            "status": "available" if readable else "not_checked",
            "reason": "skill instruction file is readable" if readable else "no readable skill instruction target was provided",
            "evidence": {"skill_paths": readable},
        }
    if source_class == "user_input":
        return {"status": "available", "reason": "user input can be requested", "evidence": {}}
    return {
        "status": "not_checked",
        "reason": f"{source_class} requires an external tool or runtime probe",
        "evidence": {},
    }


def _context_source_route(
    *,
    payload: dict[str, Any],
    next_action_text: str,
    relevant_targets: list[dict[str, Any]],
    context_status: dict[str, Any],
) -> dict[str, Any]:
    source_class, reason, confidence = _context_source_route_for_text(
        payload=payload,
        next_action_text=next_action_text,
        relevant_targets=relevant_targets,
        context_status=context_status,
    )
    fallback_sources = [
        item
        for item in ["repo_inspection", "enacta_memory", "codex_memory", "user_input"]
        if item != source_class
    ][:3]
    return {
        "schema_version": CONTEXT_SOURCE_ROUTE_SCHEMA_VERSION,
        "source_class": source_class,
        "reason": reason,
        "confidence": round(float(confidence), 4),
        "required_tools": _context_source_route_required_tools(source_class),
        "fallback_sources": fallback_sources,
        "availability": _context_source_route_availability(
            source_class,
            payload=payload,
            relevant_targets=relevant_targets,
        ),
        "runtime_location": _context_source_route_runtime_location(payload),
    }


def _context_action_plan(
    *,
    payload: dict[str, Any],
    next_action_text: str,
    source_route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    query_text = str(payload.get("query") or "").lower()
    combined = " ".join([query_text, str(next_action_text or "").lower()])

    def classify(text: str) -> tuple[str, str, list[str], str] | None:
        if not text.strip():
            return None
        if re.search(r"\b(rollout|observer|capture|logs?|session|jsonl)\b", text):
            return (
                "rollout_observer",
                "inspect_observer",
                ["rollout_observer", "engine_implementation", "engine_test", "workspace_evidence"],
                "request focuses on rollout/session observation tooling",
            )
        hint_implementation_forward = re.search(
            r"\b(fix|improve|patch|change|implement|refactor|tune)\b.{0,100}"
            r"\b(action[_ -]?hints?|first[_ -]?tool[_ -]?hint|primary|fallback|hint[_ -]?group|selector|planner|router|packing|engine)\b",
            text,
        )
        hint_implementation_backward = re.search(
            r"\b(action[_ -]?hints?|first[_ -]?tool[_ -]?hint|primary|fallback|hint[_ -]?group|selector|planner|router|packing|engine)\b.{0,100}"
            r"\b(fix|improve|patch|change|implement|refactor|tune)\b",
            text,
        )
        verification_vocabulary = re.search(
            r"\b(test|tests|pytest|regression|coverage|verify|validation|gate|assert)\b|검증|테스트", text
        )
        if hint_implementation_forward or (hint_implementation_backward and not verification_vocabulary):
            # A backward-only match (noun before verb, e.g. "before any engine
            # patch") alongside explicit verification vocabulary means the
            # request is about verifying before a change, not making one.
            return (
                "implementation",
                "inspect_implementation",
                ["engine_implementation", "engine_test", "benchmark_runner", "workspace_evidence"],
                "request asks for an implementation or engine behavior change",
            )
        if re.search(r"\b(test|tests|pytest|regression|coverage|verify|validation|gate|assert)\b|검증|테스트", text):
            return (
                "verification",
                "inspect_tests",
                ["engine_test", "benchmark_runner", "workspace_evidence", "engine_implementation"],
                "request focuses on verification or regression evidence",
            )
        if re.search(r"\b(ssh|4090|runtime|deploy|restart|health|ready|server|production)\b|서버|배포|운영", text):
            return (
                "runtime_operations",
                "probe_runtime",
                ["workspace_evidence", "engine_implementation", "engine_test", "rollout_observer"],
                "request focuses on runtime or deployment operations",
            )
        if re.search(r"\b(plan|strategy|direction|design|architecture|should|whether|goal)\b|계획|방향|설계|맞는|목표", text):
            return (
                "planning_review",
                "inspect_context",
                ["workspace_evidence", "engine_implementation", "engine_test", "benchmark_runner"],
                "request asks for a planning or direction judgment",
            )
        if re.search(
            r"\b(report|evidence|metrics|readiness|drilldown|analysis|analyze|evaluate|benchmark|replay)\b|증거|보고|분석|평가",
            text,
        ):
            return (
                "evidence_analysis",
                "inspect_evidence",
                ["workspace_evidence", "benchmark_runner", "engine_implementation", "engine_test"],
                "request focuses on evidence, benchmark, or analysis artifacts",
            )
        if re.search(
            r"\b(implement|build|fix|patch|change|improve|refactor|separate|split|planner|router|selector|scoring|hint|engine)\b|구현|고치|수정|개선|분리",
            text,
        ):
            return (
                "implementation",
                "inspect_implementation",
                ["engine_implementation", "engine_test", "benchmark_runner", "workspace_evidence"],
                "request asks for an implementation or engine behavior change",
            )
        return None

    intent, first_action_kind, preferred_roles, reason = classify(query_text) or classify(combined) or (
        "general_continuation",
        "inspect_best_target",
        ["engine_implementation", "workspace_evidence", "engine_test", "benchmark_runner"],
        "default continuation plan",
    )
    return {
        "schema_version": CONTEXT_ACTION_PLAN_SCHEMA_VERSION,
        "intent": intent,
        "first_action_kind": first_action_kind,
        "preferred_target_roles": preferred_roles,
        "reason": reason,
        "source_class": (source_route or {}).get("source_class") if isinstance(source_route, dict) else "",
        "runtime_location": (source_route or {}).get("runtime_location") if isinstance(source_route, dict) else {},
    }


def _context_action_plan_role_rank(target_role: str, action_plan: dict[str, Any] | None) -> int:
    if str(target_role or "") == "query_reference":
        return -1
    if not isinstance(action_plan, dict):
        return 99
    preferred = [str(item) for item in action_plan.get("preferred_target_roles") or []]
    try:
        return preferred.index(str(target_role or ""))
    except ValueError:
        return 99


def _context_action_hint_keyword_targets(*texts: Any) -> list[dict[str, Any]]:
    combined = " ".join(str(text or "") for text in texts).lower()
    targets: list[dict[str, Any]] = []
    if re.search(
        r"\b(action[_ -]?hints?|first[_ -]?tool[_ -]?hint|primary[_ -]?action[_ -]?hints?|fallback[_ -]?action[_ -]?hints?|hint[_ -]?group|target[_ -]?utility|packing)\b",
        combined,
    ):
        targets.extend(
            [
                {
                    "target": "app/store.py",
                    "source": "next_action_keyword.context_action_hints",
                },
                {
                    "target": "tests/test_api.py",
                    "source": "next_action_keyword.context_action_hints",
                },
            ]
        )
    avoid_hook_targets = bool(
        re.search(r"\b(?:avoid|skip|exclude|not|without|unless)\b.{0,60}\b(?:hook|hooks|install_codex_hooks)\b", combined)
        or re.search(r"\b(?:hook|hooks|install_codex_hooks)\b.{0,60}\b(?:avoid|skip|exclude|not|without|unless)\b", combined)
    )
    if not avoid_hook_targets and re.search(
        r"\b(userpromptsubmit|pre-turn|preturn|hook|hooks|install_codex_hooks)\b",
        combined,
    ):
        targets.extend(
            [
                {
                    "target": "integrations/mem0-plugin/scripts/mem1_hook.py",
                    "source": "next_action_keyword.codex_hook_autopilot",
                },
                {
                    "target": "integrations/mem0-plugin/scripts/install_codex_hooks.py",
                    "source": "next_action_keyword.codex_hook_autopilot",
                },
                {
                    "target": "scripts/start_enacta_codex_mcp.sh",
                    "source": "next_action_keyword.codex_hook_autopilot",
                },
                {
                    "target": "scripts/prepare_context_autopilot_preturn.py",
                    "source": "next_action_keyword.codex_hook_autopilot",
                },
            ]
        )
    if re.search(r"\b(rollout|observer|cli|capture|logs?|codex|session|jsonl|runtime)\b", combined):
        targets.extend(
            [
                {
                    "target": "scripts/record_context_observation_from_rollout.py",
                    "source": "next_action_keyword.rollout_observer",
                },
                {
                    "target": "scripts/record_context_outcome_cli.py",
                    "source": "next_action_keyword.rollout_observer",
                },
            ]
        )
    if re.search(r"\b(replay|calibration|benchmark|prediction|judge|workspace-only)\b", combined):
        targets.extend(
            [
                {
                    "target": "scripts/build_context_utility_replay_packets.py",
                    "source": "next_action_keyword.context_utility_replay",
                },
                {
                    "target": "scripts/evaluate_context_utility_v1.py",
                    "source": "next_action_keyword.context_utility_replay",
                },
            ]
        )
    return targets


def _context_action_hint_explicit_hook_task(*texts: Any) -> bool:
    combined = " ".join(str(text or "") for text in texts).lower()
    if (
        re.search(r"\b(?:avoid|skip|exclude|not|without|unless|only\s+when)\b.{0,80}\b(?:hook|hooks|install_codex_hooks)\b", combined)
        or re.search(r"\b(?:hook|hooks|install_codex_hooks)\b.{0,80}\b(?:avoid|skip|exclude|not|without|unless|only\s+when)\b", combined)
    ):
        return False
    return bool(
        re.search(r"\b(userpromptsubmit|pre-turn|preturn|hook|hooks|install_codex_hooks)\b", combined)
        or re.search(r"\b(local\s+mcp\s+proxy|codex\s+proxy|mcp\s+proxy)\b", combined)
    )


def _context_action_hint_target_role(target: Any, source: Any) -> str:
    target_text = str(target or "").strip()
    source_text = str(source or "").strip()
    if source_text == "query.file_reference":
        return "query_reference"
    if target_text == "app/store.py":
        return "engine_implementation"
    if target_text == "tests/test_api.py":
        return "engine_test"
    if target_text.startswith("integrations/mem0-plugin/") or target_text in {
        "scripts/start_enacta_codex_mcp.sh",
        "scripts/prepare_context_autopilot_preturn.py",
    }:
        return "hook_integration"
    if target_text.startswith("scripts/record_context_"):
        return "rollout_observer"
    if target_text.startswith("scripts/build_context_utility_") or target_text.startswith(
        "scripts/evaluate_context_utility_"
    ):
        return "benchmark_runner"
    if target_text.startswith("output/"):
        return "evidence_output"
    if source_text == "current_workspace.evidence_files" or source_text.startswith("memory:"):
        return "workspace_evidence"
    if source_text.startswith("next_action_keyword."):
        return "keyword_candidate"
    return "general"


def _context_action_hint_target_utility(
    target: Any,
    source: Any,
    *,
    query_text: Any,
    next_action_text: Any,
) -> float:
    role = _context_action_hint_target_role(target, source)
    source_text = str(source or "")
    combined = " ".join([str(query_text or ""), str(next_action_text or "")]).lower()
    explicit_hook = _context_action_hint_explicit_hook_task(query_text, next_action_text)
    score_by_role = {
        "query_reference": 1.0,
        "engine_implementation": 0.78,
        "engine_test": 0.66,
        "workspace_evidence": 0.7,
        "benchmark_runner": 0.66,
        "rollout_observer": 0.64,
        "hook_integration": 0.58 if explicit_hook else 0.34,
        "evidence_output": 0.5,
        "keyword_candidate": 0.48,
        "general": 0.42,
    }
    score = score_by_role.get(role, 0.42)
    if source_text == "next_action_keyword.context_action_hints":
        score = max(score, 0.82 if role == "engine_test" else 0.86)
    if source_text == "next_action_keyword.codex_hook_autopilot":
        score = max(score, 0.86 if explicit_hook else 0.38)
    if source_text == "next_action_keyword.rollout_observer" and re.search(
        r"\b(rollout|observer|capture|logs?|session|jsonl)\b",
        combined,
    ):
        score = max(score, 0.84)
    if source_text == "next_action_keyword.context_utility_replay" and re.search(
        r"\b(replay|calibration|benchmark|prediction|judge|workspace-only)\b",
        combined,
    ):
        score = max(score, 0.82)
    if role == "engine_implementation" and re.search(
        r"\b(engine|selector|packing|action[_ -]?hints?|first[_ -]?tool[_ -]?hint|primary|fallback|hint[_ -]?group|target[_ -]?utility|store|test)\b",
        combined,
    ):
        score = max(score, 0.9)
    if role == "engine_test" and re.search(
        r"\b(test|tests|pytest|regression|coverage|verify|validation|gate|assert)\b",
        combined,
    ):
        score = max(score, 0.86)
    if role == "hook_integration" and not explicit_hook:
        score = min(score, 0.42)
    return round(min(max(score, 0.0), 1.0), 4)


def _context_action_hint_recommended_use(target_role: str, target_utility: float, explicit_hook: bool) -> str:
    if target_role == "engine_implementation":
        return "Use first for engine behavior, packing, selector, API, and regression-test changes."
    if target_role == "engine_test":
        return "Use for regression tests and validation; prefer implementation files first unless the task is verification-focused."
    if target_role == "hook_integration":
        if explicit_hook:
            return "Use when the task is explicitly about Codex hooks, MCP proxy wiring, or hook installation."
        return "Use only after engine evidence; this is a nearby integration surface, not the default engine target."
    if target_role == "rollout_observer":
        return "Use for rollout/session capture, observation CLI, and runtime log ingestion work."
    if target_role == "benchmark_runner":
        return "Use for replay packets, benchmark construction, prediction, and evaluation scripts."
    if target_role == "evidence_output":
        return "Use for reading generated evidence; prefer implementation files when code changes are requested."
    if target_role == "query_reference":
        return "Use first because the current user request explicitly names this target."
    if target_utility >= 0.7:
        return "Use as directly relevant workspace evidence."
    return "Use as fallback context after higher-utility targets."


def _context_annotate_action_hint_target(
    target: dict[str, Any],
    *,
    query_text: Any,
    next_action_text: Any,
    original_index: int,
    action_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = dict(target)
    source = str(item.get("source") or "")
    target_text = str(item.get("target") or "")
    role = _context_action_hint_target_role(target_text, source)
    utility = _context_action_hint_target_utility(
        target_text,
        source,
        query_text=query_text,
        next_action_text=next_action_text,
    )
    explicit_hook = _context_action_hint_explicit_hook_task(query_text, next_action_text)
    plan_rank = _context_action_plan_role_rank(role, action_plan)
    item.setdefault("target_role", role)
    item.setdefault("target_utility", utility)
    item.setdefault("action_plan_match", plan_rank < 99)
    item.setdefault("action_plan_rank", plan_rank)
    item.setdefault("recommended_use", _context_action_hint_recommended_use(role, utility, explicit_hook))
    if role == "hook_integration" and not explicit_hook:
        item.setdefault("selection_guard", "Do not select before engine implementation/test targets unless the task asks for hook or proxy work.")
    elif role == "engine_test":
        item.setdefault("selection_guard", "Select before implementation files only when the task is explicitly about tests, verification, or regression coverage.")
    elif role == "evidence_output":
        item.setdefault("selection_guard", "Evidence output is for inspection; prefer code/test targets for implementation work.")
    else:
        item.setdefault("selection_guard", "Select when this target directly supports the current user request.")
    item["_original_index"] = original_index
    return item


def _context_sort_action_hint_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        targets,
        key=lambda item: (
            int(item.get("action_plan_rank") if item.get("action_plan_rank") is not None else 99),
            -float(item.get("target_utility") or 0.0),
            int(item.get("_original_index") or 0),
        ),
    )


def _context_prioritized_action_hint_targets(
    *,
    project_id: str,
    payload: dict[str, Any],
    relevant_targets: list[dict[str, Any]],
    next_action_text: str,
    source_route: dict[str, Any] | None = None,
    action_plan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    query_targets = [
        {"target": target, "source": "query.file_reference"}
        for target in _context_query_referenced_targets({"trace_query": payload.get("query")})
    ]
    raw_targets = [
        *query_targets,
        *_context_action_hint_keyword_targets(next_action_text, payload.get("query")),
        *[target for target in relevant_targets if isinstance(target, dict)],
    ]
    prioritized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, target in enumerate(raw_targets):
        target_text = str(target.get("target") or "").strip()
        key = _context_action_hint_target_key(target_text)
        if not key or key in seen:
            continue
        seen.add(key)
        prioritized.append(
            _context_annotate_action_hint_target(
                target,
                query_text=payload.get("query"),
                next_action_text=next_action_text,
                original_index=index,
                action_plan=action_plan,
            )
        )
    prioritized = _context_sort_action_hint_targets(prioritized)
    llm_result = generate_action_hint_targets(
        query=str(payload.get("query") or ""),
        next_action_text=next_action_text,
        candidate_targets=prioritized,
        source_route=source_route if isinstance(source_route, dict) else None,
        action_plan=action_plan if isinstance(action_plan, dict) else None,
        project_id=project_id,
    )
    if not llm_result.get("used") or not isinstance(llm_result.get("targets"), list):
        diagnostic = {
            key: llm_result.get(key)
            for key in (
                "used",
                "reason",
                "provider",
                "model",
                "primary_model",
                "status_code",
                "error_type",
                "attempted_models",
            )
            if key in llm_result
        }
        for target in prioritized:
            if isinstance(target, dict):
                target.setdefault("llm_action_hint_status", diagnostic)
        return prioritized
    by_target = {str(item.get("target") or ""): item for item in prioritized if isinstance(item, dict)}
    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    for item in llm_result.get("targets") or []:
        if not isinstance(item, dict):
            continue
        target_text = str(item.get("target") or "").strip()
        original = by_target.get(target_text)
        key = _context_action_hint_target_key(target_text)
        if not original or not key or key in selected_keys:
            continue
        merged = dict(original)
        merged["source"] = "llm_action_hint"
        merged["original_source"] = item.get("original_source") or original.get("source")
        merged["llm_provider"] = llm_result.get("provider")
        merged["llm_model"] = llm_result.get("model")
        merged["purpose"] = item.get("purpose") or original.get("purpose")
        merged["confidence"] = item.get("confidence", 0.78)
        merged["llm_action_hint_status"] = {
            "used": True,
            "provider": llm_result.get("provider"),
            "model": llm_result.get("model"),
            "primary_model": llm_result.get("primary_model"),
            "attempted_models": llm_result.get("attempted_models"),
        }
        selected.append(merged)
        selected_keys.add(key)
    if not selected:
        return prioritized
    remaining = [
        item
        for item in prioritized
        if _context_action_hint_target_key(item.get("target") if isinstance(item, dict) else "") not in selected_keys
    ]
    if selected and remaining:
        best_selected_utility = float(selected[0].get("target_utility") or 0.0)
        best_remaining = max(remaining, key=lambda item: float(item.get("target_utility") or 0.0))
        best_remaining_utility = float(best_remaining.get("target_utility") or 0.0)
        if best_selected_utility < 0.6 and best_remaining_utility - best_selected_utility >= 0.15 and best_remaining_utility >= 0.75:
            remaining = [
                item
                for item in remaining
                if _context_action_hint_target_key(item.get("target")) != _context_action_hint_target_key(best_remaining.get("target"))
            ]
            selected = [best_remaining, *selected]
    return [*selected, *remaining]


def _context_hint_confidence(value: Any, default: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return min(max(confidence, 0.0), 1.0)


def _context_action_hint_group(source: Any, target_utility: Any = None) -> str:
    source_text = str(source or "")
    utility = _context_hint_confidence(target_utility, 0.0) if target_utility is not None else None
    if source_text == "llm_action_hint" and utility is not None and utility < 0.75:
        return "fallback"
    if source_text != "query.file_reference" and utility is not None and utility < 0.5:
        return "fallback"
    if (
        source_text == "llm_action_hint"
        or source_text == "query.file_reference"
        or source_text == "next_action_keyword.context_action_hints"
        or source_text.startswith("memory:")
    ):
        return "primary"
    # current_workspace.evidence_files stays in the fallback tier: the
    # documented taxonomy treats workspace evidence as recovery hints, not
    # primary-hint success (docs/CONTEXT_UTILITY_EVALUATION_V1.md).
    return "fallback"


def _context_grouped_action_hints(action_hints: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    primary = [hint for hint in action_hints if hint.get("hint_group") == "primary"]
    fallback = [hint for hint in action_hints if hint.get("hint_group") != "primary"]
    if primary:
        return primary, fallback
    if not action_hints:
        return [], []
    promoted = dict(action_hints[0])
    promoted["promoted_from_fallback"] = True
    promoted["hint_group"] = "primary"
    return [promoted], action_hints[1:]


def _context_action_hints(
    *,
    project_id: str,
    payload: dict[str, Any],
    workspace_current: dict[str, Any] | None,
    relevant_targets: list[dict[str, Any]],
    next_action_text: str,
    source_route: dict[str, Any] | None = None,
    action_plan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    workdir, workdir_source = _context_action_hint_workdir_info(payload)
    hints: list[dict[str, Any]] = []
    seen: set[str] = set()
    source_class = (
        str(source_route.get("source_class") or "")
        if isinstance(source_route, dict)
        else ""
    )

    # This schema can only emit shell commands. A local target or saved command
    # would contradict an explicit GitHub route, even when it is real evidence.
    if source_class == "web_or_github":
        return []

    def add_hint(
        command: str,
        *,
        source: str,
        purpose: str,
        target: str = "",
        confidence: float = 0.55,
        target_role: str = "",
        target_utility: float | None = None,
        recommended_use: str = "",
        selection_guard: str = "",
        llm_action_hint_status: dict[str, Any] | None = None,
        original_target: str = "",
        action_plan_match: Any = None,
        action_plan_rank: Any = None,
    ) -> None:
        command = _context_safe_action_command(command)
        if not command or command in seen:
            return
        seen.add(command)
        hint = {
            "schema_version": CONTEXT_ACTION_HINTS_SCHEMA_VERSION,
            "kind": "tool_call",
            "tool_name": "functions.exec_command",
            "arguments_preview": json_dumps(
                {
                    "cmd": command,
                    "workdir": workdir,
                }
            ),
            "workdir_source": workdir_source,
            "client_workdir_required": workdir_source == "server_cwd",
            "target": target,
            "purpose": _autopilot_short_text(purpose, max_chars=180),
            "source": source,
            "confidence": round(float(confidence), 2),
        }
        if original_target and original_target != target:
            hint["original_target"] = original_target
        if target_role:
            hint["target_role"] = target_role
        if target_utility is not None:
            hint["target_utility"] = round(float(target_utility), 4)
        if recommended_use:
            hint["recommended_use"] = _autopilot_short_text(recommended_use, max_chars=180)
        if selection_guard:
            hint["selection_guard"] = _autopilot_short_text(selection_guard, max_chars=180)
        if action_plan_match is not None:
            hint["action_plan_match"] = bool(action_plan_match)
        if action_plan_rank is not None:
            try:
                hint["action_plan_rank"] = int(action_plan_rank)
            except (TypeError, ValueError):
                pass
        hint["hint_group"] = _context_action_hint_group(source, hint.get("target_utility"))
        if llm_action_hint_status:
            hint["llm_action_hint_status"] = llm_action_hint_status
        if isinstance(source_route, dict) and source_route:
            hint["source_route"] = {
                "schema_version": source_route.get("schema_version") or CONTEXT_SOURCE_ROUTE_SCHEMA_VERSION,
                "source_class": source_route.get("source_class") or "unknown",
                "confidence": source_route.get("confidence", 0.0),
                "availability": source_route.get("availability") or {},
                "runtime_location": source_route.get("runtime_location") or {},
            }
        if isinstance(action_plan, dict) and action_plan:
            hint["action_plan"] = {
                "schema_version": action_plan.get("schema_version") or CONTEXT_ACTION_PLAN_SCHEMA_VERSION,
                "intent": action_plan.get("intent") or "",
                "first_action_kind": action_plan.get("first_action_kind") or "",
                "preferred_target_roles": action_plan.get("preferred_target_roles") or [],
            }
        hints.append(hint)

    for target in _context_prioritized_action_hint_targets(
        project_id=project_id,
        payload=payload,
        relevant_targets=relevant_targets,
        next_action_text=next_action_text,
        source_route=source_route,
        action_plan=action_plan,
    ):
        if not isinstance(target, dict):
            continue
        target_text = str(target.get("target") or "").strip()
        command_target = _context_workspace_alias_target(target_text, workdir=workdir)
        command = _context_target_inspect_command(command_target)
        if command:
            add_hint(
                command,
                source=str(target.get("source") or "relevant_targets"),
                target=command_target,
                original_target=target_text,
                purpose=str(target.get("purpose") or f"Inspect the most relevant target before acting on: {next_action_text}"),
                confidence=_context_hint_confidence(target.get("confidence"), 0.7),
                target_role=str(target.get("target_role") or ""),
                target_utility=(
                    _context_hint_confidence(target.get("target_utility"), 0.0)
                    if target.get("target_utility") is not None
                    else None
                ),
                recommended_use=str(target.get("recommended_use") or ""),
                selection_guard=str(target.get("selection_guard") or ""),
                action_plan_match=target.get("action_plan_match"),
                action_plan_rank=target.get("action_plan_rank"),
                llm_action_hint_status=(
                    target.get("llm_action_hint_status")
                    if isinstance(target.get("llm_action_hint_status"), dict)
                    else None
                ),
            )
        if len(hints) >= 3:
            break

    commands = (
        workspace_current.get("commands")
        if isinstance(workspace_current, dict) and isinstance(workspace_current.get("commands"), list)
        else []
    )
    next_action_tokens = set(_context_action_key(next_action_text).split())
    for command in commands:
        safe_command = _context_safe_action_command(command)
        if not safe_command:
            continue
        command_tokens = set(_context_action_key(safe_command).split())
        overlap = len(next_action_tokens & command_tokens)
        verification_command = bool(re.search(r"\b(pytest|py_compile|replay|compare|evaluate|check)\b", safe_command))
        if overlap <= 0 and not verification_command:
            continue
        add_hint(
            safe_command,
            source="current_workspace.commands",
            purpose=f"Reuse verified workspace command related to: {next_action_text}",
            confidence=0.62 if overlap else 0.52,
        )
        if len(hints) >= 3:
            break
    # Do not turn an external route into a plausible-looking local action.
    # Callers can follow source_route.required_tools when this shell-only hint
    # schema cannot represent the required tool.
    workspace_search_routes = {"", "unknown", "repo_inspection", "codex_memory", "skill_doc"}
    if not hints and source_class in workspace_search_routes:
        command = _context_rg_hint_command(next_action_text, payload.get("query"))
        if command:
            add_hint(
                command,
                source="query_keyword_fallback",
                target=".",
                purpose=f"Search the workspace for terms related to: {next_action_text}",
                confidence=0.46,
            )
    return hints[:3]


def _context_completed_next_actions(
    *,
    project_id: str,
    task_id: str | None,
    workspace_epoch_id: str | None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if not task_id or not workspace_epoch_id:
        return []
    rows: list[Any]
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT o.*, t.payload AS trace_payload
              FROM context_outcomes o
              JOIN context_traces t
                ON t.project_id = o.project_id
               AND t.trace_id = o.trace_id
             WHERE o.project_id = ?
               AND o.task_id = ?
               AND o.first_action_productive = 1
               AND o.user_correction_required = 0
               AND o.failure_stage = 'none'
             ORDER BY o.created_at DESC
             LIMIT ?
            """,
            (project_id, task_id, int(limit)),
        ).fetchall()
    completed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        trace_payload = json_loads(row["trace_payload"], {})
        capsule = trace_payload.get("context_capsule") if isinstance(trace_payload.get("context_capsule"), dict) else {}
        provenance = capsule.get("provenance") if isinstance(capsule.get("provenance"), dict) else {}
        if str(provenance.get("workspace_epoch_id") or "") != str(workspace_epoch_id):
            continue
        next_action = capsule.get("next_action") if isinstance(capsule.get("next_action"), dict) else {}
        action_text = str(next_action.get("action") or "").strip()
        key = _context_action_key(action_text)
        if not key or key in seen:
            continue
        metadata = json_loads(row["metadata"], {})
        observed = metadata.get("observed") if isinstance(metadata.get("observed"), dict) else {}
        completion_match = _context_completion_match(
            action_text=action_text,
            row=row,
            observed=observed,
            trace_payload=trace_payload if isinstance(trace_payload, dict) else {},
        )
        if not completion_match.get("matched"):
            continue
        seen.add(key)
        completed.append(
            {
                "action": action_text,
                "action_key": key,
                "trace_id": row["trace_id"],
                "outcome_id": row["outcome_id"],
                "first_action": observed.get("first_action") or row["first_action"],
                "created_at": row["created_at"],
                "completion_match": completion_match,
            }
        )
    return completed


def _compile_context_capsule(
    *,
    project_id: str,
    payload: dict[str, Any],
    workspace_current: dict[str, Any] | None,
    selected: list[dict[str, Any]],
    context_status: dict[str, Any],
    context_hygiene: dict[str, Any],
    fallback_cascade: dict[str, Any] | None,
    compiled_at: str,
) -> dict[str, Any]:
    next_actions = _autopilot_list(
        workspace_current.get("next_actions") if isinstance(workspace_current, dict) else [],
        limit=3,
        max_chars=220,
    )
    workspace_task_id = str(workspace_current.get("task_id") or "") if isinstance(workspace_current, dict) else ""
    workspace_epoch_id = (
        str(workspace_current.get("workspace_epoch_id") or "")
        if isinstance(workspace_current, dict)
        else ""
    )
    completed_next_actions = _context_completed_next_actions(
        project_id=project_id,
        task_id=workspace_task_id,
        workspace_epoch_id=workspace_epoch_id,
    )
    completed_action_keys = {str(item.get("action_key") or "") for item in completed_next_actions if item.get("action_key")}
    remaining_next_actions = [
        action for action in next_actions if _context_action_key(action) not in completed_action_keys
    ]
    skipped_next_actions = [
        action for action in next_actions if _context_action_key(action) in completed_action_keys
    ]
    constraints = _autopilot_list(
        workspace_current.get("constraints") if isinstance(workspace_current, dict) else [],
        limit=4,
        max_chars=180,
    )
    blockers = _autopilot_list(
        workspace_current.get("blockers") if isinstance(workspace_current, dict) else [],
        limit=4,
        max_chars=180,
    )
    if not constraints and blockers:
        constraints = blockers[:2]
    selected_memory_ids = [str(memory.get("id")) for memory in selected if memory.get("id")]
    goal = ""
    status = "unknown"
    if isinstance(workspace_current, dict):
        goal = _autopilot_short_text(workspace_current.get("current_goal") or workspace_current.get("summary"), 260)
        status = _autopilot_short_text(workspace_current.get("status") or "unknown", 80)
    if not goal:
        goal = _autopilot_short_text(payload.get("query"), 260)
    next_action_text = (
        remaining_next_actions[0]
        if remaining_next_actions
        else (_autopilot_short_text(payload.get("query"), 220) if not next_actions else next_actions[-1])
    )
    next_action_reason = "current_workspace.next_actions"
    if skipped_next_actions and remaining_next_actions:
        next_action_reason = "current_workspace.next_actions.after_outcome_progress"
    elif not next_actions:
        next_action_reason = "query_fallback"
    relevant_targets = _context_relevant_targets(workspace_current, selected, fallback_cascade=fallback_cascade)
    source_route = _context_source_route(
        payload=payload,
        next_action_text=next_action_text,
        relevant_targets=relevant_targets,
        context_status=context_status,
    )
    action_plan = _context_action_plan(
        payload=payload,
        next_action_text=next_action_text,
        source_route=source_route,
    )
    action_hints = _context_action_hints(
        project_id=project_id,
        payload=payload,
        workspace_current=workspace_current,
        relevant_targets=relevant_targets,
        next_action_text=next_action_text,
        source_route=source_route,
        action_plan=action_plan,
    )
    primary_action_hints, fallback_action_hints = _context_grouped_action_hints(action_hints)
    capsule = {
        "schema_version": CONTEXT_CAPSULE_SCHEMA_VERSION,
        "goal": goal,
        "state_recorded_at": str(workspace_current.get("created_at") or workspace_current.get("recorded_at") or "") if isinstance(workspace_current, dict) else "",
        "state_age_hours": _state_age_hours(workspace_current.get("created_at") or workspace_current.get("recorded_at")) if isinstance(workspace_current, dict) else None,
        "status": status,
        "next_action": {
            "action": next_action_text,
            "target": "",
            "reason": next_action_reason,
        },
        "outcome_progress": {
            "schema_version": "mem1-context-outcome-progress-v0",
            "completed_next_action_count": len(skipped_next_actions),
            "completed_next_actions": completed_next_actions[:3],
            "skipped_next_actions": skipped_next_actions[:3],
        },
        "constraints": constraints,
        "source_route": source_route,
        "action_plan": action_plan,
        "relevant_targets": relevant_targets,
        "action_hints": action_hints,
        "primary_action_hints": primary_action_hints,
        "fallback_action_hints": fallback_action_hints,
        "verified_evidence": _autopilot_list(
            workspace_current.get("terminal_evidence_refs") if isinstance(workspace_current, dict) else [],
            limit=3,
            max_chars=160,
        ),
        "uncertainties": _autopilot_list(
            [context_status.get("primary_reason")] + list(context_status.get("missing") or []),
            limit=4,
            max_chars=160,
        ),
        "freshness": {
            "compiled_at": compiled_at,
            "live_state_checked_at": compiled_at,
        },
        "provenance": {
            "workspace_claim_id": workspace_current.get("claim_id") if isinstance(workspace_current, dict) else None,
            "workspace_epoch_id": workspace_current.get("workspace_epoch_id") if isinstance(workspace_current, dict) else None,
            "selected_memory_ids": selected_memory_ids,
            "context_hygiene_summary": context_hygiene.get("summary", ""),
        },
        "token_budget": CONTEXT_CAPSULE_TOKEN_BUDGET,
    }
    if isinstance(fallback_cascade, dict):
        capsule["fallback"] = {
            "schema_version": fallback_cascade.get("schema_version"),
            "selected_stage": fallback_cascade.get("selected_stage") or "",
            "used_stages": fallback_cascade.get("used_stages") or [],
            "suggestions": fallback_cascade.get("suggestions") or [],
            "suggested_related_task_ids": fallback_cascade.get("suggested_related_task_ids") or [],
        }
    return capsule


def _context_source_route_display_text(source_route: dict[str, Any]) -> str:
    source_class = str(source_route.get("source_class") or "unknown")
    availability = source_route.get("availability") if isinstance(source_route.get("availability"), dict) else {}
    runtime = source_route.get("runtime_location") if isinstance(source_route.get("runtime_location"), dict) else {}
    source_labels = {
        "repo_inspection": "저장소 파일 확인",
        "remote_4090_runtime": "4090 런타임 확인",
        "enacta_memory": "Forget 기억 확인",
        "codex_memory": "Codex 메모리 확인",
        "browser_or_file_view": "브라우저/파일 화면 확인",
        "goal_state": "목표 상태 확인",
        "skill_doc": "스킬 문서 확인",
        "web_or_github": "웹/GitHub 확인",
        "user_input": "사용자 확인 필요",
        "unknown": "정보 소스 미정",
    }
    runtime_labels = {
        "remote_4090_runtime": "4090에서 실행",
        "local_workspace": "현재 작업공간에서 실행",
        "unknown": "실행 위치 미정",
    }
    availability_labels = {
        "available": "확인됨",
        "not_checked": "확인 필요",
        "unavailable": "사용 불가",
        "unknown": "상태 미정",
    }
    source_label = source_labels.get(source_class, source_class)
    runtime_label = runtime_labels.get(str(runtime.get("kind") or "unknown"), str(runtime.get("kind") or "실행 위치 미정"))
    availability_label = availability_labels.get(
        str(availability.get("status") or "unknown"),
        str(availability.get("status") or "상태 미정"),
    )
    return f"{source_label} / {runtime_label} / {availability_label}"


def _context_action_plan_display_text(action_plan: dict[str, Any]) -> str:
    intent = str(action_plan.get("intent") or "general_continuation")
    first_action_kind = str(action_plan.get("first_action_kind") or "inspect_best_target")
    intent_labels = {
        "implementation": "구현 변경",
        "verification": "검증",
        "evidence_analysis": "증거 분석",
        "runtime_operations": "런타임 확인",
        "planning_review": "방향 검토",
        "rollout_observer": "세션 관측",
        "general_continuation": "작업 계속",
    }
    action_labels = {
        "inspect_implementation": "구현 파일부터 확인",
        "inspect_tests": "테스트부터 확인",
        "inspect_evidence": "증거 파일부터 확인",
        "probe_runtime": "런타임부터 확인",
        "inspect_context": "컨텍스트부터 확인",
        "inspect_observer": "관측 도구부터 확인",
        "inspect_best_target": "가장 관련 높은 대상 확인",
    }
    return f"{intent_labels.get(intent, intent)} / {action_labels.get(first_action_kind, first_action_kind)}"


GOAL_TASK_PREFIX = "goal:"
STANCE_TASK_PREFIX = "stance:"


def _stance_line(project_id: str, scope_filters: dict[str, Any] | None = None) -> str:
    """The assistant's self-recorded stance — who it was being, not what it did.

    Assistant-authored (user zero, 2026-07-25): the capsule restores task
    state but not posture; a hand that wakes as a function needs a human to
    say "remember who you were" before it acts like the one who lived the
    last session. Convention: a task_state whose task_id starts with
    "stance:", written by the assistant at natural session closes. Renders
    only while fresh (MEM1_STANCE_MAX_AGE_DAYS, default 7) — a stale stance
    would fossilize a dead persona, which is worse than waking blank.
    """
    try:
        listing = get_task_state({"limit": 12}, project_id=project_id)
    except Exception:
        return ""
    max_age_days = float(os.environ.get("MEM1_STANCE_MAX_AGE_DAYS", "7"))
    for item in listing.get("results") or []:
        if not isinstance(item, dict):
            continue
        if scope_filters and not _task_claim_scope_matches_filters(
            item.get("scope") if isinstance(item.get("scope"), dict) else {}, scope_filters
        ):
            continue
        task_id = str(item.get("task_id") or "")
        if not task_id.startswith(STANCE_TASK_PREFIX):
            continue
        if str(item.get("status") or "").lower() not in ("in_progress", "active"):
            continue
        stamp = str(item.get("updated_at") or item.get("created_at") or "")
        try:
            recorded = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - recorded).total_seconds() / 86400
        except ValueError:
            continue
        if age_days > max_age_days:
            continue
        summary = str(item.get("summary") or "").split("\n")[0][:200]
        if summary:
            return summary
    return ""


def _capsule_scope_filters(payload: dict[str, Any] | None) -> dict[str, Any]:
    """The requesting scope, for capsule layers that list task state.

    Demo-taste find (2026-07-26, pre-0.3.1): goal/stance/parallel/postit
    helpers listed the whole project, so a demo-user capsule rendered the
    real user's goals and the assistant's stance — a cross-scope leak that
    would have put private strategy on a screen recording. Every capsule
    layer that reads the ledger must honor the requesting scope.
    """
    filters = (payload or {}).get("filters")
    if not isinstance(filters, dict):
        filters = {}
    scope = {field: filters.get(field) for field in ENTITY_FIELDS if filters.get(field)}
    project = _requested_project(payload or {}, filters)
    if project:
        scope["project"] = project
    return scope


def _goal_lines(project_id: str, scope_filters: dict[str, Any] | None = None, limit: int = 2) -> list[str]:
    """Active goals — the "why" layer above tasks.

    Convention: a goal is a task_state whose task_id starts with "goal:".
    Tasks link to goals via goal_id. Goals render as their own capsule line
    and are excluded from parallel tracks (they are not work items).
    """
    try:
        listing = get_task_state({"limit": 12}, project_id=project_id)
    except Exception:
        return []
    lines: list[str] = []
    for item in listing.get("results") or []:
        if not isinstance(item, dict):
            continue
        if scope_filters and not _task_claim_scope_matches_filters(
            item.get("scope") if isinstance(item.get("scope"), dict) else {}, scope_filters
        ):
            continue
        task_id = str(item.get("task_id") or "")
        status = str(item.get("status") or "").lower()
        if not task_id.startswith(GOAL_TASK_PREFIX):
            continue
        if status not in ("in_progress", "active", "running", "blocked", "pending"):
            continue
        summary = str(item.get("summary") or "").split("\n")[0][:110]
        next_actions = item.get("next_actions") or []
        milestone = f" → {str(next_actions[0])[:60]}" if next_actions else ""
        lines.append(f"{task_id.removeprefix(GOAL_TASK_PREFIX)}: {summary}{milestone}")
        if len(lines) >= limit:
            break
    return lines


def _parallel_track_lines(project_id: str, current_task_id: str, scope_filters: dict[str, Any] | None = None, limit: int = 2) -> list[str]:
    """Other in-flight tasks, so the newest epoch can't hijack the capsule.

    Dogfooding taste-test 2026-07-23: an evening of system work made the
    morning capsule open with engine internals while the actual critical
    path (the YC deadline task) went unmentioned — the capsule showed only
    the most recently written task. One line of parallel tracks keeps every
    active thread visible without widening the budget.
    """
    try:
        listing = get_task_state({"limit": 8}, project_id=project_id)
    except Exception:
        return []
    lines: list[str] = []
    for item in listing.get("results") or []:
        if not isinstance(item, dict):
            continue
        if scope_filters and not _task_claim_scope_matches_filters(
            item.get("scope") if isinstance(item.get("scope"), dict) else {}, scope_filters
        ):
            continue
        task_id = str(item.get("task_id") or "")
        status = str(item.get("status") or "").lower()
        if not task_id or task_id == current_task_id:
            continue
        if task_id.startswith(GOAL_TASK_PREFIX):
            continue  # goals are the why-layer, rendered on their own line
        if task_id.startswith(STANCE_TASK_PREFIX):
            continue  # the stance is posture, not a work item
        if status not in ("in_progress", "active", "running", "blocked", "pending"):
            continue
        next_actions = item.get("next_actions") or []
        first = str(next_actions[0])[:90] if next_actions else ""
        lines.append(f"{task_id} — {first}" if first else task_id)
        if len(lines) >= limit:
            break
    return lines


def _open_loop_postits(project_id: str, scope_filters: dict[str, Any] | None = None, limit: int = 3) -> list[dict[str, Any]]:
    """Unverified agent-reported action claims that have stayed open too long.

    Incident #0's shape: an agent-side "action was completed" claim that
    nobody confirms or corrects just sits in the ledger looking like a fact.
    Surface the oldest few at session start until the loop is closed —
    today closing means supersede/correct or delete; attaching verification
    evidence is the W1+ upgrade.
    """
    try:
        min_age_days = float(os.environ.get("MEM1_OPEN_LOOP_DAYS", "2"))
    except ValueError:
        min_age_days = 2.0
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT c.claim_text, c.created_at, c.scope, m.metadata
            FROM claims c JOIN memories m ON m.id = c.memory_id AND m.project_id = c.project_id
            WHERE c.project_id = ? AND c.modality = 'reported' AND c.status = 'active'
              AND c.retired_at IS NULL AND m.deleted = 0
            ORDER BY c.created_at ASC
            """,
            (project_id,),
        ).fetchall()
    now_dt = datetime.now(timezone.utc)
    postits: list[dict[str, Any]] = []
    for row in rows:
        if scope_filters and not _task_claim_scope_matches_filters(
            json_loads(row["scope"], {}) or {}, scope_filters
        ):
            continue
        metadata = json_loads(row["metadata"], {})
        if isinstance(metadata, dict) and metadata.get("superseded_at"):
            continue  # corrected — the loop is closed
        created = parse_datetime(row["created_at"])
        if not created:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = (now_dt - created).total_seconds() / 86400
        if age_days < min_age_days:
            continue
        postits.append({"claim": str(row["claim_text"])[:80], "age_days": round(age_days, 1)})
        if len(postits) >= limit:
            break
    return postits


def _state_age_hours(recorded_at: str | None) -> float | None:
    """Age of a task-state record in hours; None when unparseable.

    The capsule's goal/next-action lines are fast-layer state (LOOP.md persona
    model): they harden into false "current" facts unless their age travels
    with them. Field note F1, 2026-07-31: a two-day-old beat was presented as
    the current goal with no freshness signal.
    """
    raw = str(recorded_at or "").strip()
    if not raw:
        return None
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - stamp).total_seconds() / 3600.0)


def _state_age_label(age_hours: float | None) -> str:
    if age_hours is None:
        return ""
    if age_hours < 1:
        return "방금 기록"
    if age_hours < 24:
        return f"{int(age_hours)}시간 전 기록"
    return f"{age_hours / 24:.1f}일 전 기록"


def _render_context_capsule_text(capsule: dict[str, Any]) -> str:
    next_action = capsule.get("next_action") if isinstance(capsule.get("next_action"), dict) else {}
    source_route = capsule.get("source_route") if isinstance(capsule.get("source_route"), dict) else {}
    action_plan = capsule.get("action_plan") if isinstance(capsule.get("action_plan"), dict) else {}
    constraints = [str(item) for item in capsule.get("constraints") or [] if str(item)]
    targets = [
        str(item.get("target") or "")
        for item in capsule.get("relevant_targets") or []
        if isinstance(item, dict) and str(item.get("target") or "")
    ]
    uncertainties = [str(item) for item in capsule.get("uncertainties") or [] if str(item)]
    age_hours = capsule.get("state_age_hours")
    age_label = _state_age_label(age_hours if isinstance(age_hours, (int, float)) else None)
    goal_suffix = f" ({age_label})" if age_label else ""
    lines = [
        f"현재 목표: {_autopilot_short_text(capsule.get('goal'), 240)}{goal_suffix}",
        f"현재 상태: {_autopilot_short_text(capsule.get('status'), 120)}",
        f"다음 행동: {_autopilot_short_text(next_action.get('action'), 220)}",
    ]
    try:
        stale_hours = float(os.environ.get("MEM1_CAPSULE_STALE_HOURS", "24") or 24)
    except ValueError:
        stale_hours = 24.0
    if isinstance(age_hours, (int, float)) and age_hours >= stale_hours:
        # Early position: the budget loop pops from the tail, and a missing
        # staleness warning costs more than any droppable detail (F1).
        lines.insert(
            3,
            f"⚠ 상태 신선도: 위 목표·다음 행동은 {age_label} — 유동층 낡음, 재검증 후 행동",
        )
    goal_lines = [str(item) for item in capsule.get("goal_lines") or [] if str(item)]
    if goal_lines:
        lines.append("상위 목표: " + " | ".join(goal_lines[:2]))
    stance_line = str(capsule.get("stance_line") or "")
    if stance_line:
        lines.append("자세: " + stance_line)
    parallel_tracks = [str(item) for item in capsule.get("parallel_tracks") or [] if str(item)]
    if parallel_tracks:
        # placed above the droppable tail: under budget pressure the render
        # loop pops from the end, and a shadowed deadline costs more than
        # source-route detail
        lines.append("병행 트랙: " + " | ".join(parallel_tracks[:2]))
    if constraints:
        lines.append("중요 제약: " + "; ".join(constraints[:3]))
    if targets:
        # full paths cost ~60 tokens of noise per capsule; basenames carry
        # the signal (token audit 2026-07-23: 41% of the capsule was
        # machine-template leakage — source_route, action_plan, raw
        # uncertainty enums, absolute paths. The structured capsule dict
        # keeps everything; the injected text is for a reader.)
        short_targets = [os.path.basename(target.rstrip("/")) or target for target in targets]
        lines.append("관련 대상: " + "; ".join(short_targets[:4]))
    open_loops = [item for item in capsule.get("open_loops") or [] if isinstance(item, dict)]
    if open_loops:
        lines.append(
            "열린 루프(미검증 완료 주장): "
            + " | ".join(
                f"'{item.get('claim')}' — {item.get('age_days')}일째, 증거 확인 또는 정정 필요"
                for item in open_loops[:3]
            )
        )
    text = "\n".join(line for line in lines if line.strip())
    while token_estimate(text) > CONTEXT_CAPSULE_TOKEN_BUDGET and len(lines) > 3:
        lines.pop()
        text = "\n".join(line for line in lines if line.strip())
    if token_estimate(text) > CONTEXT_CAPSULE_TOKEN_BUDGET:
        words = text.split()
        text = " ".join(words[:CONTEXT_CAPSULE_TOKEN_BUDGET])
    return text


def _compile_use_now_packet(
    *,
    capsule: dict[str, Any],
    context_status: dict[str, Any],
    context_hygiene: dict[str, Any],
    fallback_cascade: dict[str, Any] | None = None,
) -> dict[str, Any]:
    next_action = capsule.get("next_action") if isinstance(capsule.get("next_action"), dict) else {}
    targets = capsule.get("relevant_targets") if isinstance(capsule.get("relevant_targets"), list) else []
    target = ""
    if targets and isinstance(targets[0], dict):
        target = str(targets[0].get("target") or "")
    action_text = str(next_action.get("action") or "").strip()
    next_actions = []
    if action_text:
        primary_hint = None
        primary_action_hints = (
            capsule.get("primary_action_hints") if isinstance(capsule.get("primary_action_hints"), list) else []
        )
        action_hints = capsule.get("action_hints") if isinstance(capsule.get("action_hints"), list) else []
        if primary_action_hints and isinstance(primary_action_hints[0], dict):
            primary_hint = primary_action_hints[0]
        elif action_hints and isinstance(action_hints[0], dict):
            primary_hint = action_hints[0]
        next_actions.append(
            {
                "action": "continue_next_action",
                "target": target,
                "purpose": action_text,
                "source": str(next_action.get("reason") or "context_capsule"),
                **({"first_tool_hint": primary_hint} if primary_hint else {}),
            }
        )
    fallback_actions: list[dict[str, Any]] = []
    if isinstance(fallback_cascade, dict):
        for suggestion in fallback_cascade.get("suggestions") or []:
            if not isinstance(suggestion, dict):
                continue
            fallback_actions.append(
                {
                    "action": str(suggestion.get("action") or "inspect_context_fallback"),
                    "target": str(suggestion.get("target") or suggestion.get("memory_id") or ""),
                    "purpose": str(suggestion.get("purpose") or "Inspect bounded fallback context."),
                    "source": str(suggestion.get("source") or "context_fallback_cascade"),
                }
            )
    priority_fallback_actions = [
        action for action in fallback_actions if action.get("action") != "continue_current_workspace"
    ]
    if context_status.get("status") != "sufficient" and priority_fallback_actions:
        next_actions = [*priority_fallback_actions[:2], *next_actions[:1]]
    elif fallback_actions:
        next_actions = [*next_actions, *fallback_actions[:1]]
    if not next_actions and context_status.get("status") == "insufficient":
        next_actions.append(
            {
                "action": "inspect_context_gap",
                "target": str(context_status.get("primary_reason") or "context_status"),
                "purpose": "Resolve why Forget could not assemble actionable context.",
                "source": "context_status",
            }
        )
    deduped_actions: list[dict[str, Any]] = []
    seen_actions: set[tuple[str, str, str]] = set()
    for action in next_actions:
        key = (
            str(action.get("action") or ""),
            str(action.get("target") or ""),
            str(action.get("purpose") or ""),
        )
        if key in seen_actions:
            continue
        seen_actions.add(key)
        deduped_actions.append(action)
    reasons = [str(context_hygiene.get("summary") or "")]
    outcome_progress = capsule.get("outcome_progress") if isinstance(capsule.get("outcome_progress"), dict) else {}
    completed_next_action_count = int(outcome_progress.get("completed_next_action_count") or 0)
    if completed_next_action_count:
        reasons.append(f"outcome advanced {completed_next_action_count} completed next action(s)")
    effective_status = str(context_status.get("effective_status") or context_status.get("status") or "unknown")
    raw_status = str(context_status.get("status") or "unknown")
    if effective_status != "sufficient":
        reasons.append(
            f"context {effective_status}: {context_status.get('primary_reason')}"
        )
    return {
        "schema_version": CONTEXT_USE_NOW_SCHEMA_VERSION,
        "next_actions": deduped_actions,
        "source_route": capsule.get("source_route") if isinstance(capsule.get("source_route"), dict) else {},
        "action_plan": capsule.get("action_plan") if isinstance(capsule.get("action_plan"), dict) else {},
        "action_hints": capsule.get("action_hints") if isinstance(capsule.get("action_hints"), list) else [],
        "primary_action_hints": (
            capsule.get("primary_action_hints") if isinstance(capsule.get("primary_action_hints"), list) else []
        ),
        "fallback_action_hints": (
            capsule.get("fallback_action_hints") if isinstance(capsule.get("fallback_action_hints"), list) else []
        ),
        "supporting_context": _context_use_now_supporting_context(fallback_cascade),
        "reason": [reason for reason in reasons if reason],
        "context_status": effective_status,
        "raw_context_status": raw_status,
    }


def _context_use_now_supporting_context(fallback_cascade: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(fallback_cascade, dict):
        return []
    why_by_reason = {
        "selected_related_task": "Selected because the current task explicitly links to this related task.",
        "selected_reverse_related_task": "Selected because this task state explicitly links back to the current task.",
        "selected_exact_task": "Selected because it matches the current task scope.",
        "same_parent_goal": "Available because it shares the requested parent goal.",
        "same_artifact": "Available because it touches a current workspace artifact.",
        "recent_verified_state": "Available because it has recent terminal evidence.",
    }
    supporting: list[dict[str, Any]] = []
    seen: set[str] = set()
    for stage in fallback_cascade.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        for candidate in stage.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            memory_id = str(candidate.get("memory_id") or "")
            if not memory_id or memory_id in seen:
                continue
            match_reason = str(candidate.get("match_reason") or "")
            if match_reason not in why_by_reason:
                continue
            seen.add(memory_id)
            supporting.append(
                {
                    "memory_id": memory_id,
                    "role": str(candidate.get("role") or ""),
                    "task_id": str(candidate.get("task_id") or ""),
                    "match_reason": match_reason,
                    "why": why_by_reason[match_reason],
                    "summary": _autopilot_short_text(candidate.get("summary"), max_chars=180),
                    "artifacts": list(candidate.get("artifacts") or [])[:3],
                }
            )
            if len(supporting) >= 3:
                return supporting
    return supporting


def _context_autopilot_debug(
    *,
    context_status: dict[str, Any],
    capsule: dict[str, Any],
    capsule_text: str,
    final_model_context: str,
    task_scope_filtered_memory_ids: list[str],
    workspace_duplicate_filtered_memory_ids: list[str],
    role_backfill: dict[str, Any],
    fallback_cascade: dict[str, Any],
    selected: list[dict[str, Any]],
    raw_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": CONTEXT_AUTOPILOT_DEBUG_SCHEMA_VERSION,
        "policy_version": _CONTEXT_SELECTOR_POLICY_VERSION,
        "context_status": context_status,
        "capsule_token_estimate": token_estimate(capsule_text),
        "final_model_context_sha256": hashlib.sha256(final_model_context.encode("utf-8")).hexdigest(),
        "selected_ids": [str(memory.get("id")) for memory in selected if memory.get("id")],
        "raw_candidate_ids": [str(memory.get("id")) for memory in raw_candidates if memory.get("id")],
        "excluded": {
            "task_scope_filtered_ids": task_scope_filtered_memory_ids,
            "workspace_duplicate_filtered_ids": workspace_duplicate_filtered_memory_ids,
        },
        "fallback": {
            "used": context_status.get("fallback_used", []),
            "role_backfill": role_backfill,
            "cascade": fallback_cascade,
        },
        "capsule_provenance": capsule.get("provenance", {}),
    }


def _attach_context_autopilot(
    *,
    result: dict[str, Any],
    payload: dict[str, Any],
    raw_candidates: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    task_scope_filtered_memory_ids: list[str],
    workspace_duplicate_filtered_memory_ids: list[str],
    workspace_current: dict[str, Any] | None,
    role_backfill: dict[str, Any],
    compiled_at: str,
) -> dict[str, Any]:
    requested_task_id = _context_requested_task_id(payload)
    requested_related_task_ids = _context_requested_related_task_ids(payload, workspace_current)
    requested_task_scope_ids = _context_requested_task_scope_ids(requested_task_id, requested_related_task_ids)
    fallback_cascade = _context_fallback_cascade(
        payload=payload,
        requested_task_id=requested_task_id,
        requested_task_scope_ids=requested_task_scope_ids,
        raw_candidates=raw_candidates,
        selected=selected,
        task_scope_filtered_memory_ids=task_scope_filtered_memory_ids,
        workspace_duplicate_filtered_memory_ids=workspace_duplicate_filtered_memory_ids,
        workspace_current=workspace_current,
        role_backfill=role_backfill,
    )
    context_status = _context_status_for_autopilot(
        raw_candidate_count=int(result.get("raw_candidate_count") or 0),
        selected_count=int(result.get("selected_count") or 0),
        task_scope_filtered_memory_ids=task_scope_filtered_memory_ids,
        workspace_duplicate_filtered_memory_ids=workspace_duplicate_filtered_memory_ids,
        workspace_current=workspace_current,
        role_backfill=role_backfill,
        fallback_cascade=fallback_cascade,
    )
    context_hygiene = result.get("context_hygiene") if isinstance(result.get("context_hygiene"), dict) else {}
    capsule = _compile_context_capsule(
        project_id=str(result.get("project_id") or current_project_id()),
        payload=payload,
        workspace_current=workspace_current,
        selected=selected,
        context_status=context_status,
        context_hygiene=context_hygiene,
        fallback_cascade=fallback_cascade,
        compiled_at=compiled_at,
    )
    capsule_project_id = str(result.get("project_id") or current_project_id())
    capsule_scope = _capsule_scope_filters(payload)
    capsule["open_loops"] = _open_loop_postits(capsule_project_id, capsule_scope)
    current_task_id = str((workspace_current or {}).get("task_id") or "")
    capsule["parallel_tracks"] = _parallel_track_lines(capsule_project_id, current_task_id, capsule_scope)
    capsule["goal_lines"] = _goal_lines(capsule_project_id, capsule_scope)
    capsule["stance_line"] = _stance_line(capsule_project_id, capsule_scope)
    capsule_text = _render_context_capsule_text(capsule)
    final_model_context = str(result.get("context") or "")
    result["context_status"] = context_status
    result["fallback_cascade"] = fallback_cascade
    result["context_capsule"] = capsule
    result["context_capsule_text"] = capsule_text
    result["final_model_context"] = final_model_context
    result["materialization"] = {
        "schema_version": CONTEXT_MATERIALIZATION_SCHEMA_VERSION,
        "materialized_at": compiled_at,
        "policy_version": _CONTEXT_SELECTOR_POLICY_VERSION,
        "capsule_json": capsule,
        "capsule_text": capsule_text,
        "final_model_context": final_model_context,
        "final_model_context_sha256": hashlib.sha256(final_model_context.encode("utf-8")).hexdigest(),
    }
    result["use_now"] = _compile_use_now_packet(
        capsule=capsule,
        context_status=context_status,
        context_hygiene=context_hygiene,
        fallback_cascade=fallback_cascade,
    )
    result["debug"] = _context_autopilot_debug(
        context_status=context_status,
        capsule=capsule,
        capsule_text=capsule_text,
        final_model_context=final_model_context,
        task_scope_filtered_memory_ids=task_scope_filtered_memory_ids,
        workspace_duplicate_filtered_memory_ids=workspace_duplicate_filtered_memory_ids,
        role_backfill=role_backfill,
        fallback_cascade=fallback_cascade,
        selected=selected,
        raw_candidates=raw_candidates,
    )
    return result


def _compact_autopilot_materialization(materialization: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(materialization, dict):
        return {}
    return {
        "schema_version": materialization.get("schema_version") or CONTEXT_MATERIALIZATION_SCHEMA_VERSION,
        "materialized_at": materialization.get("materialized_at"),
        "policy_version": materialization.get("policy_version"),
        "final_model_context_sha256": materialization.get("final_model_context_sha256"),
    }


def prepare_context_autopilot(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    assembled = assemble_context(payload, project_id=project_id)
    include_context = _bool_or(payload.get("include_context"), False)
    include_debug = _bool_or(payload.get("include_debug"), True)
    result = {
        "schema_version": CONTEXT_AUTOPILOT_SCHEMA_VERSION,
        # The hooks' canary: they compare this against the capability they
        # were built for and warn in the capsule when the server lags. Its
        # absence is itself a signal (server ≤ 0.3.8).
        "server_version": _server_version(),
        "project_id": assembled.get("project_id"),
        "context_trace_id": assembled.get("context_trace_id"),
        "status": (assembled.get("context_status") or {}).get(
            "effective_status",
            (assembled.get("context_status") or {}).get("status", "unknown"),
        ),
        "context_status": assembled.get("context_status") or {},
        "fallback_cascade": assembled.get("fallback_cascade") or {},
        "use_now": assembled.get("use_now") or {},
        "capsule": assembled.get("context_capsule") or {},
        "capsule_text": assembled.get("context_capsule_text") or "",
        "materialization": _compact_autopilot_materialization(assembled.get("materialization") or {}),
        "evidence": {
            "schema_version": (assembled.get("evidence") or {}).get("schema_version"),
            "context_trace_id": (assembled.get("evidence") or {}).get("context_trace_id"),
            "context_sha256": (assembled.get("evidence") or {}).get("context_sha256"),
            "memory_ids": (assembled.get("evidence") or {}).get("memory_ids", []),
            "fallback_memory_ids": (assembled.get("evidence") or {}).get("fallback_memory_ids", []),
            "fallback_selected_stage": (assembled.get("evidence") or {}).get("fallback_selected_stage", ""),
            "fallback_used_stages": (assembled.get("evidence") or {}).get("fallback_used_stages", []),
            "omitted_memory_ids": (assembled.get("evidence") or {}).get("omitted_memory_ids", []),
            "working_memory_pressure": (assembled.get("evidence") or {}).get("working_memory_pressure"),
        },
    }
    if include_debug:
        result["debug"] = assembled.get("debug") or {}
    if include_context:
        result["final_model_context"] = assembled.get("final_model_context") or assembled.get("context") or ""
    return result


def _context_trace_task_id(payload: dict[str, Any], workspace_current: dict[str, Any] | None) -> str:
    requested = _context_requested_task_id(payload)
    if requested:
        return requested
    if isinstance(workspace_current, dict) and workspace_current.get("task_id"):
        return _task_state_id({"task_id": workspace_current.get("task_id")})
    return ""


def _context_trace_task_phase(payload: dict[str, Any]) -> str:
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    value = payload.get("task_phase") or payload.get("phase") or filters.get("task_phase") or filters.get("phase") or ""
    return re.sub(r"\s+", "_", str(value).strip().lower())


def _context_trace_snapshots(
    *,
    raw_candidates: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    budgeted: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    role_backfill: dict[str, Any],
) -> list[dict[str, Any]]:
    snapshots_by_id: dict[str, dict[str, Any]] = {}
    for memory in [*raw_candidates, *candidates, *budgeted, *selected]:
        memory_id = str(memory.get("id") or "")
        if memory_id:
            snapshots_by_id[memory_id] = _context_trace_candidate_snapshot(memory)
    for snapshot in role_backfill.get("candidate_snapshots") or []:
        if isinstance(snapshot, dict) and snapshot.get("id"):
            snapshots_by_id.setdefault(str(snapshot["id"]), dict(snapshot))
    return list(snapshots_by_id.values())


def _context_trace_decision_reasons(
    *,
    candidate_ids: list[str],
    raw_candidates: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    budgeted: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    task_scope_filtered_memory_ids: list[str],
    workspace_duplicate_filtered_memory_ids: list[str],
    role_backfill: dict[str, Any],
) -> dict[str, str]:
    reasons = {memory_id: "candidate_not_selected" for memory_id in candidate_ids}
    candidate_id_set = {str(memory.get("id")) for memory in candidates if memory.get("id")}
    budgeted_id_set = {str(memory.get("id")) for memory in budgeted if memory.get("id")}
    selected_id_set = {str(memory.get("id")) for memory in selected if memory.get("id")}
    for memory in raw_candidates:
        memory_id = str(memory.get("id") or "")
        if memory_id and memory_id not in candidate_id_set:
            reasons[memory_id] = "filtered_before_candidate_pool"
    for memory_id in task_scope_filtered_memory_ids:
        reasons[str(memory_id)] = "task_scope_filtered"
    for memory_id in workspace_duplicate_filtered_memory_ids:
        reasons[str(memory_id)] = "workspace_duplicate_filtered"
    for memory_id in candidate_id_set - budgeted_id_set:
        reasons[memory_id] = "token_budget_excluded"
    for memory_id in budgeted_id_set - selected_id_set:
        reasons[memory_id] = "working_memory_slot_omitted"
    for sample in role_backfill.get("rejected_samples") or []:
        if isinstance(sample, dict) and sample.get("memory_id"):
            reason = str(sample.get("reason") or "selector_rejected")
            reasons[str(sample["memory_id"])] = f"selector_{reason}"
    for sample in role_backfill.get("soft_quota_samples") or []:
        if isinstance(sample, dict) and sample.get("memory_id"):
            reasons[str(sample["memory_id"])] = "soft_quota_preserved"
    for memory in selected:
        memory_id = str(memory.get("id") or "")
        if memory_id:
            reasons[memory_id] = "selected"
    return reasons


def _record_context_trace(
    *,
    project_id: str,
    payload: dict[str, Any],
    search_payload: dict[str, Any],
    raw_candidates: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    budgeted: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    role_backfill: dict[str, Any],
    task_scope_filtered_memory_ids: list[str],
    workspace_duplicate_filtered_memory_ids: list[str],
    result: dict[str, Any],
    workspace_current: dict[str, Any] | None,
) -> dict[str, Any]:
    trace_id = str(new_id())
    now = utc_now()
    task_id = _context_trace_task_id(payload, workspace_current)
    task_phase = _context_trace_task_phase(payload)
    snapshots = _context_trace_snapshots(
        raw_candidates=raw_candidates,
        candidates=candidates,
        budgeted=budgeted,
        selected=selected,
        role_backfill=role_backfill,
    )
    candidate_ids = [snapshot["id"] for snapshot in snapshots if snapshot.get("id")]
    selected_ids = [str(memory.get("id")) for memory in selected if memory.get("id")]
    decision_reasons = _context_trace_decision_reasons(
        candidate_ids=candidate_ids,
        raw_candidates=raw_candidates,
        candidates=candidates,
        budgeted=budgeted,
        selected=selected,
        task_scope_filtered_memory_ids=task_scope_filtered_memory_ids,
        workspace_duplicate_filtered_memory_ids=workspace_duplicate_filtered_memory_ids,
        role_backfill=role_backfill,
    )
    rejected_ids = [memory_id for memory_id in candidate_ids if memory_id not in set(selected_ids)]
    scores = {snapshot["id"]: snapshot.get("score", 0.0) for snapshot in snapshots if snapshot.get("id")}
    roles = {snapshot["id"]: snapshot.get("role", "general") for snapshot in snapshots if snapshot.get("id")}
    trace_payload = {
        "schema_version": CONTEXT_TRACE_SCHEMA_VERSION,
        "trace_id": trace_id,
        "search_payload": search_payload,
        "context_hygiene": result.get("context_hygiene") or {},
        "query_evidence": result.get("query_evidence") or {},
        "working_memory": result.get("working_memory") or {},
        "resume_workspace": result.get("resume_workspace") or {},
        "context_status": result.get("context_status") or {},
        "context_capsule": result.get("context_capsule") or {},
        "context_capsule_text": result.get("context_capsule_text") or "",
        "final_model_context": result.get("final_model_context") or result.get("context") or "",
        "materialization": result.get("materialization") or {},
        "use_now": result.get("use_now") or {},
        "debug": result.get("debug") or {},
        "candidate_snapshots": snapshots,
        "role_backfill": role_backfill,
        "context_access_decision_id": result.get("context_access_decision_id"),
    }
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO context_traces (
                trace_id, project_id, task_id, task_phase, policy_version, query,
                filters, candidate_ids, selected_ids, rejected_ids, scores, roles,
                decision_reasons, token_cost, payload, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace_id,
                project_id,
                task_id,
                task_phase,
                _CONTEXT_SELECTOR_POLICY_VERSION,
                str(search_payload.get("query") or ""),
                json_dumps(search_payload.get("filters") or {}),
                json_dumps(candidate_ids),
                json_dumps(selected_ids),
                json_dumps(rejected_ids),
                json_dumps(scores),
                json_dumps(roles),
                json_dumps(decision_reasons),
                int(result.get("used_tokens") or 0),
                json_dumps(trace_payload),
                now,
            ),
        )
    return {
        "schema_version": CONTEXT_TRACE_SCHEMA_VERSION,
        "trace_id": trace_id,
        "task_id": task_id,
        "task_phase": task_phase,
        "policy_version": _CONTEXT_SELECTOR_POLICY_VERSION,
        "candidate_count": len(candidate_ids),
        "selected_count": len(selected_ids),
        "rejected_count": len(rejected_ids),
        "token_cost": int(result.get("used_tokens") or 0),
        "created_at": now,
    }


def _context_trace_row_result(row: Any, include_payload: bool = False) -> dict[str, Any]:
    payload = json_loads(row["payload"], {})
    result = {
        "schema_version": CONTEXT_TRACE_SCHEMA_VERSION,
        "trace_id": row["trace_id"],
        "project_id": row["project_id"],
        "task_id": row["task_id"],
        "task_phase": row["task_phase"],
        "policy_version": row["policy_version"],
        "query": row["query"],
        "filters": json_loads(row["filters"], {}),
        "candidate_ids": json_loads(row["candidate_ids"], []),
        "selected_ids": json_loads(row["selected_ids"], []),
        "rejected_ids": json_loads(row["rejected_ids"], []),
        "scores": json_loads(row["scores"], {}),
        "roles": json_loads(row["roles"], {}),
        "decision_reasons": json_loads(row["decision_reasons"], {}),
        "token_cost": int(row["token_cost"] or 0),
        "created_at": row["created_at"],
    }
    if include_payload:
        result["payload"] = payload
    else:
        result["candidate_count"] = len(result["candidate_ids"])
        result["selected_count"] = len(result["selected_ids"])
        result["rejected_count"] = len(result["rejected_ids"])
    return result


def get_context_trace(trace_id: str, project_id: str | None = None, include_payload: bool = True) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM context_traces WHERE project_id = ? AND trace_id = ?",
            (project_id, trace_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Context trace not found")
    return _context_trace_row_result(row, include_payload=include_payload)


def _context_outcome_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _context_outcome_has_observed_field(payload: dict[str, Any], key: str) -> bool:
    observed_payload = payload.get("observed") if isinstance(payload.get("observed"), dict) else {}
    return key in observed_payload or key in payload


def _context_first_action_hint(trace_payload: dict[str, Any]) -> dict[str, Any]:
    hints = _context_action_hints_from_trace(trace_payload)
    return hints[0] if hints else {}


def _context_action_hints_from_trace(trace_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(trace_payload, dict):
        return []
    hint_sources = [
        (trace_payload.get("use_now") or {}).get("action_hints"),
        (trace_payload.get("context_capsule") or {}).get("action_hints"),
    ]
    use_now = trace_payload.get("use_now") if isinstance(trace_payload.get("use_now"), dict) else {}
    next_actions = use_now.get("next_actions") if isinstance(use_now.get("next_actions"), list) else []
    if next_actions and isinstance(next_actions[0], dict):
        hint_sources.insert(0, [next_actions[0].get("first_tool_hint")])
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hint_list in hint_sources:
        if not isinstance(hint_list, list):
            continue
        for hint in hint_list:
            if isinstance(hint, dict) and hint:
                key = json_dumps(
                    {
                        "tool_name": hint.get("tool_name"),
                        "target": hint.get("target"),
                        "arguments_preview": hint.get("arguments_preview"),
                    }
                )
                if key in seen:
                    continue
                seen.add(key)
                collected.append(dict(hint))
    return collected


def _context_fallback_memory_ids_from_trace(trace_payload: dict[str, Any]) -> list[str]:
    if not isinstance(trace_payload, dict):
        return []
    fallback_memory_ids: list[str] = []
    seen: set[str] = set()

    def add(memory_id: Any) -> None:
        text = str(memory_id or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        fallback_memory_ids.append(text)

    debug = trace_payload.get("debug") if isinstance(trace_payload.get("debug"), dict) else {}
    fallback = debug.get("fallback") if isinstance(debug.get("fallback"), dict) else {}
    add_many = _context_fallback_memory_ids_from_cascade(fallback.get("cascade"))
    for memory_id in add_many:
        add(memory_id)
    use_now = trace_payload.get("use_now") if isinstance(trace_payload.get("use_now"), dict) else {}
    supporting_context = (
        use_now.get("supporting_context")
        if isinstance(use_now.get("supporting_context"), list)
        else []
    )
    for item in supporting_context:
        if isinstance(item, dict):
            add(item.get("memory_id"))
    evidence = (
        trace_payload.get("materialization", {}).get("capsule_json", {}).get("evidence")
        if isinstance(trace_payload.get("materialization"), dict)
        else {}
    )
    if isinstance(evidence, dict):
        for memory_id in evidence.get("fallback_memory_ids") or []:
            add(memory_id)
    return fallback_memory_ids


def _context_tool_name(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("functions."):
        text = text.removeprefix("functions.")
    return text


def _context_tool_call_name(tool_call: dict[str, Any]) -> str:
    for key in ("tool_name", "name", "tool", "recipient_name"):
        value = tool_call.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


_CONTEXT_META_PROBE_TOOL_NAMES = {
    "assemble_context",
    "prepare_context_autopilot",
    "get_task_state",
    "record_task_state",
    "record_context_observation",
    "record_context_outcome",
    "verify_context_evidence",
    "verify_memory_claims",
    "search_memories",
    "search_memory",
    "get_memories",
    "get_memory",
    "list_memories",
    "add_memory",
    "add_memories",
    "create_goal",
    "get_goal",
    "update_goal",
    "update_plan",
}


def _context_tool_basename(value: Any) -> str:
    text = _context_tool_name(value)
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.strip()


def _context_meta_probe_match(first_tool_call: dict[str, Any]) -> dict[str, Any]:
    tool_name = _context_tool_call_name(first_tool_call)
    observed_tool = _context_tool_name(tool_name)
    normalized_tool = _context_tool_basename(tool_name)
    if normalized_tool in _CONTEXT_META_PROBE_TOOL_NAMES:
        return {
            "schema_version": "mem1-context-meta-probe-match-v0",
            "matched": True,
            "tool_name": observed_tool,
            "normalized_tool_name": normalized_tool,
            "reason": "first tool call is a context, memory, goal, or evaluation probe excluded from normal first-action alignment",
        }
    nested_calls = _context_parallel_tool_calls(first_tool_call)
    if nested_calls:
        nested_names = [
            _context_tool_basename(_context_tool_call_name(call))
            for call in nested_calls
        ]
        if nested_names and all(name in _CONTEXT_META_PROBE_TOOL_NAMES for name in nested_names):
            return {
                "schema_version": "mem1-context-meta-probe-match-v0",
                "matched": True,
                "tool_name": observed_tool,
                "normalized_tool_name": _context_tool_basename(observed_tool),
                "nested_tool_names": nested_names,
                "reason": "parallel first tool call contains only context, memory, goal, or evaluation probes",
            }
    return {"schema_version": "mem1-context-meta-probe-match-v0", "matched": False}


def _context_tool_call_text(tool_call: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("target", "arguments_preview", "command", "cmd"):
        value = tool_call.get(key)
        if value not in (None, ""):
            parts.append(str(value))
    arguments = tool_call.get("arguments")
    if isinstance(arguments, dict):
        for key in ("cmd", "command", "path", "target", "workdir"):
            value = arguments.get(key)
            if value not in (None, ""):
                parts.append(str(value))
        parts.append(json_dumps(arguments))
    elif arguments not in (None, ""):
            parts.append(str(arguments))
    return " ".join(parts)


def _context_parallel_tool_calls(tool_call: dict[str, Any]) -> list[dict[str, Any]]:
    observed_tool = _context_tool_name(_context_tool_call_name(tool_call))
    if observed_tool != "multi_tool_use.parallel":
        return []
    arguments = tool_call.get("arguments")
    if not isinstance(arguments, dict):
        arguments = json_loads(str(tool_call.get("arguments_preview") or ""), {})
    if not isinstance(arguments, dict):
        arguments = {}
    tool_uses = arguments.get("tool_uses")
    if not isinstance(tool_uses, list):
        tool_uses = tool_call.get("tool_uses")
    if not isinstance(tool_uses, list):
        return []
    calls: list[dict[str, Any]] = []
    for item in tool_uses:
        if not isinstance(item, dict):
            continue
        parameters = item.get("parameters") if isinstance(item.get("parameters"), dict) else {}
        name = str(item.get("recipient_name") or item.get("tool_name") or item.get("name") or "").strip()
        if not name:
            continue
        nested: dict[str, Any] = {
            "name": name,
            "tool_name": name,
            "arguments": parameters,
            "arguments_preview": json_dumps(parameters),
        }
        for key in ("target", "path", "cmd", "command"):
            if parameters.get(key):
                nested[key] = parameters.get(key)
        calls.append(nested)
    return calls


def _context_hint_command(hint: dict[str, Any]) -> str:
    preview = str(hint.get("arguments_preview") or "")
    if not preview:
        return ""
    parsed = json_loads(preview, {})
    if isinstance(parsed, dict) and parsed.get("cmd"):
        return str(parsed["cmd"])
    return preview


def _context_target_matches(observed_text: str, expected_target: str) -> bool:
    target = str(expected_target or "").strip()
    if not target:
        return False
    haystack = str(observed_text or "")
    if target in haystack:
        return True
    normalized_target = os.path.normpath(target)
    if normalized_target and normalized_target in haystack:
        return True
    basename = os.path.basename(normalized_target)
    if basename and basename in haystack:
        return True
    parts = [part for part in normalized_target.split(os.sep) if part]
    if len(parts) >= 2:
        suffix = os.path.join(*parts[-2:])
        if suffix and suffix in haystack:
            return True
    return False


def _context_tool_hint_alignment(
    *,
    first_tool_call: dict[str, Any],
    first_hint: dict[str, Any],
) -> dict[str, Any]:
    expected_tool = _context_tool_name(first_hint.get("tool_name"))
    observed_tool = _context_tool_name(_context_tool_call_name(first_tool_call))
    expected_target = str(first_hint.get("target") or "").strip()
    expected_command = _context_hint_command(first_hint)
    nested_calls = _context_parallel_tool_calls(first_tool_call)
    if nested_calls:
        for nested_call in nested_calls:
            nested_tool = _context_tool_name(_context_tool_call_name(nested_call))
            nested_text = _context_tool_call_text(nested_call)
            nested_tool_name_match = bool(expected_tool and nested_tool and expected_tool == nested_tool)
            nested_target_match = _context_target_matches(nested_text, expected_target)
            nested_command_match = bool(expected_command and expected_command in nested_text)
            if nested_tool_name_match and (nested_target_match or nested_command_match or not expected_target):
                return {
                    "schema_version": "mem1-context-tool-hint-alignment-v0",
                    "expected_tool_name": expected_tool,
                    "observed_tool_name": observed_tool,
                    "expected_target": expected_target,
                    "tool_name_match": True,
                    "target_match": nested_target_match,
                    "command_match": nested_command_match,
                    "aligned": True,
                    "parallel_nested_match": True,
                    "parallel_candidate_count": len(nested_calls),
                    "nested_observed_tool_name": nested_tool,
                    "reason": "parallel first tool call contained a nested tool that matched the recommended action hint",
                }

    observed_text = _context_tool_call_text(first_tool_call)
    tool_name_match = bool(expected_tool and observed_tool and expected_tool == observed_tool)
    target_match = _context_target_matches(observed_text, expected_target)
    command_match = bool(expected_command and expected_command in observed_text)
    aligned = bool(tool_name_match and (target_match or command_match or not expected_target))
    if aligned:
        reason = "first tool call matched the recommended action hint"
    elif expected_tool and observed_tool and expected_tool != observed_tool:
        reason = "first tool call used a different tool than the recommended action hint"
    elif expected_target and not target_match and not command_match:
        reason = "first tool call did not target the recommended action hint target"
    else:
        reason = "first tool call did not clearly match the recommended action hint"
    return {
        "schema_version": "mem1-context-tool-hint-alignment-v0",
        "expected_tool_name": expected_tool,
        "observed_tool_name": observed_tool,
        "expected_target": expected_target,
        "tool_name_match": tool_name_match,
        "target_match": target_match,
        "command_match": command_match,
        "aligned": aligned,
        "reason": reason,
    }


def _context_tool_hint_alignments(
    *,
    first_tool_call: dict[str, Any],
    trace_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    alignments: list[dict[str, Any]] = []
    for index, hint in enumerate(_context_action_hints_from_trace(trace_payload)):
        alignment = _context_tool_hint_alignment(first_tool_call=first_tool_call, first_hint=hint)
        hint_group = str(hint.get("hint_group") or ("primary" if index == 0 else "fallback")).strip()
        alignment["hint_index"] = index
        alignment["hint_group"] = hint_group
        alignment["hint_source"] = str(hint.get("source") or "")
        alignment["hint_target"] = str(hint.get("target") or "")
        alignment["hint"] = hint
        alignments.append(alignment)
    return alignments


_CONTEXT_QUERY_REFERENCE_RE = re.compile(
    r"(?P<target>"
    r"(?:~|/|\.)?[A-Za-z0-9_.@%+=:,\-가-힣]+(?:/[A-Za-z0-9_.@%+=:,\-가-힣]+)+"
    r"|"
    r"[A-Za-z0-9_.@%+=:,\-가-힣]+\."
    r"(?:py|html|css|js|ts|tsx|json|md|txt|csv|yaml|yml|sh|sqlite3|db|png|jpg|jpeg|pdf)"
    r")"
)


def _context_trace_query_text(trace_payload: dict[str, Any]) -> str:
    texts: list[str] = []
    for key in ("trace_query", "query"):
        value = trace_payload.get(key)
        if isinstance(value, str) and value.strip():
            texts.append(value)
    search_payload = trace_payload.get("search_payload")
    if isinstance(search_payload, dict):
        value = search_payload.get("query")
        if isinstance(value, str) and value.strip():
            texts.append(value)
    return "\n".join(texts)


def _context_query_referenced_targets(trace_payload: dict[str, Any]) -> list[str]:
    query_text = _context_trace_query_text(trace_payload)
    if not query_text:
        return []
    targets: list[str] = []
    seen: set[str] = set()
    for match in _CONTEXT_QUERY_REFERENCE_RE.finditer(query_text):
        target = match.group("target").strip().rstrip(".,:;)]}")
        if not target or target in seen:
            continue
        seen.add(target)
        targets.append(target)
    return targets


def _context_query_reference_match(
    *,
    first_tool_call: dict[str, Any],
    trace_payload: dict[str, Any],
) -> dict[str, Any]:
    observed_text = _context_tool_call_text(first_tool_call)
    for target in _context_query_referenced_targets(trace_payload):
        if _context_target_matches(observed_text, target):
            return {
                "schema_version": "mem1-context-query-reference-match-v0",
                "matched": True,
                "target": target,
                "reason": "first tool call matched a path or file explicitly mentioned in the trace query",
            }
    return {"schema_version": "mem1-context-query-reference-match-v0", "matched": False}


def _context_repeated_next_action_match(trace_payload: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    capsule = trace_payload.get("context_capsule") if isinstance(trace_payload.get("context_capsule"), dict) else {}
    progress = capsule.get("outcome_progress") if isinstance(capsule.get("outcome_progress"), dict) else {}
    completed = progress.get("completed_next_actions") if isinstance(progress.get("completed_next_actions"), list) else []
    observed_key = _context_action_key(
        " ".join(
            [
                str(observed.get("first_action") or ""),
                _context_tool_call_text(observed.get("first_tool_call") or {}),
            ]
        )
    )
    if not observed_key:
        return {}
    for item in completed:
        if not isinstance(item, dict):
            continue
        action_text = str(item.get("action") or "")
        action_key = str(item.get("action_key") or _context_action_key(action_text))
        if action_key and (action_key in observed_key or observed_key in action_key):
            return {
                "schema_version": "mem1-context-repeated-work-match-v0",
                "matched_completed_action": action_text,
                "matched_trace_id": item.get("trace_id"),
                "matched_outcome_id": item.get("outcome_id"),
                "reason": "first action overlaps an already completed next action in the context capsule",
            }
    return {}


def _context_outcome_observed(payload: dict[str, Any]) -> dict[str, Any]:
    observed_payload = payload.get("observed") if isinstance(payload.get("observed"), dict) else {}

    def _value(key: str, default: Any = None) -> Any:
        if key in observed_payload:
            return observed_payload.get(key)
        return payload.get(key, default)

    first_tool_call = _value("first_tool_call", {})
    tool_result = _value("tool_result", {})
    observed = {
        "schema_version": CONTEXT_OUTCOME_OBSERVED_SCHEMA_VERSION,
        "used_memory_ids": _context_outcome_list(_value("used_memory_ids")),
        "missing_memory_ids": _context_outcome_list(_value("missing_memory_ids")),
        "harmful_memory_ids": _context_outcome_list(_value("harmful_memory_ids")),
        "first_action_productive": _bool_or(_value("first_action_productive"), False),
        "user_correction_required": _bool_or(_value("user_correction_required"), False),
        "first_action": str(_value("first_action", "") or ""),
        "repeated_work": _bool_or(_value("repeated_work"), False),
        "wrong_target": _bool_or(_value("wrong_target"), False),
        "wrong_target_explicit": _context_outcome_has_observed_field(payload, "wrong_target"),
        "first_tool_call": first_tool_call if isinstance(first_tool_call, dict) else {},
        "tool_result": tool_result if isinstance(tool_result, dict) else {},
    }
    for key in ("used_action_hint_group", "used_action_hint_source", "used_action_hint_target"):
        value = str(_value(key, "") or "").strip()
        if value:
            observed[key] = value
    return observed


def _context_outcome_enrich_observed_from_trace(
    observed: dict[str, Any],
    trace_payload: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(observed)
    first_tool_call = enriched.get("first_tool_call") if isinstance(enriched.get("first_tool_call"), dict) else {}
    meta_probe_match = _context_meta_probe_match(first_tool_call) if first_tool_call else {}
    if meta_probe_match.get("matched"):
        enriched["first_action_kind"] = "meta_probe"
        enriched["alignment_skipped"] = meta_probe_match
        if not enriched.get("wrong_target_explicit"):
            enriched["wrong_target"] = False
        return enriched
    alignments = _context_tool_hint_alignments(first_tool_call=first_tool_call, trace_payload=trace_payload) if first_tool_call else []
    query_reference_match = (
        _context_query_reference_match(first_tool_call=first_tool_call, trace_payload=trace_payload)
        if first_tool_call
        else {"schema_version": "mem1-context-query-reference-match-v0", "matched": False}
    )
    if query_reference_match.get("matched"):
        enriched["query_reference_match"] = query_reference_match
    if alignments:
        matched_alignment = next((alignment for alignment in alignments if alignment.get("aligned")), alignments[0])
        first_hint = matched_alignment.get("hint") if isinstance(matched_alignment.get("hint"), dict) else {}
        stored_alignment = {key: value for key, value in matched_alignment.items() if key != "hint"}
        enriched["first_tool_hint"] = first_hint
        enriched["first_tool_hint_alignment"] = stored_alignment
        enriched["first_tool_hint_candidate_count"] = len(alignments)
        hint_group = str(
            first_hint.get("hint_group")
            or matched_alignment.get("hint_group")
            or ("primary" if int(matched_alignment.get("hint_index") or 0) == 0 else "fallback")
        ).strip()
        hint_source = str(first_hint.get("source") or matched_alignment.get("hint_source") or "").strip()
        hint_target = str(first_hint.get("target") or matched_alignment.get("hint_target") or "").strip()
        enriched["first_tool_hint_group"] = hint_group
        enriched["first_tool_hint_source"] = hint_source
        enriched["first_tool_hint_target"] = hint_target
        enriched["first_tool_hint_index"] = int(matched_alignment.get("hint_index") or 0)
        if stored_alignment.get("aligned"):
            enriched["used_action_hint_group"] = hint_group
            enriched["used_action_hint_source"] = hint_source
            enriched["used_action_hint_target"] = hint_target
            enriched["used_action_hint_index"] = int(matched_alignment.get("hint_index") or 0)
        if (
            not stored_alignment.get("aligned")
            and not enriched.get("wrong_target")
            and not enriched.get("wrong_target_explicit")
            and not query_reference_match.get("matched")
        ):
            enriched["wrong_target"] = True
    repeated_match = _context_repeated_next_action_match(trace_payload, enriched)
    if repeated_match:
        enriched["repeated_work_match"] = repeated_match
        if not enriched.get("repeated_work"):
            enriched["repeated_work"] = True
    return enriched


def _context_outcome_inference_confidence(value: Any, default: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return round(min(max(confidence, 0.0), 1.0), 4)


def _context_outcome_inferred(payload: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    inferred_payload = payload.get("inferred") if isinstance(payload.get("inferred"), dict) else {}
    explicit_stage = str(
        inferred_payload.get("failure_stage") or payload.get("failure_stage") or payload.get("failure_type") or ""
    ).strip().lower()
    explicit_confidence = inferred_payload.get("confidence", payload.get("inference_confidence"))
    if explicit_stage in CONTEXT_UTILITY_FAILURE_STAGES:
        default_confidence = 0.95 if payload.get("failure_stage") or inferred_payload.get("failure_stage") else 0.8
        return {
            "schema_version": CONTEXT_OUTCOME_INFERRED_SCHEMA_VERSION,
            "failure_stage": explicit_stage,
            "confidence": _context_outcome_inference_confidence(explicit_confidence, default_confidence),
            "source": str(inferred_payload.get("source") or "explicit_label"),
            "reason": str(inferred_payload.get("reason") or "failure_stage provided by caller"),
        }

    if observed.get("first_action_productive") and not observed.get("user_correction_required"):
        stage = "none"
        confidence = 0.85
        reason = "first action was productive and no user correction was required"
    elif observed.get("first_action_kind") == "meta_probe":
        stage = "unknown"
        confidence = 0.4
        reason = "first action was a context, memory, goal, or evaluation probe excluded from utility alignment"
    elif observed.get("wrong_target"):
        stage = "reasoning_failure"
        confidence = 0.68
        alignment = observed.get("first_tool_hint_alignment") if isinstance(observed.get("first_tool_hint_alignment"), dict) else {}
        reason = str(alignment.get("reason") or "first tool call targeted the wrong surface")
    elif observed.get("repeated_work"):
        stage = "reasoning_failure"
        confidence = 0.62
        reason = "first action repeated work already marked complete in the context capsule"
    elif observed.get("harmful_memory_ids"):
        stage = "packing_failure"
        confidence = 0.75
        reason = "caller marked selected context as harmful"
    elif observed.get("missing_memory_ids"):
        stage = "unknown"
        confidence = 0.35
        reason = "caller marked missing memories but stage cannot be isolated automatically"
    elif not observed.get("first_action_productive"):
        stage = "reasoning_failure"
        confidence = 0.5
        reason = "first action was not productive; context may still have been sufficient"
    else:
        stage = "unknown"
        confidence = 0.25
        reason = "insufficient observed outcome fields"
    return {
        "schema_version": CONTEXT_OUTCOME_INFERRED_SCHEMA_VERSION,
        "failure_stage": stage,
        "confidence": _context_outcome_inference_confidence(explicit_confidence, confidence),
        "source": str(inferred_payload.get("source") or "system_inference"),
        "reason": str(inferred_payload.get("reason") or reason),
    }


def _context_observation_observed(payload: dict[str, Any]) -> dict[str, Any]:
    observed_payload = payload.get("observed") if isinstance(payload.get("observed"), dict) else {}

    def _value(key: str, default: Any = None) -> Any:
        if key in observed_payload:
            return observed_payload.get(key)
        return payload.get(key, default)

    first_tool_call = _value("first_tool_call", {})
    tool_result = _value("tool_result", {})
    observed: dict[str, Any] = {
        "schema_version": CONTEXT_OUTCOME_OBSERVED_SCHEMA_VERSION,
        "used_memory_ids": _context_outcome_list(_value("used_memory_ids")),
        "missing_memory_ids": _context_outcome_list(_value("missing_memory_ids")),
        "harmful_memory_ids": _context_outcome_list(_value("harmful_memory_ids")),
        "first_action": str(_value("first_action", "") or ""),
        "repeated_work": _bool_or(_value("repeated_work"), False),
        "wrong_target": _bool_or(_value("wrong_target"), False),
        "wrong_target_explicit": _context_outcome_has_observed_field(payload, "wrong_target"),
        "first_tool_call": first_tool_call if isinstance(first_tool_call, dict) else {},
        "tool_result": tool_result if isinstance(tool_result, dict) else {},
    }
    if "first_action_productive" in observed_payload or "first_action_productive" in payload:
        observed["first_action_productive"] = _bool_or(_value("first_action_productive"), False)
    if "user_correction_required" in observed_payload or "user_correction_required" in payload:
        observed["user_correction_required"] = _bool_or(_value("user_correction_required"), False)
    if "user_correction_signal" in observed_payload or "user_correction_signal" in payload:
        observed["user_correction_signal"] = _bool_or(_value("user_correction_signal"), False)
    surface_values = _context_outcome_surface_list(_value("used_context_surfaces"))
    if _bool_or(_value("used_current_workspace"), False) and "current_workspace" not in surface_values:
        surface_values.append("current_workspace")
    if surface_values:
        observed["used_context_surfaces"] = surface_values
        observed["used_current_workspace"] = "current_workspace" in surface_values
    for key in ("used_action_hint_group", "used_action_hint_source", "used_action_hint_target"):
        value = str(_value(key, "") or "").strip()
        if value:
            observed[key] = value
    return observed


def record_context_observation(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    trace_id = str(payload.get("trace_id") or "").strip()
    if not trace_id:
        raise HTTPException(status_code=400, detail="trace_id is required")
    project_id = payload.get("project_id") or project_id or current_project_id()
    with get_db() as conn:
        trace_row = conn.execute(
            "SELECT * FROM context_traces WHERE project_id = ? AND trace_id = ?",
            (project_id, trace_id),
        ).fetchone()
    if not trace_row:
        raise HTTPException(status_code=404, detail="Context trace not found")

    trace_payload = json_loads(trace_row["payload"], {})
    if isinstance(trace_payload, dict):
        trace_payload = dict(trace_payload)
        trace_payload.setdefault("trace_query", trace_row["query"])
    observed = _context_outcome_enrich_observed_from_trace(
        _context_observation_observed(payload),
        trace_payload if isinstance(trace_payload, dict) else {},
    )
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata = dict(metadata)
    metadata["observed"] = observed
    observation_id = str(new_id())
    now = utc_now()
    task_id = str(payload.get("task_id") or trace_row["task_id"] or "")
    source = str(payload.get("source") or metadata.get("source") or "runtime_observation")
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO context_observations (
                observation_id, project_id, trace_id, task_id, source,
                observed, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                project_id,
                trace_id,
                task_id,
                source,
                json_dumps(observed),
                json_dumps(metadata),
                now,
            ),
        )
    result = {
        "schema_version": CONTEXT_OBSERVATION_SCHEMA_VERSION,
        "observation_id": observation_id,
        "project_id": project_id,
        "trace_id": trace_id,
        "task_id": task_id,
        "source": source,
        "observed": observed,
        "created_at": now,
    }
    record_usage(
        project_id,
        "context_observation_record",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate(result),
        metadata={
            "trace_id": trace_id,
            "task_id": task_id,
            "source": source,
            "wrong_target": bool(observed.get("wrong_target")),
            "repeated_work": bool(observed.get("repeated_work")),
        },
    )
    return result


def _context_outcome_surface_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items: list[Any] = [value]
    elif isinstance(value, list):
        raw_items = value
    else:
        return []
    surfaces: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        surfaces.append(text)
    return surfaces


def _context_memory_id_key(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("claim:"):
        return text[len("claim:") :]
    return text


def _context_memory_id_in(memory_id: str, candidates: list[str]) -> bool:
    key = _context_memory_id_key(memory_id)
    if not key:
        return False
    return any(key == _context_memory_id_key(candidate) for candidate in candidates)


def _context_outcome_memory_id_resolution(
    conn: Any,
    project_id: str,
    values: list[str],
) -> tuple[dict[str, str], set[str]]:
    """Resolve submitted result IDs to canonical memory or claim result IDs."""
    submitted = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
    if not submitted:
        return {}, set()

    memory_placeholders = ", ".join("?" for _ in submitted)
    memory_ids = {
        str(row["id"])
        for row in conn.execute(
            f"""
            SELECT id FROM memories
             WHERE project_id = ? AND deleted = 0 AND id IN ({memory_placeholders})
            """,
            (project_id, *submitted),
        )
    }
    claim_keys = list(dict.fromkeys(_context_memory_id_key(value) for value in submitted))
    claim_placeholders = ", ".join("?" for _ in claim_keys)
    claim_ids = {
        str(row["id"])
        for row in conn.execute(
            f"""
            SELECT id FROM claims
             WHERE project_id = ? AND id IN ({claim_placeholders})
            """,
            (project_id, *claim_keys),
        )
    }

    resolution: dict[str, str] = {}
    matched: set[str] = set()
    for value in submitted:
        if value in memory_ids:
            canonical = value
            matched.add(canonical)
        elif _context_memory_id_key(value) in claim_ids:
            canonical = f"claim:{_context_memory_id_key(value)}"
            matched.add(canonical)
        else:
            canonical = value
        resolution[value] = canonical
    return resolution, matched


def _context_outcome_resolved_list(values: list[str], resolution: dict[str, str]) -> list[str]:
    resolved: list[str] = []
    for value in values:
        submitted = str(value).strip()
        canonical = resolution.get(submitted, submitted)
        if canonical and canonical not in resolved:
            resolved.append(canonical)
    return resolved


def _context_outcome_used_current_workspace_from_memory_ids(
    observed: dict[str, Any],
    trace_payload: dict[str, Any],
) -> bool:
    current_workspace_claim_id = _context_trace_current_workspace_claim_id(trace_payload)
    current_workspace_key = _context_memory_id_key(current_workspace_claim_id)
    if not current_workspace_key:
        return False
    return any(
        _context_memory_id_key(memory_id) == current_workspace_key
        for memory_id in _context_outcome_list(observed.get("used_memory_ids"))
    )


def _context_outcome_used_context_surfaces(
    *,
    payload: dict[str, Any],
    observed: dict[str, Any],
    metadata: dict[str, Any],
    trace_payload: dict[str, Any],
) -> list[str]:
    surfaces: list[str] = []
    seen: set[str] = set()

    def add_many(value: Any) -> None:
        for surface in _context_outcome_surface_list(value):
            if surface in seen:
                continue
            seen.add(surface)
            surfaces.append(surface)

    observed_payload = payload.get("observed") if isinstance(payload.get("observed"), dict) else {}
    add_many(metadata.get("used_context_surfaces"))
    add_many(payload.get("used_context_surfaces"))
    add_many(observed_payload.get("used_context_surfaces"))
    add_many(observed.get("used_context_surfaces"))
    used_current_workspace = (
        _bool_or(metadata.get("used_current_workspace"), False)
        or _bool_or(payload.get("used_current_workspace"), False)
        or _bool_or(observed_payload.get("used_current_workspace"), False)
        or _bool_or(observed.get("used_current_workspace"), False)
        or _context_outcome_used_current_workspace_from_memory_ids(observed, trace_payload)
    )
    if used_current_workspace and "current_workspace" not in seen:
        seen.add("current_workspace")
        surfaces.append("current_workspace")
    return surfaces


def _context_trace_current_workspace_claim_id(trace_payload: dict[str, Any]) -> str:
    resume_workspace = trace_payload.get("resume_workspace") if isinstance(trace_payload, dict) else {}
    current = resume_workspace.get("current") if isinstance(resume_workspace, dict) else {}
    claim_id = current.get("claim_id") if isinstance(current, dict) else ""
    if claim_id:
        return str(claim_id)
    working_memory = trace_payload.get("working_memory") if isinstance(trace_payload, dict) else {}
    roles = working_memory.get("roles") if isinstance(working_memory, dict) else {}
    current_workspace = roles.get("current_workspace") if isinstance(roles, dict) else {}
    claim_id = current_workspace.get("claim_id") if isinstance(current_workspace, dict) else ""
    return str(claim_id or "")


def _context_trace_current_workspace_available(trace_payload: dict[str, Any]) -> bool:
    if _context_trace_current_workspace_claim_id(trace_payload):
        return True
    resume_workspace = trace_payload.get("resume_workspace") if isinstance(trace_payload, dict) else {}
    if isinstance(resume_workspace, dict) and isinstance(resume_workspace.get("current"), dict):
        return True
    working_memory = trace_payload.get("working_memory") if isinstance(trace_payload, dict) else {}
    roles = working_memory.get("roles") if isinstance(working_memory, dict) else {}
    current_workspace = roles.get("current_workspace") if isinstance(roles, dict) else {}
    if isinstance(current_workspace, dict) and int(current_workspace.get("selected_count") or 0) > 0:
        return True
    fallback = trace_payload.get("fallback_cascade") if isinstance(trace_payload, dict) else {}
    return (
        isinstance(fallback, dict)
        and "current_workspace" in [str(stage) for stage in fallback.get("used_stages") or []]
    )


def _a1_outcome_half_life_days() -> float:
    return max(0.1, _float_or(os.getenv("MEM1_OUTCOME_HALF_LIFE_DAYS"), 7.0))


def _a1_outcome_events(conn: Any, project_id: str, memory_ids: set[str]) -> dict[str, list[tuple[Any, int]]]:
    """Chronological ±1 outcome event streams per memory, read from the raw
    recorded observations rather than the collapsed latest label."""
    if not memory_ids:
        return {}
    rows = conn.execute(
        """
        SELECT created_at, used_memory_ids, harmful_memory_ids, first_action_productive
          FROM context_outcomes
         WHERE project_id = ?
         ORDER BY created_at DESC
         LIMIT 500
        """,
        (project_id,),
    ).fetchall()
    streams: dict[str, list[tuple[Any, int]]] = {memory_id: [] for memory_id in memory_ids}
    for row in reversed(rows):
        stamp = parse_datetime(row["created_at"])
        if stamp is None:
            continue
        harmful = {str(memory_id) for memory_id in json_loads(row["harmful_memory_ids"], [])}
        used = {str(memory_id) for memory_id in json_loads(row["used_memory_ids"], [])}
        for memory_id in memory_ids:
            if memory_id in harmful:
                streams[memory_id].append((stamp, -1))
            elif memory_id in used and bool(row["first_action_productive"]):
                streams[memory_id].append((stamp, 1))
    return streams


def _a1_outcome_value(events: list[tuple[Any, int]], now: Any) -> dict[str, Any]:
    """A1 aggregate: half-life-weighted mean of the ±1 outcome stream — except
    when the newest events flip sign (a step change in the memory's utility),
    where only the newest same-sign run counts. Yesterday's praise must not
    dilute today's contradiction, and vice versa; no extra parameters.
    """
    half_life = _a1_outcome_half_life_days()
    if not events or now is None:
        return {"value": 0.0, "adjust": 0.0, "events": 0, "changepoint": False, "half_life_days": half_life}
    window = events[-3:]
    changepoint = len(window) >= 2 and window[-1][1] != window[-2][1]
    effective = events
    if changepoint:
        start = len(events) - 1
        while start > 0 and events[start - 1][1] == events[-1][1]:
            start -= 1
        effective = events[start:]
    numerator = denominator = 0.0
    for stamp, sign in effective:
        age_days = max(0.0, (now - stamp).total_seconds() / 86400.0)
        weight = 0.5 ** (age_days / half_life)
        numerator += weight * sign
        denominator += weight
    value = numerator / denominator if denominator else 0.0
    adjust = value * (0.05 if value >= 0 else 0.15)
    return {
        "value": round(value, 4),
        "adjust": round(adjust, 4),
        "events": len(events),
        "changepoint": changepoint,
        "half_life_days": half_life,
    }


def _close_outcome_feedback_loop(
    conn: Any,
    project_id: str,
    used_memory_ids: list[str],
    harmful_memory_ids: list[str],
    first_action_productive: bool,
    now: str,
) -> None:
    """Turn a recorded context outcome into ranking feedback.

    This is the link that makes the "verified memory" loop actually close:
    a memory flagged harmful when the agent used the assembled context gets a
    NEGATIVE signal that lowers it in future searches; a memory used
    productively gets a POSITIVE one. The magnitude comes from the A1 aggregate
    over the memory's full outcome stream (half-life weighting + changepoint),
    which reduces to the flat ±0.05/−0.15 when there is a single label.
    Explicit human feedback is never overwritten — only prior outcome-derived
    rows are replaced.
    """
    harmful = {str(memory_id) for memory_id in harmful_memory_ids if memory_id}
    productive = {
        str(memory_id) for memory_id in used_memory_ids if memory_id and first_action_productive
    } - harmful
    labeled = harmful | productive
    if not labeled:
        return
    now_stamp = parse_datetime(now)
    streams = _a1_outcome_events(conn, project_id, labeled)

    def _upsert(memory_id: str, feedback: str, reason: str, extra: dict[str, Any]) -> None:
        row = conn.execute("SELECT metadata FROM feedback WHERE memory_id = ?", (memory_id,)).fetchone()
        if row is not None:
            meta = json_loads(row["metadata"], {})
            if not isinstance(meta, dict) or meta.get("source") != "context_outcome":
                return  # respect explicit user feedback; do not clobber it
        conn.execute("DELETE FROM feedback WHERE memory_id = ?", (memory_id,))
        _entity_prune_stats_cache.clear()
        conn.execute(
            """
            INSERT INTO feedback (id, memory_id, feedback, feedback_reason, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(new_id()), memory_id, feedback, reason, json_dumps({"source": "context_outcome", **extra}), now),
        )

    for memory_id in labeled:
        a1 = _a1_outcome_value(streams.get(memory_id) or [], now_stamp)
        if a1["events"] == 0:
            # the just-inserted outcome must be visible on this connection; keep a
            # single-label fallback so a stream read miss never drops the signal
            sign = -1 if memory_id in harmful else 1
            a1 = {
                "value": float(sign),
                "adjust": -0.15 if sign < 0 else 0.05,
                "events": 1,
                "changepoint": False,
                "half_life_days": _a1_outcome_half_life_days(),
            }
        reason = (
            "flagged harmful in a context outcome"
            if memory_id in harmful
            else "used productively in a context outcome"
        )
        _upsert(memory_id, "NEGATIVE" if a1["value"] < 0 else "POSITIVE", reason, {"a1": a1})


def record_context_outcome(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    trace_id = str(payload.get("trace_id") or "").strip()
    if not trace_id:
        raise HTTPException(status_code=400, detail="trace_id is required")
    project_id = payload.get("project_id") or project_id or current_project_id()
    with get_db() as conn:
        trace_row = conn.execute(
            "SELECT * FROM context_traces WHERE project_id = ? AND trace_id = ?",
            (project_id, trace_id),
        ).fetchone()
    if not trace_row:
        raise HTTPException(status_code=404, detail="Context trace not found")

    outcome_id = str(new_id())
    now = utc_now()
    trace_payload = json_loads(trace_row["payload"], {})
    if isinstance(trace_payload, dict):
        trace_payload = dict(trace_payload)
        trace_payload.setdefault("trace_query", trace_row["query"])
    observed = _context_outcome_enrich_observed_from_trace(
        _context_outcome_observed(payload),
        trace_payload if isinstance(trace_payload, dict) else {},
    )
    inferred = _context_outcome_inferred(payload, observed)
    first_action_productive = bool(observed["first_action_productive"])
    user_correction_required = bool(observed["user_correction_required"])
    failure_stage = str(inferred["failure_stage"])
    task_id = str(payload.get("task_id") or trace_row["task_id"] or "")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata = dict(metadata)
    used_context_surfaces = _context_outcome_used_context_surfaces(
        payload=payload,
        observed=observed,
        metadata=metadata,
        trace_payload=trace_payload if isinstance(trace_payload, dict) else {},
    )
    if used_context_surfaces:
        observed["used_context_surfaces"] = used_context_surfaces
        observed["used_current_workspace"] = "current_workspace" in used_context_surfaces
        metadata["used_context_surfaces"] = used_context_surfaces
    with get_db() as conn:
        submitted_memory_ids = [
            str(memory_id)
            for memory_id in dict.fromkeys(
                [
                    *observed["used_memory_ids"],
                    *observed["harmful_memory_ids"],
                    *observed["missing_memory_ids"],
                ]
            )
            if memory_id
        ]
        memory_id_resolution, matched_memory_ids = _context_outcome_memory_id_resolution(
            conn,
            project_id,
            submitted_memory_ids,
        )
        used_memory_ids = _context_outcome_resolved_list(
            observed["used_memory_ids"],
            memory_id_resolution,
        )
        missing_memory_ids = _context_outcome_resolved_list(
            observed["missing_memory_ids"],
            memory_id_resolution,
        )
        harmful_memory_ids = _context_outcome_resolved_list(
            observed["harmful_memory_ids"],
            memory_id_resolution,
        )
        observed["used_memory_ids"] = used_memory_ids
        observed["missing_memory_ids"] = missing_memory_ids
        observed["harmful_memory_ids"] = harmful_memory_ids
        metadata["observed"] = observed
        metadata["inferred"] = inferred
        labeled_memory_ids = [
            str(memory_id)
            for memory_id in dict.fromkeys([*used_memory_ids, *harmful_memory_ids, *missing_memory_ids])
            if memory_id
        ]
        conn.execute(
            """
            INSERT INTO context_outcomes (
                outcome_id, project_id, trace_id, task_id, used_memory_ids,
                missing_memory_ids, harmful_memory_ids, first_action_productive,
                user_correction_required, failure_stage, first_action, notes,
                metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome_id,
                project_id,
                trace_id,
                task_id,
                json_dumps(used_memory_ids),
                json_dumps(missing_memory_ids),
                json_dumps(harmful_memory_ids),
                1 if first_action_productive else 0,
                1 if user_correction_required else 0,
                failure_stage,
                observed["first_action"],
                str(payload.get("notes") or ""),
                json_dumps(metadata),
                now,
            ),
        )
        _close_outcome_feedback_loop(
            conn,
            project_id,
            [memory_id for memory_id in used_memory_ids if memory_id in matched_memory_ids],
            [memory_id for memory_id in harmful_memory_ids if memory_id in matched_memory_ids],
            first_action_productive,
            now,
        )
    unmatched_memory_ids = [
        memory_id for memory_id in labeled_memory_ids if memory_id not in matched_memory_ids
    ]
    outcome_warnings: list[str] = []
    if unmatched_memory_ids:
        outcome_warnings.append(
            "unmatched_memory_ids not found in this project (typo or deleted id) — "
            "their labels were excluded from ranking feedback"
        )
    if (
        used_memory_ids
        and not first_action_productive
        and not _context_outcome_has_observed_field(payload, "first_action_productive")
    ):
        outcome_warnings.append(
            "used_memory_ids feed ranking feedback only when first_action_productive is true — "
            "pass first_action_productive explicitly when the action succeeded"
        )
    selected_ids = json_loads(trace_row["selected_ids"], [])
    used_selected_ids = [memory_id for memory_id in used_memory_ids if _context_memory_id_in(memory_id, selected_ids)]
    fallback_memory_ids = _context_fallback_memory_ids_from_trace(trace_payload if isinstance(trace_payload, dict) else {})
    used_fallback_ids = [
        memory_id for memory_id in used_memory_ids if _context_memory_id_in(memory_id, fallback_memory_ids)
    ]
    current_workspace_available = _context_trace_current_workspace_available(
        trace_payload if isinstance(trace_payload, dict) else {}
    )
    used_current_workspace = "current_workspace" in used_context_surfaces
    used_action_hint_group = str(observed.get("used_action_hint_group") or "")
    used_action_hint_source = str(observed.get("used_action_hint_source") or "")
    used_action_hint_target = str(observed.get("used_action_hint_target") or "")
    result = {
        "schema_version": CONTEXT_OUTCOME_SCHEMA_VERSION,
        "outcome_id": outcome_id,
        "project_id": project_id,
        "trace_id": trace_id,
        "task_id": task_id,
        "used_memory_ids": used_memory_ids,
        "missing_memory_ids": missing_memory_ids,
        "harmful_memory_ids": harmful_memory_ids,
        "first_action_productive": first_action_productive,
        "user_correction_required": user_correction_required,
        "failure_stage": failure_stage,
        "observed": observed,
        "inferred": inferred,
        "inference_confidence": inferred["confidence"],
        "used_selected_memory_ids": used_selected_ids,
        "selected_memory_count": len(selected_ids),
        "used_selected_ratio": round(len(used_selected_ids) / max(len(selected_ids), 1), 4),
        "fallback_memory_ids": fallback_memory_ids,
        "used_fallback_memory_ids": used_fallback_ids,
        "fallback_memory_count": len(fallback_memory_ids),
        "used_fallback_ratio": round(len(used_fallback_ids) / max(len(fallback_memory_ids), 1), 4),
        "used_context_surfaces": used_context_surfaces,
        "current_workspace_available": current_workspace_available,
        "current_workspace_claim_id": _context_trace_current_workspace_claim_id(
            trace_payload if isinstance(trace_payload, dict) else {}
        ),
        "used_current_workspace": used_current_workspace,
        "current_workspace_used_ratio": 1.0 if current_workspace_available and used_current_workspace else 0.0,
        "used_action_hint_group": used_action_hint_group,
        "used_action_hint_source": used_action_hint_source,
        "used_action_hint_target": used_action_hint_target,
        "unmatched_memory_ids": unmatched_memory_ids,
        "warnings": outcome_warnings,
        "created_at": now,
    }
    record_usage(
        project_id,
        "context_outcome_record",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate(result),
        metadata={
            "trace_id": trace_id,
            "task_id": task_id,
            "failure_stage": failure_stage,
            "first_action_productive": first_action_productive,
        },
    )
    return result


def assemble_context(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    project_id = payload.get("project_id") or project_id or current_project_id()
    budget_tokens = min(max(int(payload.get("budget_tokens") or payload.get("budget") or 800), 1), 8000)
    working_memory_slots = min(
        max(_int_or(payload.get("working_memory_slots", payload.get("slot_capacity", payload.get("slots", 7))), 7), 1),
        32,
    )
    search_payload = {
        "query": payload.get("query"),
        "filters": payload.get("filters") or {},
        "top_k": payload.get("top_k", payload.get("limit", 10)),
        "threshold": payload.get("threshold", 0.1),
        "rerank": payload.get("rerank", False),
        "reference_date": payload.get("reference_date"),
    }
    if payload.get("scope_fallback") is not None:
        search_payload["scope_fallback"] = payload.get("scope_fallback")
    replay_memory_as_of = str(
        payload.get("memory_as_of")
        or payload.get("memoryAsOf")
        or payload.get("resume_workspace_as_of")
        or payload.get("resumeWorkspaceAsOf")
        or payload.get("workspace_as_of")
        or payload.get("workspaceAsOf")
        or payload.get("as_of")
        or payload.get("asOf")
        or ""
    ).strip()
    if replay_memory_as_of:
        search_payload["memory_as_of"] = replay_memory_as_of
    resume_workspace_disabled = _bool_or(
        payload.get("disable_resume_workspace", payload.get("disableResumeWorkspace")),
        False,
    )
    if resume_workspace_disabled:
        resume_workspace = {
            "schema_version": "mem1-resume-workspace-v0",
            "status": "disabled",
            "state_source": "disabled_by_payload",
            "current": None,
        }
    else:
        resume_workspace = _resume_workspace_for_context(payload, project_id)
    workspace_current = resume_workspace.get("current") if isinstance(resume_workspace, dict) else None
    if (
        not isinstance(workspace_current, dict)
        or str(workspace_current.get("task_id") or "").startswith(GOAL_TASK_PREFIX)
        or str(workspace_current.get("task_id") or "").startswith(STANCE_TASK_PREFIX)
    ):
        # Goals are the why-layer, not work items: a goal must never hijack
        # the capsule's "current task". Fall back to the newest active
        # non-goal task so the capsule keeps pointing at real work.
        workspace_current = None
        try:
            fallback_scope = _capsule_scope_filters(payload)
            listing = get_task_state({"limit": 12}, project_id=project_id)
            for item in listing.get("results") or []:
                if fallback_scope and not _task_claim_scope_matches_filters(
                    item.get("scope") if isinstance(item.get("scope"), dict) else {}, fallback_scope
                ):
                    continue
                task_id = str(item.get("task_id") or "")
                status = str(item.get("status") or "").lower()
                if (
                    task_id
                    and not task_id.startswith(GOAL_TASK_PREFIX)
                    and not task_id.startswith(STANCE_TASK_PREFIX)
                    and status in ("in_progress", "active", "running", "blocked", "pending")
                ):
                    workspace_current = {"task_id": task_id, "status": item.get("status"),
                                         "summary": item.get("summary"),
                                         "created_at": item.get("created_at"),
                                         "next_actions": item.get("next_actions") or [],
                                         "blockers": item.get("blockers") or []}
                    break
        except Exception:
            workspace_current = None
    workspace_line = _workspace_context_line(workspace_current) if isinstance(workspace_current, dict) else ""
    workspace_tokens = min(token_estimate(workspace_line), budget_tokens) if workspace_line else 0
    search = search_memories(search_payload, project_id=project_id)
    search_candidates = search["results"]
    current_candidates = [memory for memory in search_candidates if not _context_memory_is_superseded(memory)]
    requested_task_id = _context_requested_task_id(payload)
    requested_related_task_ids = _context_requested_related_task_ids(payload, workspace_current)
    requested_task_scope_ids = _context_requested_task_scope_ids(requested_task_id, requested_related_task_ids)
    task_scoped_candidates = [
        memory
        for memory in current_candidates
        if _context_matches_requested_task(memory, requested_task_id, requested_task_scope_ids)
    ]
    task_scope_filtered_memory_ids = [
        str(memory.get("id"))
        for memory in current_candidates
        if memory.get("id")
        and not _context_matches_requested_task(memory, requested_task_id, requested_task_scope_ids)
    ]
    workspace_duplicate_memory_id = _context_workspace_duplicate_memory_id(workspace_current, requested_task_id)
    workspace_duplicate_filtered_memory_ids = [
        str(memory.get("id"))
        for memory in task_scoped_candidates
        if workspace_duplicate_memory_id and str(memory.get("id")) == workspace_duplicate_memory_id
    ]
    candidates = [
        memory
        for memory in task_scoped_candidates
        if not workspace_duplicate_memory_id or str(memory.get("id")) != workspace_duplicate_memory_id
    ]
    existing_memory_ids = {str(memory.get("id")) for memory in search_candidates if memory.get("id")}
    role_backfill: dict[str, Any] = {
        "applied": False,
        "reason": "not_needed",
        "selector_policy_version": _CONTEXT_SELECTOR_POLICY_VERSION,
        "score_floors": dict(_CONTEXT_SELECTOR_ROLE_SCORE_FLOORS),
        "tradeoff_gap_tolerance": _CONTEXT_SELECTOR_TRADEOFF_GAP_TOLERANCE,
        "soft_quotas": dict(_CONTEXT_SELECTOR_SOFT_ROLE_QUOTAS),
        "soft_quota_score_floors": dict(_CONTEXT_SELECTOR_SOFT_QUOTA_SCORE_FLOORS),
        "soft_quota_applied_count": 0,
        "soft_quota_samples": [],
        "candidate_ids": [],
        "candidate_snapshots": [],
        "eligible_memory_ids": [],
        "admissible_memory_ids": [],
        "raw_candidate_count": 0,
        "eligible_count": 0,
        "admissible_count": 0,
        "selected_count": 0,
        "memory_ids": [],
        "selected_role_counts": {role: 0 for role in _WORKING_MEMORY_ROLE_ORDER if role != "current_workspace"},
        "diversity_first_pass": False,
        "diversity_tradeoff_count": 0,
        "diversity_tradeoff_max_score_gap": 0.0,
        "diversity_tradeoff_samples": [],
        "rejected_count": 0,
        "rejection_counts": {"score_floor": 0, "tradeoff_gap": 0},
        "rejected_samples": [],
        "filters": {},
    }
    if requested_task_id and not candidates and search_candidates:
        backfill_candidates, role_backfill = _context_role_backfill_candidates(
            search_payload=search_payload,
            project_id=project_id,
            requested_task_id=requested_task_id,
            requested_task_scope_ids=requested_task_scope_ids,
            existing_memory_ids=existing_memory_ids,
            workspace_duplicate_memory_id=workspace_duplicate_memory_id,
            max_backfill=min(max(working_memory_slots, 1), 3),
        )
        candidates.extend(backfill_candidates)
    budgeted: list[dict[str, Any]] = []
    budgeted_lines: list[str] = []
    budgeted_tokens = workspace_tokens
    for memory in candidates:
        text = str(memory.get("memory", "")).strip()
        if not text:
            continue
        cost = token_estimate(text)
        if budgeted_tokens and budgeted_tokens + cost > budget_tokens:
            break
        if cost > budget_tokens:
            words = text.split()
            text = " ".join(words[:budget_tokens])
            cost = token_estimate(text)
        budgeted_tokens += cost
        item = dict(memory)
        item["reason"] = _context_reason(item)
        item["context_tokens"] = cost
        budgeted.append(item)
        budgeted_lines.append(f"- {text}")
    selected = _select_working_memory_slots(budgeted, working_memory_slots, str(search_payload["query"] or ""))
    budgeted_line_by_id = {str(memory.get("id")): line for memory, line in zip(budgeted, budgeted_lines) if memory.get("id")}
    lines = [
        budgeted_line_by_id.get(str(memory.get("id")), f"- {str(memory.get('memory') or '').strip()}")
        for memory in selected
    ]
    used_tokens = sum(int(item.get("context_tokens") or 0) for item in selected)
    selected_ids = {item.get("id") for item in selected}
    omitted_memory_ids = [memory["id"] for memory in candidates if memory.get("id") not in selected_ids]
    context_lines = [workspace_line] if workspace_line else []
    context_lines.extend(lines)
    result = {
        "project_id": project_id,
        "query": search_payload["query"],
        "filters": search_payload["filters"],
        "budget_tokens": budget_tokens,
        "used_tokens": used_tokens + workspace_tokens,
        "total_candidates": len(candidates),
        "raw_candidate_count": len(search_candidates),
        "task_scope_filtered_count": len(task_scope_filtered_memory_ids),
        "task_scope_filtered_memory_ids": task_scope_filtered_memory_ids,
        "workspace_duplicate_filtered_count": len(workspace_duplicate_filtered_memory_ids),
        "workspace_duplicate_filtered_memory_ids": workspace_duplicate_filtered_memory_ids,
        "selected_count": len(selected),
        "budgeted_count": len(budgeted),
        "budgeted_tokens": budgeted_tokens,
        "omitted_count": len(omitted_memory_ids),
        "omitted_memory_ids": omitted_memory_ids,
        "memories": selected,
        "resume_workspace": resume_workspace,
        "query_evidence": {
            "search": {
                "total_candidates": len(candidates),
                "raw_candidate_count": len(search_candidates),
                "selected_count": len(selected),
                "omitted_count": len(omitted_memory_ids),
                "task_scope_filtered_count": len(task_scope_filtered_memory_ids),
                "workspace_duplicate_filtered_count": len(workspace_duplicate_filtered_memory_ids),
                "role_aware_backfill_count": int(role_backfill.get("selected_count") or 0),
                "role_aware_backfill_memory_ids": list(role_backfill.get("memory_ids") or []),
                "role_aware_backfill_role_counts": role_backfill.get("selected_role_counts")
                if isinstance(role_backfill.get("selected_role_counts"), dict)
                else {},
                "role_aware_backfill_selector_policy_version": role_backfill.get("selector_policy_version")
                or _CONTEXT_SELECTOR_POLICY_VERSION,
                "role_aware_backfill_eligible_count": int(role_backfill.get("eligible_count") or 0),
                "role_aware_backfill_admissible_count": int(role_backfill.get("admissible_count") or 0),
                "role_aware_backfill_diversity_tradeoff_count": int(
                    role_backfill.get("diversity_tradeoff_count") or 0
                ),
                "role_aware_backfill_diversity_tradeoff_max_score_gap": round(
                    _float_or(role_backfill.get("diversity_tradeoff_max_score_gap"), 0.0),
                    4,
                ),
                "role_aware_backfill_rejected_count": int(role_backfill.get("rejected_count") or 0),
                "role_aware_backfill_rejection_counts": role_backfill.get("rejection_counts")
                if isinstance(role_backfill.get("rejection_counts"), dict)
                else {"score_floor": 0, "tradeoff_gap": 0},
                "role_aware_backfill_soft_quota_applied_count": int(
                    role_backfill.get("soft_quota_applied_count") or 0
                ),
            }
        },
        "context_hygiene": _context_hygiene_summary(
            raw_candidate_count=len(search_candidates),
            task_scoped_candidate_count=len(candidates),
            selected_count=len(selected),
            omitted_count=len(omitted_memory_ids),
            requested_task_id=requested_task_id,
            requested_related_task_ids=requested_related_task_ids,
            task_scope_filtered_memory_ids=task_scope_filtered_memory_ids,
            workspace_duplicate_filtered_memory_ids=workspace_duplicate_filtered_memory_ids,
            workspace_current=workspace_current if isinstance(workspace_current, dict) else None,
            selected_memories=selected,
            role_backfill=role_backfill,
        ),
        "working_memory": _working_memory_state(
            selected,
            candidates,
            budget_tokens,
            used_tokens,
            working_memory_slots,
            workspace_current if isinstance(workspace_current, dict) else None,
        ),
        "context": "\n".join(context_lines),
        "composer": {"external": False, "fallback": False, "provider": "local", "model": "deterministic-context-v1"},
    }
    if isinstance(workspace_current, dict):
        with get_db() as conn:
            context_access_decision_id = hybrid_workspace.record_context_access_decision(
                conn,
                project_id=project_id,
                workspace_current=workspace_current,
                decided_at=utc_now(),
                model_settings=get_project_settings(project_id),
            )
        result["context_access_decision_id"] = context_access_decision_id
    composer_settings = _context_composer_settings(payload, project_id)
    if composer_settings["url"] and selected:
        try:
            composed = _external_context_composer(payload, result, composer_settings)
            if composed:
                result = composed
        except Exception as exc:
            result["composer"] = {
                "external": True,
                "fallback": True,
                "provider": composer_settings.get("provider"),
                "model": composer_settings.get("model"),
                "url": composer_settings.get("url"),
                "error": str(exc),
            }
    materialized_at = utc_now()
    result = _attach_context_autopilot(
        result=result,
        payload=payload,
        raw_candidates=current_candidates,
        selected=selected,
        task_scope_filtered_memory_ids=task_scope_filtered_memory_ids,
        workspace_duplicate_filtered_memory_ids=workspace_duplicate_filtered_memory_ids,
        workspace_current=workspace_current if isinstance(workspace_current, dict) else None,
        role_backfill=role_backfill,
        compiled_at=materialized_at,
    )
    result["evidence"] = _context_evidence(result)
    if _bool_or(payload.get("verify_evidence", payload.get("verify")), False):
        result["verification"] = verify_context_evidence({"context_result": result}, project_id=project_id)
    trace_summary = _record_context_trace(
        project_id=project_id,
        payload=payload,
        search_payload=search_payload,
        raw_candidates=current_candidates,
        candidates=candidates,
        budgeted=budgeted,
        selected=selected,
        role_backfill=role_backfill,
        task_scope_filtered_memory_ids=task_scope_filtered_memory_ids,
        workspace_duplicate_filtered_memory_ids=workspace_duplicate_filtered_memory_ids,
        result=result,
        workspace_current=workspace_current if isinstance(workspace_current, dict) else None,
    )
    result["context_trace_id"] = trace_summary["trace_id"]
    result["context_trace"] = trace_summary
    result["evidence"]["context_trace_id"] = trace_summary["trace_id"]
    record_usage(
        project_id,
        "context_assemble",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate(result["context"]),
        metadata={
            "memory_count": len(selected),
            "budgeted_count": len(budgeted),
            "omitted_count": result["omitted_count"],
            "budget_tokens": budget_tokens,
        },
    )
    return result



SUMMARY_STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "but",
    "for",
    "from",
    "has",
    "have",
    "into",
    "just",
    "likes",
    "loves",
    "moved",
    "prefers",
    "the",
    "their",
    "this",
    "that",
    "user",
    "uses",
    "with",
    "works",
}


def summary_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "filters": json_loads(row["filters"], {}),
        "source_memory_ids": json_loads(row["source_memory_ids"], []),
        "summary": row["summary"],
        "drift": json_loads(row["drift"], {}),
        "metadata": json_loads(row["metadata"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _summary_key_terms(text: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_'-]{2,}", str(text or "")):
        value = token.strip("'_").lower()
        if not value or value in SUMMARY_STOPWORDS or value in seen:
            continue
        seen.add(value)
        terms.append(value)
    return terms[:12]


def _summary_group_key(memory: dict[str, Any]) -> tuple[Any, ...]:
    relation = _fact_relation(memory.get("memory", ""))
    if not relation:
        return ("memory", memory.get("id"))
    scope = tuple((field, memory.get(field)) for field in ENTITY_FIELDS)
    return ("relation", relation["subject"], relation["predicate"], scope)


def _summary_groups(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for memory in candidates:
        key = _summary_group_key(memory)
        group = by_key.get(key)
        if group is None:
            group = {"key": key, "memories": []}
            by_key[key] = group
            groups.append(group)
        group["memories"].append(memory)
    return groups


def _group_summary_text(memories: list[dict[str, Any]]) -> str:
    if not memories:
        return ""
    text = str(memories[0].get("memory") or "").strip()
    for memory in memories[1:]:
        text = _merge_fact(text, str(memory.get("memory") or ""))
    return text


def _build_summary(
    candidates: list[dict[str, Any]],
    budget_tokens: int,
) -> tuple[str, list[dict[str, Any]], int]:
    lines: list[str] = []
    included: list[dict[str, Any]] = []
    included_ids: set[str] = set()
    used_tokens = 0
    for group in _summary_groups(candidates):
        memories = group["memories"]
        text = _group_summary_text(memories)
        if not text:
            continue
        cost = token_estimate(text)
        if used_tokens and used_tokens + cost > budget_tokens:
            break
        if cost > budget_tokens:
            words = text.split()
            text = " ".join(words[:budget_tokens])
            cost = token_estimate(text)
        used_tokens += cost
        lines.append(f"- {text}")
        for memory in memories:
            memory_id = str(memory.get("id"))
            if memory_id and memory_id not in included_ids:
                included_ids.add(memory_id)
                included.append(memory)
    return "\n".join(lines), included, used_tokens


def _summary_drift(source_memories: list[dict[str, Any]], summary_text: str) -> dict[str, Any]:
    normalized_summary = summary_text.lower()
    covered_ids: list[str] = []
    missing_ids: list[str] = []
    missing_terms: dict[str, list[str]] = {}
    source_hashes: dict[str, str] = {}
    for memory in source_memories:
        memory_id = str(memory.get("id"))
        source_hashes[memory_id] = _compression_source_hash(memory)
        terms = _summary_key_terms(str(memory.get("memory") or ""))
        if not terms or any(term in normalized_summary for term in terms):
            covered_ids.append(memory_id)
            continue
        missing_ids.append(memory_id)
        missing_terms[memory_id] = terms
    source_count = len(source_memories)
    warnings = ["missing_source_terms"] if missing_ids else []
    return {
        "source_count": source_count,
        "covered_source_count": len(covered_ids),
        "coverage": round(len(covered_ids) / source_count, 4) if source_count else 1,
        "missing_source_ids": missing_ids,
        "missing_key_terms": missing_terms,
        "source_hashes": source_hashes,
        "warnings": warnings,
    }


def _summary_candidates(
    payload: dict[str, Any],
    filters: dict[str, Any],
    max_memories: int,
    project_id: str,
) -> list[dict[str, Any]]:
    query = str(payload.get("query") or "").strip()
    if query:
        top_k_raw = payload.get("top_k") if payload.get("top_k") is not None else payload.get("limit")
        top_k = _validated_search_top_k_value(top_k_raw, default=max_memories)
        threshold = 0 if payload.get("threshold") is None else _validated_search_threshold(payload, default=0)
        search = search_memories(
            {
                "query": query,
                "filters": filters,
                "top_k": top_k,
                "threshold": threshold,
                "rerank": payload.get("rerank", False),
                "reference_date": payload.get("reference_date"),
            },
            project_id=project_id,
        )
        return search["results"][:max_memories]
    return [
        strip_internal(memory)
        for memory in list_memory_dicts(project_id=project_id)
        if matches_filters(memory, filters)
    ][:max_memories]


def create_summary(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    project_id = payload.get("project_id") or project_id or current_project_id()
    filters = payload.get("filters") or {field: payload[field] for field in ENTITY_FIELDS if field in payload}
    validate_filters(filters)
    if not isinstance(filters, dict) or not has_entity_filter(filters):
        raise HTTPException(status_code=400, detail="filters must include at least one entity ID")
    budget_tokens = min(max(int(payload.get("budget_tokens") or payload.get("budget") or 800), 1), 8000)
    max_memories_raw = payload.get("max_memories")
    if max_memories_raw is not None:
        max_memories = _validated_bounded_int_value(max_memories_raw, "max_memories")
    else:
        max_memories_raw = payload.get("top_k") if payload.get("top_k") is not None else payload.get("limit")
        max_memories = _validated_search_top_k_value(max_memories_raw, default=50)
    summary_threshold = 0 if payload.get("threshold") is None else _validated_search_threshold(payload, default=0)
    candidates = _summary_candidates(payload, filters, max_memories, project_id)
    summary_text, source_memories, used_tokens = _build_summary(candidates, budget_tokens)
    selected_ids = {str(memory.get("id")) for memory in source_memories}
    drift = _summary_drift(source_memories, summary_text)
    drift.update(
        {
            "used_tokens": used_tokens,
            "budget_tokens": budget_tokens,
            "total_candidates": len(candidates),
            "selected_count": len(source_memories),
            "omitted_count": max(0, len(candidates) - len(source_memories)),
            "omitted_memory_ids": [memory["id"] for memory in candidates if str(memory.get("id")) not in selected_ids],
        }
    )
    metadata = {
        "query": str(payload.get("query") or ""),
        "top_k": payload.get("top_k") or payload.get("limit"),
        "threshold": summary_threshold,
        "rerank": bool(payload.get("rerank", False)),
        "user_metadata": payload.get("metadata") or {},
    }
    now = utc_now()
    summary_id = str(new_id("summary"))
    source_ids = [memory["id"] for memory in source_memories]
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO summaries (
                id, project_id, filters, source_memory_ids, summary, drift,
                metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary_id,
                project_id,
                json_dumps(filters),
                json_dumps(source_ids),
                summary_text,
                json_dumps(drift),
                json_dumps(metadata),
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM summaries WHERE id = ? AND project_id = ?", (summary_id, project_id)).fetchone()
    result = summary_row(row)
    result["source_memories"] = source_memories
    record_usage(
        project_id,
        "summary_create",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate(summary_text),
        metadata={"summary_id": summary_id, "source_count": len(source_memories), "coverage": drift["coverage"]},
    )
    return result


def list_summaries(project_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(limit, 1), 500)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM summaries
             WHERE project_id = ?
             ORDER BY created_at DESC
             LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
    return {"project_id": project_id, "count": len(rows), "results": [summary_row(row) for row in rows]}


def get_summary(summary_id: str, project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM summaries WHERE id = ? AND project_id = ?", (summary_id, project_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Summary not found")
    return summary_row(row)


def _context_reason(memory: dict[str, Any]) -> str:
    score = memory.get("score")
    categories = memory.get("categories") or []
    if categories and isinstance(score, (int, float)) and score >= 0.8:
        return "high_score_category_match"
    if isinstance(score, (int, float)) and score >= 0.8:
        return "high_score"
    if categories:
        return "category_match"
    return "ranked_search_match"


def get_memory(memory_id: str, project_id: str | None = None, include_expired: bool = False) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM memories WHERE id = ? AND project_id = ? AND deleted = 0",
            (memory_id, project_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Memory not found!")
    memory = row_to_memory(row)
    if not include_expired and memory_is_expired(memory):
        raise HTTPException(status_code=404, detail="Memory not found!")
    return strip_internal(memory)


def update_memory(memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    project_id = payload.get("project_id") or current_project_id()
    text = payload.get("text") or payload.get("memory") or payload.get("data")
    metadata = payload.get("metadata")
    expiration = payload.get("expiration_date") or payload.get("expires")
    if text is None and metadata is None and expiration is None:
        raise HTTPException(status_code=400, detail="text, metadata, or expiration_date is required")
    current = get_memory(memory_id, project_id=project_id)
    if isinstance(current.get("metadata"), dict) and current["metadata"].get("immutable") is True:
        raise HTTPException(status_code=409, detail="Memory is immutable and cannot be updated")
    new_text = str(text) if text is not None else current["memory"]
    new_metadata = dict(metadata) if isinstance(metadata, dict) else dict(current.get("metadata", {}))
    if expiration is not None:
        new_metadata["expiration_date"] = str(expiration)
    categories = categorize(new_text, new_metadata)
    now = utc_now()
    digest = content_hash(new_text, current.get("user_id"), current.get("agent_id"), current.get("app_id"), current.get("run_id"))
    embedding = embed_text(new_text, project_id=project_id)
    with get_db() as conn:
        conn.execute(
            """
            UPDATE memories
               SET memory = ?, metadata = ?, categories = ?, embedding = ?, hash = ?, updated_at = ?
             WHERE id = ? AND project_id = ? AND deleted = 0
            """,
            (new_text, json_dumps(new_metadata), json_dumps(categories), encode_embedding(embedding), digest, now, memory_id, project_id),
        )
        conn.execute(
            """
            INSERT INTO memory_history (
                id, memory_id, project_id, event, input, old_memory, new_memory,
                user_id, agent_id, app_id, run_id, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(new_id()),
                memory_id,
                project_id,
                "UPDATE",
                json_dumps([payload]),
                current["memory"],
                new_text,
                current.get("user_id"),
                current.get("agent_id"),
                current.get("app_id"),
                current.get("run_id"),
                json_dumps(new_metadata),
                now,
                now,
            ),
        )
    link_memory_entities(memory_id, new_text, project_id)
    result = get_memory(memory_id, project_id=project_id, include_expired=True)
    if memory_is_expired(result):
        vector_delete_memory(memory_id, project_id)
    else:
        vector_upsert_memory({**result, "project_id": project_id}, embedding, project_id)
    result["text"] = result["memory"]
    emit_webhook_event("memory_update", {"id": memory_id, "data": {"memory": result["memory"]}}, project_id=project_id)
    record_usage(project_id, "memory_update", input_tokens=token_estimate(payload), output_tokens=token_estimate(result), metadata={"memory_id": memory_id})
    return result


def supersede_memory(memory_id: str, payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    """Mark a memory as superseded — the verification loop's deterministic
    staleness operation.

    Non-destructive by design: the row stays retrievable ("did X change?"
    questions need the old fact), but search demotes it hard
    (MEM1_SUPERSEDED_SCORE_MULT, default 0.45) and metadata carries the
    supersession so every surface can annotate it. Embeddings and the memory
    text are untouched; explicit human feedback rows are never modified.
    """
    payload = payload or {}
    project_id = payload.get("project_id") or project_id or current_project_id()
    successor_id = str(payload.get("superseded_by") or payload.get("new_memory_id") or "").strip() or None
    reason = str(payload.get("reason") or "").strip()
    current = get_memory(memory_id, project_id=project_id, include_expired=True)
    metadata = dict(current.get("metadata") or {})
    if metadata.get("immutable") is True:
        raise HTTPException(status_code=409, detail="Memory is immutable and cannot be superseded")
    if successor_id == memory_id:
        raise HTTPException(status_code=400, detail="A memory cannot supersede itself")
    successor = get_memory(successor_id, project_id=project_id, include_expired=True) if successor_id else None

    now = utc_now()
    metadata["superseded_at"] = now
    if successor_id:
        metadata["superseded_by"] = successor_id
    if reason:
        metadata["supersede_reason"] = reason

    with get_db() as conn:
        conn.execute(
            "UPDATE memories SET metadata = ?, updated_at = ? WHERE id = ? AND project_id = ? AND deleted = 0",
            (json_dumps(metadata), now, memory_id, project_id),
        )
        if successor is not None:
            successor_metadata = dict(successor.get("metadata") or {})
            supersedes = successor_metadata.get("supersedes")
            supersedes = list(supersedes) if isinstance(supersedes, list) else []
            if memory_id not in supersedes:
                supersedes.append(memory_id)
            successor_metadata["supersedes"] = supersedes
            conn.execute(
                "UPDATE memories SET metadata = ?, updated_at = ? WHERE id = ? AND project_id = ? AND deleted = 0",
                (json_dumps(successor_metadata), now, successor_id, project_id),
            )
        conn.execute(
            "UPDATE claims SET status = 'superseded', retired_at = ?, valid_to = ?, updated_at = ? "
            "WHERE memory_id = ? AND project_id = ? AND status = 'active'",
            (now, now, now, memory_id, project_id),
        )
        conn.execute(
            """
            INSERT INTO memory_history (
                id, memory_id, project_id, event, input, old_memory, new_memory,
                user_id, agent_id, app_id, run_id, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(new_id()),
                memory_id,
                project_id,
                "SUPERSEDE",
                json_dumps([payload]),
                current["memory"],
                current["memory"],
                current.get("user_id"),
                current.get("agent_id"),
                current.get("app_id"),
                current.get("run_id"),
                json_dumps(metadata),
                now,
                now,
            ),
        )
    emit_webhook_event(
        "memory_supersede",
        {"id": memory_id, "data": {"superseded_by": successor_id, "reason": reason}},
        project_id=project_id,
    )
    return {
        "schema_version": "mem1-supersede-v1",
        "id": memory_id,
        "superseded_at": now,
        "superseded_by": successor_id,
        "reason": reason or None,
        "still_retrievable": True,
    }


def confirm_memory(memory_id: str, payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    """Close an open loop the honest way: a reported claim was true — attach
    the receipt and promote it.

    supersede says "it was wrong"; confirm says "it was right, verified".
    Without this, a TRUE unverified action claim can only be silenced by
    superseding it — making the ledger lie. Evidence is mandatory: no
    receipt, no confirmation.
    """
    payload = payload or {}
    project_id = payload.get("project_id") or project_id or current_project_id()
    evidence = str(payload.get("evidence") or "").strip()
    if not evidence:
        raise HTTPException(status_code=400, detail="evidence is required — no receipt, no confirmation")
    current = get_memory(memory_id, project_id=project_id, include_expired=True)
    metadata = dict(current.get("metadata") or {})
    if metadata.get("superseded_at"):
        raise HTTPException(status_code=409, detail="Memory is superseded — confirm its successor instead")

    now = utc_now()
    metadata["verified_at"] = now
    metadata["verified_evidence"] = evidence[:500]
    if payload.get("evidence_ref"):
        metadata["verified_evidence_ref"] = str(payload["evidence_ref"])[:300]
    trust = dict(metadata.get("trust") or {})
    trust["light"] = "green"
    trust.setdefault("source", "assistant")
    trust.setdefault("kind", "action_report")
    trust["note"] = f"verified {now[:10]}: {evidence[:120]}"
    metadata["trust"] = trust

    with get_db() as conn:
        conn.execute(
            "UPDATE memories SET metadata = ?, updated_at = ? WHERE id = ? AND project_id = ? AND deleted = 0",
            (json_dumps(metadata), now, memory_id, project_id),
        )
        conn.execute(
            "UPDATE claims SET modality = 'asserted', updated_at = ? "
            "WHERE memory_id = ? AND project_id = ? AND modality = 'reported' AND status = 'active'",
            (now, memory_id, project_id),
        )
        conn.execute(
            """
            INSERT INTO memory_history (
                id, memory_id, project_id, event, input, old_memory, new_memory,
                user_id, agent_id, app_id, run_id, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(new_id()),
                memory_id,
                project_id,
                "CONFIRM",
                json_dumps([payload]),
                current["memory"],
                current["memory"],
                current.get("user_id"),
                current.get("agent_id"),
                current.get("app_id"),
                current.get("run_id"),
                json_dumps(metadata),
                now,
                now,
            ),
        )
    emit_webhook_event(
        "memory_confirm",
        {"id": memory_id, "data": {"evidence": evidence[:200]}},
        project_id=project_id,
    )
    return {
        "schema_version": "mem1-confirm-v1",
        "id": memory_id,
        "verified_at": now,
        "evidence": evidence[:200],
        "trust_light": "green",
    }


def delete_memory(memory_id: str, project_id: str | None = None) -> dict[str, str]:
    project_id = project_id or current_project_id()
    current = get_memory(memory_id, project_id=project_id, include_expired=True)
    now = utc_now()
    with get_db() as conn:
        conn.execute("UPDATE memories SET deleted = 1, updated_at = ? WHERE id = ? AND project_id = ?", (now, memory_id, project_id))
        conn.execute("DELETE FROM memory_entities WHERE memory_id = ? AND project_id = ?", (memory_id, project_id))
        conn.execute(
            """
            INSERT INTO memory_history (
                id, memory_id, project_id, event, input, old_memory, new_memory,
                user_id, agent_id, app_id, run_id, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(new_id()),
                memory_id,
                project_id,
                "DELETE",
                "[]",
                current["memory"],
                None,
                current.get("user_id"),
                current.get("agent_id"),
                current.get("app_id"),
                current.get("run_id"),
                json_dumps(current.get("metadata", {})),
                now,
                now,
            ),
        )
    emit_webhook_event("memory_delete", {"id": memory_id, "data": {"memory": current["memory"]}}, project_id=project_id)
    vector_delete_memory(memory_id, project_id)
    record_usage(project_id, "memory_delete", input_tokens=token_estimate(current), metadata={"memory_id": memory_id})
    return {"message": "Memory deleted successfully!"}


def delete_memories(filters: dict[str, Any], project_id: str | None = None) -> dict[str, str]:
    project_id = project_id or current_project_id()
    validate_filters(filters)
    if not has_entity_filter(filters):
        raise HTTPException(status_code=400, detail="filters must include at least one entity ID")
    memories = [m for m in list_memory_dicts(project_id=project_id, include_expired=True) if matches_filters(m, filters)]
    for memory in memories:
        delete_memory(memory["id"], project_id=project_id)
    return {"message": "Memories deleted successfully!"}


def memory_history(memory_id: str, project_id: str | None = None) -> list[dict[str, Any]]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM memory_history WHERE memory_id = ? AND project_id = ? ORDER BY created_at ASC",
            (memory_id, project_id),
        ).fetchall()
    if not rows:
        get_memory(memory_id, project_id=project_id)
    return [
        {
            "id": row["id"],
            "memory_id": row["memory_id"],
            "event": row["event"],
            "input": json_loads(row["input"], []),
            "old_memory": row["old_memory"],
            "new_memory": row["new_memory"],
            "user_id": row["user_id"],
            "agent_id": row["agent_id"],
            "app_id": row["app_id"],
            "run_id": row["run_id"],
            "metadata": json_loads(row["metadata"], {}),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def submit_memory_feedback(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    memory_id = payload.get("memory_id")
    if not memory_id:
        raise HTTPException(status_code=400, detail="memory_id is required")
    memory_id = str(memory_id)
    get_memory(memory_id, project_id=project_id)

    feedback_keys = ("feedback", "rating", "value")
    feedback_present = any(key in payload for key in feedback_keys)
    reason_present = "feedback_reason" in payload or "reason" in payload
    if not feedback_present and not reason_present:
        raise HTTPException(status_code=400, detail="feedback is required")

    feedback = next((payload[key] for key in feedback_keys if key in payload), None)
    feedback_reason = payload.get("feedback_reason", payload.get("reason"))
    if feedback is None and feedback_reason is None:
        with get_db() as conn:
            conn.execute("DELETE FROM feedback WHERE memory_id = ?", (memory_id,))
        return {
            "memory_id": memory_id,
            "feedback": None,
            "feedback_reason": None,
            "message": "Feedback removed successfully!",
        }
    if feedback is None:
        raise HTTPException(status_code=400, detail="feedback is required")

    normalized_feedback = str(feedback).upper()
    if normalized_feedback not in {"POSITIVE", "NEGATIVE", "VERY_NEGATIVE"}:
        raise HTTPException(status_code=400, detail="feedback must be POSITIVE, NEGATIVE, or VERY_NEGATIVE")

    item = {
        "id": str(new_id()),
        "memory_id": memory_id,
        "feedback": normalized_feedback,
        "feedback_reason": "" if feedback_reason is None else str(feedback_reason),
        "metadata": payload.get("metadata") or {},
        "created_at": utc_now(),
    }
    with get_db() as conn:
        conn.execute("DELETE FROM feedback WHERE memory_id = ?", (memory_id,))
        _entity_prune_stats_cache.clear()
        conn.execute(
            """
            INSERT INTO feedback (id, memory_id, feedback, feedback_reason, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                item["memory_id"],
                item["feedback"],
                item["feedback_reason"],
                json_dumps(item["metadata"]),
                item["created_at"],
            ),
        )
    return item


def record_request_log(
    method: str,
    path: str,
    status_code: int,
    latency: float,
    project_id: str | None = None,
    ip: str = "",
    user_agent: str = "",
) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO request_logs (
                id, project_id, method, path, status_code, latency, ip, user_agent, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(new_id()),
                project_id or current_project_id(),
                method,
                path,
                status_code,
                latency,
                ip,
                user_agent,
                utc_now(),
            ),
        )


def list_request_logs(
    project_id: str | None = None,
    limit: int = 100,
    method: str | None = None,
    path: str | None = None,
    status_code: int | None = None,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(int(limit), 1), 500)
    where = "WHERE project_id = ?"
    params: list[Any] = [project_id]
    if method:
        where += " AND method = ?"
        params.append(method.upper())
    if path:
        where += " AND path LIKE ?"
        params.append(f"%{path}%")
    if status_code is not None:
        where += " AND status_code = ?"
        params.append(status_code)
    with get_db() as conn:
        count = conn.execute(f"SELECT COUNT(*) AS c FROM request_logs {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"""
            SELECT * FROM request_logs
             {where}
             ORDER BY created_at DESC
             LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    return {"project_id": project_id, "count": count, "results": [dict(row) for row in rows]}


TRACE_EXPORT_SOURCES = {"proposals", "feedback", "evaluation_misses", "shadow_disagreements"}
TRACE_DATASET_VERSION = "training-trace-v1"
TRACE_REDACTION_POLICY = "basic_pii_v1"
TRACE_REDACTION_POLICIES = {TRACE_REDACTION_POLICY, "strict_pii_v1"}


MEM1_POLICY_PRESETS: dict[str, dict[str, Any]] = {
    "balanced": {
        "id": "balanced",
        "name": "Balanced",
        "description": "Default review and redaction posture for production pilots.",
        "privacy": "standard",
        "retention": "standard",
        "risk_tolerance": "balanced",
        "settings": {
            "policy_preset": "balanced",
            "policy_risk_tolerance": "balanced",
            "trace_redaction_policy": TRACE_REDACTION_POLICY,
            "trace_redaction_deny_terms": [],
            "trace_redaction_allow_terms": [],
            "proposal_required_reviews": 1,
            "entity_link_prune_enabled": True,
            "entity_link_prune_min_negative_feedback": 2,
            "entity_link_prune_negative_ratio": 0.67,
            "shadow_promotion_min_confidence": 0.8,
            "shadow_canary_min_reviews": 5,
            "shadow_canary_min_precision": 0.9,
            "shadow_canary_min_confidence": 0.95,
            "promotion_audit_retention_enabled": False,
            "promotion_audit_retention_older_than_days": 30,
            "promotion_audit_retention_limit": 500,
            "promotion_audit_retention_interval_seconds": 86400,
        },
    },
    "privacy_strict": {
        "id": "privacy_strict",
        "name": "Privacy Strict",
        "description": "Higher review quorum, stricter trace redaction, and shorter audit retention.",
        "privacy": "strict",
        "retention": "short",
        "risk_tolerance": "low",
        "settings": {
            "policy_preset": "privacy_strict",
            "policy_risk_tolerance": "low",
            "trace_redaction_policy": "strict_pii_v1",
            "trace_redaction_deny_terms": ["api key", "credit card", "password", "secret", "social security", "ssn", "token"],
            "trace_redaction_allow_terms": [],
            "proposal_required_reviews": 2,
            "entity_link_prune_enabled": True,
            "entity_link_prune_min_negative_feedback": 1,
            "entity_link_prune_negative_ratio": 0.5,
            "shadow_promotion_min_confidence": 0.9,
            "shadow_canary_min_reviews": 5,
            "shadow_canary_min_precision": 0.95,
            "shadow_canary_min_confidence": 0.98,
            "promotion_audit_retention_enabled": True,
            "promotion_audit_retention_older_than_days": 14,
            "promotion_audit_retention_limit": 500,
            "promotion_audit_retention_interval_seconds": 86400,
        },
    },
    "growth_canary": {
        "id": "growth_canary",
        "name": "Growth Canary",
        "description": "Faster adapter iteration with lower canary thresholds and standard redaction.",
        "privacy": "standard",
        "retention": "extended",
        "risk_tolerance": "medium_high",
        "settings": {
            "policy_preset": "growth_canary",
            "policy_risk_tolerance": "medium_high",
            "trace_redaction_policy": TRACE_REDACTION_POLICY,
            "trace_redaction_deny_terms": [],
            "trace_redaction_allow_terms": [],
            "proposal_required_reviews": 1,
            "entity_link_prune_enabled": True,
            "entity_link_prune_min_negative_feedback": 2,
            "entity_link_prune_negative_ratio": 0.67,
            "shadow_promotion_min_confidence": 0.75,
            "shadow_canary_min_reviews": 1,
            "shadow_canary_min_precision": 0.85,
            "shadow_canary_min_confidence": 0.9,
            "promotion_audit_retention_enabled": True,
            "promotion_audit_retention_older_than_days": 60,
            "promotion_audit_retention_limit": 1000,
            "promotion_audit_retention_interval_seconds": 86400,
        },
    },
}


def _policy_preset_payload(preset: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in preset.items() if key != "settings"} | {"settings": dict(preset["settings"])}


def _policy_setting_keys() -> list[str]:
    keys: set[str] = set()
    for preset in MEM1_POLICY_PRESETS.values():
        keys.update(preset["settings"].keys())
    return sorted(keys)


def _settings_diff(before: dict[str, Any], after_updates: dict[str, Any]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for key in sorted(after_updates):
        before_value = before.get(key)
        after_value = after_updates[key]
        if before_value != after_value:
            changes.append({"key": key, "before": before_value, "after": after_value})
    return changes


def _matching_policy_preset(settings: dict[str, Any]) -> str | None:
    for preset_id, preset in MEM1_POLICY_PRESETS.items():
        if all(settings.get(key) == value for key, value in preset["settings"].items()):
            return preset_id
    return None


def list_mem1_policy_presets(project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    settings = get_project_settings(project_id)
    keys = _policy_setting_keys()
    return {
        "schema_version": "mem1-policy-presets-v1",
        "project_id": project_id,
        "current_preset": _matching_policy_preset(settings),
        "declared_preset": settings.get("policy_preset"),
        "policy_settings": {key: settings.get(key) for key in keys},
        "presets": [_policy_preset_payload(preset) for preset in MEM1_POLICY_PRESETS.values()],
    }


def apply_mem1_policy_preset(
    preset_id: str,
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    project_id = project_id or current_project_id()
    normalized_id = str(preset_id or "").strip().lower()
    preset = MEM1_POLICY_PRESETS.get(normalized_id)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Unknown Forget policy preset: {preset_id}")
    apply = _bool_or(payload.get("apply"), False)
    before = get_project_settings(project_id)
    updates = dict(preset["settings"])
    changes = _settings_diff(before, updates)
    after = update_project_settings(project_id, updates) if apply else {**before, **updates}
    result = {
        "schema_version": "mem1-policy-preset-apply-v1",
        "project_id": project_id,
        "status": "APPLIED" if apply else "READY",
        "apply": apply,
        "preset": _policy_preset_payload(preset),
        "changed": bool(changes),
        "changes": changes,
        "before": {key: before.get(key) for key in _policy_setting_keys()},
        "after": {key: after.get(key) for key in _policy_setting_keys()},
        "requested_by": payload.get("requested_by") or payload.get("reviewer_id") or "operator",
    }
    record_usage(
        project_id,
        "mem1_policy_preset_apply" if apply else "mem1_policy_preset_plan",
        input_tokens=token_estimate({"preset_id": preset_id, **payload}),
        output_tokens=token_estimate(result),
        metadata={"preset_id": normalized_id, "apply": apply, "changed": bool(changes)},
    )
    return result


def _coerce_trace_redaction_terms(raw: Any) -> list[str]:
    if raw in (None, ""):
        return []
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",")]
    elif isinstance(raw, list):
        values = [str(item).strip() for item in raw]
    else:
        return []
    seen: set[str] = set()
    terms: list[str] = []
    for value in values:
        if len(value) < 3:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(value)
    return terms


def _payload_trace_redaction_terms(payload: dict[str, Any]) -> list[str]:
    return _coerce_trace_redaction_terms(payload.get("redaction_terms") or payload.get("redact_terms"))


def _trace_redaction_rules(payload: dict[str, Any], project_id: str) -> dict[str, list[str]]:
    settings = get_project_settings(project_id)
    settings_terms = _coerce_trace_redaction_terms(settings.get("trace_redaction_terms"))
    settings_deny_terms = _coerce_trace_redaction_terms(settings.get("trace_redaction_deny_terms"))
    settings_allow_terms = _coerce_trace_redaction_terms(settings.get("trace_redaction_allow_terms"))
    payload_terms = _payload_trace_redaction_terms(payload)
    payload_deny_terms = _coerce_trace_redaction_terms(payload.get("redaction_deny_terms") or payload.get("deny_terms"))
    payload_allow_terms = _coerce_trace_redaction_terms(payload.get("redaction_allow_terms") or payload.get("allow_terms"))

    def merge_terms(values: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for term in values:
            key = term.lower()
            if key not in seen:
                seen.add(key)
                merged.append(term)
        return sorted(merged, key=len, reverse=True)

    return {
        "deny_terms": merge_terms([*settings_terms, *settings_deny_terms, *payload_terms, *payload_deny_terms]),
        "allow_terms": merge_terms([*settings_allow_terms, *payload_allow_terms]),
    }


def _trace_redaction_terms(payload: dict[str, Any], project_id: str) -> list[str]:
    return _trace_redaction_rules(payload, project_id)["deny_terms"]


def _protect_trace_allow_terms(value: str, allow_terms: list[str]) -> tuple[str, dict[str, str]]:
    replacements: dict[str, str] = {}
    for index, term in enumerate(allow_terms):
        marker = f"__TRACE_ALLOW_{index}__"
        pattern = re.compile(re.escape(term), flags=re.IGNORECASE)
        if not pattern.search(value):
            continue
        value = pattern.sub(marker, value)
        replacements[marker] = term
    return value, replacements


def _redact_trace_text(value: str, deny_terms: list[str], allow_terms: list[str] | None = None) -> str:
    value, replacements = _protect_trace_allow_terms(value, allow_terms or [])
    value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL]", value)
    value = re.sub(r"\b(?:\+?\d[\d .()\-]{7,}\d)\b", "[PHONE]", value)
    value = re.sub(r"\b(?:sk|m0sk|hf)_[A-Za-z0-9_\-]{12,}\b", "[SECRET]", value)
    for term in deny_terms:
        value = re.sub(re.escape(term), "[REDACTED]", value, flags=re.IGNORECASE)
    for marker, term in replacements.items():
        value = value.replace(marker, term)
    return value


def _redact_trace_text_with_policy(
    value: str,
    deny_terms: list[str],
    allow_terms: list[str] | None = None,
    policy: str = TRACE_REDACTION_POLICY,
) -> str:
    if policy != "strict_pii_v1":
        return _redact_trace_text(value, deny_terms, allow_terms)
    value, replacements = _protect_trace_allow_terms(value, allow_terms or [])
    value = re.sub(r"https?://[^\s\"'<>]+", "[URL]", value)
    value = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[IP]", value)
    value = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[EMAIL]", value)
    value = re.sub(r"\b(?:\+?\d[\d .()\-]{7,}\d)\b", "[PHONE]", value)
    value = re.sub(r"\b(?:sk|m0sk|hf)_[A-Za-z0-9_\-]{12,}\b", "[SECRET]", value)
    for term in deny_terms:
        value = re.sub(re.escape(term), "[REDACTED]", value, flags=re.IGNORECASE)
    for marker, term in replacements.items():
        value = value.replace(marker, term)
    return value


def _redact_trace_value(
    value: Any,
    deny_terms: list[str],
    allow_terms: list[str] | None = None,
    policy: str = TRACE_REDACTION_POLICY,
) -> Any:
    if isinstance(value, str):
        return _redact_trace_text_with_policy(value, deny_terms, allow_terms, policy)
    if isinstance(value, list):
        return [_redact_trace_value(item, deny_terms, allow_terms, policy) for item in value]
    if isinstance(value, dict):
        return {key: _redact_trace_value(item, deny_terms, allow_terms, policy) for key, item in value.items()}
    return value


def _trace_redaction_policy(payload: dict[str, Any], project_id: str | None = None) -> str:
    settings = get_project_settings(project_id or current_project_id())
    raw_policy = str(
        payload.get("redaction_policy")
        or payload.get("redaction")
        or settings.get("trace_redaction_policy")
        or ""
    ).strip().lower()
    if raw_policy in {"", "none", "false"}:
        return TRACE_REDACTION_POLICY
    if raw_policy in {"true", "1", "yes", "basic", "basic_pii"}:
        return TRACE_REDACTION_POLICY
    if raw_policy == "strict":
        return "strict_pii_v1"
    if raw_policy not in TRACE_REDACTION_POLICIES:
        raise HTTPException(status_code=400, detail=f"Unsupported trace redaction_policy: {raw_policy}")
    return raw_policy


def _trace_redaction_enabled(payload: dict[str, Any], project_id: str | None = None) -> bool:
    settings = get_project_settings(project_id or current_project_id())
    payload_policy = str(payload.get("redaction_policy") or payload.get("redaction") or "").strip().lower()
    setting_policy = str(settings.get("trace_redaction_policy") or "").strip().lower()
    policy = payload_policy or setting_policy
    deny_terms = _payload_trace_redaction_terms(payload) or _coerce_trace_redaction_terms(payload.get("redaction_deny_terms") or payload.get("deny_terms"))
    if policy and policy not in {"none", "false"}:
        _trace_redaction_policy(payload, project_id=project_id)
    payload_requests_redaction = payload_policy in {"true", "1", "yes", "basic", "basic_pii", "strict", *TRACE_REDACTION_POLICIES}
    strict_project_default = not payload_policy and setting_policy in {"strict", "strict_pii_v1"}
    return bool(payload.get("redact", False) or payload_requests_redaction or strict_project_default or deny_terms)


def _trace_term_hashes(terms: list[str]) -> list[str]:
    return [content_hash("trace-redaction-term", term.lower())[:16] for term in terms]


def _record_training_trace_audit(
    project_id: str,
    sources: list[str],
    filters: dict[str, Any],
    redaction: dict[str, Any],
    result_count: int,
    source_counts: dict[str, int],
    deny_terms: list[str],
    allow_terms: list[str],
) -> str:
    audit_id = str(new_id("trace_audit"))
    redaction_snapshot = {
        **redaction,
        "deny_term_hashes": _trace_term_hashes(deny_terms) if redaction.get("enabled") else [],
        "allow_term_hashes": _trace_term_hashes(allow_terms) if redaction.get("enabled") else [],
    }
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO trace_export_audits (
                id, project_id, dataset_version, sources, filters, redacted,
                redaction_policy, redaction, result_count, source_counts, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id,
                project_id,
                TRACE_DATASET_VERSION,
                json_dumps(sources),
                json_dumps({key: value for key, value in filters.items() if value not in (None, "", [])}),
                1 if redaction.get("enabled") else 0,
                str(redaction.get("policy") or "none"),
                json_dumps(redaction_snapshot),
                result_count,
                json_dumps(source_counts),
                utc_now(),
            ),
        )
    return audit_id


def list_training_trace_audits(
    project_id: str | None = None,
    limit: int = 100,
    dataset_version: str | None = None,
    redacted: bool | None = None,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(int(limit), 1), 500)
    where = "WHERE project_id = ?"
    params: list[Any] = [project_id]
    if dataset_version:
        where += " AND dataset_version = ?"
        params.append(dataset_version)
    if redacted is not None:
        where += " AND redacted = ?"
        params.append(1 if redacted else 0)
    with get_db() as conn:
        count = conn.execute(f"SELECT COUNT(*) AS c FROM trace_export_audits {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"""
            SELECT * FROM trace_export_audits
             {where}
             ORDER BY created_at DESC
             LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        item["sources"] = json_loads(row["sources"], [])
        item["filters"] = json_loads(row["filters"], {})
        item["redacted"] = bool(row["redacted"])
        item["redaction"] = json_loads(row["redaction"], {})
        item["source_counts"] = json_loads(row["source_counts"], {})
        results.append(item)
    return {"project_id": project_id, "count": count, "results": results}


def trace_export_approval_row(row: Any, include_data: bool = False) -> dict[str, Any]:
    data = json_loads(row["data"], {})
    item = {
        "id": row["id"],
        "project_id": row["project_id"],
        "status": row["status"],
        "dataset_version": row["dataset_version"],
        "sources": json_loads(row["sources"], []),
        "filters": json_loads(row["filters"], {}),
        "redaction": json_loads(row["redaction"], {}),
        "result_count": row["result_count"],
        "source_counts": json_loads(row["source_counts"], {}),
        "trace_audit_id": row["trace_audit_id"],
        "requested_by": row["requested_by"],
        "reviewed_by": row["reviewed_by"],
        "review_reason": row["review_reason"],
        "metadata": json_loads(row["metadata"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "reviewed_at": row["reviewed_at"],
    }
    results = data.get("results") if isinstance(data, dict) else []
    item["preview"] = results[:5] if isinstance(results, list) else []
    if include_data:
        item["data"] = data
    return item


def create_trace_export_approval(payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    payload = payload or {}
    project_id = payload.get("project_id") or project_id or current_project_id()
    if payload.get("redact") is False:
        raise HTTPException(status_code=400, detail="Trace export approvals require redact=true")
    trace_payload = {
        "limit": payload.get("limit") or 100,
        "sources": payload.get("sources") or payload.get("source") or ["feedback", "proposals", "evaluation_misses", "shadow_disagreements"],
        "status": payload.get("status"),
        "family": payload.get("family"),
        "dataset_version": payload.get("dataset_version") or payload.get("version") or TRACE_DATASET_VERSION,
        "redact": True,
        "redaction_policy": payload.get("redaction_policy") or payload.get("redactionPolicy"),
        "redaction_terms": payload.get("redaction_terms") or payload.get("redactionTerms"),
        "redaction_deny_terms": payload.get("redaction_deny_terms") or payload.get("redactionDenyTerms"),
        "redaction_allow_terms": payload.get("redaction_allow_terms") or payload.get("redactionAllowTerms"),
    }
    export = export_training_traces(trace_payload, project_id=project_id)
    approval_id = str(new_id("trace_approval"))
    now = utc_now()
    filters = {
        "status": trace_payload.get("status"),
        "family": trace_payload.get("family"),
        "limit": trace_payload.get("limit"),
        "dataset_version": TRACE_DATASET_VERSION,
    }
    data = {
        "id": approval_id,
        "project_id": project_id,
        "dataset_version": TRACE_DATASET_VERSION,
        "sources": export["sources"],
        "redaction": export["redaction"],
        "count": export["count"],
        "source_counts": export["source_counts"],
        "results": export["results"],
    }
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO trace_export_approvals (
                id, project_id, status, dataset_version, sources, filters, redaction,
                result_count, source_counts, trace_audit_id, requested_by, metadata,
                data, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                project_id,
                "PENDING",
                TRACE_DATASET_VERSION,
                json_dumps(export["sources"]),
                json_dumps({key: value for key, value in filters.items() if value not in (None, "", [])}),
                json_dumps(export["redaction"]),
                export["count"],
                json_dumps(export["source_counts"]),
                export.get("audit_id"),
                str(payload.get("requested_by") or payload.get("requester") or "api"),
                json_dumps(payload.get("metadata") or {}),
                json_dumps(data),
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM trace_export_approvals WHERE id = ? AND project_id = ?",
            (approval_id, project_id),
        ).fetchone()
    record_usage(
        project_id,
        "trace_export_approval_request",
        input_tokens=token_estimate(trace_payload),
        output_tokens=token_estimate(trace_export_approval_row(row)),
        metadata={"approval_id": approval_id, "trace_audit_id": export.get("audit_id")},
    )
    return trace_export_approval_row(row)


def list_trace_export_approvals(
    project_id: str | None = None,
    limit: int = 100,
    status: str | None = None,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(int(limit), 1), 500)
    where = "WHERE project_id = ?"
    params: list[Any] = [project_id]
    if status:
        where += " AND status = ?"
        params.append(status.upper())
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM trace_export_approvals {where} ORDER BY created_at DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
    return {"project_id": project_id, "count": len(rows), "results": [trace_export_approval_row(row) for row in rows]}


def get_trace_export_approval(approval_id: str, project_id: str | None = None, include_data: bool = False) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM trace_export_approvals WHERE id = ? AND project_id = ?",
            (approval_id, project_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Trace export approval not found")
    return trace_export_approval_row(row, include_data=include_data)


def review_trace_export_approval(
    approval_id: str,
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
    decision: str = "APPROVED",
) -> dict[str, Any]:
    payload = payload or {}
    project_id = project_id or current_project_id()
    decision = decision.upper()
    if decision not in {"APPROVED", "REJECTED"}:
        raise HTTPException(status_code=400, detail="decision must be APPROVED or REJECTED")
    reviewed_by = str(payload.get("reviewed_by") or payload.get("reviewer_id") or payload.get("reviewer") or "api_reviewer")
    reason = str(payload.get("reason") or payload.get("review_reason") or "")
    now = utc_now()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM trace_export_approvals WHERE id = ? AND project_id = ?",
            (approval_id, project_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Trace export approval not found")
        if row["status"] != "PENDING":
            raise HTTPException(status_code=409, detail="Only pending trace export approvals can be reviewed")
        conn.execute(
            """
            UPDATE trace_export_approvals
               SET status = ?, reviewed_by = ?, review_reason = ?, reviewed_at = ?, updated_at = ?
             WHERE id = ? AND project_id = ?
            """,
            (decision, reviewed_by, reason, now, now, approval_id, project_id),
        )
        updated = conn.execute(
            "SELECT * FROM trace_export_approvals WHERE id = ? AND project_id = ?",
            (approval_id, project_id),
        ).fetchone()
    record_usage(
        project_id,
        "trace_export_approval_review",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate({"approval_id": approval_id, "status": decision}),
        metadata={"approval_id": approval_id, "status": decision},
    )
    return trace_export_approval_row(updated)


def approved_trace_export_dataset(approval_id: str, project_id: str | None = None) -> dict[str, Any]:
    approval = get_trace_export_approval(approval_id, project_id=project_id, include_data=True)
    if approval["status"] != "APPROVED":
        raise HTTPException(status_code=409, detail="Trace export approval is not approved")
    data = approval.get("data") or {}
    return {
        **data,
        "approval_id": approval["id"],
        "trace_audit_id": approval["trace_audit_id"],
        "approved_by": approval["reviewed_by"],
        "approved_at": approval["reviewed_at"],
    }


def fine_tuning_job_row(row: Any) -> dict[str, Any]:
    return {
        "schema_version": FINE_TUNING_JOB_SCHEMA_VERSION,
        "id": row["id"],
        "project_id": row["project_id"],
        "status": row["status"],
        "provider": row["provider"],
        "base_model": row["base_model"],
        "adapter_model": row["adapter_model"],
        "approval_id": row["approval_id"],
        "dataset_version": row["dataset_version"],
        "dataset_count": row["dataset_count"],
        "trainer_url": row["trainer_url"],
        "result": json_loads(row["result"], {}),
        "error": row["error"],
        "metadata": json_loads(row["metadata"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


def model_artifact_row(row: Any) -> dict[str, Any]:
    return {
        "schema_version": MODEL_ARTIFACT_SCHEMA_VERSION,
        "id": row["id"],
        "project_id": row["project_id"],
        "fine_tuning_job_id": row["fine_tuning_job_id"],
        "adapter_model": row["adapter_model"],
        "provider": row["provider"],
        "artifact_uri": row["artifact_uri"],
        "checksum": row["checksum"],
        "status": row["status"],
        "metadata": json_loads(row["metadata"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def model_deployment_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "artifact_id": row["artifact_id"],
        "environment": row["environment"],
        "status": row["status"],
        "adapter_model": row["adapter_model"],
        "deployer_url": row["deployer_url"],
        "result": json_loads(row["result"], {}),
        "error": row["error"],
        "metadata": json_loads(row["metadata"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
    }


def model_activation_history_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "deployment_id": row["deployment_id"],
        "artifact_id": row["artifact_id"],
        "mode": row["mode"],
        "status": row["status"],
        "settings_before": json_loads(row["settings_before"], {}),
        "settings_after": json_loads(row["settings_after"], {}),
        "metadata": json_loads(row["metadata"], {}),
        "activated_at": row["activated_at"],
        "rolled_back_at": row["rolled_back_at"],
        "rollback_reason": row["rollback_reason"],
    }


def _artifact_fields_from_result(job_id: str, adapter_model: str, provider: str, result: dict[str, Any]) -> dict[str, Any]:
    trainer_response = result.get("trainer_response") if isinstance(result.get("trainer_response"), dict) else {}
    artifact_uri = (
        result.get("artifact_uri")
        or result.get("model_uri")
        or trainer_response.get("artifact_uri")
        or trainer_response.get("model_uri")
        or f"mem1://fine-tuning-jobs/{job_id}/artifacts/{adapter_model}"
    )
    checksum = result.get("checksum") or trainer_response.get("checksum") or content_hash("model-artifact", f"{provider}:{artifact_uri}:{adapter_model}")[:16]
    return {"artifact_uri": str(artifact_uri), "checksum": str(checksum)}


def _create_model_artifact_for_job(
    job_id: str,
    project_id: str,
    adapter_model: str,
    provider: str,
    result: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    fields = _artifact_fields_from_result(job_id, adapter_model, provider, result)
    artifact_id = str(new_id("artifact"))
    now = utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO model_artifacts (
                id, project_id, fine_tuning_job_id, adapter_model, provider,
                artifact_uri, checksum, status, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                project_id,
                job_id,
                adapter_model,
                provider,
                fields["artifact_uri"],
                fields["checksum"],
                "READY",
                json_dumps(metadata),
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM model_artifacts WHERE id = ? AND project_id = ?",
            (artifact_id, project_id),
        ).fetchone()
    return model_artifact_row(row)


def _fine_tuning_provider_result(
    job_id: str,
    dataset: dict[str, Any],
    payload: dict[str, Any],
    provider: str,
) -> dict[str, Any]:
    base_model = str(payload.get("base_model") or payload.get("model") or "memory-adapter-base").strip()
    adapter_model = str(payload.get("adapter_model") or payload.get("output_model") or f"mem1-{job_id}").strip()
    sft_dataset = build_sft_dataset(dataset)
    if provider == "local":
        return {
            "external": False,
            "adapter_model": adapter_model,
            "base_model": base_model,
            "dataset_count": dataset.get("count", 0),
            "sft_record_count": sft_dataset["record_count"],
            "sft_schema_version": sft_dataset["schema_version"],
            "message": "local fine-tuning orchestration completed",
        }
    trainer_url = str(payload.get("trainer_url") or payload.get("url") or "").strip()
    if not trainer_url:
        raise HTTPException(status_code=400, detail="trainer_url is required for non-local fine-tuning providers")
    headers = {"Content-Type": "application/json"}
    api_key = payload.get("trainer_api_key") or payload.get("api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    timeout = _float_or(payload.get("timeout"), 30.0)
    request_payload = {
        "task": "fine_tune_memory_adapter",
        "job_id": job_id,
        "approval_id": dataset.get("approval_id"),
        "dataset_version": dataset.get("dataset_version") or TRACE_DATASET_VERSION,
        "base_model": base_model,
        "adapter_model": adapter_model,
        "dataset": dataset,
        "sft_dataset": sft_dataset,
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(trainer_url, headers=headers, json=request_payload)
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, dict):
        raise ValueError("trainer response must be a JSON object")
    result = {
        "external": True,
        "adapter_model": body.get("adapter_model") or adapter_model,
        "base_model": body.get("base_model") or base_model,
        "dataset_count": dataset.get("count", 0),
        "sft_record_count": sft_dataset["record_count"],
        "sft_schema_version": sft_dataset["schema_version"],
        "trainer_response": body,
    }
    for key in (
        "trainer",
        "training_status",
        "dry_run",
        "require_cached_model",
        "base_model_cache",
        "dependencies",
        "missing_dependencies",
    ):
        if key in body:
            result[key] = body[key]
    for key in ("adapter_eval_url", "adapter_url"):
        if body.get(key):
            result[key] = body[key]
    if "training_status" not in result and body.get("status"):
        result["training_status"] = body["status"]
    return result


def create_fine_tuning_job(payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    payload = payload or {}
    project_id = payload.get("project_id") or project_id or current_project_id()
    approval_id = str(payload.get("approval_id") or payload.get("trace_export_approval_id") or "").strip()
    if not approval_id:
        raise HTTPException(status_code=400, detail="approval_id is required")
    dataset = approved_trace_export_dataset(approval_id, project_id=project_id)
    provider = str(payload.get("provider") or ("http" if payload.get("trainer_url") or payload.get("url") else "local")).strip().lower()
    if provider not in {"local", "http", "external", "api"}:
        raise HTTPException(status_code=400, detail="provider must be local or http")
    if provider in {"external", "api"}:
        provider = "http"
    if provider == "http" and not str(payload.get("trainer_url") or payload.get("url") or "").strip():
        raise HTTPException(status_code=400, detail="trainer_url is required for http provider")
    job_id = str(new_id("ftjob"))
    now = utc_now()
    base_model = str(payload.get("base_model") or payload.get("model") or "memory-adapter-base").strip()
    adapter_model = str(payload.get("adapter_model") or payload.get("output_model") or f"mem1-{job_id}").strip()
    trainer_url = str(payload.get("trainer_url") or payload.get("url") or "").strip() if provider == "http" else ""
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO fine_tuning_jobs (
                id, project_id, status, provider, base_model, adapter_model, approval_id,
                dataset_version, dataset_count, trainer_url, result, error, metadata,
                created_at, updated_at, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                project_id,
                "RUNNING",
                provider,
                base_model,
                adapter_model,
                approval_id,
                dataset.get("dataset_version") or TRACE_DATASET_VERSION,
                int(dataset.get("count") or 0),
                trainer_url,
                json_dumps({}),
                "",
                json_dumps(metadata),
                now,
                now,
                now,
            ),
        )
    try:
        result = _fine_tuning_provider_result(job_id, dataset, payload, provider)
        status = "SUCCEEDED"
        error = ""
        adapter_model = str(result.get("adapter_model") or adapter_model)
        artifact = _create_model_artifact_for_job(job_id, project_id, adapter_model, provider, result, metadata)
        result = {**result, "artifact_id": artifact["id"], "artifact_uri": artifact["artifact_uri"], "artifact_checksum": artifact["checksum"]}
    except HTTPException:
        raise
    except Exception as exc:
        result = {}
        status = "FAILED"
        error = str(exc)
    completed_at = utc_now()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE fine_tuning_jobs
               SET status = ?, adapter_model = ?, result = ?, error = ?, updated_at = ?, completed_at = ?
             WHERE id = ? AND project_id = ?
            """,
            (status, adapter_model, json_dumps(result), error, completed_at, completed_at, job_id, project_id),
        )
        row = conn.execute("SELECT * FROM fine_tuning_jobs WHERE id = ? AND project_id = ?", (job_id, project_id)).fetchone()
    record_usage(
        project_id,
        "fine_tuning_job",
        input_tokens=token_estimate(dataset),
        output_tokens=token_estimate(result or {"error": error}),
        metadata={"job_id": job_id, "approval_id": approval_id, "provider": provider, "status": status},
    )
    return fine_tuning_job_row(row)


def list_fine_tuning_jobs(project_id: str | None = None, limit: int = 100, status: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(int(limit), 1), 500)
    where = "WHERE project_id = ?"
    params: list[Any] = [project_id]
    if status:
        where += " AND status = ?"
        params.append(status.upper())
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM fine_tuning_jobs {where} ORDER BY created_at DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
    return {"project_id": project_id, "count": len(rows), "results": [fine_tuning_job_row(row) for row in rows]}


def get_fine_tuning_job(job_id: str, project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM fine_tuning_jobs WHERE id = ? AND project_id = ?", (job_id, project_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Fine-tuning job not found")
    return fine_tuning_job_row(row)


def list_model_artifacts(project_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(int(limit), 1), 500)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM model_artifacts
            WHERE project_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
    return {"project_id": project_id, "count": len(rows), "results": [model_artifact_row(row) for row in rows]}


def get_model_artifact(artifact_id: str, project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM model_artifacts WHERE id = ? AND project_id = ?", (artifact_id, project_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Model artifact not found")
    return model_artifact_row(row)


def _deployment_provider_result(artifact: dict[str, Any], payload: dict[str, Any], deployment_id: str) -> dict[str, Any]:
    environment = str(payload.get("environment") or "staging").strip()
    deployer_url = str(payload.get("deployer_url") or payload.get("url") or "").strip()
    if not deployer_url:
        return {
            "external": False,
            "environment": environment,
            "artifact_id": artifact["id"],
            "adapter_model": artifact["adapter_model"],
            "message": "local deployment handoff recorded",
        }
    headers = {"Content-Type": "application/json"}
    api_key = payload.get("deployer_api_key") or payload.get("api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    timeout = _float_or(payload.get("timeout"), 30.0)
    request_payload = {
        "task": "deploy_memory_adapter",
        "deployment_id": deployment_id,
        "environment": environment,
        "artifact": artifact,
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(deployer_url, headers=headers, json=request_payload)
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, dict):
        raise ValueError("deployer response must be a JSON object")
    return {"external": True, "environment": environment, "deployer_response": body}


def create_model_deployment(
    artifact_id: str,
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    project_id = project_id or current_project_id()
    artifact = get_model_artifact(artifact_id, project_id=project_id)
    if artifact["status"] != "READY":
        raise HTTPException(status_code=409, detail="Model artifact is not ready for deployment")
    deployment_id = str(new_id("deploy"))
    environment = str(payload.get("environment") or "staging").strip()
    deployer_url = str(payload.get("deployer_url") or payload.get("url") or "").strip()
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    now = utc_now()
    try:
        result = _deployment_provider_result(artifact, payload, deployment_id)
        status = "SUCCEEDED"
        error = ""
    except Exception as exc:
        result = {}
        status = "FAILED"
        error = str(exc)
    completed_at = utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO model_deployments (
                id, project_id, artifact_id, environment, status, adapter_model,
                deployer_url, result, error, metadata, created_at, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deployment_id,
                project_id,
                artifact_id,
                environment,
                status,
                artifact["adapter_model"],
                deployer_url,
                json_dumps(result),
                error,
                json_dumps(metadata),
                now,
                completed_at,
                completed_at,
            ),
        )
        row = conn.execute(
            "SELECT * FROM model_deployments WHERE id = ? AND project_id = ?",
            (deployment_id, project_id),
        ).fetchone()
    record_usage(
        project_id,
        "model_deployment",
        input_tokens=token_estimate({"artifact": artifact, "environment": environment}),
        output_tokens=token_estimate(result or {"error": error}),
        metadata={"deployment_id": deployment_id, "artifact_id": artifact_id, "status": status},
    )
    return model_deployment_row(row)


def list_model_deployments(project_id: str | None = None, limit: int = 100, status: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(int(limit), 1), 500)
    where = "WHERE project_id = ?"
    params: list[Any] = [project_id]
    if status:
        where += " AND status = ?"
        params.append(status.upper())
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM model_deployments {where} ORDER BY created_at DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
    return {"project_id": project_id, "count": len(rows), "results": [model_deployment_row(row) for row in rows]}


def get_model_deployment(deployment_id: str, project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM model_deployments WHERE id = ? AND project_id = ?",
            (deployment_id, project_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Model deployment not found")
    return model_deployment_row(row)


def _latest_ready_model_artifact_for_job(project_id: str, job_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT * FROM model_artifacts
            WHERE project_id = ?
              AND fine_tuning_job_id = ?
              AND status = 'READY'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (project_id, job_id),
        ).fetchone()
    return model_artifact_row(row) if row else None


def _latest_succeeded_deployment_for_artifact(project_id: str, artifact_id: str, environment: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT * FROM model_deployments
            WHERE project_id = ?
              AND artifact_id = ?
              AND environment = ?
              AND status = 'SUCCEEDED'
            ORDER BY completed_at DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (project_id, artifact_id, environment),
        ).fetchone()
    return model_deployment_row(row) if row else None


SHADOW_SETTING_KEYS = (
    "shadow_mode_enabled",
    "shadow_provider",
    "shadow_model",
    "shadow_adapter_url",
    "shadow_timeout",
    "shadow_promotion_enabled",
    "shadow_promotion_gate_passed",
    "shadow_promotion_min_confidence",
    "shadow_canary_enabled",
    "shadow_canary_min_reviews",
    "shadow_canary_min_precision",
    "shadow_canary_min_confidence",
)


def _shadow_settings_snapshot(settings: dict[str, Any]) -> dict[str, Any]:
    return {key: settings.get(key) for key in SHADOW_SETTING_KEYS}


def _adapter_url_from_deployment(
    deployment: dict[str, Any],
    artifact: dict[str, Any],
    payload: dict[str, Any],
) -> str:
    candidates: list[dict[str, Any]] = []
    candidates.append(payload)
    result = deployment.get("result") if isinstance(deployment.get("result"), dict) else {}
    deployer_response = result.get("deployer_response") if isinstance(result.get("deployer_response"), dict) else {}
    candidates.extend([deployer_response, result])
    metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {}
    candidates.append(metadata)
    for item in candidates:
        for key in ("shadow_adapter_url", "adapter_url", "adapter_eval_url", "endpoint_url", "endpoint", "url"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def activate_model_deployment(
    deployment_id: str,
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    project_id = project_id or current_project_id()
    deployment = get_model_deployment(deployment_id, project_id=project_id)
    if deployment["status"] != "SUCCEEDED":
        raise HTTPException(status_code=409, detail="Model deployment must be SUCCEEDED before activation")
    artifact = get_model_artifact(str(deployment["artifact_id"]), project_id=project_id)
    mode = str(payload.get("mode") or "shadow").strip().lower()
    if mode not in {"shadow", "canary"}:
        raise HTTPException(status_code=400, detail="mode must be shadow or canary")

    before = get_project_settings(project_id)
    adapter_url = _adapter_url_from_deployment(deployment, artifact, payload)
    provider = str(payload.get("shadow_provider") or payload.get("provider") or ("http" if adapter_url else "local")).strip()
    model = str(payload.get("shadow_model") or payload.get("model") or deployment.get("adapter_model") or artifact.get("adapter_model")).strip()
    updates: dict[str, Any] = {
        "shadow_mode_enabled": bool(payload.get("shadow_mode_enabled", payload.get("enable_shadow", True))),
        "shadow_provider": provider or "local",
        "shadow_model": model or "deployed-memory-adapter",
        "shadow_adapter_url": adapter_url,
    }
    if payload.get("shadow_timeout") is not None or payload.get("timeout") is not None:
        updates["shadow_timeout"] = _float_or(payload.get("shadow_timeout", payload.get("timeout")), 5.0)

    enable_canary = bool(payload.get("shadow_canary_enabled", payload.get("enable_canary", mode == "canary")))
    enable_promotion = bool(payload.get("shadow_promotion_enabled", payload.get("enable_promotion", enable_canary)))
    if enable_promotion:
        updates["shadow_promotion_enabled"] = True
        updates["shadow_promotion_gate_passed"] = bool(payload.get("shadow_promotion_gate_passed", payload.get("gate_passed", True)))
    if payload.get("shadow_promotion_min_confidence") is not None:
        updates["shadow_promotion_min_confidence"] = _float_or(payload.get("shadow_promotion_min_confidence"), 0.8)
    if enable_canary:
        updates["shadow_canary_enabled"] = True
    for key, default in (
        ("shadow_canary_min_reviews", 5),
        ("shadow_canary_min_precision", 0.9),
        ("shadow_canary_min_confidence", 0.95),
    ):
        if payload.get(key) is not None:
            updates[key] = _float_or(payload.get(key), default) if "precision" in key or "confidence" in key else _int_or(payload.get(key), default)

    before_snapshot = _shadow_settings_snapshot(before)
    after = update_project_settings(project_id, updates)
    after_snapshot = _shadow_settings_snapshot(after)
    activation_id = str(new_id("activation"))
    activated_at = utc_now()
    activation = {
        "id": activation_id,
        "mode": mode,
        "project_id": project_id,
        "deployment_id": deployment_id,
        "artifact_id": artifact["id"],
        "adapter_model": deployment.get("adapter_model") or artifact.get("adapter_model"),
        "updates": updates,
        "activated_at": activated_at,
    }
    metadata = deployment.get("metadata") if isinstance(deployment.get("metadata"), dict) else {}
    metadata["activation"] = activation
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO model_activation_history (
                id, project_id, deployment_id, artifact_id, mode, status,
                settings_before, settings_after, metadata, activated_at, rolled_back_at, rollback_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activation_id,
                project_id,
                deployment_id,
                artifact["id"],
                mode,
                "ACTIVE",
                json_dumps(before_snapshot),
                json_dumps(after_snapshot),
                json_dumps({"adapter_model": activation["adapter_model"], "updates": updates}),
                activated_at,
                None,
                "",
            ),
        )
        conn.execute(
            "UPDATE model_deployments SET metadata = ?, updated_at = ? WHERE id = ? AND project_id = ?",
            (json_dumps(metadata), activated_at, deployment_id, project_id),
        )
    activated_deployment = get_model_deployment(deployment_id, project_id=project_id)
    activation_record = get_model_activation(activation_id, project_id=project_id)
    record_usage(
        project_id,
        "model_deployment_activation",
        input_tokens=token_estimate({"deployment_id": deployment_id, "payload": payload}),
        output_tokens=token_estimate(updates),
        metadata={"activation_id": activation_id, "deployment_id": deployment_id, "artifact_id": artifact["id"], "mode": mode},
    )
    return {
        "project_id": project_id,
        "activation_id": activation_id,
        "activation": activation_record,
        "deployment": activated_deployment,
        "artifact": artifact,
        "mode": mode,
        "settings_before": before_snapshot,
        "settings_after": after_snapshot,
        "updated_settings": updates,
    }


def list_model_activations(project_id: str | None = None, limit: int = 100, status: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(int(limit), 1), 500)
    where = "WHERE project_id = ?"
    params: list[Any] = [project_id]
    if status:
        where += " AND status = ?"
        params.append(status.upper())
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM model_activation_history {where} ORDER BY activated_at DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
    return {"project_id": project_id, "count": len(rows), "results": [model_activation_history_row(row) for row in rows]}


def get_model_activation(activation_id: str, project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM model_activation_history WHERE id = ? AND project_id = ?",
            (activation_id, project_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Model activation not found")
    return model_activation_history_row(row)


def rollback_model_activation(
    activation_id: str,
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    project_id = project_id or current_project_id()
    activation = get_model_activation(activation_id, project_id=project_id)
    if activation["status"] != "ACTIVE":
        raise HTTPException(status_code=409, detail="Model activation is already rolled back")
    rollback_settings = activation["settings_before"]
    after = update_project_settings(project_id, rollback_settings)
    rolled_back_at = utc_now()
    reason = str(payload.get("reason") or payload.get("rollback_reason") or "").strip()
    metadata = activation.get("metadata") if isinstance(activation.get("metadata"), dict) else {}
    metadata["rollback"] = {"rolled_back_at": rolled_back_at, "reason": reason}
    with get_db() as conn:
        conn.execute(
            """
            UPDATE model_activation_history
            SET status = 'ROLLED_BACK', metadata = ?, rolled_back_at = ?, rollback_reason = ?
            WHERE id = ? AND project_id = ?
            """,
            (json_dumps(metadata), rolled_back_at, reason, activation_id, project_id),
        )
    rolled_back = get_model_activation(activation_id, project_id=project_id)
    record_usage(
        project_id,
        "model_deployment_rollback",
        input_tokens=token_estimate({"activation_id": activation_id, "reason": reason}),
        output_tokens=token_estimate(rollback_settings),
        metadata={"activation_id": activation_id, "deployment_id": activation["deployment_id"]},
    )
    return {
        "project_id": project_id,
        "activation": rolled_back,
        "settings_after": _shadow_settings_snapshot(after),
        "rolled_back": True,
    }


def model_activation_health(
    activation_id: str,
    project_id: str | None = None,
    probe_adapter: bool = False,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    activation = get_model_activation(activation_id, project_id=project_id)
    deployment = get_model_deployment(activation["deployment_id"], project_id=project_id)
    artifact = get_model_artifact(activation["artifact_id"], project_id=project_id)
    current = _shadow_settings_snapshot(get_project_settings(project_id))
    expected = activation["settings_after"]
    drifted_keys = sorted(key for key, value in expected.items() if current.get(key) != value)
    checks = {
        "activation_active": activation["status"] == "ACTIVE",
        "deployment_succeeded": deployment["status"] == "SUCCEEDED",
        "artifact_ready": artifact["status"] == "READY",
        "settings_match": not drifted_keys,
    }
    probe: dict[str, Any] | None = None
    if probe_adapter:
        settings = _shadow_settings(project_id)
        response = _call_shadow_adapter(
            "health",
            {"activation": activation, "deployment": deployment, "artifact": artifact},
            settings,
        )
        if response is None:
            probe = {"external": False, "skipped": True, "reason": "no_external_adapter"}
        else:
            probe = response
        checks["adapter_probe"] = bool(probe and probe.get("external") and not probe.get("fallback"))
    healthy = all(checks.values())
    status = "HEALTHY" if healthy else "DRIFTED"
    if activation["status"] != "ACTIVE":
        status = "INACTIVE"
    elif deployment["status"] != "SUCCEEDED" or artifact["status"] != "READY":
        status = "FAILED"
    return {
        "project_id": project_id,
        "activation_id": activation_id,
        "status": status,
        "healthy": healthy,
        "checks": checks,
        "drifted_keys": drifted_keys,
        "expected_settings": expected,
        "current_settings": current,
        "adapter_probe": probe,
        "activation": activation,
        "deployment": deployment,
        "artifact": artifact,
    }


def _latest_active_model_activation(project_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT * FROM model_activation_history
            WHERE project_id = ? AND status = 'ACTIVE'
            ORDER BY activated_at DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    return model_activation_history_row(row) if row else None


def _latest_rolled_back_model_activation(project_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT * FROM model_activation_history
            WHERE project_id = ? AND status = 'ROLLED_BACK' AND rolled_back_at IS NOT NULL
            ORDER BY rolled_back_at DESC, activated_at DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    return model_activation_history_row(row) if row else None


def _activation_rollback_override_for(
    project_id: str,
    activation_id: str,
    rolled_back_at: str,
) -> dict[str, Any] | None:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM proposals
            WHERE project_id = ?
              AND proposal_type = 'activation_rollback_override'
              AND status = 'APPLIED'
            ORDER BY reviewed_at DESC, updated_at DESC
            LIMIT 100
            """,
            (project_id,),
        ).fetchall()
    for row in rows:
        proposal = proposal_row(row)
        payload = proposal.get("payload") if isinstance(proposal.get("payload"), dict) else {}
        reviewed_at = str(proposal.get("reviewed_at") or proposal.get("updated_at") or "")
        if payload.get("activation_id") == activation_id and (not rolled_back_at or reviewed_at >= rolled_back_at):
            return proposal
    return None


def _activation_rollback_gate(project_id: str) -> dict[str, Any] | None:
    rollback = _latest_rolled_back_model_activation(project_id)
    if not rollback:
        return None
    active = _latest_active_model_activation(project_id)
    rollback_at = str(rollback.get("rolled_back_at") or rollback.get("activated_at") or "")
    active_at = str(active.get("activated_at") or "") if active else ""
    blocked_without_override = bool(not active or not active_at or (rollback_at and active_at <= rollback_at))
    override = None
    if blocked_without_override:
        override = _activation_rollback_override_for(project_id, rollback["id"], rollback_at)
    blocked = bool(blocked_without_override and not override)
    return {
        "blocked": blocked,
        "reason": "latest_activation_rolled_back" if blocked else ("override_applied" if override else "newer_activation_active"),
        "activation_id": rollback["id"],
        "deployment_id": rollback["deployment_id"],
        "artifact_id": rollback["artifact_id"],
        "rolled_back_at": rollback.get("rolled_back_at"),
        "rollback_reason": rollback.get("rollback_reason"),
        "latest_active_activation_id": active["id"] if active else None,
        "latest_active_activated_at": active.get("activated_at") if active else None,
        "override_id": override["id"] if override else None,
        "override_applied_at": override.get("reviewed_at") if override else None,
    }


def _active_activation_health(project_id: str) -> dict[str, Any] | None:
    activation = _latest_active_model_activation(project_id)
    if not activation:
        return None
    return model_activation_health(activation["id"], project_id=project_id)


def _latest_fine_tuning_job(project_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT * FROM fine_tuning_jobs
            WHERE project_id = ? AND status = 'SUCCEEDED'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    return fine_tuning_job_row(row) if row else None


def _adapter_eval_job_context(payload: dict[str, Any], project_id: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    job_id = payload.get("fine_tuning_job_id") or payload.get("fineTuningJobId") or payload.get("job_id")
    if not job_id:
        return payload, None
    job = get_fine_tuning_job(str(job_id), project_id=project_id)
    if job["status"] != "SUCCEEDED":
        raise HTTPException(status_code=409, detail="Fine-tuning job must be SUCCEEDED before adapter eval")
    merged = dict(payload)
    merged["fine_tuning_job_id"] = job["id"]
    if not (merged.get("adapter_model") or merged.get("model")):
        merged["adapter_model"] = job.get("adapter_model")
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    adapter_url = result.get("adapter_eval_url") or result.get("adapter_url")
    if adapter_url and not (merged.get("adapter_url") or merged.get("url")):
        merged["adapter_url"] = adapter_url
    return merged, {
        "id": job["id"],
        "status": job["status"],
        "provider": job["provider"],
        "adapter_model": job["adapter_model"],
        "dataset_count": job["dataset_count"],
        "approval_id": job["approval_id"],
    }


def _training_trace_sources(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("sources", payload.get("source", "all"))
    if raw in (None, "", "all", ["all"]):
        return sorted(TRACE_EXPORT_SOURCES)
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",")]
    elif isinstance(raw, list):
        values = [str(item).strip() for item in raw]
    else:
        raise HTTPException(status_code=400, detail="sources must be a list, comma-separated string, or all")
    sources = [item for item in values if item]
    unknown = sorted(set(sources) - TRACE_EXPORT_SOURCES)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown training trace source(s): {', '.join(unknown)}")
    return sources or sorted(TRACE_EXPORT_SOURCES)


def _trace_scope(item: dict[str, Any]) -> dict[str, Any]:
    return {field: item.get(field) for field in ENTITY_FIELDS if item.get(field) is not None}


def export_training_traces(payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    payload = payload or {}
    project_id = payload.get("project_id") or project_id or current_project_id()
    requested_version = str(payload.get("dataset_version") or payload.get("version") or "").strip()
    if requested_version and requested_version != TRACE_DATASET_VERSION:
        raise HTTPException(status_code=400, detail=f"Unsupported training trace dataset_version: {requested_version}")
    limit = min(max(int(payload.get("limit") or 100), 1), 1000)
    sources = _training_trace_sources(payload)
    status_filter = str(payload.get("status") or "").upper() or None
    family_filter = str(payload.get("family") or "").strip().lower() or None
    redaction_rules = _trace_redaction_rules(payload, project_id)
    redaction_terms = redaction_rules["deny_terms"]
    redaction_allow_terms = redaction_rules["allow_terms"]
    redaction_policy = _trace_redaction_policy(payload, project_id=project_id)
    redact = _trace_redaction_enabled(payload, project_id=project_id) or bool(redaction_terms)
    traces: list[dict[str, Any]] = []

    if "proposals" in sources:
        where = "WHERE project_id = ?"
        params: list[Any] = [project_id]
        if status_filter:
            where += " AND status = ?"
            params.append(status_filter)
        with get_db() as conn:
            rows = conn.execute(
                f"SELECT * FROM proposals {where} ORDER BY created_at DESC LIMIT ?",
                [*params, limit],
            ).fetchall()
        for row in rows:
            proposal = proposal_row(row)
            traces.append(
                {
                    "id": f"proposal:{proposal['id']}",
                    "source": "proposals",
                    "label": proposal["status"].lower(),
                    "input": {
                        "proposal_type": proposal["proposal_type"],
                        "payload": proposal["payload"],
                    },
                    "output": {
                        "result": proposal["result"],
                        "status": proposal["status"],
                        "review_reason": proposal["review_reason"],
                        "review_state": proposal["review_state"],
                    },
                    "metadata": {
                        "proposal_id": proposal["id"],
                        "proposal_type": proposal["proposal_type"],
                        "evidence_source": _proposal_evidence_source(proposal),
                    },
                    "created_at": proposal["created_at"],
                }
            )

    if "feedback" in sources:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT f.id, f.memory_id, f.feedback, f.feedback_reason, f.metadata AS feedback_metadata,
                       f.created_at, m.memory, m.user_id, m.agent_id, m.app_id, m.run_id,
                       m.metadata AS memory_metadata, m.categories
                  FROM feedback f
                  JOIN memories m ON m.id = f.memory_id
                 WHERE m.project_id = ?
                 ORDER BY f.created_at DESC
                 LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        for row in rows:
            memory = {
                "id": row["memory_id"],
                "memory": row["memory"],
                "metadata": json_loads(row["memory_metadata"], {}),
                "categories": json_loads(row["categories"], []),
                **{field: row[field] for field in ENTITY_FIELDS if row[field] is not None},
            }
            traces.append(
                {
                    "id": f"feedback:{row['id']}",
                    "source": "feedback",
                    "label": str(row["feedback"]).lower(),
                    "input": {"memory": memory},
                    "output": {"feedback": row["feedback"], "feedback_reason": row["feedback_reason"] or ""},
                    "metadata": {"feedback_id": row["id"], "memory_id": row["memory_id"], **json_loads(row["feedback_metadata"], {})},
                    "created_at": row["created_at"],
                }
            )

    if "evaluation_misses" in sources:
        where = "WHERE project_id = ?"
        params = [project_id]
        if status_filter:
            where += " AND status = ?"
            params.append(status_filter)
        with get_db() as conn:
            rows = conn.execute(
                f"SELECT * FROM evaluations {where} ORDER BY created_at DESC LIMIT ?",
                [*params, limit],
            ).fetchall()
        for row in rows:
            evaluation = evaluation_row(row)
            if family_filter and evaluation.get("family") != family_filter:
                continue
            for item in (evaluation.get("results", {}).get("items") or []):
                if item.get("matched") is not False:
                    continue
                traces.append(
                    {
                        "id": f"evaluation_miss:{evaluation['id']}:{item.get('index', 0)}",
                        "source": "evaluation_misses",
                        "label": "miss",
                        "input": {
                            "query": item.get("query"),
                            "expected_contains": item.get("expected_contains", []),
                            "not_expected_contains": item.get("not_expected_contains", []),
                            "expected_memory_ids": item.get("expected_memory_ids", []),
                        },
                        "output": {"results": item.get("results", []), "error": item.get("error")},
                        "metadata": {
                            "evaluation_id": evaluation["id"],
                            "evaluation_name": evaluation["name"],
                            "family": evaluation.get("family"),
                            "index": item.get("index", 0),
                            "metrics": evaluation.get("metrics", {}),
                        },
                        "created_at": evaluation["created_at"],
                    }
                )

    if "shadow_disagreements" in sources:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT * FROM events
                 WHERE project_id = ? AND event_type = 'JUDGMENT'
                 ORDER BY created_at DESC
                 LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        for row in rows:
            event = event_row(row)
            for index, decision in enumerate(event.get("results") or []):
                shadow = decision.get("shadow") if isinstance(decision, dict) else None
                if not isinstance(shadow, dict) or shadow.get("agrees_with_baseline", True):
                    continue
                traces.append(
                    {
                        "id": f"shadow_disagreement:{event['id']}:{index}",
                        "source": "shadow_disagreements",
                        "label": "disagreement",
                        "input": {
                            "candidate": decision.get("candidate"),
                            "scope": decision.get("scope", {}),
                            "baseline_decision": decision.get("decision"),
                            "baseline_output_memory": decision.get("output_memory"),
                            "baseline": {
                                "decision": decision.get("decision"),
                                "reason": decision.get("reason"),
                                "confidence": decision.get("confidence"),
                                "target_memory_ids": decision.get("target_memory_ids", []),
                                "risk_flags": decision.get("risk_flags", []),
                                "requires_review": decision.get("requires_review", False),
                                "evidence": decision.get("evidence"),
                                "output_memory": decision.get("output_memory"),
                            },
                        },
                        "output": {
                            "shadow": shadow,
                            "baseline_confidence": decision.get("confidence"),
                            "baseline_risk_flags": decision.get("risk_flags", []),
                            "baseline_requires_review": decision.get("requires_review", False),
                        },
                        "metadata": {
                            "event_id": event["id"],
                            "index": index,
                            "shadow_confidence": shadow.get("confidence"),
                            "baseline_confidence": decision.get("confidence"),
                            "baseline_target_memory_ids": decision.get("target_memory_ids", []),
                            "baseline_evidence_schema": (
                                decision.get("evidence", {}).get("schema_version")
                                if isinstance(decision.get("evidence"), dict)
                                else None
                            ),
                        },
                        "created_at": event["created_at"],
                    }
                )

    traces.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    traces = traces[:limit]
    if redact:
        traces = _redact_trace_value(traces, redaction_terms, redaction_allow_terms, redaction_policy)
    source_counts: dict[str, int] = {}
    for trace in traces:
        source_counts[trace["source"]] = source_counts.get(trace["source"], 0) + 1
    redaction = {
        "enabled": redact,
        "policy": redaction_policy if redact else "none",
        "term_count": len(redaction_terms) if redact else 0,
        "deny_term_count": len(redaction_terms) if redact else 0,
        "allow_term_count": len(redaction_allow_terms) if redact else 0,
    }
    audit_id = _record_training_trace_audit(
        project_id,
        sources,
        {"status": status_filter, "family": family_filter, "limit": limit, "dataset_version": TRACE_DATASET_VERSION},
        redaction,
        len(traces),
        source_counts,
        redaction_terms,
        redaction_allow_terms,
    )
    result = {
        "project_id": project_id,
        "dataset_version": TRACE_DATASET_VERSION,
        "audit_id": audit_id,
        "sources": sources,
        "redaction": redaction,
        "count": len(traces),
        "source_counts": source_counts,
        "results": traces,
    }
    return result


def _safe_adapter_eval_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sensitive = {"adapter_api_key", "adapterApiKey", "api_key", "apiKey", "authorization", "token"}
    return {key: value for key, value in payload.items() if key not in sensitive}


def _normalize_trace_label(value: Any) -> str:
    return re.sub(r"\s+", "_", str(value or "").strip().lower())


def _model_adapter_prediction(
    trace: dict[str, Any],
    labels: list[str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    adapter_url = str(payload.get("adapter_url") or payload.get("url") or "").strip()
    adapter_model = str(payload.get("adapter_model") or payload.get("model") or "").strip()
    if not adapter_url:
        return {
            "label": _normalize_trace_label(trace.get("label")),
            "confidence": 1.0,
            "reason": "local_trace_label_baseline",
            "external": False,
        }

    headers = {"Content-Type": "application/json"}
    api_key = payload.get("adapter_api_key") or payload.get("api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    timeout = _float_or(payload.get("timeout"), 10.0)
    request_payload = {
        "task": "training_trace_eval",
        "dataset_version": TRACE_DATASET_VERSION,
        "labels": labels,
        "adapter_model": adapter_model or None,
        "trace": trace,
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(adapter_url, headers=headers, json=request_payload)
        response.raise_for_status()
        data = response.json()
    label = data.get("label") or data.get("prediction") or data.get("decision")
    return {
        "label": _normalize_trace_label(label),
        "confidence": _float_or(data.get("confidence"), 0.0),
        "reason": str(data.get("reason") or "external_model_adapter"),
        "external": True,
    }


def _evaluate_model_adapter(
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
    *,
    event_type: str = "MODEL_ADAPTER_EVAL",
    usage_operation: str = "model_adapter_eval",
) -> dict[str, Any]:
    payload = payload or {}
    project_id = payload.get("project_id") or project_id or current_project_id()
    payload, fine_tuning_job = _adapter_eval_job_context(payload, project_id)
    started_at = utc_now()
    start_time = time.perf_counter()
    event_id = create_event(
        event_type,
        _safe_adapter_eval_payload(payload),
        {"dataset_version": TRACE_DATASET_VERSION},
        project_id=project_id,
    )
    trace_payload = {
        "limit": payload.get("limit") or 100,
        "sources": payload.get("sources") or payload.get("source") or ["feedback", "proposals", "evaluation_misses", "shadow_disagreements"],
        "status": payload.get("status"),
        "family": payload.get("family"),
        "dataset_version": payload.get("dataset_version") or payload.get("version") or TRACE_DATASET_VERSION,
        "redact": payload.get("redact", True),
        "redaction_policy": payload.get("redaction_policy") or payload.get("redactionPolicy"),
        "redaction_terms": payload.get("redaction_terms") or payload.get("redactionTerms"),
        "redaction_deny_terms": payload.get("redaction_deny_terms") or payload.get("redactionDenyTerms"),
        "redaction_allow_terms": payload.get("redaction_allow_terms") or payload.get("redactionAllowTerms"),
    }
    trace_export = export_training_traces(trace_payload, project_id=project_id)
    traces = trace_export["results"]
    labels = sorted({_normalize_trace_label(trace.get("label")) for trace in traces if trace.get("label")})
    results = []
    matched_count = 0
    for trace in traces:
        expected = _normalize_trace_label(trace.get("label"))
        try:
            prediction = _model_adapter_prediction(trace, labels, payload)
            predicted = prediction["label"]
            error = ""
        except Exception as exc:
            prediction = {"label": "", "confidence": 0.0, "reason": "adapter_error", "external": bool(payload.get("adapter_url"))}
            predicted = ""
            error = str(exc)
        matched = bool(expected and predicted == expected)
        matched_count += 1 if matched else 0
        result = {
            "trace_id": trace.get("id"),
            "source": trace.get("source"),
            "expected_label": expected,
            "predicted_label": predicted,
            "matched": matched,
            "confidence": prediction.get("confidence", 0.0),
            "reason": prediction.get("reason", ""),
            "external": bool(prediction.get("external")),
        }
        if error:
            result["error"] = error
        results.append(result)
    total = len(results)
    metrics = {
        "accuracy": round(matched_count / total, 4) if total else 0,
        "matched_count": matched_count,
        "item_count": total,
        "label_count": len(labels),
        "external": bool(payload.get("adapter_url") or payload.get("url")),
    }
    complete_event(event_id, "SUCCEEDED", results, started_at, start_time)
    response = {
        "id": event_id,
        "project_id": project_id,
        "name": payload.get("name") or "model_adapter_trace_eval",
        "dataset_version": TRACE_DATASET_VERSION,
        "adapter_model": payload.get("adapter_model") or payload.get("model") or ("external" if metrics["external"] else "local_trace_label_baseline"),
        "fine_tuning_job": fine_tuning_job,
        "labels": labels,
        "metrics": metrics,
        "trace_export": {
            "count": trace_export["count"],
            "sources": trace_export["sources"],
            "redaction": trace_export["redaction"],
            "source_counts": trace_export["source_counts"],
        },
        "results": results,
    }
    record_usage(
        project_id,
        usage_operation,
        input_tokens=token_estimate(trace_payload),
        output_tokens=token_estimate(response),
        metadata={"event_id": event_id, "dataset_version": TRACE_DATASET_VERSION, "fine_tuning_job_id": fine_tuning_job["id"] if fine_tuning_job else None},
    )
    return response


def evaluate_model_adapter(payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    return _evaluate_model_adapter(payload, project_id)


def _normalize_adapter_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(candidate)
    aliases = {
        "adapterUrl": "adapter_url",
        "adapterModel": "adapter_model",
        "adapterApiKey": "adapter_api_key",
        "fineTuningJobId": "fine_tuning_job_id",
        "jobId": "fine_tuning_job_id",
        "datasetVersion": "dataset_version",
        "redactionPolicy": "redaction_policy",
        "redactionTerms": "redaction_terms",
        "redactionDenyTerms": "redaction_deny_terms",
        "redactionAllowTerms": "redaction_allow_terms",
        "includeResults": "include_results",
    }
    for alias, canonical in aliases.items():
        if alias in normalized and canonical not in normalized:
            normalized[canonical] = normalized[alias]
    return normalized


def _adapter_candidate_name(candidate: dict[str, Any]) -> str:
    name = (
        candidate.get("name")
        or candidate.get("adapter_model")
        or candidate.get("model")
        or candidate.get("fine_tuning_job_id")
    )
    if not name:
        name = "external_adapter" if candidate.get("adapter_url") or candidate.get("url") else "deterministic_baseline"
    return str(name).strip() or "adapter_candidate"


def _is_baseline_adapter_candidate(candidate: dict[str, Any]) -> bool:
    return not any(
        candidate.get(key)
        for key in (
            "adapter_url",
            "url",
            "adapter_model",
            "model",
            "fine_tuning_job_id",
            "job_id",
        )
    )


def compare_model_adapters(payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    payload = payload or {}
    project_id = payload.get("project_id") or project_id or current_project_id()
    raw_candidates = payload.get("candidates", payload.get("adapters", payload.get("models", [])))
    if isinstance(raw_candidates, dict):
        raw_candidates = [raw_candidates]
    if not isinstance(raw_candidates, list):
        raise HTTPException(status_code=400, detail="candidates must be a list of adapter candidate objects")
    candidates: list[dict[str, Any]] = []
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            raise HTTPException(status_code=400, detail="each adapter candidate must be an object")
        candidates.append(_normalize_adapter_candidate(raw_candidate))
    include_baseline = _bool_or(payload.get("include_baseline", payload.get("includeBaseline")), True)
    if include_baseline and not any(_is_baseline_adapter_candidate(candidate) for candidate in candidates):
        candidates.insert(0, {"name": "deterministic_baseline"})
    if not candidates:
        raise HTTPException(status_code=400, detail="at least one adapter candidate is required")

    comparison_name = str(payload.get("name") or "model_adapter_comparison").strip() or "model_adapter_comparison"
    trace_filters = {
        "limit": payload.get("limit") or 100,
        "sources": payload.get("sources") or payload.get("source") or ["feedback", "proposals", "evaluation_misses", "shadow_disagreements"],
        "status": payload.get("status"),
        "family": payload.get("family"),
        "dataset_version": payload.get("dataset_version") or payload.get("datasetVersion") or payload.get("version") or TRACE_DATASET_VERSION,
        "redact": payload.get("redact", True),
        "redaction_policy": payload.get("redaction_policy") or payload.get("redactionPolicy"),
        "redaction_terms": payload.get("redaction_terms") or payload.get("redactionTerms"),
        "redaction_deny_terms": payload.get("redaction_deny_terms") or payload.get("redactionDenyTerms"),
        "redaction_allow_terms": payload.get("redaction_allow_terms") or payload.get("redactionAllowTerms"),
    }
    trace_filters = {key: value for key, value in trace_filters.items() if value is not None}
    include_results = _bool_or(payload.get("include_results", payload.get("includeResults")), False)
    safe_candidates = [
        _safe_adapter_eval_payload({"name": _adapter_candidate_name(candidate), **candidate})
        for candidate in candidates
    ]
    started_at = utc_now()
    start_time = time.perf_counter()
    comparison_event_id = create_event(
        "MODEL_ADAPTER_COMPARISON",
        {
            "schema_version": MODEL_ADAPTER_COMPARISON_SCHEMA_VERSION,
            "name": comparison_name,
            "trace_filters": _safe_adapter_eval_payload(trace_filters),
            "candidates": safe_candidates,
        },
        {"dataset_version": TRACE_DATASET_VERSION},
        project_id=project_id,
    )

    results = []
    for index, candidate in enumerate(candidates):
        candidate_name = _adapter_candidate_name(candidate)
        eval_payload = {**trace_filters, **candidate, "name": f"{comparison_name}:{candidate_name}"}
        evaluation = _evaluate_model_adapter(
            eval_payload,
            project_id=project_id,
            event_type="MODEL_ADAPTER_COMPARISON_CANDIDATE_EVAL",
            usage_operation="model_adapter_comparison_candidate_eval",
        )
        fine_tuning_job = evaluation.get("fine_tuning_job") if isinstance(evaluation.get("fine_tuning_job"), dict) else None
        item = {
            "candidate": _safe_adapter_eval_payload({"name": candidate_name, **candidate}),
            "candidate_name": candidate_name,
            "evaluation_id": evaluation["id"],
            "adapter_model": evaluation.get("adapter_model"),
            "fine_tuning_job_id": fine_tuning_job.get("id") if fine_tuning_job else None,
            "metrics": evaluation["metrics"],
            "labels": evaluation["labels"],
            "trace_export": evaluation["trace_export"],
            "_index": index,
        }
        if include_results:
            item["results"] = evaluation["results"]
        results.append(item)

    ranked = sorted(
        results,
        key=lambda item: (
            -_float_or(item["metrics"].get("accuracy"), 0.0),
            -_int_or(item["metrics"].get("matched_count"), 0),
            -_int_or(item["metrics"].get("item_count"), 0),
            str(item["candidate_name"]),
            item["_index"],
        ),
    )
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
        item.pop("_index", None)
    response = {
        "schema_version": MODEL_ADAPTER_COMPARISON_SCHEMA_VERSION,
        "id": comparison_event_id,
        "project_id": project_id,
        "name": comparison_name,
        "dataset_version": TRACE_DATASET_VERSION,
        "trace_filters": _safe_adapter_eval_payload(trace_filters),
        "candidate_count": len(ranked),
        "best_candidate": ranked[0] if ranked else None,
        "results": ranked,
        "evaluation_ids": [item["evaluation_id"] for item in ranked],
    }
    complete_event(comparison_event_id, "SUCCEEDED", response, started_at, start_time)
    record_usage(
        project_id,
        "model_adapter_comparison",
        input_tokens=token_estimate({"trace_filters": trace_filters, "candidates": safe_candidates}),
        output_tokens=token_estimate(response),
        metadata={"event_id": comparison_event_id, "candidate_count": len(ranked), "dataset_version": TRACE_DATASET_VERSION},
    )
    return response


def _latest_model_adapter_eval(project_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT * FROM events
            WHERE project_id = ?
              AND event_type = 'MODEL_ADAPTER_EVAL'
              AND status = 'SUCCEEDED'
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    if not row:
        return None
    event = event_row(row)
    results = event.get("results") if isinstance(event.get("results"), list) else []
    item_count = len(results)
    matched_count = sum(1 for result in results if isinstance(result, dict) and result.get("matched"))
    labels = sorted(
        {
            str(result.get("expected_label"))
            for result in results
            if isinstance(result, dict) and result.get("expected_label")
        }
    )
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    external = bool(payload.get("adapter_url") or payload.get("url")) or any(
        isinstance(result, dict) and result.get("external") for result in results
    )
    return {
        "id": event["id"],
        "project_id": event["project_id"],
        "created_at": event["created_at"],
        "updated_at": event["updated_at"],
        "dataset_version": metadata.get("dataset_version") or TRACE_DATASET_VERSION,
        "fine_tuning_job_id": payload.get("fine_tuning_job_id") or metadata.get("fine_tuning_job_id"),
        "adapter_model": payload.get("adapter_model")
        or payload.get("model")
        or ("external" if external else "local_trace_label_baseline"),
        "labels": labels,
        "metrics": {
            "accuracy": round(matched_count / item_count, 4) if item_count else 0,
            "matched_count": matched_count,
            "item_count": item_count,
            "label_count": len(labels),
            "external": external,
        },
    }


PROMOTION_BLOCKER_REVIEWABLE_CODES = {
    "benchmark_regression",
    "benchmark_accuracy_below_threshold",
    "shadow_blocked_proposals",
    "shadow_rollbacks_present",
}


def promotion_blocker_review_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "blocker_code": row["blocker_code"],
        "blocker_key": row["blocker_key"],
        "reviewer_id": row["reviewer_id"],
        "decision": row["decision"],
        "reason": row["reason"] or "",
        "blocker_snapshot": json_loads(row["blocker_snapshot"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _promotion_blocker_review_state(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    latest = reviews[0] if reviews else None
    status = latest["decision"] if latest else "OPEN"
    return {
        "status": status,
        "resolved": status in {"ACKNOWLEDGED", "RESOLVED", "WAIVED"},
        "review_count": len(reviews),
        "latest_review": latest,
        "reviews": reviews,
    }


def _promotion_blocker_signature_payload(blocker: dict[str, Any]) -> dict[str, Any]:
    excluded = {"message", "review_key", "review_state", "reviewable"}
    return {key: value for key, value in blocker.items() if key not in excluded}


def _promotion_blocker_key(blocker: dict[str, Any]) -> str:
    return content_hash(
        "promotion-blocker",
        str(blocker.get("code") or ""),
        json_dumps(_promotion_blocker_signature_payload(blocker)),
    )[:16]


def _promotion_blocker_reviews_for(project_id: str, blockers: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    blocker_keys = {
        (str(blocker.get("code") or ""), str(blocker.get("review_key") or ""))
        for blocker in blockers
        if blocker.get("reviewable") and blocker.get("review_key")
    }
    if not blocker_keys:
        return {}
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM promotion_blocker_reviews
            WHERE project_id = ?
            ORDER BY updated_at DESC
            LIMIT 500
            """,
            (project_id,),
        ).fetchall()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (row["blocker_code"], row["blocker_key"])
        if key in blocker_keys:
            grouped.setdefault(key, []).append(promotion_blocker_review_row(row))
    return grouped


def _annotate_promotion_blockers(project_id: str, blockers: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    annotated = []
    for blocker in blockers:
        item = dict(blocker)
        item["reviewable"] = item.get("code") in PROMOTION_BLOCKER_REVIEWABLE_CODES
        item["review_key"] = _promotion_blocker_key(item)
        annotated.append(item)
    reviews_by_key = _promotion_blocker_reviews_for(project_id, annotated)
    open_blockers = []
    reviewed_blockers = []
    for blocker in annotated:
        reviews = reviews_by_key.get((blocker["code"], blocker["review_key"]), [])
        blocker["review_state"] = _promotion_blocker_review_state(reviews)
        if blocker["reviewable"] and blocker["review_state"]["resolved"]:
            reviewed_blockers.append(blocker)
        else:
            open_blockers.append(blocker)
    return {"raw_blockers": annotated, "blockers": open_blockers, "reviewed_blockers": reviewed_blockers}


def _normalize_promotion_blocker_review_decision(value: Any) -> str:
    decision = str(value or "WAIVE").strip().upper()
    if decision in {"ACK", "ACKNOWLEDGE", "ACKNOWLEDGED"}:
        return "ACKNOWLEDGED"
    if decision in {"RESOLVE", "RESOLVED"}:
        return "RESOLVED"
    if decision in {"WAIVE", "WAIVED"}:
        return "WAIVED"
    if decision in {"REOPEN", "REOPENED"}:
        return "REOPENED"
    raise HTTPException(status_code=400, detail="decision must be ACKNOWLEDGE, RESOLVE, WAIVE, or REOPEN")


def _promotion_report_filters_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "limit": "limit",
        "min_adapter_accuracy": "min_adapter_accuracy",
        "minAdapterAccuracy": "min_adapter_accuracy",
        "min_benchmark_accuracy": "min_benchmark_accuracy",
        "minBenchmarkAccuracy": "min_benchmark_accuracy",
        "min_context_accuracy": "min_context_accuracy",
        "minContextAccuracy": "min_context_accuracy",
        "min_shadow_precision": "min_shadow_precision",
        "minShadowPrecision": "min_shadow_precision",
        "min_shadow_reviews": "min_shadow_reviews",
        "minShadowReviews": "min_shadow_reviews",
        "require_self_improvement_ready": "require_self_improvement_ready",
        "requireSelfImprovementReady": "require_self_improvement_ready",
    }
    filters: dict[str, Any] = {}
    for source, target in mapping.items():
        if source in payload and payload[source] is not None:
            filters[target] = payload[source]
    return filters


def review_model_adapter_promotion_blocker(
    blocker_code: str,
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    payload = payload or {}
    blocker_code = str(blocker_code or payload.get("blocker_code") or payload.get("code") or "").strip()
    if not blocker_code:
        raise HTTPException(status_code=400, detail="blocker_code is required")
    report_filters = _promotion_report_filters_from_payload(payload)
    report = model_adapter_promotion_report(project_id=project_id, record=False, **report_filters)
    candidates = [blocker for blocker in report.get("raw_blockers", []) if blocker.get("code") == blocker_code]
    blocker_key = str(payload.get("blocker_key") or payload.get("review_key") or payload.get("key") or "").strip()
    if blocker_key:
        candidates = [blocker for blocker in candidates if blocker.get("review_key") == blocker_key]
    if not candidates:
        raise HTTPException(status_code=404, detail="Promotion blocker not found in current report")
    if len(candidates) > 1:
        raise HTTPException(status_code=400, detail="blocker_key is required when multiple blockers share the code")
    blocker = candidates[0]
    if not blocker.get("reviewable"):
        raise HTTPException(status_code=409, detail=f"{blocker_code} is a hard promotion gate and cannot be reviewed away")

    decision = _normalize_promotion_blocker_review_decision(payload.get("decision"))
    reviewer_id = str(payload.get("reviewer_id") or payload.get("reviewer") or "operator").strip()
    if not reviewer_id:
        raise HTTPException(status_code=400, detail="reviewer_id is required")
    reason = str(payload.get("reason") or payload.get("review_reason") or "")
    now = utc_now()
    with get_db() as conn:
        existing = conn.execute(
            """
            SELECT id FROM promotion_blocker_reviews
            WHERE project_id = ? AND blocker_code = ? AND blocker_key = ? AND reviewer_id = ?
            """,
            (project_id, blocker_code, blocker["review_key"], reviewer_id),
        ).fetchone()
        if existing:
            review_id = existing["id"]
            conn.execute(
                """
                UPDATE promotion_blocker_reviews
                   SET decision = ?, reason = ?, blocker_snapshot = ?, updated_at = ?
                 WHERE id = ? AND project_id = ?
                """,
                (decision, reason, json_dumps(blocker), now, review_id, project_id),
            )
        else:
            review_id = str(new_id("promotion_blocker_review"))
            conn.execute(
                """
                INSERT INTO promotion_blocker_reviews (
                    id, project_id, blocker_code, blocker_key, reviewer_id, decision,
                    reason, blocker_snapshot, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (review_id, project_id, blocker_code, blocker["review_key"], reviewer_id, decision, reason, json_dumps(blocker), now, now),
            )
        row = conn.execute(
            "SELECT * FROM promotion_blocker_reviews WHERE id = ? AND project_id = ?",
            (review_id, project_id),
        ).fetchone()
    updated_report = model_adapter_promotion_report(project_id=project_id, record=False, **report_filters)
    updated_blocker = next(
        (
            item
            for item in updated_report.get("raw_blockers", [])
            if item.get("code") == blocker_code and item.get("review_key") == blocker["review_key"]
        ),
        blocker,
    )
    review = promotion_blocker_review_row(row)
    record_usage(
        project_id,
        "promotion_blocker_review",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate(updated_blocker),
        metadata={"blocker_code": blocker_code, "blocker_key": blocker["review_key"], "decision": decision, "reviewer_id": reviewer_id},
    )
    return {
        "blocker_code": blocker_code,
        "blocker_key": blocker["review_key"],
        "review": review,
        "blocker": updated_blocker,
        "report": {
            "recommendation": updated_report["recommendation"],
            "can_promote": updated_report["can_promote"],
            "blocker_codes": [item.get("code") for item in updated_report.get("blockers", [])],
            "reviewed_blocker_count": len(updated_report.get("reviewed_blockers", [])),
        },
    }


def activate_model_adapter_promotion(
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    project_id = project_id or current_project_id()
    apply_changes = _bool_or(payload.get("apply"), False)
    report_filters = _promotion_report_filters_from_payload(payload)
    report = model_adapter_promotion_report(project_id=project_id, record=False, **report_filters)
    report_thresholds = report.get("thresholds") if isinstance(report.get("thresholds"), dict) else {}
    require_preflight_ready = _bool_or(payload.get("require_preflight_ready", payload.get("requirePreflightReady")), False)
    require_lora_ready = _bool_or(payload.get("require_lora_ready", payload.get("requireLoraReady")), False)
    include_preflight_details = _bool_or(
        payload.get("include_preflight_details", payload.get("includePreflightDetails")),
        False,
    )
    from .preflight import mem1_preflight_payload

    preflight = mem1_preflight_payload(
        project_id=project_id,
        limit=_int_or(report_thresholds.get("limit", report_filters.get("limit")), 100),
        min_adapter_accuracy=_float_or(
            report_thresholds.get("min_adapter_accuracy", report_filters.get("min_adapter_accuracy")),
            0.9,
        ),
        min_benchmark_accuracy=_float_or(
            report_thresholds.get("min_benchmark_accuracy", report_filters.get("min_benchmark_accuracy")),
            1.0,
        ),
        min_context_accuracy=_float_or(
            report_thresholds.get("min_context_accuracy", report_filters.get("min_context_accuracy")),
            1.0,
        ),
        min_shadow_precision=_float_or(
            report_thresholds.get("min_shadow_precision", report_filters.get("min_shadow_precision")),
            0.9,
        ),
        min_shadow_reviews=_int_or(
            report_thresholds.get("min_shadow_reviews", report_filters.get("min_shadow_reviews")),
            1,
        ),
        require_self_improvement_ready=_bool_or(
            report_thresholds.get("require_self_improvement_ready", report_filters.get("require_self_improvement_ready")),
            False,
        ),
        require_promotion_ready=require_preflight_ready,
        require_lora_ready=require_lora_ready,
        include_details=include_preflight_details,
    )
    preflight_blocked = require_preflight_ready and not preflight.get("ready")
    if not report.get("can_promote") or preflight_blocked:
        result = {
            "project_id": project_id,
            "status": "BLOCKED",
            "apply": apply_changes,
            "report": report,
            "blockers": report.get("blockers", []),
            "preflight": preflight,
            "preflight_blocker_codes": preflight.get("blocker_codes", []),
        }
        if apply_changes:
            message = "Preflight has open blockers" if preflight_blocked else "Promotion report has open blockers"
            raise HTTPException(status_code=409, detail={"message": message, **result})
        return result

    adapter_eval = report.get("adapter_eval") if isinstance(report.get("adapter_eval"), dict) else {}
    fine_tuning_job = report.get("fine_tuning_job") if isinstance(report.get("fine_tuning_job"), dict) else None
    linked_job_id = str(adapter_eval.get("fine_tuning_job_id") or "").strip()
    report_job_id = str((fine_tuning_job or {}).get("id") or "").strip()
    allow_unlinked_artifact = _bool_or(
        payload.get("allow_unlinked_artifact", payload.get("allowUnlinkedArtifact", False)),
        False,
    )
    artifact = None
    artifact_id = str(payload.get("artifact_id") or payload.get("artifactId") or "").strip()
    if artifact_id:
        artifact = get_model_artifact(artifact_id, project_id=project_id)
    else:
        if not linked_job_id:
            raise HTTPException(
                status_code=409,
                detail="Latest adapter eval is not linked to a fine-tuning job; pass fine_tuning_job_id to adapter eval or explicitly select an artifact with allow_unlinked_artifact=true",
            )
        artifact = _latest_ready_model_artifact_for_job(project_id, linked_job_id)
    if not artifact:
        raise HTTPException(status_code=409, detail="No READY model artifact found for the promoted adapter")
    if artifact["status"] != "READY":
        raise HTTPException(status_code=409, detail="Selected model artifact is not READY")
    artifact_job_id = str(artifact.get("fine_tuning_job_id") or "").strip()
    if linked_job_id and artifact_job_id != linked_job_id:
        raise HTTPException(status_code=409, detail="Selected model artifact does not match the evaluated fine-tuning job")
    if not linked_job_id and not allow_unlinked_artifact:
        raise HTTPException(
            status_code=409,
            detail="Latest adapter eval is not linked to a fine-tuning job; set allow_unlinked_artifact=true only for an explicit operator override",
        )
    provenance = {
        "adapter_eval_id": adapter_eval.get("id"),
        "adapter_eval_fine_tuning_job_id": linked_job_id or None,
        "report_fine_tuning_job_id": report_job_id or None,
        "artifact_id": artifact["id"],
        "artifact_fine_tuning_job_id": artifact_job_id or None,
        "linked": bool(linked_job_id and artifact_job_id == linked_job_id),
        "allow_unlinked_artifact": allow_unlinked_artifact,
    }

    environment = str(payload.get("environment") or "canary").strip()
    mode = str(payload.get("mode") or "canary").strip().lower()
    if mode not in {"shadow", "canary"}:
        raise HTTPException(status_code=400, detail="mode must be shadow or canary")
    reuse_deployment = _bool_or(payload.get("reuse_deployment"), True)
    deployment = None
    deployment_id = str(payload.get("deployment_id") or payload.get("deploymentId") or "").strip()
    if deployment_id:
        deployment = get_model_deployment(deployment_id, project_id=project_id)
    elif reuse_deployment:
        deployment = _latest_succeeded_deployment_for_artifact(project_id, artifact["id"], environment)
    deployment_action = "reuse" if deployment else "create"

    deployment_payload = {
        "environment": environment,
        "deployer_url": payload.get("deployer_url") or payload.get("deployerUrl"),
        "deployer_api_key": payload.get("deployer_api_key") or payload.get("deployerApiKey"),
        "timeout": payload.get("deployment_timeout") or payload.get("deploymentTimeout") or payload.get("timeout"),
        "metadata": {
            "source": "model_adapter_promotion",
            "report_recommendation": report.get("recommendation"),
            "adapter_eval_id": (report.get("adapter_eval") or {}).get("id") if isinstance(report.get("adapter_eval"), dict) else None,
        },
    }
    activation_payload = {
        "mode": mode,
        "shadow_adapter_url": payload.get("shadow_adapter_url") or payload.get("shadowAdapterUrl") or payload.get("adapter_url") or payload.get("adapterUrl"),
        "shadow_provider": payload.get("shadow_provider") or payload.get("shadowProvider") or payload.get("provider"),
        "shadow_model": payload.get("shadow_model") or payload.get("shadowModel") or payload.get("model") or artifact.get("adapter_model"),
        "shadow_timeout": payload.get("shadow_timeout") or payload.get("shadowTimeout"),
        "shadow_promotion_enabled": payload.get("shadow_promotion_enabled", payload.get("shadowPromotionEnabled", True)),
        "shadow_promotion_gate_passed": payload.get("shadow_promotion_gate_passed", payload.get("shadowPromotionGatePassed", True)),
        "shadow_promotion_min_confidence": payload.get("shadow_promotion_min_confidence") or payload.get("shadowPromotionMinConfidence"),
        "shadow_canary_enabled": payload.get("shadow_canary_enabled", payload.get("shadowCanaryEnabled", mode == "canary")),
        "shadow_canary_min_reviews": payload.get("shadow_canary_min_reviews") or payload.get("shadowCanaryMinReviews"),
        "shadow_canary_min_precision": payload.get("shadow_canary_min_precision") or payload.get("shadowCanaryMinPrecision"),
        "shadow_canary_min_confidence": payload.get("shadow_canary_min_confidence") or payload.get("shadowCanaryMinConfidence"),
    }
    activation_payload = {key: value for key, value in activation_payload.items() if value is not None}

    status = "READY"
    activation = None
    if apply_changes:
        if deployment is None:
            deployment = create_model_deployment(
                artifact["id"],
                {key: value for key, value in deployment_payload.items() if value is not None},
                project_id=project_id,
            )
        if deployment["status"] != "SUCCEEDED":
            raise HTTPException(status_code=409, detail="Promotion deployment did not succeed")
        activation = activate_model_deployment(deployment["id"], activation_payload, project_id=project_id)
        status = "APPLIED"

    response = {
        "project_id": project_id,
        "status": status,
        "apply": apply_changes,
        "mode": mode,
        "environment": environment,
        "report": report,
        "artifact": artifact,
        "deployment": deployment,
        "activation": activation,
        "deployment_action": deployment_action,
        "provenance": provenance,
        "preflight": preflight,
        "deployment_payload": {key: value for key, value in deployment_payload.items() if key != "deployer_api_key" and value is not None},
        "activation_payload": activation_payload,
    }
    record_usage(
        project_id,
        "model_adapter_promotion_activation",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate({"status": status, "artifact_id": artifact["id"], "deployment_id": deployment["id"] if deployment else None}),
        metadata={
            "status": status,
            "apply": apply_changes,
            "mode": mode,
            "environment": environment,
            "artifact_id": artifact["id"],
            "deployment_id": deployment["id"] if deployment else None,
            "activation_id": activation.get("activation_id") if isinstance(activation, dict) else None,
            "report_recommendation": report.get("recommendation"),
            "preflight_ready": preflight.get("ready"),
            "preflight_blocker_codes": preflight.get("blocker_codes", []),
        },
    )
    return response


def model_adapter_promotion_report(
    project_id: str | None = None,
    limit: int = 100,
    min_adapter_accuracy: float = 0.9,
    min_benchmark_accuracy: float = 1.0,
    min_shadow_precision: float = 0.9,
    min_shadow_reviews: int = 1,
    min_context_accuracy: float = 1.0,
    require_self_improvement_ready: bool = False,
    record: bool = True,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(limit, 1), 500)
    min_adapter_accuracy = 0.9 if min_adapter_accuracy is None else min_adapter_accuracy
    min_benchmark_accuracy = 1.0 if min_benchmark_accuracy is None else min_benchmark_accuracy
    min_context_accuracy = 1.0 if min_context_accuracy is None else min_context_accuracy
    min_shadow_precision = 0.9 if min_shadow_precision is None else min_shadow_precision
    min_shadow_reviews = 1 if min_shadow_reviews is None else min_shadow_reviews
    thresholds = {
        "min_adapter_accuracy": max(0.0, min(float(min_adapter_accuracy), 1.0)),
        "min_benchmark_accuracy": max(0.0, min(float(min_benchmark_accuracy), 1.0)),
        "min_context_accuracy": max(0.0, min(float(min_context_accuracy), 1.0)),
        "min_shadow_precision": max(0.0, min(float(min_shadow_precision), 1.0)),
        "min_shadow_reviews": max(int(min_shadow_reviews), 0),
        "require_self_improvement_ready": _bool_or(require_self_improvement_ready),
    }
    adapter_eval = _latest_model_adapter_eval(project_id)
    fine_tuning_job = None
    if adapter_eval and adapter_eval.get("fine_tuning_job_id"):
        try:
            fine_tuning_job = get_fine_tuning_job(str(adapter_eval["fine_tuning_job_id"]), project_id=project_id)
        except HTTPException:
            fine_tuning_job = None
    if fine_tuning_job is None:
        fine_tuning_job = _latest_fine_tuning_job(project_id)
    evaluations = list_evaluations(project_id=project_id, limit=limit)
    families = evaluations.get("families", [])
    shadow = shadow_rollout_summary(project_id=project_id, limit=max(limit, 1000))
    activation_rollback = _activation_rollback_gate(project_id)
    activation_health = _active_activation_health(project_id)
    self_improvement = self_improvement_status(
        project_id=project_id,
        min_context_accuracy=thresholds["min_context_accuracy"],
        min_adapter_accuracy=thresholds["min_adapter_accuracy"],
    )

    blockers: list[dict[str, Any]] = []
    if thresholds["require_self_improvement_ready"] and not self_improvement["ready"]:
        blockers.append(
            {
                "code": "self_improvement_not_ready",
                "message": "Self-improvement readiness has open blockers.",
                "blocker_codes": self_improvement["blocker_codes"],
                "blockers": self_improvement["blockers"],
            }
        )
    if activation_rollback and activation_rollback.get("blocked"):
        blockers.append(
            {
                "code": "activation_rollback",
                "message": "Latest deployment activation was rolled back; activate a newer deployment before promotion.",
                "activation_id": activation_rollback.get("activation_id"),
                "deployment_id": activation_rollback.get("deployment_id"),
                "rolled_back_at": activation_rollback.get("rolled_back_at"),
                "rollback_reason": activation_rollback.get("rollback_reason"),
            }
        )
    if activation_health and not activation_health.get("healthy"):
        blockers.append(
            {
                "code": "activation_unhealthy",
                "message": "Active deployment activation is unhealthy or drifted.",
                "status": activation_health.get("status"),
                "drifted_keys": activation_health.get("drifted_keys", []),
            }
        )
    if not adapter_eval:
        blockers.append({"code": "no_adapter_eval", "message": "Run adapter eval before promotion."})
    else:
        metrics = adapter_eval["metrics"]
        if metrics["item_count"] <= 0:
            blockers.append({"code": "empty_adapter_eval", "message": "Adapter eval has no trace items."})
        if metrics["accuracy"] < thresholds["min_adapter_accuracy"]:
            blockers.append(
                {
                    "code": "adapter_accuracy_below_threshold",
                    "message": "Adapter eval accuracy is below threshold.",
                    "value": metrics["accuracy"],
                    "threshold": thresholds["min_adapter_accuracy"],
                }
            )

    if not families:
        blockers.append({"code": "no_benchmark_evaluations", "message": "Run benchmark evaluations before promotion."})
    regression_families = [family for family in families if family.get("latest_regression")]
    if regression_families:
        blockers.append(
            {
                "code": "benchmark_regression",
                "message": "One or more benchmark families regressed.",
                "families": [
                    {
                        "family": family["family"],
                        "latest_accuracy": family.get("latest_accuracy"),
                        "latest_regression": family.get("latest_regression"),
                        "latest_evaluation_id": family.get("latest_evaluation_id"),
                        "latest_created_at": family.get("latest_created_at"),
                    }
                    for family in regression_families
                ],
            }
        )
    low_accuracy_families = [
        family
        for family in families
        if float(family.get("latest_accuracy") or 0) < thresholds["min_benchmark_accuracy"]
    ]
    if low_accuracy_families:
        blockers.append(
            {
                "code": "benchmark_accuracy_below_threshold",
                "message": "One or more benchmark families are below threshold.",
                "families": [
                    {
                        "family": family["family"],
                        "latest_accuracy": family.get("latest_accuracy"),
                        "latest_evaluation_id": family.get("latest_evaluation_id"),
                        "latest_created_at": family.get("latest_created_at"),
                        "threshold": thresholds["min_benchmark_accuracy"],
                    }
                    for family in low_accuracy_families
                ],
            }
        )

    reviewed = int(shadow.get("reviewed") or 0)
    if reviewed < thresholds["min_shadow_reviews"]:
        blockers.append(
            {
                "code": "insufficient_shadow_reviews",
                "message": "Not enough reviewed shadow promotions.",
                "value": reviewed,
                "threshold": thresholds["min_shadow_reviews"],
            }
        )
    if reviewed and float(shadow.get("precision") or 0) < thresholds["min_shadow_precision"]:
        blockers.append(
            {
                "code": "shadow_precision_below_threshold",
                "message": "Shadow promotion precision is below threshold.",
                "value": shadow.get("precision"),
                "threshold": thresholds["min_shadow_precision"],
            }
        )
    if int(shadow.get("blocked_count") or 0) > 0:
        blockers.append(
            {
                "code": "shadow_blocked_proposals",
                "message": "Shadow rollout still has blocked proposals.",
                "value": shadow.get("blocked_count"),
                "pending_count": shadow.get("pending_count"),
            }
        )
    if int(shadow.get("rollback_count") or 0) > 0:
        blockers.append(
            {
                "code": "shadow_rollbacks_present",
                "message": "Shadow rollout has rollback events.",
                "value": shadow.get("rollback_count"),
                "rollback_events": shadow.get("rollback_events", []),
            }
        )

    blocker_review_state = _annotate_promotion_blockers(project_id, blockers)
    raw_blockers = blocker_review_state["raw_blockers"]
    blockers = blocker_review_state["blockers"]
    reviewed_blockers = blocker_review_state["reviewed_blockers"]
    can_promote = not blockers
    report = {
        "schema_version": MODEL_ADAPTER_PROMOTION_REPORT_SCHEMA_VERSION,
        "project_id": project_id,
        "generated_at": utc_now(),
        "recommendation": "promote_to_canary" if can_promote else "hold",
        "can_promote": can_promote,
        "thresholds": thresholds,
        "adapter_eval": adapter_eval,
        "fine_tuning_job": fine_tuning_job,
        "activation_rollback": activation_rollback,
        "activation_health": activation_health,
        "self_improvement": self_improvement,
        "benchmarks": {
            "family_count": len(families),
            "regression_count": len(regression_families),
            "low_accuracy_count": len(low_accuracy_families),
            "families": families,
        },
        "shadow_rollout": shadow,
        "blockers": blockers,
        "raw_blockers": raw_blockers,
        "reviewed_blockers": reviewed_blockers,
        "reviewed_blocker_count": len(reviewed_blockers),
    }
    if record:
        record_usage(
            project_id,
            "model_adapter_promotion_report",
            output_tokens=token_estimate(blockers),
            metadata={
                "recommendation": report["recommendation"],
                "can_promote": can_promote,
                "blocker_count": len(blockers),
                "blocker_codes": [blocker.get("code") for blocker in blockers],
                "blockers": blockers,
                "thresholds": thresholds,
                "activation_rollback": activation_rollback,
                "activation_health_status": activation_health.get("status") if activation_health else None,
                "self_improvement_ready": self_improvement["ready"],
                "self_improvement_blocker_codes": self_improvement["blocker_codes"],
                "adapter_eval_id": adapter_eval.get("id") if adapter_eval else None,
                "fine_tuning_job_id": fine_tuning_job.get("id") if fine_tuning_job else None,
            },
        )
    return report


def _promotion_report_snapshot(row: Any) -> dict[str, Any]:
    metadata = json_loads(row["metadata"], {})
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "created_at": row["created_at"],
        "status": row["status"],
        "recommendation": metadata.get("recommendation") or "hold",
        "can_promote": bool(metadata.get("can_promote", False)),
        "blocker_count": int(metadata.get("blocker_count") or 0),
        "blocker_codes": metadata.get("blocker_codes") or [],
        "blockers": metadata.get("blockers") or [],
        "thresholds": metadata.get("thresholds") or {},
        "activation_rollback": metadata.get("activation_rollback"),
        "activation_health_status": metadata.get("activation_health_status"),
        "self_improvement_ready": bool(metadata.get("self_improvement_ready", False)),
        "self_improvement_blocker_codes": metadata.get("self_improvement_blocker_codes") or [],
        "adapter_eval_id": metadata.get("adapter_eval_id"),
        "fine_tuning_job_id": metadata.get("fine_tuning_job_id"),
    }


def model_adapter_promotion_audit(
    project_id: str | None = None,
    limit: int = 100,
    blocker_code: str | None = None,
    min_adapter_accuracy: float = 0.9,
    min_benchmark_accuracy: float = 1.0,
    min_shadow_precision: float = 0.9,
    min_shadow_reviews: int = 1,
    min_context_accuracy: float = 1.0,
    require_self_improvement_ready: bool = False,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(int(limit), 1), 500)
    blocker_code = str(blocker_code or "").strip()
    current_report = model_adapter_promotion_report(
        project_id=project_id,
        limit=limit,
        min_adapter_accuracy=min_adapter_accuracy,
        min_benchmark_accuracy=min_benchmark_accuracy,
        min_context_accuracy=min_context_accuracy,
        min_shadow_precision=min_shadow_precision,
        min_shadow_reviews=min_shadow_reviews,
        require_self_improvement_ready=require_self_improvement_ready,
        record=False,
    )
    with get_db() as conn:
        usage_rows = conn.execute(
            """
            SELECT * FROM usage_events
            WHERE project_id = ? AND operation = 'model_adapter_promotion_report'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project_id, min(limit * 5, 1000)),
        ).fetchall()
        override_rows = conn.execute(
            """
            SELECT * FROM proposals
            WHERE project_id = ? AND proposal_type = 'activation_rollback_override'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
    snapshots = [_promotion_report_snapshot(row) for row in usage_rows]
    if blocker_code:
        snapshots = [snapshot for snapshot in snapshots if blocker_code in set(snapshot.get("blocker_codes") or [])]
    snapshots = snapshots[:limit]
    request_logs = list_request_logs(
        project_id=project_id,
        limit=limit,
        method="GET",
        path="/model-adapters/promotion-report/",
    )
    overrides = [proposal_row(row) for row in override_rows]
    current_blocker_codes = [blocker.get("code") for blocker in current_report.get("blockers", [])]
    return {
        "project_id": project_id,
        "generated_at": utc_now(),
        "blocker_code": blocker_code or None,
        "current_report": current_report,
        "current_blocker_codes": current_blocker_codes,
        "snapshot_count": len(snapshots),
        "hold_count": sum(1 for snapshot in snapshots if snapshot.get("recommendation") == "hold"),
        "snapshots": snapshots,
        "override_count": len(overrides),
        "overrides": overrides,
        "request_count": request_logs["count"],
        "request_logs": request_logs["results"],
    }


def export_model_adapter_promotion_audit(
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    project_id = project_id or current_project_id()
    filters = {
        "limit": int(payload.get("limit") or 100),
        "blocker_code": payload.get("blocker_code") or payload.get("blockerCode"),
        "min_adapter_accuracy": payload.get("min_adapter_accuracy", payload.get("minAdapterAccuracy", 0.9)),
        "min_benchmark_accuracy": payload.get("min_benchmark_accuracy", payload.get("minBenchmarkAccuracy", 1.0)),
        "min_context_accuracy": payload.get("min_context_accuracy", payload.get("minContextAccuracy", 1.0)),
        "min_shadow_precision": payload.get("min_shadow_precision", payload.get("minShadowPrecision", 0.9)),
        "min_shadow_reviews": payload.get("min_shadow_reviews", payload.get("minShadowReviews", 1)),
        "require_self_improvement_ready": _bool_or(
            payload.get("require_self_improvement_ready", payload.get("requireSelfImprovementReady")), False
        ),
    }
    audit = model_adapter_promotion_audit(project_id=project_id, **filters)
    body = {
        "schema_version": "promotion-audit-bundle-v1",
        "bundle_id": str(new_id("promotion_audit")),
        "project_id": project_id,
        "generated_at": utc_now(),
        "filters": filters,
        "audit": audit,
    }
    canonical = json_dumps(body)
    checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    signing_key = os.getenv("MEM1_AUDIT_SIGNING_KEY") or os.getenv("MEM1_API_KEY", "m0-local-dev-key")
    signature = hmac.new(signing_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    key_id = hashlib.sha256(signing_key.encode("utf-8")).hexdigest()[:16]
    result = {
        **body,
        "integrity": {
            "algorithm": "HMAC-SHA256",
            "canonical_json_sha256": checksum,
            "signature": signature,
            "signing_key_id": key_id,
        },
    }
    record_usage(
        project_id,
        "promotion_audit_export",
        output_tokens=token_estimate(audit),
        metadata={
            "bundle_id": body["bundle_id"],
            "checksum": checksum,
            "signing_key_id": key_id,
            "filters": filters,
            "snapshot_count": audit.get("snapshot_count"),
            "override_count": audit.get("override_count"),
        },
    )
    return result


def verify_model_adapter_promotion_audit_bundle(
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    project_id = project_id or current_project_id()
    bundle = payload.get("bundle") if isinstance(payload.get("bundle"), dict) else payload
    integrity = bundle.get("integrity") if isinstance(bundle.get("integrity"), dict) else {}
    body = {key: value for key, value in bundle.items() if key != "integrity"}
    canonical = json_dumps(body)
    expected_checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    signing_key = os.getenv("MEM1_AUDIT_SIGNING_KEY") or os.getenv("MEM1_API_KEY", "m0-local-dev-key")
    expected_signature = hmac.new(signing_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    provided_checksum = str(integrity.get("canonical_json_sha256") or "")
    provided_signature = str(integrity.get("signature") or "")
    checksum_valid = hmac.compare_digest(provided_checksum, expected_checksum)
    signature_valid = hmac.compare_digest(provided_signature, expected_signature)
    schema_valid = bundle.get("schema_version") == "promotion-audit-bundle-v1"
    project_valid = not bundle.get("project_id") or bundle.get("project_id") == project_id
    result = {
        "valid": bool(schema_valid and project_valid and checksum_valid and signature_valid),
        "schema_valid": schema_valid,
        "project_valid": project_valid,
        "checksum_valid": checksum_valid,
        "signature_valid": signature_valid,
        "bundle_id": bundle.get("bundle_id"),
        "project_id": project_id,
        "bundle_project_id": bundle.get("project_id"),
        "expected_checksum": expected_checksum,
        "provided_checksum": provided_checksum,
        "signing_key_id": hashlib.sha256(signing_key.encode("utf-8")).hexdigest()[:16],
    }
    record_usage(
        project_id,
        "promotion_audit_verify",
        input_tokens=token_estimate(body),
        metadata={
            "bundle_id": result["bundle_id"],
            "valid": result["valid"],
            "checksum_valid": checksum_valid,
            "signature_valid": signature_valid,
        },
    )
    return result


PROMOTION_AUDIT_OPERATIONS = {
    "model_adapter_promotion_report",
    "promotion_audit_export",
    "promotion_audit_verify",
}

PROMOTION_AUDIT_RETENTION_POLICY_DEFAULTS = {
    "enabled": False,
    "older_than_days": 30,
    "limit": 500,
    "requested_by": "retention_policy",
    "interval_seconds": 86400,
}


def model_adapter_promotion_audit_retention(
    project_id: str | None = None,
    older_than_days: int = 30,
    limit: int = 500,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    older_than_days = max(int(older_than_days), 0)
    limit = min(max(int(limit), 1), 5000)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    placeholders = ", ".join("?" for _ in PROMOTION_AUDIT_OPERATIONS)
    params: list[Any] = [project_id, *sorted(PROMOTION_AUDIT_OPERATIONS), cutoff]
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM usage_events
            WHERE project_id = ?
              AND operation IN ({placeholders})
              AND created_at <= ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        count = conn.execute(
            f"""
            SELECT COUNT(*) AS c FROM usage_events
            WHERE project_id = ?
              AND operation IN ({placeholders})
              AND created_at <= ?
            """,
            params,
        ).fetchone()["c"]
    candidates = []
    operation_counts: dict[str, int] = {}
    for row in rows:
        metadata = json_loads(row["metadata"], {})
        operation = row["operation"]
        operation_counts[operation] = operation_counts.get(operation, 0) + 1
        candidates.append(
            {
                "id": row["id"],
                "operation": operation,
                "created_at": row["created_at"],
                "status": row["status"],
                "bundle_id": metadata.get("bundle_id"),
                "checksum": metadata.get("checksum"),
                "recommendation": metadata.get("recommendation"),
                "blocker_codes": metadata.get("blocker_codes") or [],
                "valid": metadata.get("valid"),
            }
        )
    return {
        "project_id": project_id,
        "generated_at": utc_now(),
        "dry_run": True,
        "policy": {"older_than_days": older_than_days, "cutoff": cutoff},
        "candidate_count": count,
        "returned_count": len(candidates),
        "operation_counts": operation_counts,
        "candidates": candidates,
    }


def model_adapter_promotion_audit_retention_policy(project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    settings = get_project_settings(project_id)
    older_than_days = settings.get(
        "promotion_audit_retention_older_than_days",
        PROMOTION_AUDIT_RETENTION_POLICY_DEFAULTS["older_than_days"],
    )
    limit = settings.get("promotion_audit_retention_limit", PROMOTION_AUDIT_RETENTION_POLICY_DEFAULTS["limit"])
    interval_seconds = settings.get(
        "promotion_audit_retention_interval_seconds",
        PROMOTION_AUDIT_RETENTION_POLICY_DEFAULTS["interval_seconds"],
    )
    return {
        "project_id": project_id,
        "enabled": bool(settings.get("promotion_audit_retention_enabled", PROMOTION_AUDIT_RETENTION_POLICY_DEFAULTS["enabled"])),
        "older_than_days": max(int(PROMOTION_AUDIT_RETENTION_POLICY_DEFAULTS["older_than_days"] if older_than_days is None else older_than_days), 0),
        "limit": min(max(int(PROMOTION_AUDIT_RETENTION_POLICY_DEFAULTS["limit"] if limit is None else limit), 1), 5000),
        "interval_seconds": max(
            int(PROMOTION_AUDIT_RETENTION_POLICY_DEFAULTS["interval_seconds"] if interval_seconds is None else interval_seconds),
            0,
        ),
        "requested_by": str(
            settings.get("promotion_audit_retention_requested_by", PROMOTION_AUDIT_RETENTION_POLICY_DEFAULTS["requested_by"])
            or "retention_policy"
        ),
        "last_run_at": settings.get("promotion_audit_retention_last_run_at"),
        "last_status": settings.get("promotion_audit_retention_last_status"),
        "last_error": settings.get("promotion_audit_retention_last_error"),
        "last_proposal_id": settings.get("promotion_audit_retention_last_proposal_id"),
        "last_archive_id": settings.get("promotion_audit_retention_last_archive_id"),
        "archive_required": True,
        "apply_requires_review": True,
    }


def update_model_adapter_promotion_audit_retention_policy(
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    project_id = project_id or current_project_id()
    updates: dict[str, Any] = {}
    if "enabled" in payload:
        updates["promotion_audit_retention_enabled"] = bool(payload.get("enabled"))
    older_than_days = payload.get("older_than_days")
    if older_than_days is None:
        older_than_days = payload.get("olderThanDays")
    if older_than_days is not None:
        updates["promotion_audit_retention_older_than_days"] = max(
            int(older_than_days),
            0,
        )
    if payload.get("limit") is not None:
        updates["promotion_audit_retention_limit"] = min(max(int(payload["limit"]), 1), 5000)
    interval_seconds = payload.get("interval_seconds")
    if interval_seconds is None:
        interval_seconds = payload.get("intervalSeconds")
    if interval_seconds is not None:
        updates["promotion_audit_retention_interval_seconds"] = max(int(interval_seconds), 0)
    requested_by = payload.get("requested_by")
    if requested_by is None:
        requested_by = payload.get("requestedBy")
    if requested_by is not None:
        updates["promotion_audit_retention_requested_by"] = str(
            requested_by or "retention_policy"
        )
    if updates:
        update_project_settings(project_id, updates)
    return model_adapter_promotion_audit_retention_policy(project_id=project_id)


def _pending_promotion_audit_retention_proposal(
    project_id: str,
    older_than_days: int,
    limit: int,
) -> dict[str, Any] | None:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM proposals
            WHERE project_id = ?
              AND proposal_type = 'promotion_audit_retention_apply'
              AND status = 'PENDING'
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (project_id,),
        ).fetchall()
    for row in rows:
        proposal = proposal_row(row)
        payload = proposal.get("payload") or {}
        if int(payload.get("older_than_days", -1)) == older_than_days and int(payload.get("limit", -1)) == limit:
            return proposal
    return None


def _update_promotion_audit_retention_policy_run_state(
    project_id: str,
    status: str,
    proposal: dict[str, Any] | None = None,
    archive: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any]:
    updates = {
        "promotion_audit_retention_last_run_at": utc_now(),
        "promotion_audit_retention_last_status": status,
        "promotion_audit_retention_last_error": error,
        "promotion_audit_retention_last_proposal_id": proposal.get("id") if proposal else None,
        "promotion_audit_retention_last_archive_id": archive.get("archive_id") if archive else None,
    }
    update_project_settings(project_id, updates)
    return model_adapter_promotion_audit_retention_policy(project_id=project_id)


def run_model_adapter_promotion_audit_retention_policy(
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    project_id = project_id or current_project_id()
    policy = model_adapter_promotion_audit_retention_policy(project_id=project_id)
    force = bool(payload.get("force", False))
    if not policy["enabled"] and not force:
        raise HTTPException(status_code=409, detail="Promotion audit retention policy is disabled")
    older_than_days = payload.get("older_than_days")
    if older_than_days is None:
        older_than_days = payload.get("olderThanDays", policy["older_than_days"])
    limit = payload.get("limit")
    if limit is None:
        limit = policy["limit"]
    requested_by = payload.get("requested_by")
    if requested_by is None:
        requested_by = payload.get("requestedBy") or policy["requested_by"]
    older_than_days = int(older_than_days)
    limit = int(limit)
    requested_by = str(requested_by)
    older_than_days = max(older_than_days, 0)
    limit = min(max(limit, 1), 5000)
    existing = None if force else _pending_promotion_audit_retention_proposal(project_id, older_than_days, limit)
    if existing:
        archive = existing.get("result", {}).get("archive")
        updated_policy = _update_promotion_audit_retention_policy_run_state(
            project_id,
            "pending_proposal_exists",
            proposal=existing,
            archive=archive,
        )
        return {
            "project_id": project_id,
            "generated_at": utc_now(),
            "status": "pending_proposal_exists",
            "policy": updated_policy,
            "proposal": existing,
            "archive": archive,
        }
    proposal = request_model_adapter_promotion_audit_retention_apply(
        {"older_than_days": older_than_days, "limit": limit, "requested_by": requested_by},
        project_id=project_id,
    )
    archive = proposal.get("result", {}).get("archive")
    updated_policy = _update_promotion_audit_retention_policy_run_state(
        project_id,
        "proposal_created",
        proposal=proposal,
        archive=archive,
    )
    return {
        "project_id": project_id,
        "generated_at": utc_now(),
        "status": "proposal_created",
        "policy": {
            **updated_policy,
            "older_than_days": max(older_than_days, 0),
            "limit": min(max(limit, 1), 5000),
            "requested_by": requested_by,
        },
        "proposal": proposal,
        "archive": archive,
    }


def run_due_model_adapter_promotion_audit_retention_policies(
    project_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    projects: list[str] = []
    with get_db() as conn:
        if project_id:
            rows = conn.execute("SELECT project_id FROM projects WHERE project_id = ?", (project_id,)).fetchall()
        else:
            rows = conn.execute("SELECT project_id FROM projects ORDER BY project_id ASC").fetchall()
    projects = [row["project_id"] for row in rows]
    results = []
    for candidate_project_id in projects:
        policy = model_adapter_promotion_audit_retention_policy(project_id=candidate_project_id)
        if not policy["enabled"] and not force:
            results.append({"project_id": candidate_project_id, "status": "disabled", "policy": policy})
            continue
        last_run_at = parse_datetime(policy.get("last_run_at"))
        interval_seconds = int(policy.get("interval_seconds") or 0)
        due = force or last_run_at is None or interval_seconds <= 0 or (parse_datetime(now) - last_run_at).total_seconds() >= interval_seconds
        if not due:
            results.append({"project_id": candidate_project_id, "status": "not_due", "policy": policy})
            continue
        try:
            results.append(
                run_model_adapter_promotion_audit_retention_policy(
                    {
                        "older_than_days": policy["older_than_days"],
                        "limit": policy["limit"],
                        "requested_by": policy["requested_by"],
                        "force": force,
                    },
                    project_id=candidate_project_id,
                )
            )
        except HTTPException as exc:
            updated_policy = _update_promotion_audit_retention_policy_run_state(
                candidate_project_id,
                "skipped",
                error=str(exc.detail),
            )
            results.append(
                {
                    "project_id": candidate_project_id,
                    "generated_at": utc_now(),
                    "status": "skipped",
                    "error": exc.detail,
                    "policy": updated_policy,
                }
            )
    return {
        "generated_at": now,
        "project_id": project_id,
        "count": len(results),
        "created_count": sum(1 for item in results if item.get("status") == "proposal_created"),
        "pending_count": sum(1 for item in results if item.get("status") == "pending_proposal_exists"),
        "skipped_count": sum(1 for item in results if item.get("status") in {"disabled", "not_due", "skipped"}),
        "results": results,
    }


def _promotion_audit_retention_preview(payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    retention = model_adapter_promotion_audit_retention(
        project_id=project_id,
        older_than_days=int(payload.get("older_than_days", 30)),
        limit=int(payload.get("limit", 500)),
    )
    candidate_ids = [candidate["id"] for candidate in retention["candidates"]]
    if not candidate_ids:
        raise HTTPException(status_code=409, detail="No promotion audit retention candidates found")
    archive = export_model_adapter_promotion_audit_retention_archive(payload, project_id=project_id)
    return {
        "action": "APPLY_PROMOTION_AUDIT_RETENTION",
        "requested_by": payload.get("requested_by") or "operator",
        "dry_run": True,
        "policy": retention["policy"],
        "candidate_count": retention["candidate_count"],
        "returned_count": retention["returned_count"],
        "operation_counts": retention["operation_counts"],
        "candidate_ids": candidate_ids,
        "candidates": retention["candidates"],
        "archive": {
            "schema_version": archive["schema_version"],
            "archive_id": archive["archive_id"],
            "checksum": archive["integrity"]["canonical_json_sha256"],
            "signature": archive["integrity"]["signature"],
            "signing_key_id": archive["integrity"]["signing_key_id"],
        },
    }


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def export_model_adapter_promotion_audit_retention_archive(
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    project_id = project_id or current_project_id()
    retention = model_adapter_promotion_audit_retention(
        project_id=project_id,
        older_than_days=int(payload.get("older_than_days", payload.get("olderThanDays", 30))),
        limit=int(payload.get("limit", 500)),
    )
    candidate_ids = [candidate["id"] for candidate in retention["candidates"]]
    records = []
    if candidate_ids:
        operations = sorted(PROMOTION_AUDIT_OPERATIONS)
        operation_placeholders = ", ".join("?" for _ in operations)
        with get_db() as conn:
            for chunk in _chunks(candidate_ids, 400):
                id_placeholders = ", ".join("?" for _ in chunk)
                rows = conn.execute(
                    f"""
                    SELECT * FROM usage_events
                    WHERE project_id = ?
                      AND id IN ({id_placeholders})
                      AND operation IN ({operation_placeholders})
                    ORDER BY created_at ASC
                    """,
                    [project_id, *chunk, *operations],
                ).fetchall()
                for row in rows:
                    records.append(
                        {
                            "id": row["id"],
                            "operation": row["operation"],
                            "input_tokens": row["input_tokens"],
                            "output_tokens": row["output_tokens"],
                            "total_tokens": row["total_tokens"],
                            "cost": row["cost"],
                            "latency": row["latency"],
                            "status": row["status"],
                            "event_id": row["event_id"],
                            "metadata": json_loads(row["metadata"], {}),
                            "created_at": row["created_at"],
                        }
                    )
    body = {
        "schema_version": "promotion-audit-retention-archive-v1",
        "archive_id": str(new_id("promotion_audit_retention_archive")),
        "project_id": project_id,
        "generated_at": utc_now(),
        "retention": retention,
        "records": records,
    }
    canonical = json_dumps(body)
    checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    signing_key = os.getenv("MEM1_AUDIT_SIGNING_KEY") or os.getenv("MEM1_API_KEY", "m0-local-dev-key")
    signature = hmac.new(signing_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    key_id = hashlib.sha256(signing_key.encode("utf-8")).hexdigest()[:16]
    result = {
        **body,
        "integrity": {
            "algorithm": "HMAC-SHA256",
            "canonical_json_sha256": checksum,
            "signature": signature,
            "signing_key_id": key_id,
        },
    }
    record_usage(
        project_id,
        "promotion_audit_retention_archive",
        output_tokens=token_estimate(records),
        metadata={
            "archive_id": body["archive_id"],
            "checksum": checksum,
            "signing_key_id": key_id,
            "candidate_count": retention["candidate_count"],
            "returned_count": retention["returned_count"],
        },
    )
    return result


def verify_model_adapter_promotion_audit_retention_archive(
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    project_id = project_id or current_project_id()
    archive = payload.get("archive") if isinstance(payload.get("archive"), dict) else payload
    integrity = archive.get("integrity") if isinstance(archive.get("integrity"), dict) else {}
    body = {key: value for key, value in archive.items() if key != "integrity"}
    canonical = json_dumps(body)
    expected_checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    signing_key = os.getenv("MEM1_AUDIT_SIGNING_KEY") or os.getenv("MEM1_API_KEY", "m0-local-dev-key")
    expected_signature = hmac.new(signing_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    provided_checksum = str(integrity.get("canonical_json_sha256") or "")
    provided_signature = str(integrity.get("signature") or "")
    checksum_valid = hmac.compare_digest(provided_checksum, expected_checksum)
    signature_valid = hmac.compare_digest(provided_signature, expected_signature)
    schema_valid = archive.get("schema_version") == "promotion-audit-retention-archive-v1"
    project_valid = not archive.get("project_id") or archive.get("project_id") == project_id
    result = {
        "valid": bool(schema_valid and project_valid and checksum_valid and signature_valid),
        "schema_valid": schema_valid,
        "project_valid": project_valid,
        "checksum_valid": checksum_valid,
        "signature_valid": signature_valid,
        "archive_id": archive.get("archive_id"),
        "project_id": project_id,
        "archive_project_id": archive.get("project_id"),
        "expected_checksum": expected_checksum,
        "provided_checksum": provided_checksum,
        "signing_key_id": hashlib.sha256(signing_key.encode("utf-8")).hexdigest()[:16],
    }
    record_usage(
        project_id,
        "promotion_audit_retention_archive_verify",
        input_tokens=token_estimate(body),
        metadata={
            "archive_id": result["archive_id"],
            "valid": result["valid"],
            "checksum_valid": checksum_valid,
            "signature_valid": signature_valid,
        },
    )
    return result


def _apply_promotion_audit_retention(payload: dict[str, Any], preview: dict[str, Any], project_id: str) -> dict[str, Any]:
    candidate_ids = [str(candidate_id) for candidate_id in preview.get("candidate_ids", []) if candidate_id]
    if not candidate_ids:
        raise HTTPException(status_code=409, detail="Retention proposal has no candidate ids")
    operations = sorted(PROMOTION_AUDIT_OPERATIONS)
    operation_placeholders = ", ".join("?" for _ in operations)
    existing_rows = []
    with get_db() as conn:
        for chunk in _chunks(candidate_ids, 400):
            id_placeholders = ", ".join("?" for _ in chunk)
            existing_rows.extend(
                conn.execute(
                    f"""
                    SELECT id, operation FROM usage_events
                    WHERE project_id = ?
                      AND id IN ({id_placeholders})
                      AND operation IN ({operation_placeholders})
                    """,
                    [project_id, *chunk, *operations],
                ).fetchall()
            )
        existing_ids = {row["id"] for row in existing_rows}
        missing_ids = [candidate_id for candidate_id in candidate_ids if candidate_id not in existing_ids]
        if missing_ids:
            raise HTTPException(status_code=409, detail="Retention proposal drifted; create a new proposal")
        operation_counts: dict[str, int] = {}
        for row in existing_rows:
            operation = row["operation"]
            operation_counts[operation] = operation_counts.get(operation, 0) + 1
        deleted_count = 0
        for chunk in _chunks(candidate_ids, 400):
            id_placeholders = ", ".join("?" for _ in chunk)
            cursor = conn.execute(
                f"""
                DELETE FROM usage_events
                WHERE project_id = ?
                  AND id IN ({id_placeholders})
                  AND operation IN ({operation_placeholders})
                """,
                [project_id, *chunk, *operations],
            )
            deleted_count += max(cursor.rowcount or 0, 0)
    result = {
        "action": "APPLY_PROMOTION_AUDIT_RETENTION",
        "applied_at": utc_now(),
        "requested_by": payload.get("requested_by") or preview.get("requested_by") or "operator",
        "policy": preview.get("policy") or {},
        "deleted_count": deleted_count,
        "deleted_ids": candidate_ids,
        "operation_counts": operation_counts,
    }
    record_usage(
        project_id,
        "promotion_audit_retention_apply",
        input_tokens=token_estimate(preview),
        output_tokens=token_estimate(result),
        metadata={
            "deleted_count": deleted_count,
            "operation_counts": operation_counts,
            "older_than_days": result["policy"].get("older_than_days"),
            "cutoff": result["policy"].get("cutoff"),
        },
    )
    return result


def request_model_adapter_promotion_audit_retention_apply(
    payload: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    older_than_days = payload.get("older_than_days", payload.get("olderThanDays", 30))
    limit = payload.get("limit", 500)
    requested_by = payload.get("requested_by") or payload.get("requestedBy") or "operator"
    return create_proposal(
        {
            "proposal_type": "promotion_audit_retention_apply",
            "older_than_days": older_than_days,
            "limit": limit,
            "requested_by": requested_by,
            "review_reason": f"promotion_audit_retention_apply:{older_than_days}:{limit}",
        },
        project_id=project_id,
    )


def list_events(
    page: int = 1,
    page_size: int = 100,
    project_id: str | None = None,
    event_type: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    # Server-side filters advertised by /v1/events/filters/.
    where = "project_id = ?"
    params: list[Any] = [project_id]
    if event_type:
        where += " AND UPPER(event_type) = ?"
        params.append(str(event_type).strip().upper())
    if status:
        where += " AND UPPER(status) = ?"
        params.append(str(status).strip().upper())
    with get_db() as conn:
        count = conn.execute(f"SELECT COUNT(*) AS c FROM events WHERE {where}", params).fetchone()["c"]
        rows = conn.execute(
            f"SELECT * FROM events WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, page_size, (page - 1) * page_size),
        ).fetchall()
    return {
        "count": count,
        "next": f"/v1/events/?page={page + 1}&page_size={page_size}" if page * page_size < count else None,
        "previous": f"/v1/events/?page={page - 1}&page_size={page_size}" if page > 1 else None,
        "results": [event_row(row) for row in rows],
    }


def event_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"] if "project_id" in row.keys() else "proj_local",
        "event_type": row["event_type"],
        "status": row["status"],
        "payload": json_loads(row["payload"], {}),
        "metadata": json_loads(row["metadata"], {}),
        "results": json_loads(row["results"], []),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "latency": row["latency"],
    }


def get_event(event_id: str, project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM events WHERE id = ? AND project_id = ?", (event_id, project_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    return event_row(row)


def stats(project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        memory_count = conn.execute("SELECT COUNT(*) AS c FROM memories WHERE project_id = ? AND deleted = 0", (project_id,)).fetchone()["c"]
        add_events = conn.execute("SELECT COUNT(*) AS c FROM events WHERE project_id = ? AND event_type = 'ADD'", (project_id,)).fetchone()["c"]
        search_events = conn.execute("SELECT COUNT(*) AS c FROM events WHERE project_id = ? AND event_type = 'SEARCH'", (project_id,)).fetchone()["c"]
        users = conn.execute("SELECT COUNT(DISTINCT user_id) AS c FROM memories WHERE project_id = ? AND deleted = 0 AND user_id IS NOT NULL", (project_id,)).fetchone()["c"]
    usage = usage_summary(project_id, limit=1)
    return {
        "project_id": project_id,
        "total_memories": memory_count,
        "total_search_events": search_events,
        "total_add_events": add_events,
        "total_users": users,
        "total_tokens": usage["total_tokens"],
        "total_cost": usage["total_cost"],
    }


def _export_memory(memory: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict) or not properties:
        return strip_internal(memory)
    exported: dict[str, Any] = {}
    for key in properties:
        if key in memory:
            exported[key] = memory[key]
        elif key == "text":
            exported[key] = memory["memory"]
        elif key == "category":
            exported[key] = (memory.get("categories") or ["general"])[0]
        elif key.startswith("metadata."):
            value: Any = memory.get("metadata", {})
            for part in key.split(".")[1:]:
                if not isinstance(value, dict):
                    value = None
                    break
                value = value.get(part)
            exported[key] = value
        else:
            exported[key] = memory.get("metadata", {}).get(key)
    return exported


def create_memory_export(payload: dict[str, Any], project_id: str | None = None) -> dict[str, str]:
    project_id = payload.get("project_id") or project_id or current_project_id()
    schema = payload.get("schema")
    if not isinstance(schema, dict):
        raise HTTPException(status_code=400, detail="schema is required")
    filters = payload.get("filters") or {}
    validate_filters(filters)
    memories = list_memory_dicts(project_id=project_id)
    if filters:
        memories = [memory for memory in memories if matches_filters(memory, filters)]
    data = {
        "id": str(new_id()),
        "project_id": project_id,
        "status": "SUCCEEDED",
        "filters": filters,
        "schema": schema,
        "memories": [_export_memory(memory, schema) for memory in memories],
    }
    now = utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO exports (id, project_id, status, schema, filters, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["id"],
                project_id,
                data["status"],
                json_dumps(schema),
                json_dumps(filters),
                json_dumps(data),
                now,
                now,
            ),
        )
    record_usage(project_id, "memory_export", input_tokens=token_estimate(filters), output_tokens=token_estimate(data), metadata={"export_id": data["id"]})
    return {
        "message": "Memory export request received. The export will be ready in a few seconds.",
        "id": data["id"],
    }


def get_memory_export(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    project_id = payload.get("project_id") or project_id or current_project_id()
    export_id = payload.get("memory_export_id") or payload.get("id")
    filters = payload.get("filters") or {}
    validate_filters(filters)
    with get_db() as conn:
        if export_id:
            row = conn.execute("SELECT * FROM exports WHERE id = ? AND project_id = ?", (export_id, project_id)).fetchone()
        else:
            row = conn.execute("SELECT * FROM exports WHERE project_id = ? ORDER BY created_at DESC LIMIT 1", (project_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Memory export not found")
    data = json_loads(row["data"], {})
    if filters:
        memories = [memory for memory in list_memory_dicts(project_id=project_id) if matches_filters(memory, filters)]
        schema = data.get("schema") or json_loads(row["schema"], {})
        data = {**data, "filters": filters, "memories": [_export_memory(memory, schema) for memory in memories]}
    return data


DATA_REQUEST_TYPES = {"export", "delete"}
DATA_REQUEST_EXPORT_SCHEMA = {
    "properties": {
        "id": {},
        "memory": {},
        "metadata": {},
        "categories": {},
        "user_id": {},
        "agent_id": {},
        "app_id": {},
        "run_id": {},
        "created_at": {},
        "updated_at": {},
    }
}


def _data_request_filters(payload: dict[str, Any]) -> dict[str, Any]:
    raw_filters = payload.get("filters")
    filters = dict(raw_filters) if isinstance(raw_filters, dict) else {}
    for field in ENTITY_FIELDS:
        if payload.get(field) not in (None, ""):
            filters[field] = payload[field]
    validate_filters(filters)
    if not has_entity_filter(filters):
        raise HTTPException(status_code=400, detail="data request filters must include at least one entity ID")
    return filters


def _redact_data_request_payload(data: dict[str, Any], payload: dict[str, Any], project_id: str) -> dict[str, Any]:
    redaction_rules = _trace_redaction_rules(payload, project_id)
    policy = _trace_redaction_policy(payload, project_id=project_id)
    redacted = _redact_trace_value(data, redaction_rules["deny_terms"], redaction_rules["allow_terms"], policy)
    return {
        "data": redacted,
        "redaction": {
            "enabled": True,
            "policy": policy,
            "deny_term_count": len(redaction_rules["deny_terms"]),
            "allow_term_count": len(redaction_rules["allow_terms"]),
        },
    }


def mem1_data_request(payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    payload = payload or {}
    project_id = payload.get("project_id") or project_id or current_project_id()
    request_type = str(payload.get("request_type") or payload.get("type") or "export").strip().lower()
    if request_type not in DATA_REQUEST_TYPES:
        raise HTTPException(status_code=400, detail="request_type must be export or delete")
    filters = _data_request_filters(payload)
    apply = _bool_or(payload.get("apply"), False)
    requested_by = str(payload.get("requested_by") or "operator")
    include_expired = request_type == "delete"
    memories = [
        memory
        for memory in list_memory_dicts(project_id=project_id, include_expired=include_expired)
        if matches_filters(memory, filters)
    ]
    result: dict[str, Any] = {
        "schema_version": "mem1-data-request-v1",
        "project_id": project_id,
        "request_type": request_type,
        "status": "READY",
        "apply": apply,
        "requested_by": requested_by,
        "filters": filters,
        "matched_count": len(memories),
        "memory_ids": [memory["id"] for memory in memories],
    }
    if _bool_or(payload.get("include_preview"), False):
        result["preview"] = [strip_internal(memory) for memory in memories[: min(len(memories), 10)]]
    if not apply:
        record_usage(
            project_id,
            "mem1_data_request_plan",
            input_tokens=token_estimate(payload),
            output_tokens=token_estimate(result),
            metadata={"request_type": request_type, "matched_count": len(memories), "apply": False},
        )
        return result

    if request_type == "delete":
        if str(payload.get("confirm") or "").strip().upper() != "DELETE":
            raise HTTPException(status_code=409, detail="confirm=DELETE is required to apply a delete data request")
        delete_memories(filters, project_id=project_id)
        result.update(
            {
                "status": "APPLIED",
                "deleted_count": len(memories),
                "deleted_at": utc_now(),
            }
        )
    else:
        schema = payload.get("schema") if isinstance(payload.get("schema"), dict) else DATA_REQUEST_EXPORT_SCHEMA
        created = create_memory_export({"schema": schema, "filters": filters}, project_id=project_id)
        export = get_memory_export({"memory_export_id": created["id"]}, project_id=project_id)
        redact = _bool_or(payload.get("redact"), True)
        export_payload = _redact_data_request_payload(export, payload, project_id) if redact else {"data": export, "redaction": {"enabled": False, "policy": "none"}}
        result.update(
            {
                "status": "APPLIED",
                "export_id": created["id"],
                "export": export_payload["data"] if _bool_or(payload.get("include_data"), True) else {"id": created["id"]},
                "redaction": export_payload["redaction"],
            }
        )
    record_usage(
        project_id,
        f"mem1_data_request_{request_type}",
        input_tokens=token_estimate(payload),
        output_tokens=token_estimate(result),
        metadata={"request_type": request_type, "matched_count": len(memories), "apply": True},
    )
    return result


LORA_REQUIRED_PACKAGES = ("torch", "transformers", "peft", "trl", "datasets", "accelerate")
DEFAULT_LORA_BASE_MODEL_CANDIDATES = (
    {
        "model_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "expected_size_gb": 4.5,
        "target_modules": "q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj",
        "training_profile": "first_real_candidate_4bit_lora",
        "notes": "First larger OSS policy candidate after tiny-gpt2 smoke.",
    },
    {
        "model_id": "sshleifer/tiny-gpt2",
        "expected_size_gb": 0.05,
        "target_modules": "c_attn,c_proj",
        "training_profile": "smoke_only",
        "notes": "Fast GPU/API smoke only; not a real policy candidate.",
    },
)


def _huggingface_cache_roots() -> list[str]:
    cache_roots = []
    explicit_cache = os.getenv("HUGGINGFACE_HUB_CACHE")
    if explicit_cache:
        cache_roots.append(os.path.expanduser(explicit_cache))
    hf_home = os.getenv("HF_HOME")
    if hf_home:
        cache_roots.append(os.path.join(os.path.expanduser(hf_home), "hub"))
    cache_roots.append(os.path.expanduser("~/.cache/huggingface/hub"))
    return list(dict.fromkeys(cache_roots))


def _cached_huggingface_base_models() -> list[dict[str, Any]]:
    models: dict[str, dict[str, Any]] = {}
    for root in _huggingface_cache_roots():
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            if not entry.startswith("models--"):
                continue
            cache_dir = os.path.join(root, entry)
            snapshots_dir = os.path.join(cache_dir, "snapshots")
            snapshots: list[str] = []
            if os.path.isdir(snapshots_dir):
                snapshots = sorted(
                    os.path.join(snapshots_dir, name)
                    for name in os.listdir(snapshots_dir)
                    if os.path.isdir(os.path.join(snapshots_dir, name))
                )
            model_id = entry.removeprefix("models--").replace("--", "/")
            models[model_id] = {
                "model_id": model_id,
                "cache_dir": cache_dir,
                "snapshot_count": len(snapshots),
                "snapshot_path": snapshots[-1] if snapshots else None,
            }
    return list(models.values())


def _base_model_cache_status(model_id: str) -> dict[str, Any]:
    model_id = str(model_id or "").strip()
    if not model_id:
        return {
            "model_id": model_id,
            "cached": False,
            "cache_dir": None,
            "snapshot_count": 0,
            "snapshot_path": None,
            "source": "missing",
        }
    local_path = os.path.expanduser(model_id)
    if os.path.exists(local_path):
        return {
            "model_id": model_id,
            "cached": True,
            "cache_dir": os.path.abspath(local_path),
            "snapshot_count": 1 if os.path.isdir(local_path) else 0,
            "snapshot_path": os.path.abspath(local_path),
            "source": "local_path",
        }
    cache_name = f"models--{model_id.replace('/', '--')}"
    for root in _huggingface_cache_roots():
        cache_dir = os.path.join(root, cache_name)
        snapshots_dir = os.path.join(cache_dir, "snapshots")
        if not os.path.isdir(cache_dir):
            continue
        snapshot_count = 0
        snapshot_path = None
        if os.path.isdir(snapshots_dir):
            snapshots = sorted(
                os.path.join(snapshots_dir, name)
                for name in os.listdir(snapshots_dir)
                if os.path.isdir(os.path.join(snapshots_dir, name))
            )
            snapshot_count = len(snapshots)
            snapshot_path = snapshots[-1] if snapshots else None
        return {
            "model_id": model_id,
            "cached": True,
            "cache_dir": cache_dir,
            "snapshot_count": snapshot_count,
            "snapshot_path": snapshot_path,
            "source": "huggingface_hub",
        }
    return {
        "model_id": model_id,
        "cached": False,
        "cache_dir": None,
        "snapshot_count": 0,
        "snapshot_path": None,
        "source": "huggingface_hub",
    }


def _existing_parent(path: str) -> str:
    candidate = os.path.expanduser(path)
    while candidate and not os.path.exists(candidate):
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent
    return candidate if os.path.exists(candidate) else "/"


def _model_cache_disk_state() -> dict[str, Any]:
    root = _huggingface_cache_roots()[0]
    usage_path = _existing_parent(root)
    usage = shutil.disk_usage(usage_path)
    return {
        "cache_root": root,
        "usage_path": usage_path,
        "free_gb": round(usage.free / (1024**3), 3),
        "total_gb": round(usage.total / (1024**3), 3),
        "used_gb": round(usage.used / (1024**3), 3),
    }


def _candidate_model_dict(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, str):
        raw = {"model_id": raw}
    if not isinstance(raw, dict):
        return None
    model_id = str(raw.get("model_id") or raw.get("id") or raw.get("name") or "").strip()
    if not model_id:
        return None
    return {
        "model_id": model_id,
        "expected_size_gb": _float_or(raw.get("expected_size_gb"), 0.0),
        "target_modules": str(raw.get("target_modules") or "").strip(),
        "training_profile": str(raw.get("training_profile") or raw.get("profile") or "").strip(),
        "notes": str(raw.get("notes") or raw.get("reason") or "").strip(),
    }


def lora_base_model_plan(payload: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    payload = payload or {}
    project_id = payload.get("project_id") or project_id or current_project_id()
    readiness = lora_training_readiness(project_id=project_id)
    raw_candidates = payload.get("candidates") or payload.get("models") or list(DEFAULT_LORA_BASE_MODEL_CANDIDATES)
    if isinstance(raw_candidates, (str, dict)):
        raw_candidates = [raw_candidates]
    candidates = [_candidate_model_dict(item) for item in raw_candidates if item is not None]
    candidates = [candidate for candidate in candidates if candidate]
    if not candidates:
        candidates = [dict(candidate) for candidate in DEFAULT_LORA_BASE_MODEL_CANDIDATES]

    disk = _model_cache_disk_state()
    safety_multiplier = max(1.0, _float_or(payload.get("disk_safety_multiplier"), 1.25))
    planned: list[dict[str, Any]] = []
    for candidate in candidates:
        cache = _base_model_cache_status(candidate["model_id"])
        expected_size_gb = float(candidate.get("expected_size_gb") or 0.0)
        required_free_gb = round(expected_size_gb * safety_multiplier, 3) if expected_size_gb else None
        enough_disk = required_free_gb is None or disk["free_gb"] >= required_free_gb
        if readiness["status"] != "READY":
            action = "fix_lora_readiness"
        elif cache["cached"]:
            action = "train"
        elif enough_disk:
            action = "download_and_pin"
        else:
            action = "free_disk"
        planned.append(
            {
                **candidate,
                "cache": cache,
                "cached": bool(cache["cached"]),
                "offline_trainable": bool(readiness["ready"] and cache["cached"]),
                "download_required": not cache["cached"],
                "required_free_gb": required_free_gb,
                "enough_disk": enough_disk,
                "next_action": action,
                "train_command": (
                    f"python scripts/train_policy_lora.py policy_sft.jsonl --base-model {candidate['model_id']} "
                    "--output-dir /tmp/mem1-policy-lora --dry-run --require-cached-model"
                ),
            }
        )

    real_candidates = [item for item in planned if item["training_profile"] != "smoke_only"]
    recommended = next((item for item in real_candidates if item["next_action"] in {"train", "download_and_pin"}), None)
    recommended = recommended or (planned[0] if planned else None)
    return {
        "schema_version": "mem1-lora-base-model-plan-v1",
        "project_id": project_id,
        "readiness_status": readiness["status"],
        "readiness_ready": readiness["ready"],
        "cache_roots": _huggingface_cache_roots(),
        "disk": disk,
        "disk_safety_multiplier": safety_multiplier,
        "candidate_count": len(planned),
        "candidates": planned,
        "recommended_model_id": recommended.get("model_id") if recommended else None,
        "recommended_next_action": recommended.get("next_action") if recommended else None,
        "cached_base_model_count": readiness.get("cached_base_model_count", 0),
        "approved_export_count": readiness.get("approved_export_count", 0),
    }


def lora_training_readiness(project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    dependencies = {
        name: importlib.util.find_spec(name) is not None
        for name in LORA_REQUIRED_PACKAGES
    }
    missing = [name for name, available in dependencies.items() if not available]
    cached_base_models = _cached_huggingface_base_models()
    cuda_available: bool | None = None
    cuda_device_count = 0
    cuda_device_name: str | None = None
    if dependencies.get("torch"):
        try:
            import torch  # type: ignore[import-not-found]

            cuda_available = bool(torch.cuda.is_available())
            cuda_device_count = int(torch.cuda.device_count()) if cuda_available else 0
            if cuda_device_count:
                cuda_device_name = str(torch.cuda.get_device_name(0))
        except Exception:
            cuda_available = False
    with get_db() as conn:
        approved_exports = conn.execute(
            "SELECT COUNT(*) AS c FROM trace_export_approvals WHERE project_id = ? AND status = 'APPROVED'",
            (project_id,),
        ).fetchone()["c"]
        latest_approval_row = conn.execute(
            """
            SELECT *
              FROM trace_export_approvals
             WHERE project_id = ? AND status = 'APPROVED'
             ORDER BY reviewed_at DESC, created_at DESC
             LIMIT 1
            """,
            (project_id,),
        ).fetchone()
    if missing:
        status = "MISSING_DEPENDENCIES"
    elif cuda_available is False:
        status = "NO_CUDA"
    elif not approved_exports:
        status = "NO_APPROVED_DATASET"
    else:
        status = "READY"
    latest = (
        {
            "id": latest_approval_row["id"],
            "status": latest_approval_row["status"],
            "dataset_version": latest_approval_row["dataset_version"],
            "result_count": latest_approval_row["result_count"],
            "source_counts": json_loads(latest_approval_row["source_counts"], {}),
            "trace_audit_id": latest_approval_row["trace_audit_id"],
            "reviewed_at": latest_approval_row["reviewed_at"],
        }
        if latest_approval_row
        else None
    )
    return {
        "schema_version": "mem1-lora-readiness-v1",
        "project_id": project_id,
        "status": status,
        "ready": status == "READY",
        "dependencies": dependencies,
        "missing_dependencies": missing,
        "gpu": {
            "cuda_available": cuda_available,
            "device_count": cuda_device_count,
            "device_name": cuda_device_name,
        },
        "approved_export_count": int(approved_exports),
        "latest_approved_export": latest,
        "required_packages": list(LORA_REQUIRED_PACKAGES),
        "cached_base_model_count": len(cached_base_models),
        "cached_base_models": cached_base_models,
        "offline_ready": bool(cached_base_models),
    }


def _evaluation_alias_candidates(item: dict[str, Any], query: str) -> list[dict[str, str]]:
    raw_candidates = item.get("expected_aliases") or item.get("alias_proposals") or []
    if isinstance(raw_candidates, dict):
        raw_candidates = [raw_candidates]
    candidates: list[dict[str, str]] = []
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            continue
        entity = str(raw.get("entity") or raw.get("canonical") or raw.get("expected_entity") or "").strip()
        alias = str(raw.get("alias") or raw.get("alias_candidate") or raw.get("observed_alias") or "").strip()
        if entity and alias:
            candidates.append({"entity": entity, "alias": alias, "entity_type": str(raw.get("entity_type") or raw.get("entityType") or "concept")})

    entity = str(item.get("expected_entity") or item.get("canonical_entity") or "").strip()
    alias = str(item.get("alias_candidate") or item.get("observed_alias") or item.get("alias") or "").strip()
    if entity and not alias:
        alias = query.strip()
    if entity and alias:
        candidates.append({"entity": entity, "alias": alias, "entity_type": str(item.get("entity_type") or item.get("entityType") or "concept")})

    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        key = (normalize_entity(candidate["entity"]), normalize_entity(candidate["alias"]))
        if not key[0] or not key[1] or key[0] == key[1] or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _pending_alias_proposal_exists(project_id: str, entity: str, alias: str) -> bool:
    normalized_entity = normalize_entity(entity)
    normalized_alias = normalize_entity(alias)
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT payload FROM proposals
             WHERE project_id = ? AND proposal_type = 'entity_alias' AND status = 'PENDING'
            """,
            (project_id,),
        ).fetchall()
    for row in rows:
        payload = json_loads(row["payload"], {})
        if normalize_entity(str(payload.get("entity") or "")) == normalized_entity and normalize_entity(str(payload.get("alias") or "")) == normalized_alias:
            return True
    return False


def _alias_already_known(project_id: str, entity: str, alias: str) -> bool:
    normalized_entity = normalize_entity(entity)
    normalized_alias = normalize_entity(alias)
    aliases = _entity_alias_map(project_id)
    row = aliases.get(normalized_alias)
    return bool(row and row.get("normalized_entity") == normalized_entity)


def _default_evaluation_family(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name or "").lower()).strip("_")
    for prefix in (
        "multi_session",
        "team_workspace",
        "noisy_tool",
        "long_horizon",
        "multi_user",
        "group_chat",
        "context_budget",
        "smoke",
    ):
        if normalized.startswith(prefix):
            return prefix
    return normalized.split("_", 1)[0] if normalized else "default"


def _evaluation_item_family(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    family = metadata.get("family") or item.get("family") or _default_evaluation_family(str(item.get("name") or ""))
    return str(family or "default").strip().lower()


def _evaluation_family_summaries(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for item in items:
        family = _evaluation_item_family(item)
        metrics = item.get("metrics", {})
        try:
            accuracy = float(metrics.get("accuracy") or 0)
        except (TypeError, ValueError):
            accuracy = 0.0
        bucket = summaries.setdefault(
            family,
            {
                "family": family,
                "count": 0,
                "regression_count": 0,
                "accuracy_total": 0.0,
                "best_accuracy": None,
                "latest_accuracy": None,
                "latest_regression": False,
                "latest_evaluation_id": None,
                "latest_created_at": None,
            },
        )
        bucket["count"] += 1
        bucket["accuracy_total"] += accuracy
        bucket["regression_count"] += 1 if metrics.get("regression") else 0
        bucket["best_accuracy"] = accuracy if bucket["best_accuracy"] is None else max(bucket["best_accuracy"], accuracy)
        if bucket["latest_created_at"] is None:
            bucket["latest_accuracy"] = accuracy
            bucket["latest_regression"] = bool(metrics.get("regression", False))
            bucket["latest_evaluation_id"] = item["id"]
            bucket["latest_created_at"] = item["created_at"]
    results = []
    for bucket in summaries.values():
        bucket["avg_accuracy"] = round(bucket.pop("accuracy_total") / max(bucket["count"], 1), 4)
        results.append(bucket)
    return sorted(results, key=lambda item: item["family"])


def evaluation_row(row: Any) -> dict[str, Any]:
    item = {
        "id": row["id"],
        "project_id": row["project_id"],
        "name": row["name"],
        "status": row["status"],
        "dataset": json_loads(row["dataset"], []),
        "results": json_loads(row["results"], {}),
        "metrics": json_loads(row["metrics"], {}),
        "metadata": json_loads(row["metadata"], {}) if "metadata" in row.keys() else {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    item["family"] = _evaluation_item_family(item)
    return item


def create_evaluation(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    project_id = payload.get("project_id") or project_id or current_project_id()
    dataset = payload.get("dataset") or payload.get("items") or []
    if not isinstance(dataset, list) or not dataset:
        raise HTTPException(status_code=400, detail="dataset is required")
    name = payload.get("name") or "Memory Evaluation"
    metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata") or {}, dict) else {}
    family = payload.get("family") or payload.get("benchmark_family") or metadata.get("family")
    if family:
        metadata["family"] = str(family)
    eval_id = str(new_id())
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    feedback_actions: list[dict[str, Any]] = []
    alias_failures: dict[tuple[str, str], dict[str, Any]] = {}
    hits = 0
    total = 0
    total_latency = 0.0
    apply_feedback = bool(payload.get("apply_feedback", False))
    generate_alias_proposals = bool(payload.get("generate_alias_proposals", False))
    min_alias_failures = max(1, int(payload.get("min_alias_failures") or 2))

    for index, item in enumerate(dataset):
        query = str(item.get("query") or "").strip()
        filters = item.get("filters") or {}
        expected_contains = [str(v).lower() for v in item.get("expected_contains", [])]
        not_expected_contains = [str(v).lower() for v in item.get("not_expected_contains", [])]
        expected_ids = {str(v) for v in item.get("expected_memory_ids", [])}
        top_k = _validated_search_top_k_value(
            item.get("top_k") if item.get("top_k") is not None else payload.get("top_k"),
            default=10,
        )
        threshold_raw = item.get("threshold", payload.get("threshold", 0))
        threshold = _validated_search_threshold_value(0 if threshold_raw is None else threshold_raw)
        item_started = time.perf_counter()
        try:
            # A dataset row that predates the filter contract (or carries a
            # typo) scores as a failed row; it must not abort the whole run
            # like a malformed run request would.
            validate_filters(filters)
        except HTTPException as exc:
            total += 1
            results.append({"index": index, "query": query, "matched": False, "error": str(exc.detail), "results": []})
            continue
        try:
            search = search_memories(
                {
                    "query": query,
                    "filters": filters,
                    "top_k": top_k,
                    "threshold": threshold,
                    "rerank": bool(item.get("rerank", payload.get("rerank", True))),
                    "reference_date": item.get("reference_date", payload.get("reference_date")),
                },
                project_id=project_id,
            )
            latency = round((time.perf_counter() - item_started) * 1000, 3)
            returned = search["results"]
            text_blob = "\n".join(result.get("memory", "").lower() for result in returned)
            id_set = {result.get("id") for result in returned}
            matched = True
            if expected_contains:
                matched = all(fragment in text_blob for fragment in expected_contains)
            if not_expected_contains:
                matched = matched and all(fragment not in text_blob for fragment in not_expected_contains)
            if expected_ids:
                matched = expected_ids.issubset(id_set)
            if generate_alias_proposals and not matched:
                for candidate in _evaluation_alias_candidates(item, query):
                    key = (normalize_entity(candidate["entity"]), normalize_entity(candidate["alias"]))
                    bucket = alias_failures.setdefault(
                        key,
                        {"payload": candidate, "count": 0, "queries": [], "indexes": []},
                    )
                    bucket["count"] += 1
                    bucket["queries"].append(query)
                    bucket["indexes"].append(index)
            if apply_feedback and returned:
                top_result = returned[0]
                feedback_actions.append(
                    {
                        "memory_id": top_result["id"],
                        "feedback": "POSITIVE" if matched else "NEGATIVE",
                        "feedback_reason": f"evaluation:{name}:{'matched' if matched else 'missed'}:{query}",
                    }
                )
            hits += 1 if matched else 0
            total += 1
            total_latency += latency
            results.append(
                {
                    "index": index,
                    "query": query,
                    "matched": matched,
                    "latency": latency,
                    "expected_contains": expected_contains,
                    "not_expected_contains": not_expected_contains,
                    "expected_memory_ids": list(expected_ids),
                    "results": returned,
                }
            )
        except HTTPException:
            raise
        except Exception as exc:
            total += 1
            results.append({"index": index, "query": query, "matched": False, "error": str(exc), "results": []})

    elapsed = round((time.perf_counter() - started) * 1000, 3)
    applied_feedback: list[dict[str, Any]] = []
    if apply_feedback:
        for action in feedback_actions:
            try:
                applied_feedback.append(submit_memory_feedback(action, project_id=project_id))
            except HTTPException:
                pass
    alias_proposals: list[dict[str, Any]] = []
    if generate_alias_proposals:
        for failure in alias_failures.values():
            candidate = failure["payload"]
            if failure["count"] < min_alias_failures:
                continue
            if _alias_already_known(project_id, candidate["entity"], candidate["alias"]):
                continue
            if _pending_alias_proposal_exists(project_id, candidate["entity"], candidate["alias"]):
                continue
            evidence = {
                "source": "evaluation",
                "evaluation_name": name,
                "failure_count": failure["count"],
                "queries": failure["queries"],
                "indexes": failure["indexes"],
            }
            proposal = create_proposal(
                {
                    "proposal_type": "entity_alias",
                    "payload": {**candidate, "evidence": evidence},
                    "review_reason": f"evaluation:{name}:alias_failure:{failure['count']}",
                },
                project_id=project_id,
            )
            proposal["failure_count"] = failure["count"]
            proposal["queries"] = failure["queries"]
            proposal["indexes"] = failure["indexes"]
            alias_proposals.append(proposal)
    metrics = {
        "accuracy": round(hits / total, 4) if total else 0,
        "hit_count": hits,
        "item_count": total,
        "avg_latency": round(total_latency / total, 3) if total else 0,
        "total_latency": elapsed,
        "token_efficiency": round((hits / max(token_estimate(results), 1)) * 1000, 4) if hits else 0,
        "feedback_count": len(applied_feedback),
        "alias_proposal_count": len(alias_proposals),
    }
    regression_threshold = max(0.0, float(payload.get("regression_threshold") or 0))
    now = utc_now()
    data = {"items": results, "feedback": applied_feedback, "alias_proposals": alias_proposals}
    with get_db() as conn:
        previous = conn.execute(
            """
            SELECT id, metrics FROM evaluations
            WHERE project_id = ? AND name = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (project_id, name),
        ).fetchone()
        previous_accuracy: float | None = None
        previous_evaluation_id = previous["id"] if previous else None
        if previous:
            try:
                previous_accuracy = float(json_loads(previous["metrics"], {}).get("accuracy"))
            except (TypeError, ValueError):
                previous_accuracy = None
        accuracy_delta = round(metrics["accuracy"] - previous_accuracy, 4) if previous_accuracy is not None else None
        metrics.update(
            {
                "previous_evaluation_id": previous_evaluation_id,
                "previous_accuracy": round(previous_accuracy, 4) if previous_accuracy is not None else None,
                "accuracy_delta": accuracy_delta,
                "regression_threshold": regression_threshold,
                "regression": bool(accuracy_delta is not None and accuracy_delta < -regression_threshold),
            }
        )
        conn.execute(
            """
            INSERT INTO evaluations (
                id, project_id, name, status, dataset, results, metrics, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eval_id,
                project_id,
                name,
                "SUCCEEDED",
                json_dumps(dataset),
                json_dumps(data),
                json_dumps(metrics),
                json_dumps(metadata),
                now,
                now,
            ),
        )
    record_usage(
        project_id,
        "memory_evaluation",
        input_tokens=token_estimate(dataset),
        output_tokens=token_estimate(data),
        latency=elapsed,
        metadata={"evaluation_id": eval_id, "family": metadata.get("family"), **metrics},
    )
    return {
        "id": eval_id,
        "project_id": project_id,
        "name": name,
        "status": "SUCCEEDED",
        "metrics": metrics,
        "metadata": metadata,
        "family": _evaluation_item_family({"name": name, "metadata": metadata}),
        "results": data,
        "created_at": now,
        "updated_at": now,
    }


def create_context_evaluation(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    project_id = payload.get("project_id") or project_id or current_project_id()
    dataset = payload.get("context") or payload.get("dataset") or payload.get("items") or []
    if not isinstance(dataset, list) or not dataset:
        raise HTTPException(status_code=400, detail="context dataset is required")
    name = payload.get("name") or "Context Evaluation"
    metadata = dict(payload.get("metadata") or {}) if isinstance(payload.get("metadata") or {}, dict) else {}
    family = payload.get("family") or payload.get("benchmark_family") or metadata.get("family") or "context_composer"
    metadata["family"] = str(family)
    metadata["evaluation_type"] = "context"
    eval_id = str(new_id())
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    hits = 0
    total = 0
    total_latency = 0.0
    total_used_tokens = 0
    total_omitted = 0
    budget_violations = 0
    expected_misses = 0
    stale_violations = 0
    omission_violations = 0
    composer_external_count = 0
    composer_fallback_count = 0
    expected_composer_fallback_count = 0
    unexpected_composer_fallback_count = 0
    working_memory_overflow_count = 0
    working_memory_high_pressure_count = 0
    total_working_memory_slots = 0
    context_evidence_missing_count = 0
    context_evidence_hash_mismatch_count = 0
    context_grounding_verified_count = 0
    context_grounding_missing_count = 0
    context_grounding_unsupported_count = 0

    for index, item in enumerate(dataset):
        query = str(item.get("query") or "").strip()
        budget_tokens = int(item.get("budget_tokens") or item.get("budget") or payload.get("budget_tokens") or 800)
        expected_contains = [str(v).lower() for v in item.get("expected_contains", [])]
        not_expected_contains = [str(v).lower() for v in item.get("not_expected_contains", [])]
        expected_ids = {str(v) for v in item.get("expected_memory_ids", [])}
        min_omitted = item.get("min_omitted_count")
        top_k_raw = item.get("top_k")
        if top_k_raw is None:
            top_k_raw = payload.get("top_k")
        if top_k_raw is None:
            top_k_raw = item.get("limit")
        if top_k_raw is None:
            top_k_raw = payload.get("limit")
        top_k = _validated_search_top_k_value(top_k_raw, default=10)
        threshold_raw = item.get("threshold", payload.get("threshold", 0.1))
        threshold = _validated_search_threshold_value(0.1 if threshold_raw is None else threshold_raw)
        expect_composer_fallback = _bool_or(
            item.get(
                "expect_composer_fallback",
                item.get(
                    "expected_composer_fallback",
                    payload.get("expect_composer_fallback", payload.get("expected_composer_fallback")),
                ),
            ),
            False,
        )
        item_started = time.perf_counter()
        try:
            context = assemble_context(
                {
                    **item,
                    "budget_tokens": budget_tokens,
                    "top_k": top_k,
                    "threshold": threshold,
                    "rerank": bool(item.get("rerank", payload.get("rerank", True))),
                    "working_memory_slots": item.get("working_memory_slots")
                    or item.get("slot_capacity")
                    or item.get("slots")
                    or payload.get("working_memory_slots")
                    or payload.get("slot_capacity")
                    or payload.get("slots"),
                    "composer_url": item.get("composer_url") or item.get("context_composer_url") or payload.get("composer_url") or payload.get("context_composer_url"),
                    "composer_model": item.get("composer_model") or item.get("context_composer_model") or payload.get("composer_model") or payload.get("context_composer_model"),
                    "composer_api_key": item.get("composer_api_key") or item.get("context_composer_api_key") or payload.get("composer_api_key") or payload.get("context_composer_api_key"),
                    "composer_timeout": item.get("composer_timeout") or item.get("context_composer_timeout") or payload.get("composer_timeout") or payload.get("context_composer_timeout"),
                },
                project_id=project_id,
            )
            latency = round((time.perf_counter() - item_started) * 1000, 3)
            text_blob = str(context.get("context") or "").lower()
            selected_ids = {str(memory.get("id")) for memory in context.get("memories", [])}
            budget_ok = int(context.get("used_tokens") or 0) <= budget_tokens
            expected_ok = all(fragment in text_blob for fragment in expected_contains)
            stale_ok = all(fragment not in text_blob for fragment in not_expected_contains)
            ids_ok = expected_ids.issubset(selected_ids)
            evidence = context.get("evidence") if isinstance(context.get("evidence"), dict) else {}
            evidence_ids = {str(value) for value in evidence.get("memory_ids") or []}
            evidence_hashes = evidence.get("source_hashes") if isinstance(evidence.get("source_hashes"), dict) else {}
            evidence_ok = (
                evidence.get("schema_version") == "mem1-context-evidence-v1"
                and isinstance(evidence.get("context_sha256"), str)
                and len(str(evidence.get("context_sha256"))) == 64
            )
            evidence_hashes_ok = evidence_ids == selected_ids and set(evidence_hashes) == evidence_ids
            omitted_ok = True
            if min_omitted is not None:
                omitted_ok = int(context.get("omitted_count") or 0) >= int(min_omitted)
            matched = bool(budget_ok and expected_ok and stale_ok and ids_ok and omitted_ok and evidence_ok and evidence_hashes_ok)
            hits += 1 if matched else 0
            total += 1
            total_latency += latency
            total_used_tokens += int(context.get("used_tokens") or 0)
            total_omitted += int(context.get("omitted_count") or 0)
            composer = context.get("composer") if isinstance(context.get("composer"), dict) else {}
            composer_external_count += 1 if composer.get("external") else 0
            composer_fallback = bool(composer.get("fallback"))
            composer_fallback_count += 1 if composer_fallback else 0
            expected_composer_fallback_count += 1 if composer_fallback and expect_composer_fallback else 0
            unexpected_composer_fallback_count += 1 if composer_fallback and not expect_composer_fallback else 0
            claim_verification = composer.get("claim_verification") if isinstance(composer.get("claim_verification"), dict) else None
            if composer.get("external") and not composer_fallback:
                if not claim_verification:
                    context_grounding_missing_count += 1
                elif claim_verification.get("status") != "VERIFIED" or int(claim_verification.get("unsupported_count") or 0):
                    context_grounding_unsupported_count += 1
                else:
                    context_grounding_verified_count += 1
            working_memory = context.get("working_memory") if isinstance(context.get("working_memory"), dict) else {}
            working_memory_overflow_count += int(working_memory.get("overflow_count") or 0)
            working_memory_high_pressure_count += 1 if working_memory.get("pressure") == "high" else 0
            total_working_memory_slots += int(working_memory.get("slot_count") or 0)
            budget_violations += 0 if budget_ok else 1
            expected_misses += 0 if expected_ok and ids_ok else 1
            stale_violations += 0 if stale_ok else 1
            omission_violations += 0 if omitted_ok else 1
            context_evidence_missing_count += 0 if evidence_ok else 1
            context_evidence_hash_mismatch_count += 0 if evidence_hashes_ok else 1
            results.append(
                {
                    "index": index,
                    "query": query,
                    "matched": matched,
                    "latency": latency,
                    "budget_ok": budget_ok,
                    "expected_ok": expected_ok,
                    "stale_ok": stale_ok,
                    "ids_ok": ids_ok,
                    "omitted_ok": omitted_ok,
                    "evidence_ok": evidence_ok,
                    "evidence_hashes_ok": evidence_hashes_ok,
                    "expect_composer_fallback": expect_composer_fallback,
                    "expected_contains": expected_contains,
                    "not_expected_contains": not_expected_contains,
                    "expected_memory_ids": list(expected_ids),
                    "budget_tokens": budget_tokens,
                    "used_tokens": context.get("used_tokens"),
                    "omitted_count": context.get("omitted_count"),
                    "selected_count": context.get("selected_count"),
                    "context": context.get("context"),
                    "composer": composer,
                    "working_memory": working_memory,
                    "evidence": evidence,
                    "memories": context.get("memories", []),
                }
            )
        except HTTPException:
            raise
        except Exception as exc:
            total += 1
            context_evidence_missing_count += 1
            context_evidence_hash_mismatch_count += 1
            results.append({"index": index, "query": query, "matched": False, "error": str(exc), "context": ""})

    elapsed = round((time.perf_counter() - started) * 1000, 3)
    metrics = {
        "accuracy": round(hits / total, 4) if total else 0,
        "hit_count": hits,
        "item_count": total,
        "avg_latency": round(total_latency / total, 3) if total else 0,
        "total_latency": elapsed,
        "avg_used_tokens": round(total_used_tokens / total, 3) if total else 0,
        "avg_omitted_count": round(total_omitted / total, 3) if total else 0,
        "budget_violation_count": budget_violations,
        "expected_miss_count": expected_misses,
        "stale_violation_count": stale_violations,
        "omission_violation_count": omission_violations,
        "composer_external_count": composer_external_count,
        "composer_fallback_count": composer_fallback_count,
        "expected_composer_fallback_count": expected_composer_fallback_count,
        "unexpected_composer_fallback_count": unexpected_composer_fallback_count,
        "working_memory_overflow_count": working_memory_overflow_count,
        "working_memory_high_pressure_count": working_memory_high_pressure_count,
        "avg_working_memory_slots": round(total_working_memory_slots / total, 3) if total else 0,
        "context_evidence_missing_count": context_evidence_missing_count,
        "context_evidence_hash_mismatch_count": context_evidence_hash_mismatch_count,
        "context_grounding_verified_count": context_grounding_verified_count,
        "context_grounding_missing_count": context_grounding_missing_count,
        "context_grounding_unsupported_count": context_grounding_unsupported_count,
        "context_token_efficiency": round((hits / max(total_used_tokens, 1)) * 1000, 4) if hits else 0,
    }
    regression_threshold = max(0.0, float(payload.get("regression_threshold") or 0))
    now = utc_now()
    data = {"items": results}
    with get_db() as conn:
        previous = conn.execute(
            """
            SELECT id, metrics FROM evaluations
            WHERE project_id = ? AND name = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (project_id, name),
        ).fetchone()
        previous_accuracy: float | None = None
        previous_evaluation_id = previous["id"] if previous else None
        if previous:
            try:
                previous_accuracy = float(json_loads(previous["metrics"], {}).get("accuracy"))
            except (TypeError, ValueError):
                previous_accuracy = None
        accuracy_delta = round(metrics["accuracy"] - previous_accuracy, 4) if previous_accuracy is not None else None
        metrics.update(
            {
                "previous_evaluation_id": previous_evaluation_id,
                "previous_accuracy": round(previous_accuracy, 4) if previous_accuracy is not None else None,
                "accuracy_delta": accuracy_delta,
                "regression_threshold": regression_threshold,
                "regression": bool(accuracy_delta is not None and accuracy_delta < -regression_threshold),
            }
        )
        conn.execute(
            """
            INSERT INTO evaluations (
                id, project_id, name, status, dataset, results, metrics, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eval_id,
                project_id,
                name,
                "SUCCEEDED",
                json_dumps(dataset),
                json_dumps(data),
                json_dumps(metrics),
                json_dumps(metadata),
                now,
                now,
            ),
        )
    record_usage(
        project_id,
        "context_evaluation",
        input_tokens=token_estimate(dataset),
        output_tokens=token_estimate(data),
        latency=elapsed,
        metadata={"evaluation_id": eval_id, "family": metadata.get("family"), **metrics},
    )
    return {
        "id": eval_id,
        "project_id": project_id,
        "name": name,
        "status": "SUCCEEDED",
        "metrics": metrics,
        "metadata": metadata,
        "family": _evaluation_item_family({"name": name, "metadata": metadata}),
        "results": data,
        "created_at": now,
        "updated_at": now,
    }


def list_evaluations(
    project_id: str | None = None,
    limit: int = 100,
    name: str | None = None,
    status: str | None = None,
    regression: bool | None = None,
    family: str | None = None,
) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    limit = min(max(limit, 1), 500)
    where = "WHERE project_id = ?"
    params: list[Any] = [project_id]
    if name:
        where += " AND name = ?"
        params.append(name)
    if status:
        where += " AND status = ?"
        params.append(status.upper())
    fetch_limit = 1000 if regression is not None or family else limit
    params.append(fetch_limit)
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM evaluations {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
    items = [evaluation_row(row) for row in rows]
    if regression is not None:
        items = [item for item in items if bool(item.get("metrics", {}).get("regression", False)) is regression]
    if family:
        expected_family = _evaluation_item_family({"name": family, "metadata": {"family": family}})
        items = [item for item in items if _evaluation_item_family(item) == expected_family]
    items = items[:limit]
    filters = {"name": name, "status": status, "regression": regression, "family": family}
    return {
        "project_id": project_id,
        "count": len(items),
        "filters": {key: value for key, value in filters.items() if value is not None},
        "families": _evaluation_family_summaries(items),
        "results": items,
    }


def get_evaluation(evaluation_id: str, project_id: str | None = None) -> dict[str, Any]:
    project_id = project_id or current_project_id()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM evaluations WHERE id = ? AND project_id = ?",
            (evaluation_id, project_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return evaluation_row(row)


def normalize_webhook_event(event_type: str) -> str:
    return event_type.strip().lower().replace(":", "_")


def webhook_delivery_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"] if "project_id" in row.keys() else "proj_local",
        "webhook_id": row["webhook_id"],
        "event_type": row["event_type"],
        "url": row["url"],
        "payload": json_loads(row["payload"], {}),
        "status": row["status"],
        "status_code": row["status_code"],
        "response_body": row["response_body"],
        "error": row["error"],
        "attempts": row["attempts"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_webhook_deliveries(webhook_id: str | None = None, limit: int = 100, project_id: str | None = None) -> list[dict[str, Any]]:
    project_id = project_id or current_project_id()
    limit = min(max(limit, 1), 500)
    with get_db() as conn:
        if webhook_id:
            rows = conn.execute(
                "SELECT * FROM webhook_deliveries WHERE webhook_id = ? AND project_id = ? ORDER BY created_at DESC LIMIT ?",
                (webhook_id, project_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM webhook_deliveries WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
    return [webhook_delivery_row(row) for row in rows]


def _record_webhook_delivery(
    project_id: str,
    webhook_id: str,
    event_type: str,
    url: str,
    payload: dict[str, Any],
    status: str,
    status_code: int | None = None,
    response_body: str = "",
    error: str = "",
    attempts: int = 1,
) -> None:
    now = utc_now()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO webhook_deliveries (
                id, project_id, webhook_id, event_type, url, payload, status, status_code,
                response_body, error, attempts, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(new_id()),
                project_id,
                webhook_id,
                event_type,
                url,
                json_dumps(payload),
                status,
                status_code,
                response_body[:1000],
                error[:1000],
                attempts,
                now,
                now,
            ),
        )


def emit_webhook_event(event_type: str, event_details: dict[str, Any], project_id: str = "proj_local") -> None:
    normalized = normalize_webhook_event(event_type)
    payload = {"event_details": {"event": normalized.removeprefix("memory_").upper(), **event_details}}
    max_attempts = max(1, int(os.getenv("MEM1_WEBHOOK_RETRIES", "3")))
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM webhooks WHERE is_active = 1 AND project_id = ? ORDER BY created_at ASC",
            (project_id,),
        ).fetchall()
    for row in rows:
        subscribed = {normalize_webhook_event(item) for item in json_loads(row["event_types"], [])}
        if normalized not in subscribed and "*" not in subscribed:
            continue
        url = row["url"]
        if url.startswith("mem1://"):
            _record_webhook_delivery(project_id, row["webhook_id"], normalized, url, payload, "SUCCEEDED", 202, "local capture")
            continue
        attempts = 0
        last_status_code: int | None = None
        last_response = ""
        last_error = ""
        status = "FAILED"
        for attempt in range(1, max_attempts + 1):
            attempts = attempt
            try:
                with httpx.Client(timeout=2.5) as client:
                    response = client.post(
                        url,
                        json=payload,
                        headers={
                            "User-Agent": "Mem1-Webhook/0.1",
                            "X-Mem1-Event": normalized,
                            "X-Mem0-Event": normalized,
                            "X-Mem1-Webhook-Id": row["webhook_id"],
                        },
                    )
                last_status_code = response.status_code
                last_response = response.text
                last_error = ""
                status = "SUCCEEDED" if 200 <= response.status_code < 300 else "FAILED"
                if status == "SUCCEEDED":
                    break
            except Exception as exc:
                last_status_code = None
                last_response = ""
                last_error = str(exc)
        _record_webhook_delivery(
            project_id,
            row["webhook_id"],
            normalized,
            url,
            payload,
            status,
            last_status_code,
            last_response,
            last_error,
            attempts,
        )
