"""Zero-price Memory Agent market contract tests."""
from __future__ import annotations

import os

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-memory-agent-market.sqlite3")

import pytest  # noqa: E402

from forget import market, receipts  # noqa: E402
from forget.db import init_db  # noqa: E402
from forget.store import add_memories, list_memory_dicts  # noqa: E402


SOURCE_APP = "shareable-guides"
PUBLISHER = "publisher.agent"
PUBLISHER_VAULT = "vault.publisher"
BUYER_VAULT = "vault.person-1"


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "market.sqlite3"))
    monkeypatch.setattr(receipts, "RECEIPT_KEY_PATH", tmp_path / "receipt.key")
    monkeypatch.setattr(receipts, "ED25519_KEY_PATH", tmp_path / "ed25519.key")
    monkeypatch.setattr(receipts, "ED25519_PUB_PATH", tmp_path / "ed25519.pub")
    init_db()
    add_memories({
        "messages": [{"role": "user", "content":
                      "A design critique should begin with the user's primary commitment."
                      " Never add a panel without a reason. Contact 010-4821-7733."}],
        "app_id": SOURCE_APP,
        "agent_id": PUBLISHER,
        "infer": False,
        "metadata": {"market_publishable": True},
    })
    add_memories({
        "messages": [{"role": "user", "content":
                      "I personally dislike crowded dashboards and this is private self memory."}],
        "app_id": SOURCE_APP,
        "agent_id": PUBLISHER,
        "user_id": PUBLISHER_VAULT,
        "infer": False,
    })


def _memory_id(*, owned: bool) -> str:
    return next(
        row["id"] for row in list_memory_dicts()
        if bool(row.get("user_id")) is owned
    )


def _draft(**overrides):
    payload = {
        "name": "Calm Product Critic",
        "summary": "Reviews product decisions with a commitment-first lens.",
        "capability": "product-critique",
        "source_app": SOURCE_APP,
        "answer_mode": "passage",
        "max_items": 2,
    }
    payload.update(overrides)
    return market.create_product(
        payload,
        publisher_principal=PUBLISHER,
        publisher_vault_id=PUBLISHER_VAULT,
    )


def _published():
    product = _draft()
    item = market.review_product_item(
        product["product_id"],
        {"memory_id": _memory_id(owned=False), "reviewed": True},
        publisher_principal=PUBLISHER,
    )
    published = market.publish_product(product["product_id"], publisher_principal=PUBLISHER)
    return published, item


def _grant(product_id: str, *, principal: str = "codex.agent", client: str = "codex", quota: int = 3):
    quote = market.product_quote(
        {"product_id": product_id, "purpose": "Review the current product UX", "quota": quota},
        buyer_principal=principal,
        buyer_vault_id=BUYER_VAULT,
        client_id=client,
    )["quote"]
    grant = market.grant_create(
        {"quote_id": quote["quote_id"], "approve": True},
        buyer_principal=principal,
        buyer_vault_id=BUYER_VAULT,
        client_id=client,
    )
    return quote, grant


def test_self_memory_is_structurally_non_sale():
    product = _draft()
    with pytest.raises(ValueError, match="self memories are non-sale"):
        market.review_product_item(
            product["product_id"],
            {"memory_id": _memory_id(owned=True), "reviewed": True},
            publisher_principal=PUBLISHER,
        )


def test_review_and_publish_are_both_explicit():
    product = _draft()
    with pytest.raises(ValueError, match="reviewed=true"):
        market.review_product_item(
            product["product_id"], {"memory_id": _memory_id(owned=False)},
            publisher_principal=PUBLISHER,
        )
    with pytest.raises(ValueError, match="reviewed item"):
        market.publish_product(product["product_id"], publisher_principal=PUBLISHER)


