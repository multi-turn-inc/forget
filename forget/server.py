"""Forget — the open-source memory engine, served over HTTP.

Two surfaces:
  * ``POST /mcp`` — the MCP endpoint (streamable-http JSON-RPC). This is how
    Claude Code, Claude Desktop (via mcp-remote), and Codex connect.
  * ``/v1/memories/...`` — a minimal REST surface over the same engine.

Auth is a Bearer/Token API key resolved by ``store.require_auth``. The core
is single-tenant and quota-free; hosted deployments inject tenancy and
billing through :mod:`forget.ports` without the core importing either.
"""
from __future__ import annotations

from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .db import init_db
from .mcp import TOOLS, handle_mcp_rpc, mem1_capabilities_payload
from .store import (
    add_memories,
    delete_memories,
    delete_memory,
    get_event,
    get_memories,
    get_memory,
    list_events,
    list_memory_dicts,
    memory_history,
    memory_relations,
    require_auth,
    search_memories,
    stale_candidate_pairs,
    submit_memory_feedback,
    supersede_memory,
    update_memory,
)
from .utils import ENTITY_FIELDS, parse_datetime, utc_now

app = FastAPI(title="forget", description="Memory for your AI. It forgets the junk, keeps what matters.")

# Schema is created eagerly at import so plain TestClient(app) usage and
# one-off scripts work without lifespan events (mirrors the engine's history).
init_db()


async def auth(request: Request) -> None:
    require_auth(request)


@app.get("/ready")
def ready() -> dict[str, Any]:
    return {"status": "ready", "service": "forget"}


# --- MCP --------------------------------------------------------------------


@app.get("/mcp", dependencies=[Depends(auth)])
def mcp_info() -> dict[str, Any]:
    return {
        "name": "forget-mcp",
        "transport": "streamable-http",
        "tools": [tool["name"] for tool in TOOLS],
    }


def _mcp_dispatch(payload: Any, context: dict[str, str] | None) -> JSONResponse:
    if isinstance(payload, list):
        responses = [response for item in payload if (response := handle_mcp_rpc(item, context=context)) is not None]
        return JSONResponse(responses)
    response = handle_mcp_rpc(payload, context=context)
    if response is None:
        return JSONResponse({}, status_code=202)
    return JSONResponse(response)


@app.post("/mcp", dependencies=[Depends(auth)])
def mcp_rpc(payload: Any = Body(...), profile: str | None = None) -> JSONResponse:
    return _mcp_dispatch(payload, {"tool_profile": profile} if profile else None)


@app.get("/mcp/{app_id}/http/{user_id}", dependencies=[Depends(auth)])
def mcp_scope_info(app_id: str, user_id: str) -> dict[str, Any]:
    # Identity echo for connection doctors: confirms which scope this
    # endpoint pins before any tool call is made (forget-connect probes it).
    return {"name": "forget-mcp", "user_id": user_id, "client_name": app_id}


@app.post("/mcp/{app_id}/http/{user_id}", dependencies=[Depends(auth)])
def mcp_rpc_scoped(
    app_id: str, user_id: str, payload: Any = Body(...), profile: str | None = None
) -> JSONResponse:
    # Scoped MCP endpoint (same path shape as the hosted gateway): every
    # tool call inherits this user/app scope unless the caller names an
    # entity explicitly — an unscoped local /mcp connection otherwise
    # searches the default scope and misses the user's memories entirely
    # (2026-07-13 dogfooding: a fresh client recalled nothing).
    context: dict[str, str] = {"user_id": user_id, "client_name": app_id}
    if profile:
        context["tool_profile"] = profile
    return _mcp_dispatch(payload, context)


@app.get("/v1/capabilities", dependencies=[Depends(auth)])
def capabilities() -> dict[str, Any]:
    return mem1_capabilities_payload()


# --- REST -------------------------------------------------------------------


