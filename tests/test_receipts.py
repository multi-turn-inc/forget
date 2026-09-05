"""P-F-3 v0 계약 — 삭제 영수증 (망각 헌장 L1-③).

계약 4: ①삭제 후 검색 미노출 ②세계모델 재파생 후 사건 부재 ③영수증의
계층 주장 = 실측(verified True) ④영수증에 원문 부재(해시만) + 서명 검증.
"""
import json
import os

import pytest

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-receipts.sqlite3")

from forget import receipts, worldmodel  # noqa: E402
from forget.db import init_db  # noqa: E402
from forget import store  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "r.sqlite3"))
    monkeypatch.setattr(worldmodel, "DEFAULT_WORLD_DB", str(tmp_path / "world.sqlite3"))
    monkeypatch.setattr(receipts, "RECEIPT_KEY_PATH", tmp_path / "key")
    init_db()
    yield


def test_delete_with_receipt_four_contracts(tmp_path):
    secret = "지워야 할 비밀: 프로젝트 X를 2026-07-01에 시작했다"
    store.add_memories({"messages": [{"role": "user", "content": secret}],
                        "user_id": "u", "infer": False, "hebbian": False})
    found = store.search_memories({"query": "프로젝트 X 시작", "filters": {"user_id": "u"},
                                   "top_k": 3, "threshold": 0.0})
    mid = str(found["results"][0]["id"])
    worldmodel.rebuild(worldmodel.DEFAULT_WORLD_DB, strict_events=True,
                       ledger_db=os.environ["MEM1_DB_PATH"])

    receipt = receipts.delete_with_receipt(
        mid, ledger_db=os.environ["MEM1_DB_PATH"],
        world_db=worldmodel.DEFAULT_WORLD_DB)

    # ① 검색 미노출
    after = store.search_memories({"query": "프로젝트 X 시작", "filters": {"user_id": "u"},
                                   "top_k": 5, "threshold": 0.0})
    assert all(str(m["id"]) != mid for m in after["results"])
    # ② 세계모델 부재 (영수증 발급 경로가 재파생을 수행)
    assert receipt["layers"]["worldmodel_events"] in {"absent", "no_world_db"}
    # ③ 계층 주장 = 실측
    assert receipt["verified"] is True
    assert receipt["layers"]["ledger"] == "soft_deleted"
    # ④ 원문 부재 — 해시만, 서명 유효
    dumped = json.dumps(receipt, ensure_ascii=False)
    assert "프로젝트 X" not in dumped and "비밀" not in dumped
    assert len(receipt["content_sha256"]) == 64
    assert receipts.verify_receipt(receipt) is True
    # 변조 감지
    tampered = {**receipt, "reason": "changed"}
    assert receipts.verify_receipt(tampered) is False


def test_delete_missing_raises(tmp_path):
    with pytest.raises(KeyError):
        receipts.delete_with_receipt("no-such-id",
                                     ledger_db=os.environ["MEM1_DB_PATH"],
                                     world_db=worldmodel.DEFAULT_WORLD_DB)
