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

import json
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .db import init_db
from .mcp import TEAM_AGENTS, TEAM_LEDGER_APP, TOOLS, handle_mcp_rpc, mem1_capabilities_payload
from .store import (
    add_memories,
    assemble_context,
    delete_memories,
    delete_memory,
    get_event,
    get_memories,
    get_memory,
    list_events,
    list_memory_dicts,
    strip_internal,
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
from . import __version__


def _source_commit() -> str | None:
    """Git commit of the source tree serving this process, or None when
    running from an installed dist. ``__version__`` alone can't distinguish
    two source checkouts (both say "+source"), so a dogfood deploy is only
    verifiable against the commit hash."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = out.stdout.strip()
    return commit if out.returncode == 0 and len(commit) == 40 else None


SOURCE_COMMIT = _source_commit()

app = FastAPI(
    title="forget",
    description="Memory for your AI. It forgets the junk, keeps what matters.",
    version=__version__,
)

# Schema is created eagerly at import so plain TestClient(app) usage and
# one-off scripts work without lifespan events (mirrors the engine's history).
init_db()


def _warm_recall_gate() -> None:
    """게이트 모델 예열 — 재시작 직후의 콜드 로드(실측 11s)가 첫 high-기어
    회상을 훅 한도 밖으로 밀어내 통째로 버려지게 한다. 1토큰 핑이 keep_alive
    상주를 미리 걸어둔다. 실패는 무해하므로 삼킨다 (TestClient 환경 포함)."""
    try:
        from . import store as _store
        llm = _store._resolve_recall_llm()
        if not llm or ":11434" not in llm["base_url"]:
            return
        import urllib.request as _rq
        req = _rq.Request(
            llm["base_url"].replace("/v1", "/api/chat"),
            data=json.dumps({
                "model": llm["model"], "messages": [{"role": "user", "content": "0"}],
                "stream": False, "think": False,
                "keep_alive": os.getenv("MEM1_GATE_KEEP_ALIVE", "24h"),
                "options": {"num_predict": 1},
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        _rq.urlopen(req, timeout=120).read()
    except Exception:
        pass


if os.getenv("MEM1_GATE_WARMUP", "1").strip().lower() not in {"0", "off", "false"}:
    threading.Thread(target=_warm_recall_gate, daemon=True).start()


async def auth(request: Request) -> None:
    require_auth(request)


@app.get("/ready")
def ready() -> dict[str, Any]:
    return {
        "status": "ready",
        "service": "forget",
        "version": __version__,
        "commit": SOURCE_COMMIT,
    }


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


def _credential_bound_team_principal(request: Request, claimed: str | None = None) -> str:
    """Resolve team attribution from the authenticated API-key row.

    Query parameters are never credentials. ``principal`` is retained only as
    a migration assertion and must match the principal bound to the bearer
    credential. This makes old connector URLs fail closed instead of silently
    selecting an author.
    """
    auth_context = getattr(request.state, "auth_context", None) or {}
    bound = str(auth_context.get("agent_principal") or "").strip()
    asserted = str(claimed or "").strip()
    if asserted and asserted != bound:
        raise HTTPException(
            status_code=403,
            detail="principal query does not match the authenticated credential",
        )
    return bound


def _request_auth_context(request: Request) -> dict[str, Any]:
    return getattr(request.state, "auth_context", None) or {}


def _has_auth_scope(context: dict[str, Any], scope: str) -> bool:
    scopes = context.get("scopes") or []
    return isinstance(scopes, list) and ("*" in scopes or scope in scopes)


def _require_grant_owner(request: Request) -> dict[str, Any]:
    context = _request_auth_context(request)
    role = str(context.get("role") or context.get("project_role") or "").lower()
    if context.get("is_operator") is True or role in {"owner", "admin", "operator"} \
            or _has_auth_scope(context, "grants:admin"):
        return context
    raise HTTPException(status_code=403, detail="grant administration requires owner authority")


def _require_agent_principal(request: Request) -> str:
    principal = str(_request_auth_context(request).get("agent_principal") or "").strip()
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", principal) is None:
        raise HTTPException(status_code=403, detail="an agent-bound credential is required")
    return principal


def _has_team_reader_credential(request: Request) -> bool:
    return _credential_bound_team_principal(request) in TEAM_AGENTS


def _contains_team_ledger_selector(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip() == TEAM_LEDGER_APP
    if isinstance(value, dict):
        return any(_contains_team_ledger_selector(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_team_ledger_selector(item) for item in value)
    return False


def _filters_target_team_ledger(value: Any) -> bool:
    if isinstance(value, dict):
        if "app_id" in value and _contains_team_ledger_selector(value.get("app_id")):
            return True
        return any(_filters_target_team_ledger(item) for item in value.values())
    if isinstance(value, list):
        return any(_filters_target_team_ledger(item) for item in value)
    return False


def _require_team_reader_for_filters(request: Request, filters: Any) -> bool:
    authorized = _has_team_reader_credential(request)
    if _filters_target_team_ledger(filters) and not authorized:
        raise HTTPException(status_code=403, detail="team-ledger reads require an agent-bound Bearer credential")
    return authorized


def _without_team_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in items
        if not (
            str(item.get("app_id") or "").strip() == TEAM_LEDGER_APP
            and not item.get("user_id")
        )
    ]


@app.post("/mcp", dependencies=[Depends(auth)])
def mcp_rpc(
    request: Request,
    payload: Any = Body(...),
    profile: str | None = None,
    principal: str | None = None,
    ptoken: str | None = None,
) -> JSONResponse:
    if ptoken:
        raise HTTPException(status_code=400, detail="query-string team tokens are not accepted")
    context: dict[str, str] = {}
    if profile:
        context["tool_profile"] = profile
    bound_principal = _credential_bound_team_principal(request, principal)
    if bound_principal:
        context["team_principal"] = bound_principal
        context["team_principal_auth"] = "credential"
    return _mcp_dispatch(payload, context or None)


@app.get("/mcp/{app_id}/http/{user_id}", dependencies=[Depends(auth)])
def mcp_scope_info(
    app_id: str,
    user_id: str,
    request: Request,
    profile: str | None = None,
    project: str | None = None,
    principal: str | None = None,
    ptoken: str | None = None,
) -> dict[str, Any]:
    # Identity echo for connection doctors: confirms which scope this
    # endpoint pins before any tool call is made (forget-connect probes it).
    info = {"name": "forget-mcp", "user_id": user_id, "client_name": app_id}
    if profile:
        info["tool_profile"] = profile
    if project:
        info["project"] = project
    if ptoken:
        raise HTTPException(status_code=400, detail="query-string team tokens are not accepted")
    bound_principal = _credential_bound_team_principal(request, principal)
    if bound_principal:
        info["team_principal"] = bound_principal
    return info


@app.post("/mcp/{app_id}/http/{user_id}", dependencies=[Depends(auth)])
def mcp_rpc_scoped(
    app_id: str,
    user_id: str,
    request: Request,
    payload: Any = Body(...),
    profile: str | None = None,
    project: str | None = None,
    principal: str | None = None,
    ptoken: str | None = None,
) -> JSONResponse:
    # Scoped MCP endpoint (same path shape as the hosted gateway): every
    # tool call inherits this user/app scope unless the caller names an
    # entity explicitly — an unscoped local /mcp connection otherwise
    # searches the default scope and misses the user's memories entirely
    # (2026-07-13 dogfooding: a fresh client recalled nothing).
    # ?project=<key>는 무필터 호출에 프로젝트 층(훅의 layered_filter와 동일)을
    # 추가로 고정한다 — 공용 서버는 cwd가 없으므로 연결 URL이 프로젝트를 나른다.
    context: dict[str, str] = {"user_id": user_id, "client_name": app_id}
    if profile:
        context["tool_profile"] = profile
    if project:
        context["project_key"] = project
    if ptoken:
        raise HTTPException(status_code=400, detail="query-string team tokens are not accepted")
    bound_principal = _credential_bound_team_principal(request, principal)
    if bound_principal:
        context["team_principal"] = bound_principal
        context["team_principal_auth"] = "credential"
    return _mcp_dispatch(payload, context)


@app.get("/v1/capabilities", dependencies=[Depends(auth)])
def capabilities() -> dict[str, Any]:
    return mem1_capabilities_payload()


# --- REST -------------------------------------------------------------------


@app.get("/v1/memories/", dependencies=[Depends(auth)])
def memories_list(
    request: Request,
    user_id: str | None = None,
    agent_id: str | None = None,
    app_id: str | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    filters = {k: v for k, v in {"user_id": user_id, "agent_id": agent_id, "app_id": app_id, "run_id": run_id}.items() if v}
    authorized = _require_team_reader_for_filters(request, filters)
    # 공개 경계: 내부 표현(_embedding, hash, project_id)은 여기서 끝난다 (#7)
    rows = [m for m in list_memory_dicts() if not filters or all(m.get(k) == v for k, v in filters.items())]
    if not authorized:
        rows = _without_team_rows(rows)
    return [strip_internal(m) for m in rows]


@app.post("/v1/memories/", dependencies=[Depends(auth)])
def memories_create(payload: dict[str, Any]) -> dict[str, Any]:
    # The team ledger has one write entrance. A bearer credential proves who
    # is calling but does not replace team_note's PII, link, lifecycle, and
    # idempotency checks; raw memory writes therefore cannot target its
    # ownerless app pool.
    from .scope_guard import TEAM_LEDGER_APP as _team_app
    if str(payload.get("app_id") or "").strip() == _team_app:
        raise HTTPException(
            status_code=403,
            detail="team ledger writes must use the authenticated team_note tool",
        )
    # B3O 제품 레인 이중 게이트 (승격 계약 §④, 경계 해제 2026-08-29 정훈):
    # b3o.* 스코프 쓰기는 «자동 기억 생성 금지» 불변식을 서버가 공동 집행 —
    # native 사람 승인 UI만이 human_approved를 공급한다. 에코 차단기는
    # add 경로에 이미 상주(두 번째 벽).
    if str(payload.get("app_id") or "").strip().startswith("b3o.") \
            and payload.get("human_approved") is not True:
        raise HTTPException(
            status_code=403,
            detail="b3o.* writes require human_approved=true (native approval gate)",
        )
    if "messages" not in payload:
        text = payload.get("text") or payload.get("memory") or payload.get("data")
        if not text:
            raise HTTPException(status_code=400, detail="messages or text is required")
        payload = {**payload, "messages": [{"role": "user", "content": str(text)}], "infer": False}
    result = add_memories(payload)
    event = get_event(result["event_id"])
    created = event.get("results", [])
    if created:
        return get_memory(created[0]["id"])
    # A near-duplicate write strengthens its original instead of appending
    # (Hebbian merge) — the caller still gets a memory object back: the
    # reinforced one. POSTing a restatement is not an error.
    merged = result.get("merged") or []
    if merged:
        return get_memory(merged[0]["id"])
    return result


@app.post("/v1/memories/search/", dependencies=[Depends(auth)])
def memories_search(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    filters = payload.get("filters") or {field: payload[field] for field in ENTITY_FIELDS if field in payload}
    authorized = _require_team_reader_for_filters(request, filters)
    result = search_memories({**payload, "filters": filters})
    if not authorized:
        result = {**result, "results": _without_team_rows(list(result.get("results") or []))}
    if payload.get("enable_graph"):
        result["relations"] = memory_relations(result.get("results", []))
    return result


# --- 기억 경제: 그랜트 + 검문 서빙 + 접근 영수증 (MEMORY_ECONOMY.md) --------


@app.post("/v1/grants/", dependencies=[Depends(auth)])
def grants_create(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    from . import grants
    _require_grant_owner(request)
    try:
        return grants.create_grant(payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.get("/v1/grants/", dependencies=[Depends(auth)])
def grants_list(request: Request, include_revoked: bool = False) -> list[dict[str, Any]]:
    from . import grants
    _require_grant_owner(request)
    return grants.list_grants(include_revoked=include_revoked)


@app.post("/v1/grants/{grant_id}/revoke", dependencies=[Depends(auth)])
def grants_revoke(grant_id: str, request: Request) -> dict[str, Any]:
    from . import grants
    _require_grant_owner(request)
    try:
        return grants.revoke_grant(grant_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error))


@app.post("/v1/memories/serve/", dependencies=[Depends(auth)])
def memories_serve(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """그랜트 검사 하의 공유 원장 서빙 — 영수증 선기록, 거부도 영수증."""
    from . import grants
    principal = _require_agent_principal(request)
    claimed = str(payload.get("grantee") or "").strip()
    if claimed and claimed != principal:
        raise HTTPException(status_code=403, detail="grantee does not match the authenticated principal")
    payload = {**payload, "grantee": principal}
    try:
        return grants.serve(payload)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.get("/v1/receipts/statement/", dependencies=[Depends(auth)])
def receipts_statement(request: Request, grantee: str | None = None,
                       scope_app: str | None = None, days: int = 30) -> dict[str, Any]:
    """사용 명세서 — 소유자는 전체, 에이전트 자격은 자기 grantee 몫만."""
    from . import grants
    context = _request_auth_context(request)
    principal = str(context.get("agent_principal") or "").strip()
    role = str(context.get("role") or context.get("project_role") or "").lower()
    is_owner = context.get("is_operator") is True or role in {"owner", "admin", "operator"}
    if not is_owner:
        if not principal:
            raise HTTPException(status_code=403, detail="statement requires owner or agent credential")
        grantee = principal   # 자기 명세만 — 조회 권한이 신원에 결합
    return grants.usage_statement(grantee=grantee, scope_app=scope_app, days=days)


@app.get("/v1/receipts/access/", dependencies=[Depends(auth)])
def access_receipts_list(request: Request, grantee: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    from . import grants
    _require_grant_owner(request)
    return grants.list_access_receipts(grantee=grantee, limit=limit)


@app.post("/v1/team/confirm/", dependencies=[Depends(auth)])
def team_confirm(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    """owner 확인 영수증 — owner_sourced(yellow)를 green으로 승격하는 유일한 문.

    소유자 자격 전용(_require_grant_owner 재사용) — 에이전트 자격 403.
    단방향: 취소 없음(잘못 확인했으면 결정 자체를 supersede). 영수증은 공용
    서명기(canonical-v1)라 verify_receipt·공개키로 제3자 검증 가능.
    """
    _require_grant_owner(request)
    from .mcp import TEAM_LEDGER_APP
    from .receipts import sign_receipt
    from .store import current_project_id, list_memory_dicts
    from .utils import new_id, utc_now
    item_id = str(payload.get("item_id") or "").strip()
    if not item_id:
        raise HTTPException(status_code=400, detail="item_id is required")
    row = next((m for m in list_memory_dicts()
                if str(m.get("id")) == item_id and m.get("app_id") == TEAM_LEDGER_APP
                and not m.get("user_id")), None)
    if row is None:
        raise HTTPException(status_code=404, detail="item_id is not a team-ledger item")
    meta = row.get("metadata") or {}
    if not meta.get("owner_sourced") or meta.get("kind") != "decision":
        raise HTTPException(status_code=400,
                            detail="only owner_sourced decisions can be owner-confirmed")
    context = _request_auth_context(request)
    confirmed_by = str(context.get("agent_principal") or context.get("role") or "owner")
    project_id = current_project_id()
    receipt = sign_receipt({
        "kind": "owner_confirmation",
        "receipt_id": new_id("oconfirm"),
        "item_id": item_id,
        "confirmed_by": confirmed_by,
        "at": utc_now(),
    })
    from .db import get_db
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO team_confirmations (item_id, project_id, confirmed_by,"
            " receipt_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (item_id, project_id, confirmed_by,
             json.dumps(receipt, ensure_ascii=False), receipt["at"]),
        )
        if cursor.rowcount == 0:
            prior = conn.execute(
                "SELECT receipt_json FROM team_confirmations WHERE project_id = ? AND item_id = ?",
                (project_id, item_id)).fetchone()
            return {"confirmed": True, "idempotent_replay": True,
                    "receipt": json.loads(prior["receipt_json"])}
    return {"confirmed": True, "receipt": receipt}


@app.get("/v1/receipts/public_key/", dependencies=[Depends(auth)])
def receipts_public_key() -> dict[str, Any]:
    """영수증 검증 공개키(Ed25519) — 제3자가 서버 신뢰 없이 검증할 때 쓴다."""
    from .receipts import receipt_public_key
    return {"algo": "ed25519", "public_key": receipt_public_key(),
            "canonical": "sort_keys JSON minus signature fields (canonical-v1)"}


@app.post("/v1/receipts/verify/", dependencies=[Depends(auth)])
def receipts_verify(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Verify signature plus exact access-receipt request bindings."""
    from .receipts import verify_receipt
    if set(payload) - {"receipt", "expected"}:
        raise HTTPException(status_code=400, detail="unknown receipt verification fields")
    receipt = payload.get("receipt")
    if not isinstance(receipt, dict) or "signature_hmac_sha256" not in receipt:
        raise HTTPException(status_code=400, detail="receipt with signature_hmac_sha256 is required")
    if receipt.get("kind") == "access_receipt":
        from . import grants
        principal = _require_agent_principal(request)
        expected = payload.get("expected")
        if not isinstance(expected, dict) or set(expected) != {"query", "grantee", "scope_app"}:
            raise HTTPException(
                status_code=400,
                detail="access receipt verification requires exact query, grantee and scope_app expectations",
            )
        query = str(expected.get("query") or "")
        grantee = str(expected.get("grantee") or "")
        scope_app = str(expected.get("scope_app") or "")
        if grantee != principal:
            raise HTTPException(status_code=403, detail="expected grantee does not match the authenticated principal")
        if (
            not query or query.strip() != query or len(query.encode("utf-8")) > 8 * 1024
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", grantee)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", scope_app)
        ):
            raise HTTPException(status_code=400, detail="invalid access receipt expectations")
        checks = grants.verify_access_receipt(
            receipt,
            expected_query=query,
            expected_grantee=grantee,
            expected_scope_app=scope_app,
        )
    else:
        if _request_auth_context(request).get("actor_type") == "anonymous":
            raise HTTPException(status_code=403, detail="authenticated receipt verification is required")
        signature_valid = bool(verify_receipt(receipt))
        checks = {
            "valid": signature_valid,
            "signature_valid": signature_valid,
            "persistence_valid": True,
            "binding_valid": True,
        }
    return {"schema_version": "forget-receipt-verification-v1", **checks}


