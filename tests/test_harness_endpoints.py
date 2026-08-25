"""자기 하네스 기관 표면 계약 (헌장 개정 3) — pi 확장이 소비하는 HTTP.

계약: ①유언장 arm/release가 규율(사유·영수증 의무 → 400)을 HTTP에서도
지킨다 ②consolidate는 쓰기 부작용 없는 순수 변환 — LLM이 죽어도 핸들
섹션은 산다 ③요약 텍스트에 "do not paraphrase" 핸들 블록이 실린다.
"""
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-harness-ep.sqlite3")

from forget import selfharness as sh  # noqa: E402
from forget import worldmodel  # noqa: E402
from forget.server import app  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "hep.sqlite3"))
    monkeypatch.setattr(worldmodel, "DEFAULT_WORLD_DB", str(tmp_path / "world.sqlite3"))
    # 증류 LLM은 죽은 주소로 — fail-open 경로가 계약이다
    monkeypatch.setenv("MEM1_HARNESS_DISTILL_URL", "http://127.0.0.1:1/v1/chat/completions")
    yield


def test_hands_http_lifecycle_and_discipline():
    client = TestClient(app)
    bad = client.post("/v1/worldmodel/hands/", json={
        "id": "h1", "kind": "watch", "what": "감시", "why": "", "source_ref": "r"})
    assert bad.status_code == 400 and "사유" in bad.json()["error"] or "필요" in bad.json()["error"]
    ok = client.post("/v1/worldmodel/hands/", json={
        "id": "h1", "kind": "watch", "what": "터널 감시", "why": "L2 런 진행 중",
        "source_ref": "test"})
    assert ok.status_code == 200 and ok.json()["armed"] is True
    lst = client.get("/v1/worldmodel/hands/")
    assert [h["id"] for h in lst.json()["hands"]] == ["h1"]
    rel_bad = client.post("/v1/worldmodel/hands/release/", json={"id": "h1", "reason": " "})
    assert rel_bad.status_code == 400
    rel = client.post("/v1/worldmodel/hands/release/", json={"id": "h1", "reason": "런 종료"})
    assert rel.status_code == 200 and rel.json()["changed"] is True
    assert client.get("/v1/worldmodel/hands/").json()["hands"] == []


def test_consolidate_pure_and_handles_survive_dead_llm():
    client = TestClient(app)
    empty = client.post("/v1/harness/consolidate/", json={"turns": []})
    assert empty.status_code == 400
    res = client.post("/v1/harness/consolidate/", json={"turns": [
        {"role": "assistant",
         "content": "커밋 e58e825 판정 기록, http://localhost:8000/v1/memories/search/ 검증 2026-08-25."},
    ]})
    assert res.status_code == 200
    body = res.json()
    assert body["distilled"]["distilled_by"] == "none"     # LLM 죽음 = fail-open
    assert "do not paraphrase" in body["summary"]          # 핸들 블록은 산다
    assert "e58e825" in body["summary"]
    assert "/v1/memories/search/" in body["summary"]
    assert body["distilled"]["facts"] == []