def test_publisher_provenance_and_publication_gate_are_signed():
    product, item = _published()
    assert product["publisher_principal"] == PUBLISHER
    assert product["status"] == "published"
    assert item["reviewed_by"] == PUBLISHER
    assert item["redactions"] == 1
    assert receipts.verify_receipt(product["publish_receipt"]) is True
    commitment = product["publish_receipt"]["items"][0]
    assert commitment["source_memory_id"] == item["source_memory_id"]
    assert "curated_sha256" in commitment


def test_catalog_exposes_only_published_minimal_metadata():
    draft = _draft(name="Hidden draft")
    product, _ = _published()
    found = market.catalog_search({"query": "commitment", "capability": "product-critique"})
    assert [row["product_id"] for row in found["products"]] == [product["product_id"]]
    assert draft["product_id"] not in {row["product_id"] for row in found["products"]}
    assert "source_app" not in found["products"][0]
    assert "publisher_vault_id" not in found["products"][0]
    assert found["products"][0]["price_units"] == 0


def test_quote_requires_visible_approval_and_exact_identity_binding():
    product, _ = _published()
    quote = market.product_quote(
        {"product_id": product["product_id"], "purpose": "UX review"},
        buyer_principal="codex.agent", buyer_vault_id=BUYER_VAULT, client_id="codex",
    )["quote"]
    assert quote["price_units"] == 0
    with pytest.raises(ValueError, match="approve=true"):
        market.grant_create(
            {"quote_id": quote["quote_id"]},
            buyer_principal="codex.agent", buyer_vault_id=BUYER_VAULT, client_id="codex",
        )
    with pytest.raises(PermissionError, match="authenticated buyer"):
        market.grant_create(
            {"quote_id": quote["quote_id"], "approve": True},
            buyer_principal="claude.agent", buyer_vault_id=BUYER_VAULT, client_id="claude-code",
        )


def test_consult_is_minimal_pii_gated_zero_price_and_receipted():
    product, _ = _published()
    _, grant = _grant(product["product_id"])
    out = market.agent_consult(
        {"grant_id": grant["grant_id"], "query": "primary commitment design panel", "request_id": "consult-1"},
        buyer_principal="codex.agent", buyer_vault_id=BUYER_VAULT, client_id="codex",
    )
    assert out["allowed"] is True
    assert 0 < len(out["results"]) <= 2
    assert set(out["results"][0]) == {"ref", "text", "score"}
    assert "010-4821-7733" not in out["results"][0]["text"]
    assert "[redacted-phone]" in out["results"][0]["text"]
    assert out["receipt"]["charged_units"] == 0
    assert out["receipt"]["publisher_principal"] == PUBLISHER
    assert receipts.verify_receipt(out["receipt"]) is True


def test_consult_receipt_is_persisted_before_results(monkeypatch):
    product, _ = _published()
    _, grant = _grant(product["product_id"])

    def fail(*args, **kwargs):
        raise RuntimeError("receipt store unavailable")

    monkeypatch.setattr(market, "_write_consult_receipt", fail)
    with pytest.raises(RuntimeError, match="receipt store unavailable"):
        market.agent_consult(
            {"grant_id": grant["grant_id"], "query": "design"},
            buyer_principal="codex.agent", buyer_vault_id=BUYER_VAULT, client_id="codex",
        )


def test_idempotency_quota_and_revocation_fail_closed():
    product, _ = _published()
    _, grant = _grant(product["product_id"], quota=1)
    args = dict(buyer_principal="codex.agent", buyer_vault_id=BUYER_VAULT, client_id="codex")
    first = market.agent_consult(
        {"grant_id": grant["grant_id"], "query": "design", "request_id": "same-request"}, **args,
    )
    replay = market.agent_consult(
        {"grant_id": grant["grant_id"], "query": "design", "request_id": "same-request"}, **args,
    )
    exhausted = market.agent_consult(
        {"grant_id": grant["grant_id"], "query": "design", "request_id": "new-request"}, **args,
    )
    assert first["allowed"] is True
    assert replay["reason"] == "idempotent-replay" and replay["results"] == []
    assert exhausted["allowed"] is False and exhausted["reason"] == "quota-exhausted"
    market.grant_revoke(grant["grant_id"], **args)
    revoked = market.agent_consult(
        {"grant_id": grant["grant_id"], "query": "design", "request_id": "after-revoke"}, **args,
    )
    assert revoked["reason"] == "grant-revoked"


