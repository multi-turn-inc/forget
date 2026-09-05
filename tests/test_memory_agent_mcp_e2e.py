"""One provider-neutral Memory Agent flow through real MCP HTTP routes."""
from __future__ import annotations

import os
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-memory-agent-mcp.sqlite3")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from forget import market, receipts  # noqa: E402
from forget.db import init_db  # noqa: E402
from forget.server import app  # noqa: E402
from forget.store import add_memories, create_api_key, list_memory_dicts  # noqa: E402


VAULT = "vault.person-1"
SOURCE_APP = "market-source"


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "mcp-market.sqlite3"))
    monkeypatch.setattr(receipts, "RECEIPT_KEY_PATH", tmp_path / "receipt.key")
    monkeypatch.setattr(receipts, "ED25519_KEY_PATH", tmp_path / "ed25519.key")
    monkeypatch.setattr(receipts, "ED25519_PUB_PATH", tmp_path / "ed25519.pub")
    init_db()


def _publish_test_product() -> str:
    add_memories({
        "messages": [{"role": "user", "content":
                      "For a calm interface, keep one primary commitment visible and disclose evidence on demand."}],
        "app_id": SOURCE_APP,
        "agent_id": "publisher.agent",
        "infer": False,
    })
    source_id = next(row["id"] for row in list_memory_dicts() if row.get("app_id") == SOURCE_APP)
    product = market.create_product(
        {"name": "Calm Interface Memory", "summary": "Commitment-first UX advice.",
         "capability": "ux-review", "source_app": SOURCE_APP,
         "answer_mode": "passage", "max_items": 1},
        publisher_principal="publisher.agent",
        publisher_vault_id="vault.publisher",
    )
    market.review_product_item(
        product["product_id"], {"memory_id": source_id, "reviewed": True},
        publisher_principal="publisher.agent",
    )
    market.publish_product(product["product_id"], publisher_principal="publisher.agent")
    return product["product_id"]


def _key(principal: str) -> str:
    return create_api_key({
        "name": f"{principal} market e2e",
        "owner_user_id": VAULT,
        "agent_principal": principal,
        "scopes": ["project:read", "memory:read"],
    })["api_key"]


def _rpc(client: TestClient, path: str, key: str, tool: str, arguments: dict, call_id: int):
    response = client.post(
        path,
        headers={"Authorization": f"Bearer {key}"},
        json={"jsonrpc": "2.0", "id": call_id, "method": "tools/call",
              "params": {"name": tool, "arguments": arguments}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "error" not in body, body
    return body["result"]["structuredContent"]


def _tool_names(client: TestClient, path: str, key: str) -> set[str]:
    response = client.post(
        path,
        headers={"Authorization": f"Bearer {key}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == 200
    return {tool["name"] for tool in response.json()["result"]["tools"]}


def _path_from_url(value: str) -> str:
    parsed = urlsplit(value)
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")


def test_codex_and_claude_mcp_complete_same_market_flow_with_separate_credentials():
    product_id = _publish_test_product()
    client = TestClient(app)
    codex_key = _key("codex.agent")
    claude_key = _key("claude.agent")
    codex_path = f"/mcp/forget/http/{VAULT}?profile=codex"
    claude_path = f"/mcp/forget/http/{VAULT}?profile=claude"
    market_tools = {
        "catalog_search", "product_quote", "grant_create",
        "agent_consult", "receipt_verify", "grant_revoke",
    }
    assert market_tools <= _tool_names(client, codex_path, codex_key)
    assert market_tools <= _tool_names(client, claude_path, claude_key)

    catalog = _rpc(client, codex_path, codex_key, "catalog_search", {"query": "interface"}, 2)
    assert [row["product_id"] for row in catalog["products"]] == [product_id]

    codex_quote = _rpc(
        client, codex_path, codex_key, "product_quote",
        {"product_id": product_id, "purpose": "Review a new interface", "quota": 2}, 3,
    )["quote"]
    codex_grant = _rpc(
        client, codex_path, codex_key, "grant_create",
        {"quote_id": codex_quote["quote_id"], "approve": True}, 4,
    )
    codex_consult = _rpc(
        client, codex_path, codex_key, "agent_consult",
        {"grant_id": codex_grant["grant_id"], "query": "primary commitment evidence",
         "request_id": "codex-consult-1"}, 5,
    )
    codex_verified = _rpc(
        client, codex_path, codex_key, "receipt_verify",
        {"receipt": codex_consult["receipt"], "expected_query": "primary commitment evidence",
         "expected_product_id": product_id}, 6,
    )
    assert codex_consult["allowed"] is True
    assert codex_consult["receipt"]["buyer_principal"] == "codex.agent"
    assert codex_consult["receipt"]["buyer_vault_id"] == VAULT
    assert codex_consult["receipt"]["client_id"] == "codex"
    assert codex_consult["receipt"]["charged_units"] == 0
    assert codex_verified["valid"] is True

    claude_quote = _rpc(
        client, claude_path, claude_key, "product_quote",
        {"product_id": product_id, "purpose": "Review the same interface", "quota": 1}, 7,
    )["quote"]
    claude_grant = _rpc(
        client, claude_path, claude_key, "grant_create",
        {"quote_id": claude_quote["quote_id"], "approve": True}, 8,
    )
    claude_consult = _rpc(
        client, claude_path, claude_key, "agent_consult",
        {"grant_id": claude_grant["grant_id"], "query": "primary commitment evidence",
         "request_id": "claude-consult-1"}, 9,
    )
    assert claude_consult["results"] == codex_consult["results"]
    assert claude_consult["receipt"]["buyer_principal"] == "claude.agent"
    assert claude_consult["receipt"]["buyer_vault_id"] == VAULT
    assert claude_consult["receipt"]["client_id"] == "claude-code"

    _rpc(
        client, codex_path, codex_key, "grant_revoke",
        {"grant_id": codex_grant["grant_id"]}, 10,
    )
    denied = _rpc(
        client, codex_path, codex_key, "agent_consult",
        {"grant_id": codex_grant["grant_id"], "query": "commitment",
         "request_id": "codex-after-revoke"}, 11,
    )
    assert denied["allowed"] is False and denied["reason"] == "grant-revoked"


def test_market_mcp_rejects_unbound_vault_and_profile_switching():
    product_id = _publish_test_product()
    client = TestClient(app)
    no_vault = create_api_key({"name": "unbound", "agent_principal": "codex.unbound"})["api_key"]
    result = client.post(
        "/mcp/forget/http/claimed-vault?profile=codex",
        headers={"Authorization": f"Bearer {no_vault}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "product_quote", "arguments": {
                  "product_id": product_id, "purpose": "Should fail"}}},
    ).json()
    assert "credential-bound personal vault" in result["error"]["message"]

    codex_key = _key("codex.agent")
    mismatch = client.post(
        "/mcp/forget/http/a-different-vault?profile=codex",
        headers={"Authorization": f"Bearer {codex_key}"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"name": "catalog_search", "arguments": {}}},
    ).json()
    assert "URL vault does not match" in mismatch["error"]["message"]

    result = client.post(
        f"/mcp/forget/http/{VAULT}",
        headers={"Authorization": f"Bearer {codex_key}"},
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
              "params": {"name": "catalog_search", "arguments": {}}},
    ).json()
    assert "profile=codex or profile=claude" in result["error"]["message"]