@app.get("/v1/memories/", dependencies=[Depends(auth)])
def memories_list(
    user_id: str | None = None,
    agent_id: str | None = None,
    app_id: str | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    filters = {k: v for k, v in {"user_id": user_id, "agent_id": agent_id, "app_id": app_id, "run_id": run_id}.items() if v}
    return [m for m in list_memory_dicts() if not filters or all(m.get(k) == v for k, v in filters.items())]


@app.post("/v1/memories/", dependencies=[Depends(auth)])
def memories_create(payload: dict[str, Any]) -> dict[str, Any]:
    if "messages" not in payload:
        text = payload.get("text") or payload.get("memory") or payload.get("data")
        if not text:
            raise HTTPException(status_code=400, detail="messages or text is required")
        payload = {**payload, "messages": [{"role": "user", "content": str(text)}], "infer": False}
    result = add_memories(payload)
    event = get_event(result["event_id"])
    created = event.get("results", [])
    if not created:
        return result
    return get_memory(created[0]["id"])


@app.post("/v1/memories/search/", dependencies=[Depends(auth)])
def memories_search(payload: dict[str, Any]) -> dict[str, Any]:
    filters = payload.get("filters") or {field: payload[field] for field in ENTITY_FIELDS if field in payload}
    result = search_memories({**payload, "filters": filters})
    if payload.get("enable_graph"):
        result["relations"] = memory_relations(result.get("results", []))
    return result


@app.post("/v2/memories/", dependencies=[Depends(auth)])
def memories_list_filtered(payload: dict[str, Any], request: Request, page: int = 1, page_size: int = 100) -> dict[str, Any]:
    payload = payload or {}
    filters = payload.get("filters")
    if not isinstance(filters, dict) or not filters:
        envelope_keys = {"org_id", "project_id", "source", "page", "page_size", "show_expired"}
        filters = {key: value for key, value in payload.items() if key not in envelope_keys and value not in (None, "")}
    selected_project = str(payload.get("project_id") or getattr(request.state, "project_id", "proj_local"))
    normalized_page = max(int(page or payload.get("page") or 1), 1)
    normalized_page_size = min(max(int(page_size or payload.get("page_size") or 100), 1), 200)
    return get_memories(
        filters,
        page=normalized_page,
        page_size=normalized_page_size,
        project_id=selected_project,
        show_expired=bool(payload.get("show_expired", False)),
    )


@app.get("/v1/memories/events/", dependencies=[Depends(auth)])
def memories_events(page: int = 1, page_size: int = 100) -> dict[str, Any]:
    return list_events(page=page, page_size=page_size)


@app.post("/v1/memories/stale-candidates/", dependencies=[Depends(auth)])
def memories_stale_candidates(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return stale_candidate_pairs(payload or {})


@app.get("/v1/memories/{memory_id}/", dependencies=[Depends(auth)])
def memories_read(memory_id: str) -> dict[str, Any]:
    return get_memory(memory_id)


@app.put("/v1/memories/{memory_id}/", dependencies=[Depends(auth)])
def memories_update(memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return update_memory(memory_id, payload)


@app.post("/v1/memories/{memory_id}/supersede/", dependencies=[Depends(auth)])
def memories_supersede(memory_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return supersede_memory(memory_id, payload or {})


@app.delete("/v1/memories/{memory_id}/", dependencies=[Depends(auth)])
def memories_delete(memory_id: str) -> JSONResponse:
    return JSONResponse(delete_memory(memory_id), status_code=200)


@app.get("/v1/memories/{memory_id}/history/", dependencies=[Depends(auth)])
def memories_history(memory_id: str) -> list[dict[str, Any]]:
    return list(reversed(memory_history(memory_id)))


@app.delete("/v1/memories/", dependencies=[Depends(auth)])
def memories_delete_all(payload: dict[str, Any] | None = None) -> dict[str, str]:
    payload = payload or {}
    filters = payload.get("filters") or {field: payload[field] for field in ENTITY_FIELDS if field in payload}
    return delete_memories(filters)


@app.post("/v1/feedback/", dependencies=[Depends(auth)])
def submit_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    return submit_memory_feedback(payload)


# --- mem0-compatible v3 surface ----------------------------------------------
# Response shaping matches the mem0 platform contract so existing mem0 and
# OpenMemory clients can point at Forget unchanged.


def _public_metadata(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _public_categories(memory: dict[str, Any]) -> Any:
    metadata = _public_metadata(memory.get("metadata"))
    explicit = metadata.get("categories") or metadata.get("custom_categories")
    return explicit if explicit else None


def _structured_attributes(memory: dict[str, Any]) -> dict[str, Any]:
    timestamp = memory.get("created_at") or memory.get("updated_at") or utc_now()
    parsed = parse_datetime(timestamp) or parse_datetime(utc_now())
    if parsed is None:
        return {
            "year": 1970, "month": 1, "day": 1, "hour": 0, "minute": 0,
            "day_of_week": "Thursday", "day_of_year": 1, "week_of_year": 1,
            "quarter": 1, "is_weekend": False,
        }
    iso_calendar = parsed.isocalendar()
    return {
        "year": parsed.year,
        "month": parsed.month,
        "day": parsed.day,
        "hour": parsed.hour,
        "minute": parsed.minute,
        "day_of_week": parsed.strftime("%A"),
        "day_of_year": int(parsed.strftime("%j")),
        "week_of_year": int(iso_calendar.week),
        "quarter": ((parsed.month - 1) // 3) + 1,
        "is_weekend": parsed.weekday() >= 5,
    }


def _public_memory(memory: dict[str, Any]) -> dict[str, Any]:
    return {
        "categories": _public_categories(memory),
        "created_at": memory.get("created_at"),
        "expiration_date": memory.get("expiration_date"),
        "id": memory.get("id"),
        "memory": memory.get("memory"),
        "metadata": _public_metadata(memory.get("metadata")),
        "structured_attributes": _structured_attributes(memory),
        "updated_at": memory.get("updated_at"),
        "user_id": memory.get("user_id"),
    }


def _public_search_result(memory: dict[str, Any]) -> dict[str, Any]:
    score = float(memory.get("score") or 0.0)
    result = {
        "agent_id": memory.get("agent_id"),
        "app_id": memory.get("app_id"),
        "categories": _public_categories(memory),
        "created_at": memory.get("created_at"),
        "id": memory.get("id"),
        "memory": memory.get("memory"),
        "metadata": _public_metadata(memory.get("metadata")),
        "run_id": memory.get("run_id"),
        "score": score,
        "score_breakdown": memory.get("score_breakdown") or {},
        "updated_at": memory.get("updated_at"),
        "user_id": memory.get("user_id"),
    }
    if "reranker_score" in memory:
        result["reranker_score"] = memory.get("reranker_score")
    if memory.get("scope") == "fallback":
        result["scope"] = "fallback"
        result["scope_source"] = memory.get("scope_source")
    return result


@app.post("/v3/memories/add/", dependencies=[Depends(auth)])
def memories_add_v3(payload: dict[str, Any]) -> dict[str, Any]:
    result = add_memories(payload)
    return {"event_id": result["event_id"], "status": result["status"]}


@app.post("/v3/memories/", dependencies=[Depends(auth)])
def memories_list_v3(payload: dict[str, Any], page: int = 1, page_size: int = 100) -> Any:
    # mem0 platform v3 contract: POST /v3/memories/ with `messages` is an add.
    if isinstance(payload.get("messages"), list):
        result = add_memories(payload)
        return {"event_id": result["event_id"], "status": result["status"]}
    top_level_entities = [field for field in ENTITY_FIELDS if field in payload]
    if top_level_entities:
        return JSONResponse({"error": "Entity IDs must be passed inside filters"}, status_code=400)
    filters = payload.get("filters")
    if not isinstance(filters, dict):
        return JSONResponse({"error": "filters is required"}, status_code=400)
    result = get_memories(filters, page=page, page_size=page_size, show_expired=bool(payload.get("show_expired", False)))
    return {**result, "results": [_public_memory(item) for item in result.get("results", [])]}


@app.post("/v3/memories/search/", dependencies=[Depends(auth)])
def memories_search_v3(payload: dict[str, Any]) -> Any:
    top_level_entities = [field for field in ENTITY_FIELDS if field in payload]
    if top_level_entities:
        return JSONResponse({"error": "Entity IDs must be passed inside filters"}, status_code=400)
    if not payload.get("query"):
        return JSONResponse({"error": "query is required"}, status_code=400)
    result = search_memories(payload)
    return {"results": [_public_search_result(item) for item in result.get("results", [])]}
