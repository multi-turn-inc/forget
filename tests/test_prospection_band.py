"""전망 밴드 — 기대 헤드의 캡슐 접속 계약 (탑다운 헌장 L2 "예측 기계" v0).

계약: ①기본 꺼짐 — 플래그 없이는 밴드도 필드도 비어 있다 ②켜면 세계모델의
열린-고리 기대가 [전망] 줄로 주입되고 그 비용이 예산에 예약된다 ③파생 DB가
없으면 조용히 건너뛰고 읽기 경로가 파일을 만들지 않는다 (fail-open).
"""
import os
import sqlite3

import pytest

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-prospection.sqlite3")

from forget import store, worldmodel  # noqa: E402
from forget.db import init_db  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "prospect.sqlite3"))
    monkeypatch.setenv("MEM1_RECALL_TEMPORAL", "0")
    monkeypatch.delenv("MEM1_PROSPECTION", raising=False)
    # 격리: 확장 밴드가 실기질(~/.forget)을 읽지 못하게 고스트 경로로 —
    # 없으면 이 테스트들이 이 기계의 실제 무소식 엔티티를 주입받는다.
    monkeypatch.setattr(worldmodel, "DEFAULT_SUBSTRATE_DB", str(tmp_path / "ghost-sub.sqlite3"))
    monkeypatch.setattr(worldmodel, "DEFAULT_LEDGER_DB", str(tmp_path / "ghost-led.sqlite3"))
    init_db()
    yield


def _seed_world(path: str) -> None:
    ledger = path + ".ledger"
    conn = sqlite3.connect(ledger)
    conn.execute("CREATE TABLE memories (id TEXT, memory TEXT, metadata TEXT,"
                 " created_at TEXT, updated_at TEXT, deleted INTEGER DEFAULT 0)")
    conn.execute(
        "INSERT INTO memories VALUES ('m1', '배포 완료 보고',"
        " '{\"trust\": {\"kind\": \"action_report\", \"light\": \"yellow\"}}',"
        " '2026-08-01T00:00:00Z', '2026-08-01T00:00:00Z', 0)")
    conn.commit()
    conn.close()
    worldmodel.rebuild(path, ledger)


def _assemble(user: str, **extra) -> dict:
    store.add_memories({"messages": [{"role": "user", "content": "정훈은 커피를 좋아한다"}],
                        "user_id": user, "infer": False, "hebbian": False})
    return store.assemble_context({"query": "커피", "filters": {"user_id": user},
                                   "budget_tokens": 500, "record_trace": False,
                                   "disable_resume_workspace": True, **extra})


def test_default_off_no_band(tmp_path, monkeypatch):
    world = str(tmp_path / "world.sqlite3")
    _seed_world(world)
    monkeypatch.setattr(worldmodel, "DEFAULT_WORLD_DB", world)
    result = _assemble("u-off")
    assert result.get("prospection") == []
    assert "[전망]" not in str(result.get("context") or "")


def test_flag_on_injects_expectation_and_reserves_budget(tmp_path, monkeypatch):
    world = str(tmp_path / "world.sqlite3")
    _seed_world(world)
    monkeypatch.setattr(worldmodel, "DEFAULT_WORLD_DB", world)
    off = _assemble("u-on-base")
    on = _assemble("u-on", include_prospection=True)
    assert len(on["prospection"]) == 1
    assert "증거 확인 또는 정정" in on["prospection"][0]["expectation"]
    # 예약 계정: 밴드 비용만큼 used_tokens가 커진다 (같은 기억 구성 기준)
    assert on["used_tokens"] > off["used_tokens"]


def test_missing_world_db_is_silent_and_not_created(tmp_path, monkeypatch):
    ghost = str(tmp_path / "no-such-world.sqlite3")
    monkeypatch.setattr(worldmodel, "DEFAULT_WORLD_DB", ghost)
    result = _assemble("u-ghost", include_prospection=True)
    assert result["prospection"] == []
    assert not os.path.exists(ghost)  # 읽기 경로는 파일을 만들지 않는다


def test_band_includes_quiet_entity_until_dismissed(tmp_path, monkeypatch):
    # 밴드 확장 계약 (마찰 #1 수리 후): 무소식 기대 1칸이 [전망]에 실리고,
    # dismiss_entity 영수증이 있으면 빠진다 — 기대의 전 생애주기가 밴드에서 돈다.
    world = str(tmp_path / "world.sqlite3")
    _seed_world(world)
    sub = str(tmp_path / "sub.sqlite3")
    conn = sqlite3.connect(sub)
    conn.execute("CREATE TABLE entities (name TEXT, type_id INTEGER, freq INTEGER)")
    conn.execute("CREATE TABLE mentions (memory_id TEXT, entity TEXT)")
    conn.execute("INSERT INTO entities VALUES ('show hn', 1, 30)")
    conn.execute("INSERT INTO mentions VALUES ('m1', 'show hn')")
    conn.commit(); conn.close()
    monkeypatch.setattr(worldmodel, "DEFAULT_WORLD_DB", world)
    monkeypatch.setattr(worldmodel, "DEFAULT_SUBSTRATE_DB", sub)
    monkeypatch.setattr(worldmodel, "DEFAULT_LEDGER_DB", world + ".ledger")  # m1: 2026-08-01
    on = _assemble("u-quiet", include_prospection=True)
    kinds = [i.get("kind") for i in on["prospection"]]
    assert "quiet_entity" in kinds and len(on["prospection"]) == 2  # 고리 1 + 무소식 1
    ctx = str(on.get("context") or "")
    assert "[전망]" in ctx and "무소식" in ctx
    worldmodel.dismiss_entity(world, "show hn", "보류 결정으로 실효", "게이트 결정")
    after = _assemble("u-quiet2", include_prospection=True)
    assert "quiet_entity" not in [i.get("kind") for i in after["prospection"]]
