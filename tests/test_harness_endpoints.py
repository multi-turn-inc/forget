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
from forget.db import init_db  # noqa: E402
from forget.server import app  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "hep.sqlite3"))
    monkeypatch.setattr(worldmodel, "DEFAULT_WORLD_DB", str(tmp_path / "world.sqlite3"))
    # 증류 LLM은 죽은 주소로 — fail-open 경로가 계약이다
    monkeypatch.setenv("MEM1_HARNESS_DISTILL_URL", "http://127.0.0.1:1/v1/chat/completions")
    init_db()   # persist 계약이 원장 테이블을 실제로 쓴다
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


def test_consolidate_persist_writes_ledger_and_hands(monkeypatch):
    # 잠들기 전 소화 계약: persist=true면 사실→원장(출처 태그·yellow), 의도→
    # 유언장(kind=intent). LLM이 죽어 증류가 비면 persist 계수도 0 — 무해.
    from forget import selfharness as shmod
    monkeypatch.setattr(shmod, "distill_turns", lambda turns, llm=None: {
        "facts": ["P-X 판정 기각 — 영수증 abc1234"], "lessons": [],
        "intents": ["다음 기상은 서버 재개 확인"],
        "handles": [{"kind": "commit", "value": "abc1234"}], "distilled_by": "llm"})
    # server.py는 selfharness에서 distill_turns를 지연 임포트하므로 모듈 속성 패치로 충분
    client = TestClient(app)
    res = client.post("/v1/harness/consolidate/", json={
        "turns": [{"role": "user", "content": "x"}],
        "persist": True, "user_id": "u-cons", "session_ref": "test-sess"})
    assert res.status_code == 200
    p = res.json()["distilled"]["persisted"]
    assert p == {"facts": 1, "lessons": 0, "intents": 1, "errors": 0}
    from forget.store import search_memories
    found = search_memories({"query": "P-X 판정", "filters": {"user_id": "u-cons"},
                             "top_k": 3, "threshold": 0.0})
    assert any("abc1234" in str(m.get("memory")) for m in found["results"])
    meta = (found["results"][0].get("metadata") or {})
    assert meta.get("source") == "consolidation"
    hands = worldmodel.standing_hands(worldmodel.DEFAULT_WORLD_DB)
    assert any(h["kind"] == "intent" and "서버 재개" in h["what"] for h in hands)


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
