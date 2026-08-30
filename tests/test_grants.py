"""접근 그랜트·출구 검문·접근 영수증 계약 테스트 (MEMORY_ECONOMY.md 내부 경제).

계약 7: ①그랜트 하 서빙 + PII 검문 ②그랜트 밖 거부 + 거부 영수증
③영수증 서명이 verify_receipt로 검증 ④쿼터 소진 → 거부 ⑤폐기(revoke) 즉시 거부
⑥self층(소유 user_id)은 서빙에 안 실림 ⑦영수증 선기록(쓰기 실패 시 서빙 없음).
"""
import os
import sqlite3

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-grants.sqlite3")

import pytest  # noqa: E402

from forget import grants, receipts  # noqa: E402
from forget.db import init_db  # noqa: E402
from forget.store import add_memories, create_api_key  # noqa: E402

APP = "econ-app"


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "g.sqlite3"))
    monkeypatch.setattr(receipts, "RECEIPT_KEY_PATH", tmp_path / "key")
    monkeypatch.setattr(receipts, "ED25519_KEY_PATH", tmp_path / "ed25519.key")
    monkeypatch.setattr(receipts, "ED25519_PUB_PATH", tmp_path / "ed25519.pub")
    init_db()
    # 공유 원장: PII 섞인 팀 사실 (app 스코프, user_id 없음)
    add_memories({"messages": [{"role": "user", "content":
                  "Team decision: next client meeting is on Sept 3, contact 010-4821-7733"}],
                  "app_id": APP, "agent_id": "agent-a", "infer": False})
    # self층: 소유 user_id — 비매품
    add_memories({"messages": [{"role": "user", "content":
                  "I am cautious and always double-check before acting"}],
                  "app_id": APP, "agent_id": "agent-a", "user_id": "owner-a",
                  "infer": False})


def _grant(**overrides):
    payload = {"grantee_pattern": "team-agent-1", "scope_app": APP, "quota": 5}
    payload.update(overrides)
    return grants.create_grant(payload)


def test_serve_with_gate_redacts_pii():
    _grant()
    out = grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                        "query": "client meeting contact"})
    assert out["allowed"] is True
    texts = " ".join(r["memory"] for r in out["results"])
    assert "Sept 3" in texts                       # 지식은 흐른다
    assert "010-4821-7733" not in texts            # PII는 안 흐른다
    assert "[redacted-phone]" in texts
    assert out["receipt"]["redactions"] >= 1


def test_out_of_grant_refused_and_receipted():
    _grant()
    out = grants.serve({"grantee": "stranger-1", "scope_app": APP, "query": "meeting"})
    assert out["allowed"] is False and out["results"] == []
    assert out["reason"] == "no-matching-grant"
    ledger = grants.list_access_receipts(grantee="stranger-1")
    assert len(ledger) == 1 and ledger[0]["allowed"] is False


def test_receipt_signature_verifies_with_existing_verifier():
    _grant()
    out = grants.serve({"grantee": "team-agent-1", "scope_app": APP, "query": "meeting"})
    assert receipts.verify_receipt(out["receipt"]) is True
    tampered = {**out["receipt"], "items_served": 999}
    assert receipts.verify_receipt(tampered) is False


def test_quota_exhaustion_refuses():
    _grant(quota=2)
    for _ in range(2):
        assert grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                             "query": "meeting"})["allowed"] is True
    out = grants.serve({"grantee": "team-agent-1", "scope_app": APP, "query": "meeting"})
    assert out["allowed"] is False and out["reason"] == "quota-exhausted"


def test_revoke_refuses_immediately():
    grant = _grant()
    assert grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                         "query": "meeting"})["allowed"] is True
    grants.revoke_grant(grant["id"])
    out = grants.serve({"grantee": "team-agent-1", "scope_app": APP, "query": "meeting"})
    assert out["allowed"] is False and out["reason"] == "no-matching-grant"


def test_self_layer_never_served():
    _grant()
    out = grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                        "query": "cautious double-check personality"})
    texts = " ".join(r["memory"] for r in out["results"])
    assert "cautious" not in texts  # 소유 user_id 행은 그랜트가 못 연다


def test_no_receipt_no_serve(monkeypatch):
    _grant()

    def boom(receipt, project_id):
        raise RuntimeError("receipt store down")

    monkeypatch.setattr(grants, "_write_receipt", boom)
    with pytest.raises(RuntimeError):
        grants.serve({"grantee": "team-agent-1", "scope_app": APP, "query": "meeting"})


# ---- gpt-live 인계 5건 (2026-08-28) ------------------------------------------