def test_request_id_cannot_be_rebound_to_query_grant_vault_or_client():
    product, _ = _published()
    _, grant = _grant(product["product_id"], quota=5)
    _, other_grant = _grant(product["product_id"], quota=5)
    args = dict(buyer_principal="codex.agent", buyer_vault_id=BUYER_VAULT, client_id="codex")
    market.agent_consult(
        {"grant_id": grant["grant_id"], "query": "design", "request_id": "fixed-request"},
        **args,
    )
    variants = [
        ({"grant_id": grant["grant_id"], "query": "different", "request_id": "fixed-request"}, args),
        ({"grant_id": other_grant["grant_id"], "query": "design", "request_id": "fixed-request"}, args),
        ({"grant_id": grant["grant_id"], "query": "design", "request_id": "fixed-request"},
         {**args, "buyer_vault_id": "vault.other"}),
        ({"grant_id": grant["grant_id"], "query": "design", "request_id": "fixed-request"},
         {**args, "client_id": "claude-code"}),
    ]
    for payload, binding in variants:
        with pytest.raises(ValueError, match="request_id is already bound"):
            market.agent_consult(payload, **binding)


def test_receipt_verification_binds_query_product_vault_principal_and_client():
    product, _ = _published()
    _, grant = _grant(product["product_id"])
    out = market.agent_consult(
        {"grant_id": grant["grant_id"], "query": "design", "request_id": "verify-1"},
        buyer_principal="codex.agent", buyer_vault_id=BUYER_VAULT, client_id="codex",
    )
    checks = market.receipt_verify(
        out["receipt"], expected_query="design", expected_product_id=product["product_id"],
        buyer_principal="codex.agent", buyer_vault_id=BUYER_VAULT, client_id="codex",
    )
    wrong_client = market.receipt_verify(
        out["receipt"], expected_query="design", expected_product_id=product["product_id"],
        buyer_principal="codex.agent", buyer_vault_id=BUYER_VAULT, client_id="claude-code",
    )
    assert checks == {"valid": True, "signature_valid": True,
                      "persistence_valid": True, "binding_valid": True}
    assert wrong_client["valid"] is False and wrong_client["binding_valid"] is False


def test_codex_and_claude_share_one_vault_but_keep_separate_principals_and_grants():
    product, _ = _published()
    _, codex_grant = _grant(product["product_id"], principal="codex.agent", client="codex")
    _, claude_grant = _grant(product["product_id"], principal="claude.agent", client="claude-code")
    codex = market.agent_consult(
        {"grant_id": codex_grant["grant_id"], "query": "commitment"},
        buyer_principal="codex.agent", buyer_vault_id=BUYER_VAULT, client_id="codex",
    )
    claude = market.agent_consult(
        {"grant_id": claude_grant["grant_id"], "query": "commitment"},
        buyer_principal="claude.agent", buyer_vault_id=BUYER_VAULT, client_id="claude-code",
    )
    assert codex["results"] == claude["results"]
    assert codex["receipt"]["buyer_vault_id"] == claude["receipt"]["buyer_vault_id"] == BUYER_VAULT
    assert codex["receipt"]["buyer_principal"] != claude["receipt"]["buyer_principal"]
    denied = market.agent_consult(
        {"grant_id": codex_grant["grant_id"], "query": "commitment"},
        buyer_principal="claude.agent", buyer_vault_id=BUYER_VAULT, client_id="claude-code",
    )
    assert denied["allowed"] is False and denied["reason"] == "principal-mismatch"
