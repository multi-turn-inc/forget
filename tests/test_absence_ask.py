"""부재 응답 계약 — «내가 없을 때 나 대신 답하는 AI» v0.

계약: ①green 근거가 있으면 답한다 ②근거가 없으면 «모르겠어요»·0원 ③비-green 행동급(게이트)
사실은 근거가 못 된다 ④로컬 전용(share=private) 기억은 근거가 못 된다 ⑤가게 범위(projects)
밖 기억은 근거가 못 된다 ⑥LLM이 없으면 원문을 내보내지 않는다 ⑦영수증은 검증된다
⑧페이지는 무인증으로 열린다 ⑨없는 가게는 404.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-absence.sqlite3")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from forget import absence, receipts, store  # noqa: E402
from forget.db import init_db  # noqa: E402
from forget.server import app  # noqa: E402
from forget.store import add_memories  # noqa: E402

OWNER = "owner-absent"
SECRET = "정훈의 forget 회사 계좌 잔고는 1,234만원이다"


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "a.sqlite3"))
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    monkeypatch.setattr(receipts, "RECEIPT_KEY_PATH", tmp_path / "receipt.key")
    monkeypatch.setattr(receipts, "ED25519_KEY_PATH", tmp_path / "ed25519.key")
    monkeypatch.setattr(receipts, "ED25519_PUB_PATH", tmp_path / "ed25519.pub")
    cfg = tmp_path / "absence.json"
    cfg.write_text(json.dumps({"shops": [{
        "handle": "junghun", "user_id": OWNER, "title": "정훈에게 묻기",
        "intro": "창업 판단 2026", "projects": ["forget"], "price_krw": 500,
    }]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("MEM1_ABSENCE_CONFIG", str(cfg))
    monkeypatch.setenv("MEM1_ABSENCE_CLI", "0")  # 테스트는 CLI 폴백을 밀폐한다
    absence._RATE.clear()
    init_db()
    # LLM: 근거를 그대로 답으로 돌려주는 가짜 (조합 품질이 아니라 근거 선택 계약을 검사한다)
    monkeypatch.setattr(store, "_resolve_recall_llm", lambda: {"base_url": "http://fake/v1", "model": "fake", "api_key": "x"})
    monkeypatch.setattr(absence, "_llm_chat", lambda llm, prompt, **kw: "ANSWER::" + prompt.split("근거:\n", 1)[1])


def _add(text: str, role: str = "user", **meta):
    payload = {"messages": [{"role": "user" if role == "user" else "assistant", "content": text}],
               "user_id": OWNER, "source_role": role, "infer": False, "hebbian": False}
    if meta:
        payload["metadata"] = meta
    add_memories(payload)


def _ask(q: str) -> dict:
    client = TestClient(app)
    r = client.post("/ask/junghun", json={"question": q})
    assert r.status_code == 200, r.text
    return r.json()


def test_answers_from_green_basis_and_charges():
    _add("정훈은 forget 회사의 다음 제품으로 부재 응답 링크를 만들기로 했다.", project="forget")
    out = _ask("정훈의 다음 제품은 뭐야")
    assert out["status"] == "answered" and out["answer"].startswith("ANSWER::")
    assert out["basis_count"] >= 1 and out["lights"]["green"] >= 1
    assert out["charged_krw"] == 500


def test_unknown_when_no_basis_costs_nothing():
    _add("정훈은 forget 회사의 다음 제품으로 부재 응답 링크를 만들기로 했다.", project="forget")
    out = _ask("화성의 대기 조성은 어떻게 되나요")
    assert out["status"] == "unknown" and out["answer"] is None
    assert out["charged_krw"] == 0 and out["basis_count"] == 0


def test_gated_action_grade_yellow_is_never_basis():
    _add("정훈의 오디션 동영상 제출 마감은 9/7 오후 3시까지다.", role="assistant", project="forget")
    out = _ask("정훈 오디션 동영상 제출 마감이 언제야")
    assert out["basis_count"] == 0 and out["status"] == "unknown"


def test_private_share_is_never_basis():
    _add(SECRET, project="forget", share="private")
    out = _ask("정훈 회사 계좌 잔고가 얼마야")
    assert out["basis_count"] == 0 and SECRET not in json.dumps(out, ensure_ascii=False)


def test_out_of_scope_project_is_never_basis():
    _add("정훈은 주차폴 과제에서 블록체인 정산 검증을 맡았다.", project="dip-parking")
    out = _ask("정훈이 주차폴 과제에서 뭘 맡았어")
    assert out["basis_count"] == 0


def test_without_llm_no_raw_text_leaves(monkeypatch):
    monkeypatch.setattr(store, "_resolve_recall_llm", lambda: None)
    _add("정훈은 forget 회사의 다음 제품으로 부재 응답 링크를 만들기로 했다.", project="forget")
    out = _ask("정훈의 다음 제품은 뭐야")
    assert out["status"] == "unavailable" and out["answer"] is None
    assert "부재 응답 링크" not in json.dumps(out, ensure_ascii=False)


def test_receipt_verifies_and_commits_to_question():
    _add("정훈은 forget 회사의 다음 제품으로 부재 응답 링크를 만들기로 했다.", project="forget")
    out = _ask("정훈의 다음 제품은 뭐야")
    r = out["receipt"]
    assert receipts.verify_receipt(dict(r))
    assert r["question_commitment"] == absence._question_commitment("정훈의 다음 제품은  뭐야 ")
    assert r["charged_krw"] == 500 and r["handle"] == "junghun"


def test_page_is_public_and_unknown_shop_404():
    client = TestClient(app)
    page = client.get("/ask/junghun")
    assert page.status_code == 200 and "<h1>정훈</h1>" in page.text and "정훈에게 물어보기" in page.text
    # 손님 화면에는 신호등·status 같은 우리 내부 어휘가 없다
    assert "들은 것" not in page.text and "확실" not in page.text
    assert client.get("/ask/nobody").status_code == 404
    assert client.post("/ask/nobody", json={"question": "?"}).status_code == 404


def test_rate_limit_rejects_after_hourly_cap(monkeypatch):
    monkeypatch.setattr(absence, "RATE_LIMIT_PER_HOUR", 2)
    _add("정훈은 forget 회사의 다음 제품으로 부재 응답 링크를 만들기로 했다.", project="forget")
    client = TestClient(app)
    assert client.post("/ask/junghun", json={"question": "다음 제품?"}).status_code == 200
    assert client.post("/ask/junghun", json={"question": "다음 제품?"}).status_code == 200
    third = client.post("/ask/junghun", json={"question": "다음 제품?"})
    assert third.status_code == 429


def test_rate_limit_window_slides():
    absence._RATE.clear()
    key = "junghun|1.2.3.4"
    base = 1_000_000.0
    for i in range(absence.RATE_LIMIT_PER_HOUR):
        assert absence.rate_limited(key, now=base + i) is False
    assert absence.rate_limited(key, now=base + 100) is True
    assert absence.rate_limited(key, now=base + 3601) is False  # 첫 항목이 창 밖으로


def test_cli_noise_lines_are_stripped_from_answers():
    raw = "Client.listTools() called but server does not advertise tools capability - returning empty list\n정훈은 forget으로 기억을 만듭니다."
    assert absence._strip_cli_noise(raw) == "정훈은 forget으로 기억을 만듭니다."


def test_cli_is_invoked_bare_and_without_owner_mcp(monkeypatch, tmp_path):
    fake = tmp_path / "claude"; fake.write_text("#!/bin/sh\necho ok\n"); fake.chmod(0o755)
    monkeypatch.setenv("MEM1_ABSENCE_CLI", "1")
    monkeypatch.setenv("MEM1_ABSENCE_CLAUDE_BIN", str(fake))
    seen = {}
    import subprocess
    real = subprocess.run
    def spy(cmd, **kw):
        seen["cmd"] = cmd
        return real(cmd, **kw)
    monkeypatch.setattr(subprocess, "run", spy)
    assert absence._cli_chat("q") == "ok"
    assert {"--strict-mcp-config", "--setting-sources", "--no-session-persistence", "-p"} <= set(seen["cmd"])
    assert "--bare" not in seen["cmd"]  # OAuth를 버려 «Not logged in»으로 죽는다


def test_persona_prompt_is_first_person_and_shop_voice():
    basis = [{"memory": "LongMemEval-V2 종합점수에서 공개 1위 시스템을 상회했다.", "trust": {"light": "green"}}]
    shop = {"name": "김정훈", "voice": "반말, 짧게.", "unknown": "몰라. 정훈한테 물어봐."}
    prompt = absence.compose_prompt(absence.shop_owner(shop, "junghun"), "벤치마크 점수는?", basis,
                                    voice=shop["voice"], unknown=absence.shop_unknown(shop))
    assert "당신은 김정훈 본인입니다" in prompt and "1인칭" in prompt and "비서가 아니라" in prompt
    assert "반말, 짧게." in prompt and "몰라. 정훈한테 물어봐." in prompt
    assert prompt.rstrip().endswith("김정훈:")
    # 3인칭 비서 문면은 사라졌다
    assert "대신 답하는 비서" not in prompt


def test_unknown_detection_accepts_shop_unknown_and_short_negatives():
    assert absence._is_unknown("몰라. 정훈한테 물어봐.", "몰라. 정훈한테 물어봐.")
    assert absence._is_unknown("모르겠어, 그건.", absence.UNKNOWN_MESSAGE)
    assert not absence._is_unknown("9월 7일 오후 3시까지야.", "몰라.")
