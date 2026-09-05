"""Provider-neutral, zero-price Memory Agent marketplace prototype.

The market is deliberately *not* a second search entrance into a person's
live vault.  A publisher explicitly reviews ownerless source memories while a
product is in draft.  The reviewed, PII-gated snapshot is copied into a
separate corpus; consultations can read only that corpus.

Security invariants:

* owned/self memories (``user_id`` present) cannot become product items;
* publication, quote approval, consultation and revocation are explicit;
* buyer identity comes from an agent-bound credential, never from arguments;
* grants are exact-principal, exact-vault and exact-client;
* every consultation, including denials, is signed and persisted before any
  result is returned; and
* this prototype always reports ``charged_units=0``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import get_db, json_loads
from .grants import PII_DETECTORS, REQUEST_ID_RE, _apply_gate, _query_commitment
from .receipts import sign_receipt, verify_receipt
from .utils import new_id, parse_datetime, utc_now


SCHEMA_VERSION = "forget-memory-agent-market-v1"
TERMS_VERSION = "memory-agent-terms-v1"
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}")
MAX_PURPOSE_CHARS = 240
MAX_CURATED_CHARS = 2000
MAX_RESULT_CHARS = 600
MAX_RESULTS = 3
QUOTE_TTL_MINUTES = 15
GRANT_TTL_HOURS = 24


def _bounded_identifier(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if IDENTIFIER_RE.fullmatch(text) is None:
        raise ValueError(f"{name} must be a bounded identifier")
    return text


def _bounded_text(value: Any, name: str, *, limit: int, required: bool = True) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{name} is required")
    if len(text) > limit:
        raise ValueError(f"{name} exceeds {limit} characters")
    return text


def _future_iso(*, minutes: int = 0, hours: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes, hours=hours)).isoformat()


def _is_expired(value: Any) -> bool:
    parsed = parse_datetime(value)
    return parsed is None or parsed <= datetime.now(timezone.utc)


def _product_public(row: Any) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "product_id": row["id"],
        "name": row["name"],
        "summary": row["summary"],
        "capability": row["capability"],
        "publisher_principal": row["publisher_principal"],
        "answer_mode": row["answer_mode"],
        "max_items": int(row["max_items"]),
        "price_units": 0,
        "terms_version": row["terms_version"],
        "status": row["status"],
        "published_at": row["published_at"],
    }


def _product_admin(row: Any) -> dict[str, Any]:
    product = _product_public(row)
    product.update({
        "project_id": row["project_id"],
        "publisher_vault_id": row["publisher_vault_id"],
        "source_app": row["source_app"],
        "created_at": row["created_at"],
        "retired_at": row["retired_at"],
        "publish_receipt": json_loads(row["publish_receipt_json"], None)
        if row["publish_receipt_json"] else None,
    })
    return product


def _get_product(product_id: str, project_id: str) -> Any:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM memory_agent_products WHERE project_id = ? AND id = ?",
            (project_id, product_id),
        ).fetchone()
    if row is None:
        raise KeyError(f"product not found: {product_id}")
    return row


def create_product(
    payload: dict[str, Any],
    *,
    publisher_principal: str,
    publisher_vault_id: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Create a draft.  Caller identity must already be credential-bound."""
    from .store import current_project_id

    project_id = project_id or current_project_id()
    publisher_principal = _bounded_identifier(publisher_principal, "publisher_principal")
    publisher_vault_id = _bounded_identifier(publisher_vault_id, "publisher_vault_id")
    source_app = _bounded_identifier(payload.get("source_app"), "source_app")
    team_app = (os.getenv("MEM1_TEAM_LEDGER_APP") or "forget-dev").strip()
    if source_app == team_app:
        raise ValueError("the team consensus ledger cannot be published as a product")
    answer_mode = str(payload.get("answer_mode") or "pointer").strip()
    if answer_mode not in {"pointer", "passage"}:
        raise ValueError("answer_mode must be 'pointer' or 'passage'")
    max_items = int(payload.get("max_items") or MAX_RESULTS)
    if not 1 <= max_items <= MAX_RESULTS:
        raise ValueError(f"max_items must be between 1 and {MAX_RESULTS}")
    now = utc_now()
    row = {
        "id": new_id("mproduct"),
        "project_id": project_id,
        "publisher_principal": publisher_principal,
        "publisher_vault_id": publisher_vault_id,
        "name": _bounded_text(payload.get("name"), "name", limit=80),
        "summary": _bounded_text(payload.get("summary"), "summary", limit=300),
        "capability": _bounded_identifier(payload.get("capability"), "capability"),
        "source_app": source_app,
        "answer_mode": answer_mode,
        "max_items": max_items,
        "price_units": 0,
        "terms_version": TERMS_VERSION,
        "status": "draft",
        "publish_receipt_json": None,
        "created_at": now,
        "published_at": None,
        "retired_at": None,
    }
    with get_db() as conn:
        conn.execute(
            "INSERT INTO memory_agent_products (id, project_id, publisher_principal,"
            " publisher_vault_id, name, summary, capability, source_app, answer_mode,"
            " max_items, price_units, terms_version, status, publish_receipt_json,"
            " created_at, published_at, retired_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(row.values()),
        )
    return _product_admin(row)


