"""/v1/similarity/ — 의미 사용판정(mechanical-echo v3)의 서버 반쪽.

계약: 훅이 기억 probe(sources)와 세션의 답변 문장(targets)을 보내면, 색인과
같은 임베딩 스택으로 probe별 최대 코사인을 돌려준다. 같은 스택이어야 색인과
사용판정이 따로 놀지 않는다.
"""
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-similarity.sqlite3")

from forget.db import init_db  # noqa: E402
from forget.server import app  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "sim.sqlite3"))
    init_db()
    yield


client = TestClient(app)


def test_identical_text_scores_near_one_and_unrelated_lower():
    resp = client.post("/v1/similarity/", json={
        "sources": ["정훈은 매일 아침 드립 커피를 내려 마신다"],
        "targets": ["정훈은 매일 아침 드립 커피를 내려 마신다",
                    "서버 배포는 launchctl kickstart로 재시작한다"],
    })
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["max_similarity"] > 0.99
    assert result["target_index"] == 0


def test_each_source_gets_its_own_verdict():
    resp = client.post("/v1/similarity/", json={
        "sources": ["캐시 배치 실측", "커피 내리는 습관"],
        "targets": ["캐시 배치 실측 완료 — 20.1% 절감", "아침마다 커피를 내려 마신다"],
    })
    body = resp.json()
    assert body["n_sources"] == 2
    assert body["results"][0]["target_index"] == 0
    assert body["results"][1]["target_index"] == 1


def test_empty_inputs_are_rejected():
    assert client.post("/v1/similarity/", json={"sources": [], "targets": ["x"]}).status_code == 400
    assert client.post("/v1/similarity/", json={"sources": ["x"], "targets": []}).status_code == 400


def test_input_caps_are_enforced_not_erred():
    resp = client.post("/v1/similarity/", json={
        "sources": [f"기억 {i}" for i in range(80)],
        "targets": ["문장 하나"],
    })
    assert resp.status_code == 200
    assert resp.json()["n_sources"] == 64   # 상한에서 자른다 — 훅은 오류가 아니라 결과를 원한다