def test_connector_artifacts_drive_both_complete_profile_flows(tmp_path):
    """The exact URLs and credentials written by forget-connect are executable."""
    product_id = _publish_test_product()
    claude_key = _key("claude.connector")
    codex_key = _key("codex.connector")
    package_root = Path(__file__).parents[1] / "packages" / "forget-connect"
    binary = package_root / "bin" / "forget-connect.js"
    home = tmp_path / "client-home"
    base_env = {
        **os.environ,
        "HOME": str(home),
        "CODEX_HOME": str(home / ".codex"),
        "FORGET_PROXY_LAUNCHCTL": "skip",
    }

    for client_id, key in (("claude-code", claude_key), ("codex", codex_key)):
        completed = subprocess.run(
            [
                "node", str(binary), "connect", "--client", client_id, "--yes",
                "--user-id", VAULT, "--app-id", "forget", "--local-auth",
                "--no-proxy",
            ],
            cwd=package_root,
            env={**base_env, "FORGET_API_KEY": key},
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert key not in completed.stdout and key not in completed.stderr

    claude_config = json.loads((home / ".claude.json").read_text())
    claude_server = claude_config["mcpServers"]["forget"]
    assert claude_server["headers"]["Authorization"] == f"Bearer {claude_key}"
    claude_path = _path_from_url(claude_server["url"])

    codex_config = (home / ".codex" / "config.toml").read_text()
    codex_url = re.search(r'^url = "([^"]+)"$', codex_config, re.MULTILINE)
    codex_auth = re.search(r'Authorization = "Bearer ([^"]+)"', codex_config)
    assert codex_url and codex_auth and codex_auth.group(1) == codex_key
    codex_path = _path_from_url(codex_url.group(1))
    assert claude_path.endswith("profile=claude")
    assert codex_path.endswith("profile=codex")

    client = TestClient(app)
    outputs = []
    for index, (client_id, path, key) in enumerate((
        ("claude-code", claude_path, claude_key),
        ("codex", codex_path, codex_key),
    )):
        catalog = _rpc(client, path, key, "catalog_search", {"query": "interface"}, 20 + index * 10)
        assert catalog["products"][0]["product_id"] == product_id
        quote = _rpc(
            client, path, key, "product_quote",
            {"product_id": product_id, "purpose": "Connector artifact E2E", "quota": 1},
            21 + index * 10,
        )["quote"]
        grant = _rpc(
            client, path, key, "grant_create",
            {"quote_id": quote["quote_id"], "approve": True}, 22 + index * 10,
        )
        consulted = _rpc(
            client, path, key, "agent_consult",
            {"grant_id": grant["grant_id"], "query": "primary commitment",
             "request_id": f"connector-{client_id}"}, 23 + index * 10,
        )
        verified = _rpc(
            client, path, key, "receipt_verify",
            {"receipt": consulted["receipt"], "expected_query": "primary commitment",
             "expected_product_id": product_id}, 24 + index * 10,
        )
        assert consulted["allowed"] is True and verified["valid"] is True
        assert consulted["receipt"]["client_id"] == client_id
        outputs.append(consulted["results"])
        _rpc(
            client, path, key, "grant_revoke",
            {"grant_id": grant["grant_id"]}, 25 + index * 10,
        )
    assert outputs[0] == outputs[1]