def review_product_item(
    product_id: str,
    payload: dict[str, Any],
    *,
    publisher_principal: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Copy one explicitly reviewed, ownerless source row into the product."""
    from .store import current_project_id

    project_id = project_id or current_project_id()
    publisher_principal = _bounded_identifier(publisher_principal, "publisher_principal")
    if payload.get("reviewed") is not True:
        raise ValueError("reviewed=true is required for explicit publication review")
    memory_id = _bounded_identifier(payload.get("memory_id"), "memory_id")
    product = _get_product(product_id, project_id)
    if product["publisher_principal"] != publisher_principal:
        raise PermissionError("publisher credential does not own this product")
    if product["status"] != "draft":
        raise ValueError("only draft products can accept reviewed items")
    with get_db() as conn:
        source = conn.execute(
            "SELECT id, memory, user_id, app_id, hash, metadata FROM memories"
            " WHERE project_id = ? AND id = ? AND deleted = 0",
            (project_id, memory_id),
        ).fetchone()
    if source is None:
        raise KeyError(f"source memory not found: {memory_id}")
    if source["user_id"] not in (None, ""):
        raise ValueError("owned self memories are non-sale and cannot be reviewed into a product")
    if str(source["app_id"] or "") != product["source_app"]:
        raise ValueError("source memory is outside the product source_app")
    metadata = json_loads(source["metadata"], {})
    if metadata.get("owner_sourced") is True:
        raise ValueError("owner-sourced consensus cannot be sold as a Memory Agent item")
    curated, redactions = _apply_gate(str(source["memory"] or ""), list(PII_DETECTORS))
    curated = curated.strip()[:MAX_CURATED_CHARS]
    if not curated:
        raise ValueError("source memory is empty after the publication gate")
    now = utc_now()
    item = {
        "id": new_id("mitem"),
        "project_id": project_id,
        "product_id": product_id,
        "source_memory_id": memory_id,
        "source_hash": str(source["hash"] or hashlib.sha256(str(source["memory"]).encode()).hexdigest()),
        "curated_text": curated,
        "reviewed_by": publisher_principal,
        "reviewed_at": now,
        "created_at": now,
    }
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO memory_agent_items (id, project_id, product_id, source_memory_id,"
                " source_hash, curated_text, reviewed_by, reviewed_at, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tuple(item.values()),
            )
    except Exception as error:
        if "UNIQUE constraint failed" in str(error):
            raise ValueError("source memory was already reviewed into this product") from error
        raise
    return {
        "schema_version": SCHEMA_VERSION,
        "item_id": item["id"],
        "product_id": product_id,
        "source_memory_id": memory_id,
        "source_hash": item["source_hash"],
        "reviewed_by": publisher_principal,
        "reviewed_at": now,
        "redactions": redactions,
    }


def publish_product(
    product_id: str,
    *,
    publisher_principal: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    from .store import current_project_id

    project_id = project_id or current_project_id()
    publisher_principal = _bounded_identifier(publisher_principal, "publisher_principal")
    product = _get_product(product_id, project_id)
    if product["publisher_principal"] != publisher_principal:
        raise PermissionError("publisher credential does not own this product")
    if product["status"] == "published":
        return _product_admin(product)
    if product["status"] != "draft":
        raise ValueError("only draft products can be published")
    with get_db() as conn:
        items = conn.execute(
            "SELECT id, source_memory_id, source_hash, curated_text, reviewed_by, reviewed_at"
            " FROM memory_agent_items WHERE project_id = ? AND product_id = ?"
            " ORDER BY created_at, id",
            (project_id, product_id),
        ).fetchall()
    if not items:
        raise ValueError("at least one explicitly reviewed item is required")
    item_commitments = [
        {
            "item_id": row["id"],
            "source_memory_id": row["source_memory_id"],
            "source_hash": row["source_hash"],
            "curated_sha256": hashlib.sha256(row["curated_text"].encode()).hexdigest(),
            "reviewed_by": row["reviewed_by"],
            "reviewed_at": row["reviewed_at"],
        }
        for row in items
    ]
    now = utc_now()
    receipt = sign_receipt({
        "kind": "memory_agent_publish_receipt",
        "receipt_id": new_id("mpublish"),
        "product_id": product_id,
        "publisher_principal": publisher_principal,
        "publisher_vault_id": product["publisher_vault_id"],
        "source_app": product["source_app"],
        "terms_version": product["terms_version"],
        "price_units": 0,
        "items": item_commitments,
        "at": now,
    })
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE memory_agent_products SET status = 'published', published_at = ?,"
            " publish_receipt_json = ? WHERE project_id = ? AND id = ? AND status = 'draft'",
            (now, json.dumps(receipt, ensure_ascii=False), project_id, product_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("product publication lost its draft-state race")
    return _product_admin(_get_product(product_id, project_id))


def catalog_search(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    from .store import current_project_id

    project_id = project_id or current_project_id()
    query = _bounded_text(payload.get("query"), "query", limit=200, required=False).lower()
    capability = str(payload.get("capability") or "").strip()
    if capability:
        capability = _bounded_identifier(capability, "capability")
    limit = max(1, min(int(payload.get("limit") or 20), 50))
    sql = "SELECT * FROM memory_agent_products WHERE project_id = ? AND status = 'published'"
    params: list[Any] = [project_id]
    if capability:
        sql += " AND capability = ?"
        params.append(capability)
    if query:
        sql += " AND (lower(name) LIKE ? OR lower(summary) LIKE ? OR lower(capability) LIKE ?)"
        needle = f"%{query}%"
        params.extend([needle, needle, needle])
    sql += " ORDER BY published_at DESC, id LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"schema_version": SCHEMA_VERSION, "products": [_product_public(row) for row in rows]}


def product_quote(
    payload: dict[str, Any],
    *,
    buyer_principal: str,
    buyer_vault_id: str,
    client_id: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    from .store import current_project_id

    project_id = project_id or current_project_id()
    buyer_principal = _bounded_identifier(buyer_principal, "buyer_principal")
    buyer_vault_id = _bounded_identifier(buyer_vault_id, "buyer_vault_id")
    client_id = _bounded_identifier(client_id, "client_id")
    product_id = _bounded_identifier(payload.get("product_id"), "product_id")
    purpose = _bounded_text(payload.get("purpose"), "purpose", limit=MAX_PURPOSE_CHARS)
    quota = int(payload.get("quota") or 10)
    if not 1 <= quota <= 100:
        raise ValueError("quota must be between 1 and 100")
    product = _get_product(product_id, project_id)
    if product["status"] != "published":
        raise ValueError("product is not available")
    now = utc_now()
    expires_at = _future_iso(minutes=QUOTE_TTL_MINUTES)
    quote = sign_receipt({
        "kind": "memory_agent_quote",
        "quote_id": new_id("mquote"),
        "product_id": product_id,
        "product_name": product["name"],
        "publisher_principal": product["publisher_principal"],
        "buyer_principal": buyer_principal,
        "buyer_vault_id": buyer_vault_id,
        "client_id": client_id,
        "purpose": purpose,
        "answer_mode": product["answer_mode"],
        "max_items": int(product["max_items"]),
        "deny_pii": list(PII_DETECTORS),
        "quota": quota,
        "price_units": 0,
        "terms_version": product["terms_version"],
        "at": now,
        "expires_at": expires_at,
    })
    with get_db() as conn:
        conn.execute(
            "INSERT INTO memory_agent_quotes (id, project_id, product_id, buyer_principal,"
            " buyer_vault_id, client_id, purpose, quote_json, created_at, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (quote["quote_id"], project_id, product_id, buyer_principal, buyer_vault_id,
             client_id, purpose, json.dumps(quote, ensure_ascii=False), now, expires_at),
        )
    return {"schema_version": SCHEMA_VERSION, "quote": quote,
            "approval_required": True, "charged_units": 0}


def grant_create(
    payload: dict[str, Any],
    *,
    buyer_principal: str,
    buyer_vault_id: str,
    client_id: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    from .store import current_project_id

    project_id = project_id or current_project_id()
    buyer_principal = _bounded_identifier(buyer_principal, "buyer_principal")
    buyer_vault_id = _bounded_identifier(buyer_vault_id, "buyer_vault_id")
    client_id = _bounded_identifier(client_id, "client_id")
    quote_id = _bounded_identifier(payload.get("quote_id"), "quote_id")
    if payload.get("approve") is not True:
        raise ValueError("approve=true is required to create a grant")
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM memory_agent_quotes WHERE project_id = ? AND id = ?",
            (project_id, quote_id),
        ).fetchone()
        prior = conn.execute(
            "SELECT * FROM memory_agent_grants WHERE project_id = ? AND quote_id = ?",
            (project_id, quote_id),
        ).fetchone()
    if prior is not None:
        if (prior["buyer_principal"], prior["buyer_vault_id"], prior["client_id"]) != (
            buyer_principal, buyer_vault_id, client_id
        ):
            raise PermissionError("quote was already approved by a different credential binding")
        return _grant_public(prior, idempotent_replay=True)
    if row is None:
        raise KeyError(f"quote not found: {quote_id}")
    quote = json.loads(row["quote_json"])
    if not verify_receipt(quote):
        raise ValueError("quote signature is invalid")
    if _is_expired(row["expires_at"]):
        raise ValueError("quote expired")
    if (row["buyer_principal"], row["buyer_vault_id"], row["client_id"]) != (
        buyer_principal, buyer_vault_id, client_id
    ):
        raise PermissionError("quote does not match the authenticated buyer, vault and client")
    product = _get_product(row["product_id"], project_id)
    if product["status"] != "published":
        raise ValueError("product is no longer available")
    now = utc_now()
    grant = {
        "id": new_id("mgrant"),
        "project_id": project_id,
        "quote_id": quote_id,
        "product_id": row["product_id"],
        "buyer_principal": buyer_principal,
        "buyer_vault_id": buyer_vault_id,
        "client_id": client_id,
        "purpose": row["purpose"],
        "quota": int(quote["quota"]),
        "used": 0,
        "created_at": now,
        "expires_at": _future_iso(hours=GRANT_TTL_HOURS),
        "revoked_at": None,
    }
    with get_db() as conn:
        conn.execute(
            "INSERT INTO memory_agent_grants (id, project_id, quote_id, product_id,"
            " buyer_principal, buyer_vault_id, client_id, purpose, quota, used,"
            " created_at, expires_at, revoked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(grant.values()),
        )
    return _grant_public(grant)


def _grant_public(row: Any, *, idempotent_replay: bool = False) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "grant_id": row["id"],
        "quote_id": row["quote_id"],
        "product_id": row["product_id"],
        "buyer_principal": row["buyer_principal"],
        "buyer_vault_id": row["buyer_vault_id"],
        "client_id": row["client_id"],
        "purpose": row["purpose"],
        "quota": int(row["quota"]),
        "used": int(row["used"]),
        "expires_at": row["expires_at"],
        "revoked_at": row["revoked_at"],
        "idempotent_replay": idempotent_replay,
    }


def _replay_receipt(request_id: str, buyer_principal: str, project_id: str) -> dict[str, Any] | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT receipt_json FROM memory_agent_receipts WHERE project_id = ?"
            " AND buyer_principal = ? AND request_id = ?",
            (project_id, buyer_principal, request_id),
        ).fetchone()
    return json.loads(row["receipt_json"]) if row else None


def _admit(
    grant_id: str,
    *,
    buyer_principal: str,
    buyer_vault_id: str,
    client_id: str,
    project_id: str,
) -> tuple[Any | None, Any | None, str]:
    with get_db() as conn:
        grant = conn.execute(
            "SELECT * FROM memory_agent_grants WHERE project_id = ? AND id = ?",
            (project_id, grant_id),
        ).fetchone()
    if grant is None:
        return None, None, "grant-not-found"
    product = _get_product(grant["product_id"], project_id)
    if grant["buyer_principal"] != buyer_principal:
        return grant, product, "principal-mismatch"
    if grant["buyer_vault_id"] != buyer_vault_id:
        return grant, product, "vault-mismatch"
    if grant["client_id"] != client_id:
        return grant, product, "client-mismatch"
    if grant["revoked_at"]:
        return grant, product, "grant-revoked"
    if _is_expired(grant["expires_at"]):
        return grant, product, "grant-expired"
    if product["status"] != "published":
        return grant, product, "product-unavailable"
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE memory_agent_grants SET used = used + 1 WHERE project_id = ? AND id = ?"
            " AND buyer_principal = ? AND buyer_vault_id = ? AND client_id = ?"
            " AND revoked_at IS NULL AND used < quota",
            (project_id, grant_id, buyer_principal, buyer_vault_id, client_id),
        )
        if cursor.rowcount != 1:
            return grant, product, "quota-exhausted"
    return grant, product, "granted"


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9가-힣]{2,}", text)}


def _rank_items(product_id: str, query: str, project_id: str) -> list[tuple[Any, float]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM memory_agent_items WHERE project_id = ? AND product_id = ?"
            " ORDER BY reviewed_at DESC, id",
            (project_id, product_id),
        ).fetchall()
    query_tokens = _tokens(query)
    ranked: list[tuple[Any, float]] = []
    for row in rows:
        item_tokens = _tokens(row["curated_text"])
        overlap = len(query_tokens & item_tokens)
        score = overlap / max(1, len(query_tokens))
        ranked.append((row, round(score, 4)))
    return sorted(ranked, key=lambda pair: (pair[1], pair[0]["reviewed_at"]), reverse=True)


def _write_consult_receipt(receipt: dict[str, Any], project_id: str) -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO memory_agent_receipts (id, project_id, grant_id, product_id,"
            " buyer_principal, buyer_vault_id, client_id, allowed, reason, query_commitment,"
            " request_id, items_served, redactions, charged_units, receipt_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (receipt["receipt_id"], project_id, receipt.get("grant_id"), receipt.get("product_id"),
             receipt["buyer_principal"], receipt["buyer_vault_id"], receipt["client_id"],
             int(receipt["allowed"]), receipt["reason"], receipt["query_commitment"],
             receipt.get("request_id"), receipt["items_served"], receipt["redactions"],
             receipt["charged_units"], json.dumps(receipt, ensure_ascii=False), receipt["at"]),
        )


def agent_consult(
    payload: dict[str, Any],
    *,
    buyer_principal: str,
    buyer_vault_id: str,
    client_id: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    from .store import current_project_id

    project_id = project_id or current_project_id()
    buyer_principal = _bounded_identifier(buyer_principal, "buyer_principal")
    buyer_vault_id = _bounded_identifier(buyer_vault_id, "buyer_vault_id")
    client_id = _bounded_identifier(client_id, "client_id")
    grant_id = _bounded_identifier(payload.get("grant_id"), "grant_id")
    query = _bounded_text(payload.get("query"), "query", limit=8192)
    request_id = str(payload.get("request_id") or "").strip() or None
    if request_id and REQUEST_ID_RE.fullmatch(request_id) is None:
        raise ValueError("request_id must be a 1-128 character identifier")
    if request_id:
        prior = _replay_receipt(request_id, buyer_principal, project_id)
        if prior is not None:
            exact_replay = (
                prior.get("grant_id") == grant_id
                and prior.get("buyer_vault_id") == buyer_vault_id
                and prior.get("client_id") == client_id
                and hmac.compare_digest(
                    str(prior.get("query_commitment") or ""),
                    _query_commitment(query),
                )
            )
            if not exact_replay:
                raise ValueError(
                    "request_id is already bound to a different grant, query, vault, or client"
                )
            return {"schema_version": SCHEMA_VERSION, "allowed": bool(prior["allowed"]),
                    "reason": "idempotent-replay", "results": [], "receipt": prior}

    grant, product, reason = _admit(
        grant_id,
        buyer_principal=buyer_principal,
        buyer_vault_id=buyer_vault_id,
        client_id=client_id,
        project_id=project_id,
    )
    results: list[dict[str, Any]] = []
    redactions = 0
    item_refs: list[str] = []
    if reason == "granted" and product is not None:
        requested = int(payload.get("top_k") or product["max_items"])
        top_k = max(1, min(requested, int(product["max_items"]), MAX_RESULTS))
        for row, score in _rank_items(product["id"], query, project_id)[:top_k]:
            item_refs.append(row["id"])
            if product["answer_mode"] == "pointer":
                results.append({"ref": row["id"], "score": score})
                continue
            gated, count = _apply_gate(str(row["curated_text"] or "")[:MAX_RESULT_CHARS], list(PII_DETECTORS))
            redactions += count
            results.append({"ref": row["id"], "text": gated, "score": score})

    receipt = sign_receipt({
        "kind": "memory_agent_consult_receipt",
        "receipt_id": new_id("mreceipt"),
        "grant_id": grant["id"] if grant is not None else grant_id,
        "product_id": product["id"] if product is not None else None,
        "publisher_principal": product["publisher_principal"] if product is not None else None,
        "buyer_principal": buyer_principal,
        "buyer_vault_id": buyer_vault_id,
        "client_id": client_id,
        "purpose": grant["purpose"] if grant is not None else None,
        "allowed": reason == "granted",
        "reason": reason,
        "query_commitment": _query_commitment(query),
        "request_id": request_id,
        "answer_mode": product["answer_mode"] if product is not None else None,
        "item_refs": item_refs,
        "items_served": len(results),
        "redactions": redactions,
        "charged_units": 0,
        "at": utc_now(),
    })
    # Fail closed: no persisted receipt means no result leaves this function.
    _write_consult_receipt(receipt, project_id)
    return {"schema_version": SCHEMA_VERSION, "allowed": reason == "granted",
            "reason": reason, "results": results, "receipt": receipt}


def receipt_verify(
    receipt: dict[str, Any],
    *,
    expected_query: str,
    expected_product_id: str,
    buyer_principal: str,
    buyer_vault_id: str,
    client_id: str,
    project_id: str | None = None,
) -> dict[str, bool]:
    from .store import current_project_id

    project_id = project_id or current_project_id()
    signature_valid = bool(verify_receipt(receipt))
    with get_db() as conn:
        row = conn.execute(
            "SELECT receipt_json FROM memory_agent_receipts WHERE project_id = ? AND id = ?",
            (project_id, str(receipt.get("receipt_id") or "")),
        ).fetchone()
    persisted = json.loads(row["receipt_json"]) if row else None
    persistence_valid = persisted == receipt
    binding_valid = (
        receipt.get("kind") == "memory_agent_consult_receipt"
        and hmac.compare_digest(str(receipt.get("query_commitment") or ""), _query_commitment(expected_query))
        and receipt.get("product_id") == expected_product_id
        and receipt.get("buyer_principal") == buyer_principal
        and receipt.get("buyer_vault_id") == buyer_vault_id
        and receipt.get("client_id") == client_id
        and int(receipt.get("charged_units") or 0) == 0
    )
    return {
        "valid": signature_valid and persistence_valid and binding_valid,
        "signature_valid": signature_valid,
        "persistence_valid": persistence_valid,
        "binding_valid": binding_valid,
    }


def grant_revoke(
    grant_id: str,
    *,
    buyer_principal: str,
    buyer_vault_id: str,
    client_id: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    from .store import current_project_id

    project_id = project_id or current_project_id()
    grant_id = _bounded_identifier(grant_id, "grant_id")
    buyer_principal = _bounded_identifier(buyer_principal, "buyer_principal")
    buyer_vault_id = _bounded_identifier(buyer_vault_id, "buyer_vault_id")
    client_id = _bounded_identifier(client_id, "client_id")
    now = utc_now()
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE memory_agent_grants SET revoked_at = ? WHERE project_id = ? AND id = ?"
            " AND buyer_principal = ? AND buyer_vault_id = ? AND client_id = ?"
            " AND revoked_at IS NULL",
            (now, project_id, grant_id, buyer_principal, buyer_vault_id, client_id),
        )
        if cursor.rowcount != 1:
            raise KeyError("grant not found, binding mismatch, or already revoked")
    return {"schema_version": SCHEMA_VERSION, "grant_id": grant_id,
            "revoked": True, "revoked_at": now}