@app.post("/v1/similarity/", dependencies=[Depends(auth)])
def texts_similarity(payload: dict[str, Any]) -> dict[str, Any]:
    """Max cosine of each source text against a set of target texts.

    Exists for semantic usage detection (mechanical-echo v3): the 6-gram verbatim
    check caught 0 of 60 natural usages of real memories — models paraphrase, they
    don't quote 80-char runs (measured 2026-08-23, scripts/eval_semantic_echo.py).
    Hooks send memory probes as sources and the session's assistant sentences as
    targets; the same server embedding stack that indexes memories judges usage,
    so the two never drift apart.
    """
    sources = [str(t) for t in (payload.get("sources") or []) if str(t).strip()][:64]
    targets = [str(t) for t in (payload.get("targets") or []) if str(t).strip()][:400]
    if not sources or not targets:
        return JSONResponse({"error": "sources and targets are required"}, status_code=400)
    from .memory_engine import cosine_similarity
    from .providers import embed_text

    target_vecs = [embed_text(t) for t in targets]
    results = []
    for source in sources:
        vec = embed_text(source)
        sims = [cosine_similarity(vec, tv) for tv in target_vecs]
        best = max(range(len(sims)), key=lambda i: sims[i])
        results.append({"max_similarity": round(float(sims[best]), 4), "target_index": best})
    return {"results": results, "n_sources": len(sources), "n_targets": len(targets)}