def test_request_id_idempotent_replay_no_double_quota():
    _grant(quota=2)
    first = grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                          "query": "meeting", "request_id": "req-1"})
    replay = grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                           "query": "meeting", "request_id": "req-1"})
    assert replay["reason"] == "idempotent-replay"
    assert replay["receipt"]["receipt_id"] == first["receipt"]["receipt_id"]
    # 쿼터는 1만 소모 — 남은 1로 새 요청이 여전히 입장한다
    fresh = grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                          "query": "meeting", "request_id": "req-2"})
    assert fresh["allowed"] is True


def test_atomic_admission_never_exceeds_quota_under_concurrency():
    import threading

    _grant(quota=3)
    allowed = []
    def hit(i):
        out = grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                            "query": f"meeting {i}"})
        if out["allowed"]:
            allowed.append(1)
    threads = [threading.Thread(target=hit, args=(i,)) for i in range(9)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(allowed) == 3  # 동시 9요청 → 정확히 quota만 입장


def test_query_commitment_is_keyed_not_plain_sha():
    import hashlib as _hl
    _grant()
    out = grants.serve({"grantee": "team-agent-1", "scope_app": APP, "query": "meeting"})
    receipt = out["receipt"]
    assert receipt["query_commitment"] != _hl.sha256(b"meeting").hexdigest()
    assert "query_hash" not in receipt
    assert receipts.verify_receipt(receipt) is True  # 커밋먼트 포함 서명 유효


def test_verify_access_receipt_binds_query_principal_scope_and_persistence():
    _grant()
    out = grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                        "query": "meeting", "request_id": "verify-1"})
    receipt = out["receipt"]
    checks = grants.verify_access_receipt(
        receipt,
        expected_query="meeting",
        expected_grantee="team-agent-1",
        expected_scope_app=APP,
    )
    assert checks == {"valid": True, "signature_valid": True,
                      "persistence_valid": True, "binding_valid": True}
    wrong_query = grants.verify_access_receipt(
        receipt,
        expected_query="different",
        expected_grantee="team-agent-1",
        expected_scope_app=APP,
    )
    assert wrong_query["valid"] is False and wrong_query["binding_valid"] is False
    wrong_project = grants.verify_access_receipt(
        receipt,
        expected_query="meeting",
        expected_grantee="team-agent-1",
        expected_scope_app=APP,
        project_id="other-project",
    )
    assert wrong_project["valid"] is False and wrong_project["persistence_valid"] is False


def test_receipt_verification_endpoint_requires_exact_expectations():
    from fastapi.testclient import TestClient
    from forget.server import app

    _grant()
    receipt = grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                            "query": "meeting", "request_id": "verify-http"})["receipt"]
    client = TestClient(app)
    agent_key = create_api_key({"name": "agent key", "agent_principal": "team-agent-1"})
    headers = {"Authorization": f"Bearer {agent_key['api_key']}"}
    payload = {"receipt": receipt, "expected": {
        "query": "meeting", "grantee": "team-agent-1", "scope_app": APP,
    }}
    verified = client.post("/v1/receipts/verify/", json=payload, headers=headers)
    assert verified.status_code == 200
    assert verified.json() == {
        "schema_version": "forget-receipt-verification-v1",
        "valid": True,
        "signature_valid": True,
        "persistence_valid": True,
        "binding_valid": True,
    }
    wrong = client.post("/v1/receipts/verify/", json={**payload, "expected": {
        **payload["expected"], "query": "different",
    }}, headers=headers)
    assert wrong.status_code == 200 and wrong.json()["valid"] is False
    assert wrong.json()["binding_valid"] is False
    assert client.post("/v1/receipts/verify/", json={"receipt": receipt}, headers=headers).status_code == 400
    assert client.post("/v1/receipts/verify/", json={**payload, "extra": True}, headers=headers).status_code == 400


def test_request_id_is_a_bounded_identifier():
    _grant()
    with pytest.raises(ValueError):
        grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                      "query": "meeting", "request_id": "bad request"})


def test_exact_principal_is_default_and_does_not_expand():
    grant = _grant()
    assert grant["principal_mode"] == "exact"
    assert grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                         "query": "meeting"})["allowed"] is True
    denied = grants.serve({"grantee": "team-agent-2", "scope_app": APP,
                           "query": "meeting"})
    assert denied["allowed"] is False and denied["reason"] == "no-matching-grant"


def test_wildcard_principal_requires_visible_owner_opt_in():
    with pytest.raises(ValueError, match="allow_pattern=true"):
        _grant(grantee_pattern="team-agent-*")
    pattern = _grant(grantee_pattern="team-agent-*", allow_pattern=True)
    assert pattern["principal_mode"] == "pattern"
    assert grants.serve({"grantee": "team-agent-9", "scope_app": APP,
                         "query": "meeting"})["allowed"] is True


