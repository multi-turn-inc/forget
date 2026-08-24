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
    assert not any("[전망]" in l for l in result.get("context_lines", []) or [])


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