@app.post("/v1/context/assemble/", dependencies=[Depends(auth)])
def context_assemble(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Assemble one turn's context capsule.

    Search returns candidates; assembly decides what the model reads — that is the
    product, and it was reachable only over MCP. Every non-MCP adapter (editor
    plugins, agent harnesses) therefore had to reimplement ranking, dedup and
    budgeting for itself, and drift from this one. Same assembler, every transport.
    """
    filters = payload.get("filters") or {field: payload[field] for field in ENTITY_FIELDS if field in payload}
    _require_team_reader_for_filters(request, filters)
    return assemble_context({**payload, "filters": filters})


@app.post("/v2/memories/", dependencies=[Depends(auth)])
def memories_list_filtered(payload: dict[str, Any], request: Request, page: int = 1, page_size: int = 100) -> dict[str, Any]:
    payload = payload or {}
    filters = payload.get("filters")
    if not isinstance(filters, dict) or not filters:
        envelope_keys = {"org_id", "project_id", "source", "page", "page_size", "show_expired"}
        filters = {key: value for key, value in payload.items() if key not in envelope_keys and value not in (None, "")}
    selected_project = str(payload.get("project_id") or getattr(request.state, "project_id", "proj_local"))
    authorized = _require_team_reader_for_filters(request, filters)
    normalized_page = max(int(page or payload.get("page") or 1), 1)
    normalized_page_size = min(max(int(page_size or payload.get("page_size") or 100), 1), 200)
    result = get_memories(
        filters,
        page=normalized_page,
        page_size=normalized_page_size,
        project_id=selected_project,
        show_expired=bool(payload.get("show_expired", False)),
    )
    if not authorized:
        result = {**result, "results": _without_team_rows(list(result.get("results") or []))}
    return result


@app.get("/v1/memories/events/", dependencies=[Depends(auth)])
def memories_events(page: int = 1, page_size: int = 100) -> dict[str, Any]:
    result = list_events(page=page, page_size=page_size)
    rows = [
        event for event in result.get("results") or []
        if not _filters_target_team_ledger(event.get("payload") or {})
    ]
    return {**result, "count": len(rows), "next": None, "results": rows}


@app.post("/v1/memories/stale-candidates/", dependencies=[Depends(auth)])
def memories_stale_candidates(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return stale_candidate_pairs(payload or {})


@app.get("/v1/memories/{memory_id}/", dependencies=[Depends(auth)])
def memories_read(memory_id: str, request: Request) -> dict[str, Any]:
    memory = get_memory(memory_id)
    if not _has_team_reader_credential(request) and not _without_team_rows([memory]):
        raise HTTPException(status_code=403, detail="team-ledger reads require an agent-bound Bearer credential")
    return memory


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
def memories_history(memory_id: str, request: Request) -> list[dict[str, Any]]:
    memory = get_memory(memory_id, include_expired=True)
    if not _has_team_reader_credential(request) and not _without_team_rows([memory]):
        raise HTTPException(status_code=403, detail="team-ledger reads require an agent-bound Bearer credential")
    return list(reversed(memory_history(memory_id)))


@app.delete("/v1/memories/", dependencies=[Depends(auth)])
def memories_delete_all(payload: dict[str, Any] | None = None) -> dict[str, str]:
    payload = payload or {}
    filters = payload.get("filters") or {field: payload[field] for field in ENTITY_FIELDS if field in payload}
    return delete_memories(filters)


@app.post("/v1/feedback/", dependencies=[Depends(auth)])
def submit_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    return submit_memory_feedback(payload)


# --- 자기 하네스 기관 표면 (헌장 개정 3: pi 루프가 HTTP로 소비) ----------------
# 기관(유언장·증류)은 Python 정본에 산다 — TS 확장은 얇은 접착제만.


def _persist_consolidation(distilled: dict[str, Any], *, user_id: str | None,
                           session_ref: str) -> dict[str, Any]:
    """잠들기 전 소화 — 증류물을 상태 계층에 내린다. 실패는 항목별로 삼키고
    계수만 정직하게 반환한다 (응고화 실패가 압축을 죽이면 안 된다)."""
    import hashlib

    from . import worldmodel
    from .store import add_memories
    out = {"facts": 0, "lessons": 0, "intents": 0, "errors": 0}
    uid = user_id or "junghunkim"
    for kind in ("facts", "lessons"):
        for item in distilled.get(kind) or []:
            try:
                add_memories({
                    "messages": [{"role": "assistant", "content": str(item)}],
                    "user_id": uid, "infer": False, "hebbian": False,
                    "metadata": {"source": "consolidation", "session_ref": session_ref,
                                 "consolidation_kind": kind,
                                 "trust": {"kind": "fact" if kind == "facts" else "lesson",
                                           "light": "yellow", "source": "assistant",
                                           "note": "sleep-time consolidation — verify before acting"}},
                })
                out[kind] += 1
            except Exception:
                out["errors"] += 1
    for item in distilled.get("intents") or []:
        try:
            echo_of = worldmodel.recently_released_similar(
                worldmodel.DEFAULT_WORLD_DB, str(item))
            if echo_of:
                # 되새김 가드: 방금 해제된 손의 메아리 — 재등기 금지 (실측
                # 2026-08-25: 해제 13초 뒤 같은 의도 부활). 계수는 정직하게.
                out["skipped_rumination"] = out.get("skipped_rumination", 0) + 1
                continue
            dup_of = worldmodel.active_similar_hand(
                worldmodel.DEFAULT_WORLD_DB, str(item))
            if dup_of:
                # 복제 가드: 산 유언의 문면 변형 재등기 금지 (H-1 실측:
                # 같은 의도 2건). 기존 유언이 정본 — 갱신도 하지 않는다.
                out["skipped_duplicate"] = out.get("skipped_duplicate", 0) + 1
                continue
            hand_id = "cons-" + hashlib.sha256(str(item).encode()).hexdigest()[:10]
            worldmodel.arm_hand(
                worldmodel.DEFAULT_WORLD_DB, hand_id, "intent", str(item),
                "응고화가 채집한 미완 의도 — 다음 기상이 재심사", session_ref)
            out["intents"] += 1
        except Exception:
            out["errors"] += 1
    return out


@app.get("/v1/worldmodel/hands/", dependencies=[Depends(auth)])
def worldmodel_hands() -> dict[str, Any]:
    from . import worldmodel
    return {"hands": worldmodel.standing_hands(worldmodel.DEFAULT_WORLD_DB)}


@app.post("/v1/worldmodel/hands/", dependencies=[Depends(auth)])
def worldmodel_arm_hand(payload: dict[str, Any]) -> dict[str, Any]:
    from . import worldmodel
    try:
        return worldmodel.arm_hand(
            worldmodel.DEFAULT_WORLD_DB, str(payload.get("id") or ""),
            str(payload.get("kind") or ""), str(payload.get("what") or ""),
            str(payload.get("why") or ""), str(payload.get("source_ref") or ""),
            expires_at=payload.get("expires_at"))
    except (ValueError, KeyError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/v1/worldmodel/hands/release/", dependencies=[Depends(auth)])
def worldmodel_release_hand(payload: dict[str, Any]) -> dict[str, Any]:
    from . import worldmodel
    try:
        return worldmodel.release_hand(
            worldmodel.DEFAULT_WORLD_DB, str(payload.get("id") or ""),
            str(payload.get("reason") or ""))
    except (ValueError, KeyError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/v1/harness/consolidate/", dependencies=[Depends(auth)])
def harness_consolidate(payload: dict[str, Any]) -> dict[str, Any]:
    """응고화 v0 — pi의 session_before_compact가 이 요약으로 압축을 대체한다.

    turns[{role, content}] → 증류(핸들=코드·내용=로컬 LLM, fail-open) →
    캡슐 텍스트(요약 대체용) + 구조 레코드. persist=true면 잠들기 전 소화까지:
    사실·교훈→원장(add, 출처 태그 consolidation — 게이트·중복 제거는 원장
    몫), 의도→유언장(arm, kind=intent). 기본 false — 순수 변환 유지.
    """
    from .selfharness import distill_turns
    turns = payload.get("turns") or []
    if not isinstance(turns, list) or not turns:
        return JSONResponse({"error": "turns[] 필요"}, status_code=400)
    distilled = distill_turns(turns[:400])
    if payload.get("persist"):
        distilled["persisted"] = _persist_consolidation(
            distilled, user_id=str(payload.get("user_id") or "") or None,
            session_ref=str(payload.get("session_ref") or "pi-session"))
    lines = ["## State capsule (consolidated by forget — not a lossy summary)"]
    for key, title in [("facts", "Facts (with receipts)"), ("lessons", "Lessons"),
                       ("intents", "Standing intents (inherit or release)")]:
        items = distilled.get(key) or []
        if items:
            lines.append(f"### {title}")
            lines.extend(f"- {item}" for item in items)
    handles = distilled.get("handles") or []
    if handles:
        lines.append("### Handles (exact — do not paraphrase)")
        lines.extend(f"- {h['kind']}: {h['value']}" for h in handles)
    return {"summary": "\n".join(lines), "distilled": distilled}


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
def memories_list_v3(payload: dict[str, Any], request: Request, page: int = 1, page_size: int = 100) -> Any:
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
    authorized = _require_team_reader_for_filters(request, filters)
    result = get_memories(filters, page=page, page_size=page_size, show_expired=bool(payload.get("show_expired", False)))
    if not authorized:
        result = {**result, "results": _without_team_rows(list(result.get("results") or []))}
    return {**result, "results": [_public_memory(item) for item in result.get("results", [])]}


@app.get("/v3/recall/activity", dependencies=[Depends(auth)])
def recall_activity_view() -> dict[str, Any]:
    from .store import recall_activity

    return recall_activity()


@app.post("/v3/memories/search/", dependencies=[Depends(auth)])
def memories_search_v3(payload: dict[str, Any], request: Request) -> Any:
    top_level_entities = [field for field in ENTITY_FIELDS if field in payload]
    if top_level_entities:
        return JSONResponse({"error": "Entity IDs must be passed inside filters"}, status_code=400)
    if not payload.get("query"):
        return JSONResponse({"error": "query is required"}, status_code=400)
    authorized = _require_team_reader_for_filters(request, payload.get("filters") or {})
    result = search_memories(payload)
    rows = list(result.get("results") or [])
    if not authorized:
        rows = _without_team_rows(rows)
    response: dict[str, Any] = {"results": [_public_search_result(item) for item in rows]}
    if result.get("recall_layer"):
        response["recall_layer"] = result["recall_layer"]
    return response