def test_principal_contract_rejects_ambiguous_or_invalid_controls():
    with pytest.raises(ValueError, match="boolean"):
        _grant(allow_pattern="yes")
    with pytest.raises(ValueError, match="bounded principal"):
        _grant(grantee_pattern="team agent 1")
    with pytest.raises(ValueError, match="invalid pattern"):
        _grant(grantee_pattern="team-agent-*/admin", allow_pattern=True)


def test_legacy_wildcard_grants_migrate_to_visible_pattern_mode(tmp_path, monkeypatch):
    path = tmp_path / "legacy.sqlite3"
    monkeypatch.setenv("MEM1_DB_PATH", str(path))
    with sqlite3.connect(path) as conn:
        conn.execute(
            """CREATE TABLE access_grants (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner_user_id TEXT,
                grantee_pattern TEXT NOT NULL, scope_app TEXT NOT NULL,
                deny_pii TEXT NOT NULL DEFAULT '[]', quota INTEGER NOT NULL DEFAULT 100,
                used INTEGER NOT NULL DEFAULT 0, answer_mode TEXT NOT NULL DEFAULT 'passage',
                expires_at TEXT, revoked_at TEXT, created_at TEXT NOT NULL
            )"""
        )
        values = ("proj_local", None, APP, "[]", 5, 0, "passage", None, None, "2026-08-28T00:00:00Z")
        conn.execute(
            "INSERT INTO access_grants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy-pattern", values[0], values[1], "team-agent-*", *values[2:]),
        )
        conn.execute(
            "INSERT INTO access_grants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy-exact", values[0], values[1], "team-agent-1", *values[2:]),
        )
    init_db()
    with sqlite3.connect(path) as conn:
        modes = dict(conn.execute("SELECT id, principal_mode FROM access_grants"))
    assert modes == {"legacy-pattern": "pattern", "legacy-exact": "exact"}


def test_http_grant_admin_and_serving_principal_are_separate_authorities():
    from fastapi.testclient import TestClient
    from forget.server import app

    client = TestClient(app)
    agent_key = create_api_key({"name": "agent", "agent_principal": "team-agent-1"})
    other_key = create_api_key({"name": "other", "agent_principal": "team-agent-2"})
    owner_key = create_api_key({"name": "owner", "scopes": ["grants:admin"]})
    agent_headers = {"Authorization": f"Bearer {agent_key['api_key']}"}
    other_headers = {"Authorization": f"Bearer {other_key['api_key']}"}
    owner_headers = {"Authorization": f"Bearer {owner_key['api_key']}"}
    grant_payload = {"grantee_pattern": "team-agent-1", "scope_app": APP, "quota": 2}

    assert client.post("/v1/grants/", json=grant_payload).status_code == 403
    assert client.post("/v1/grants/", json=grant_payload, headers=agent_headers).status_code == 403
    created = client.post("/v1/grants/", json=grant_payload, headers=owner_headers)
    assert created.status_code == 200 and created.json()["principal_mode"] == "exact"
    grant_id = created.json()["id"]
    assert client.get("/v1/grants/", headers=agent_headers).status_code == 403
    assert client.get("/v1/grants/", headers=owner_headers).status_code == 200

    serve_payload = {"grantee": "team-agent-1", "scope_app": APP,
                     "query": "team fact", "request_id": "bound-serve"}
    assert client.post("/v1/memories/serve/", json=serve_payload).status_code == 403
    assert client.post("/v1/memories/serve/", json=serve_payload, headers=other_headers).status_code == 403
    served = client.post("/v1/memories/serve/", json=serve_payload, headers=agent_headers)
    assert served.status_code == 200 and served.json()["allowed"] is True
    assert served.json()["receipt"]["grantee"] == "team-agent-1"

    assert client.get("/v1/receipts/access/", headers=agent_headers).status_code == 403
    assert client.get("/v1/receipts/access/", headers=owner_headers).status_code == 200
    assert client.post(f"/v1/grants/{grant_id}/revoke", headers=agent_headers).status_code == 403
    assert client.post(f"/v1/grants/{grant_id}/revoke", headers=owner_headers).status_code == 200


def test_pointer_mode_returns_refs_not_passages():
    _grant(answer_mode="pointer")
    out = grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                        "query": "client meeting contact"})
    assert out["allowed"] is True and out["results"]
    for row in out["results"]:
        assert "memory" not in row and row.get("ref")  # 원문 0, 참조만
    assert out["receipt"]["answer_mode"] == "pointer"


