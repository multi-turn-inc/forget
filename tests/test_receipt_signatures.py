"""영수증 서명 v1 (Ed25519) 계약 테스트 — 제3자 검증의 성립.

계약: ①새 영수증은 HMAC+Ed25519 이중 서명 ②제3자가 공개키만으로(서버 키
없이) 검증 가능 ③변조는 양쪽 다 실패 ④구판(HMAC 단독) 영수증은 계속 검증
⑤삭제·접근 영수증이 같은 정준형(canonical-v1: SIGNATURE_FIELDS 제외)을 공유.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-rsig.sqlite3")

import pytest  # noqa: E402

from forget import grants, receipts  # noqa: E402
from forget.db import init_db  # noqa: E402
from forget.store import add_memories  # noqa: E402

APP = "econ-app"


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "r.sqlite3"))
    monkeypatch.setattr(receipts, "RECEIPT_KEY_PATH", tmp_path / "key")
    monkeypatch.setattr(receipts, "ED25519_KEY_PATH", tmp_path / "ed.key")
    monkeypatch.setattr(receipts, "ED25519_PUB_PATH", tmp_path / "ed.pub")
    init_db()
    add_memories({"messages": [{"role": "user", "content": "team fact for serving"}],
                  "app_id": APP, "agent_id": "agent-a", "infer": False})
    grants.create_grant({"grantee_pattern": "team-agent-1", "scope_app": APP})


def _serve_receipt():
    return grants.serve({"grantee": "team-agent-1", "scope_app": APP,
                         "query": "team fact"})["receipt"]


def test_dual_signature_present_and_verifies():
    receipt = _serve_receipt()
    assert receipt.get("signature_hmac_sha256") and receipt.get("signature_ed25519")
    assert receipt.get("public_key_ed25519") == receipts.receipt_public_key()
    assert receipts.verify_receipt(receipt) is True


def test_third_party_verifies_with_public_key_only():
    """외부 검증자 시뮬레이션 — 서버 코드·HMAC 키 없이 공개키와 정준형만."""
    from nacl.signing import VerifyKey
    receipt = _serve_receipt()
    body = {k: v for k, v in receipt.items()
            if k not in ("signature_hmac_sha256", "signature_ed25519", "public_key_ed25519")}
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True).encode()
    VerifyKey(bytes.fromhex(receipt["public_key_ed25519"]))\
        .verify(payload, bytes.fromhex(receipt["signature_ed25519"]))  # 예외 없으면 성립


def test_tamper_fails_both_ways():
    receipt = _serve_receipt()
    tampered = {**receipt, "items_served": 999}
    assert receipts.verify_receipt(tampered) is False
    forged = {**receipt, "signature_ed25519": "00" * 64}
    assert receipts.verify_receipt(forged) is False


def test_legacy_hmac_only_receipt_still_verifies():
    legacy = {"kind": "access_receipt", "receipt_id": "old-1", "allowed": True}
    body = json.dumps(legacy, ensure_ascii=False, sort_keys=True).encode()
    import hashlib, hmac as _hmac
    legacy["signature_hmac_sha256"] = _hmac.new(
        receipts._receipt_key(), body, hashlib.sha256).hexdigest()
    assert receipts.verify_receipt(legacy) is True     # 구판 호환


def test_delete_receipt_uses_same_canonical():
    row = add_memories({"messages": [{"role": "user", "content": "to be deleted"}],
                        "app_id": APP, "agent_id": "agent-a", "infer": False})
    from forget.store import get_event
    memory_id = get_event(row["event_id"])["results"][0]["id"]
    receipt = receipts.delete_with_receipt(memory_id)
    assert receipt.get("signature_ed25519")
    assert receipts.verify_receipt(receipt) is True


def test_ed25519_first_use_is_atomic_under_concurrency():
    receipts.ED25519_KEY_PATH.unlink(missing_ok=True)
    receipts.ED25519_PUB_PATH.unlink(missing_ok=True)
    with ThreadPoolExecutor(max_workers=16) as pool:
        public_keys = list(pool.map(lambda _index: receipts.receipt_public_key(), range(64)))
    assert len(set(public_keys)) == 1
    assert len(receipts.ED25519_KEY_PATH.read_bytes()) == 32
    assert receipts.ED25519_KEY_PATH.stat().st_mode & 0o777 == 0o600
    assert receipts.ED25519_PUB_PATH.stat().st_mode & 0o777 == 0o600
    assert not list(receipts.ED25519_KEY_PATH.parent.glob(f".{receipts.ED25519_KEY_PATH.name}.*"))