def test_serve_never_leaks_other_app_shared_rows():
    """교차-앱 누수 회귀 (2026-08-29 데모 리허설 실측): scope_app 그랜트는
    그 앱의 공유 원장만 연다 — 타 앱 공유 행은 폴백으로도 안 나온다."""
    _grant()
    add_memories({"messages": [{"role": "user", "content":
                  "다른 앱의 내부 제안: 로드맵 수렴 회의 기록"}],
                  "app_id": "other-app", "agent_id": "agent-z", "infer": False})
    out = grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                        "query": "로드맵 수렴 회의"})
    assert out["allowed"] is True
    for row in out["results"]:
        assert "로드맵 수렴" not in row["memory"]        # 타 앱 행 무누출


def test_usage_statement_aggregates_receipts():
    """사용 명세서 (마켓 제도): 원천은 영수증뿐 — 서빙·거절·검문·일별 집계."""
    _grant()
    grants.serve({"grantee": "team-agent-1", "scope_app": APP, "query": "client meeting contact"})
    grants.serve({"grantee": "team-agent-1", "scope_app": APP, "query": "meeting"})
    grants.serve({"grantee": "stranger-9", "scope_app": APP, "query": "meeting"})   # 거절
    st = grants.usage_statement(grantee="team-agent-1", scope_app=APP, days=7)
    assert st["serves"] == 2 and st["denials"] == 0
    assert st["redactions_total"] >= 1                     # PII 검문이 명세에 잡힘
    assert sum(d["serves"] for d in st["by_day"].values()) == 2
    st_all = grants.usage_statement(scope_app=APP, days=7)
    assert st_all["denials"] == 1                          # 거절도 명세에


def test_statement_endpoint_scopes_to_own_grantee():
    from fastapi.testclient import TestClient
    from forget.server import app
    from forget.store import create_api_key
    _grant()
    grants.serve({"grantee": "team-agent-1", "scope_app": APP, "query": "meeting"})
    client = TestClient(app)
    key = create_api_key({"name": "k", "agent_principal": "team-agent-1"})
    out = client.get("/v1/receipts/statement/?grantee=someone-else",
                     headers={"Authorization": f"Bearer {key['api_key']}"})
    assert out.status_code == 200
    assert out.json()["grantee"] == "team-agent-1"          # 신원에 강제 결합


def test_grant_expiry_defaults_to_ttl_and_indefinite_is_explicit():
    """만료 기본값 (마켓 제도): 키 부재→30일, 무기한은 명시적 선택만."""
    g_default = grants.create_grant({"grantee_pattern": "ttl-agent", "scope_app": APP})
    assert g_default["expires_at"] is not None            # 침묵 무기한 없음
    g_never = grants.create_grant({"grantee_pattern": "ttl-agent", "scope_app": APP,
                                   "expires_at": "never"})
    assert g_never["expires_at"] is None                  # 의도 기록된 무기한
    g_exp = grants.create_grant({"grantee_pattern": "ttl-agent", "scope_app": APP,
                                 "expires_at": "2020-01-01T00:00:00Z"})
    out = grants.serve({"grantee": "ttl-agent", "scope_app": APP, "query": "x"})
    assert out["allowed"] is True                         # never 그랜트로 입장
    grants.revoke_grant(g_never["id"])
    grants.revoke_grant(g_default["id"])
    out2 = grants.serve({"grantee": "ttl-agent", "scope_app": APP, "query": "x"})
    assert out2["allowed"] is False and out2["reason"] == "grant-expired"
    grants.revoke_grant(g_exp["id"])


def test_statement_carries_quota_remaining():
    g = _grant()
    grants.serve({"grantee": "team-agent-1", "scope_app": APP, "query": "meeting"})
    st = grants.usage_statement(grantee="team-agent-1", scope_app=APP, days=7)
    row = next(r for r in st["live_grants"] if r["id"] == g["id"])
    assert row["remaining"] == row["quota"] - row["used"] and row["used"] >= 1


def test_b3o_scope_grant_rejects_indefinite_expiry():
    """승격 계약 집행: b3o.* 그랜트는 만료 필수 — 무기한은 구조적으로 불가."""
    with pytest.raises(ValueError, match="finite expires_at"):
        grants.create_grant({"grantee_pattern": "b3o-desktop", "scope_app": "b3o.ws1",
                             "expires_at": "never"})
    ok = grants.create_grant({"grantee_pattern": "b3o-desktop", "scope_app": "b3o.ws1"})
    assert ok["expires_at"] is not None                   # 기본값 30일이 채움
    grants.revoke_grant(ok["id"])
