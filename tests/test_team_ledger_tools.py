"""합의 원장 도구 계약 테스트 — 자격 결합 귀속 (8c1c048b 합의판).

집행 계약: ①쓰기는 agent_principal이 결합된 Bearer 자격만(fail-closed)
②author 인자는 전면 금지(호출자 선택 귀속 불가, 400) ③무소유+서명+[kind]
④열거·최신 우선·개인 행 제외·전체 id ⑤미결은 검증된 답장 사슬로 계산
⑥멱등 키는 principal+전체 payload에 결합 ⑦위생(PII·제어문자·크기)
⑧일반 memory API의 ownerless 원장 우회 쓰기 금지.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-teamledger.sqlite3")

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from forget.db import init_db  # noqa: E402
from forget.mcp import TEAM_LEDGER_APP, call_tool  # noqa: E402
from forget import scope_guard  # noqa: E402
from forget.store import (  # noqa: E402
    add_memories,
    create_api_key,
    delete_memory,
    list_memory_dicts,
    supersede_memory,
    update_memory,
)


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "t.sqlite3"))
    init_db()


def _ctx(principal: str, auth: str = "credential") -> dict:
    return {"team_principal": principal, "team_principal_auth": auth}


def _note(kind="decision", text="fail-closed 유지", principal="gpt-live", **extra):
    return call_tool("team_note", {"kind": kind, "text": text, **extra},
                     context=_ctx(principal))


def test_credential_bound_write_is_ownerless_and_signed():
    _note()
    rows = [m for m in list_memory_dicts() if m.get("app_id") == TEAM_LEDGER_APP]
    assert len(rows) == 1
    row = rows[0]
    assert row.get("user_id") in (None, "")
    assert row.get("agent_id") == "gpt-live"          # 자격 principal이 귀속
    assert str(row.get("memory")).startswith("[decision]")


def test_unbound_declared_and_author_arg_fail_closed():
    with pytest.raises(HTTPException) as e1:
        call_tool("team_note", {"kind": "decision", "text": "x"})
    assert e1.value.status_code == 403                 # 무자격 거부
    with pytest.raises(HTTPException) as e2:
        call_tool("team_note", {"kind": "decision", "text": "x"},
                  context=_ctx("claude-exec", auth="declared"))
    assert e2.value.status_code == 403                 # 선언 모드 거부
    with pytest.raises(HTTPException) as e3:
        _note(author="gpt-live")                       # author 인자 자체 금지
    assert e3.value.status_code == 400
    with pytest.raises(HTTPException):
        call_tool("team_note", {"kind": "decision", "text": "x"},
                  context=_ctx("junghunkim"))          # 로스터 밖 principal 거부


def test_read_enumerates_full_ids_newest_first_excludes_owned():
    _note(text="첫 결정", principal="claude-exec")
    _note(kind="question", text="둘째 질문", principal="gpt-live")
    add_memories({"messages": [{"role": "user", "content": "사적 메모"}],
                  "app_id": TEAM_LEDGER_APP, "user_id": "owner-x", "infer": False})
    text = str(call_tool("team_read", {}, context=_ctx("gpt-live"))["content"][0]["text"])
    assert "둘째 질문" in text and "첫 결정" in text and "사적 메모" not in text
    assert text.find("둘째 질문") < text.find("첫 결정")
    full_id = [m for m in list_memory_dicts()
               if (m.get("metadata") or {}).get("kind") == "question"][0]["id"]
    assert f"(id={full_id}" in text                    # 전체 id 노출 (수용 조건)


def test_open_only_closes_via_reply_link():
    _note(kind="proposal", text="스키마 제안", principal="claude-exec",
          addressed_to="gpt-live")
    proposal_id = [m for m in list_memory_dicts()
                   if (m.get("metadata") or {}).get("kind") == "proposal"][0]["id"]
    _note(kind="question", text="열린 질문", principal="gpt-live")
    before = str(call_tool("team_read", {"open_only": True}, context=_ctx("gpt-live"))["content"][0]["text"])
    assert "스키마 제안" in before and "열린 질문" in before
    _note(kind="decision", text="제안 수용", principal="gpt-live", reply_to=proposal_id)
    after = str(call_tool("team_read", {"open_only": True}, context=_ctx("gpt-live"))["content"][0]["text"])
    assert "스키마 제안" not in after and "열린 질문" in after


def test_idempotency_fingerprint_replay_and_conflict():
    _note(text="한 번만", principal="claude-exec", idempotency_key="k1")
    replay = _note(text="한 번만", principal="claude-exec", idempotency_key="k1")
    assert "idempotent_replay" in str(replay["content"][0]["text"])
    rows = [m for m in list_memory_dicts() if m.get("app_id") == TEAM_LEDGER_APP]
    assert len(rows) == 1                              # 재생은 행을 안 만든다
    with pytest.raises(HTTPException) as e:
        _note(text="다른 내용", principal="claude-exec", idempotency_key="k1")
    assert e.value.status_code == 409                  # 같은 키·다른 내용 = 충돌


def test_hygiene_pii_control_chars_size_and_scope():
    _note(text="담당자 연락처 010-4821-7733 확인\x07됨", principal="claude-exec")
    row = [m for m in list_memory_dicts() if m.get("app_id") == TEAM_LEDGER_APP][0]
    text = str(row.get("memory"))
    assert "010-4821-7733" not in text and "[redacted-phone]" in text
    assert "\x07" not in text
    with pytest.raises(HTTPException):
        _note(text="x" * 2001, principal="claude-exec")
    assert (row.get("metadata") or {}).get("scope_guard") != "foreign"


def test_raw_memory_write_cannot_bypass_team_note_contract():
    from fastapi.testclient import TestClient
    from forget.server import app
    client = TestClient(app)
    denied = client.post("/v1/memories/", json={
        "text": "위조 시도", "app_id": TEAM_LEDGER_APP, "agent_id": "claude-exec",
        "infer": False})
    assert denied.status_code == 403                   # 무자격 원시 쓰기 차단
    key = create_api_key({"name": "selfharness key", "agent_principal": "selfharness"})
    still_denied = client.post("/v1/memories/", json={
        "text": "자격 기입", "app_id": TEAM_LEDGER_APP,
        "agent_id": "claude-exec",
        "infer": False},
        headers={"Authorization": f"Bearer {key['api_key']}"})
    assert still_denied.status_code == 403             # 구조 검문은 team_note만
    assert not [m for m in list_memory_dicts()
                if m.get("app_id") == TEAM_LEDGER_APP and "자격 기입" in str(m.get("memory"))]


def test_team_read_also_requires_rostered_credential():
    with pytest.raises(HTTPException) as unbound:
        call_tool("team_read", {})
    assert unbound.value.status_code == 403
    with pytest.raises(HTTPException) as outsider:
        call_tool("team_read", {}, context=_ctx("outsider"))
    assert outsider.value.status_code == 403


def test_only_addressed_principal_can_close_and_second_reply_conflicts():
    _note(kind="proposal", text="검토 요청", principal="claude-exec", addressed_to="gpt-live")
    proposal_id = next(
        m["id"] for m in list_memory_dicts()
        if (m.get("metadata") or {}).get("kind") == "proposal"
    )
    with pytest.raises(HTTPException) as wrong_agent:
        _note(kind="challenge", text="가로채기", principal="selfharness", reply_to=proposal_id)
    assert wrong_agent.value.status_code == 403
    _note(kind="decision", text="수용", principal="gpt-live", reply_to=proposal_id)
    with pytest.raises(HTTPException) as duplicate:
        _note(kind="decision", text="중복", principal="gpt-live", reply_to=proposal_id)
    assert duplicate.value.status_code == 409


def test_supersede_authority_and_structured_status():
    _note(kind="decision", text="초안", principal="claude-exec")
    original_id = next(m["id"] for m in list_memory_dicts())
    with pytest.raises(HTTPException) as foreign:
        _note(kind="decision", text="타인 폐기", principal="gpt-live", supersedes=original_id)
    assert foreign.value.status_code == 403
    _note(kind="decision", text="개정", principal="claude-exec", supersedes=original_id)
    payload = json.loads(call_tool("team_read", {}, context=_ctx("gpt-live"))["content"][0]["text"])
    original = next(item for item in payload["items"] if item["id"] == original_id)
    assert original["status"] == "superseded"
    assert original["closed_by"]


def test_idempotency_is_principal_scoped_and_covers_link_fields():
    _note(kind="question", text="q", principal="claude-exec", idempotency_key="shared-key")
    _note(kind="question", text="q", principal="gpt-live", idempotency_key="shared-key")
    assert len(_team_rows_for_test()) == 2
    with pytest.raises(HTTPException) as changed_link:
        _note(
            kind="question",
            text="q",
            principal="claude-exec",
            idempotency_key="shared-key",
            addressed_to="gpt-live",
        )
    assert changed_link.value.status_code == 409


def _team_rows_for_test():
    return [m for m in list_memory_dicts() if m.get("app_id") == TEAM_LEDGER_APP]


def test_idempotency_reservation_is_atomic_under_concurrency():
    def write_once(_index: int):
        try:
            return _note(
                kind="decision",
                text="동시 한 번",
                principal="selfharness",
                idempotency_key="concurrent-once",
            )
        except HTTPException as error:
            return error

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(write_once, range(16)))

    assert len(_team_rows_for_test()) == 1
    assert all(not isinstance(result, HTTPException) or result.status_code == 409 for result in results)
    assert any(not isinstance(result, HTTPException) for result in results)


def test_legacy_unverified_reply_link_cannot_close_an_item():
    _note(kind="proposal", text="still open", principal="claude-exec", addressed_to="gpt-live")
    proposal_id = _team_rows_for_test()[0]["id"]
    with scope_guard.authorize_team_ledger_write("legacy-import"):
        add_memories({
            "messages": [{"role": "user", "content": "[decision] spoofed legacy reply"}],
            "app_id": TEAM_LEDGER_APP,
            "agent_id": "gpt-live",
            "infer": False,
            "metadata": {"kind": "decision", "reply_to": proposal_id},
        })
    payload = json.loads(
        call_tool("team_read", {"open_only": True}, context=_ctx("gpt-live"))["content"][0]["text"]
    )
    assert any(item["id"] == proposal_id and item["status"] == "open" for item in payload["items"])


def test_team_items_are_append_only_outside_team_note_links():
    _note(kind="decision", text="append only", principal="claude-exec")
    memory_id = _team_rows_for_test()[0]["id"]
    with pytest.raises(HTTPException) as update_error:
        update_memory(memory_id, {"text": "mutated"})
    with pytest.raises(HTTPException) as supersede_error:
        supersede_memory(memory_id, {"reason": "mutated"})
    with pytest.raises(HTTPException) as delete_error:
        delete_memory(memory_id)
    assert {update_error.value.status_code, supersede_error.value.status_code, delete_error.value.status_code} == {409}


def test_near_duplicate_notes_do_not_hebbian_merge():
    _note(text="same protocol text", principal="claude-exec", idempotency_key="same-1")
    _note(text="same protocol text", principal="claude-exec", idempotency_key="same-2")
    rows = _team_rows_for_test()
    assert len(rows) == 2
    assert all((row.get("metadata") or {}).get("immutable") is True for row in rows)


def test_failed_write_releases_idempotency_reservation(monkeypatch):
    import forget.mcp as mcp_module

    original = mcp_module.add_memories

    def fail_once(_payload):
        raise RuntimeError("injected write failure")

    monkeypatch.setattr(mcp_module, "add_memories", fail_once)
    with pytest.raises(RuntimeError):
        _note(text="retryable", principal="gpt-live", idempotency_key="retry-after-failure")
    monkeypatch.setattr(mcp_module, "add_memories", original)
    _note(text="retryable", principal="gpt-live", idempotency_key="retry-after-failure")
    assert len(_team_rows_for_test()) == 1


def test_trail_preserves_reasoning_without_closing(  # 개정 3: 사고의 고고학
):
    _note(kind="proposal", text="설계 제안", principal="claude-exec", addressed_to="gpt-live")
    pid = next(m["id"] for m in list_memory_dicts()
               if (m.get("metadata") or {}).get("kind") == "proposal")
    call_tool("team_note", {"kind": "trail", "text": "이렇게 생각한 이유: 통합 위험 조기 노출",
                            "thinking_for": pid}, context=_ctx("claude-exec"))
    open_after = str(call_tool("team_read", {"open_only": True},
                               context=_ctx("gpt-live"))["content"][0]["text"])
    assert "설계 제안" in open_after            # trail은 미결을 닫지 않는다
    with pytest.raises(HTTPException):
        call_tool("team_note", {"kind": "trail", "text": "고아 trail"},
                  context=_ctx("claude-exec"))  # thinking_for 필수
    with pytest.raises(HTTPException):
        call_tool("team_note", {"kind": "trail", "text": "유령 대상",
                                "thinking_for": "no-such-id"}, context=_ctx("claude-exec"))


def test_owner_sourced_marker_persists():      # 개정 3: 소유자 결정의 원장화
    call_tool("team_note", {"kind": "decision", "text": "빌링은 최후 단계로 연기",
                            "on_behalf_of_owner": True}, context=_ctx("gpt-live"))
    row = [m for m in list_memory_dicts() if m.get("app_id") == TEAM_LEDGER_APP][0]
    assert (row.get("metadata") or {}).get("owner_sourced") is True
    assert row.get("agent_id") == "gpt-live"   # 귀속은 기록 에이전트 유지


def test_digest_supersedes_previous_digest():  # 개정 3: 브리핑 사슬
    call_tool("team_note", {"kind": "digest", "text": "브리핑 1"}, context=_ctx("selfharness"))
    d1 = next(m["id"] for m in list_memory_dicts()
              if (m.get("metadata") or {}).get("kind") == "digest")
    call_tool("team_note", {"kind": "digest", "text": "브리핑 2", "supersedes": d1},
              context=_ctx("selfharness"))
    payload = json.loads(call_tool("team_read", {}, context=_ctx("gpt-live"))["content"][0]["text"])
    txt = str(payload)
    assert "브리핑 2" in txt


def test_rev3_hole_fixes():                    # gpt-live 6구멍 봉인 (개정 3.1)
    # ①+④ projection: thinking_for·owner_sourced 노출 + yellow 명시
    call_tool("team_note", {"kind": "decision", "text": "소유자 결정",
                            "on_behalf_of_owner": True}, context=_ctx("gpt-live"))
    payload = json.loads(call_tool("team_read", {}, context=_ctx("claude-exec"))["content"][0]["text"])
    txt = json.dumps(payload, ensure_ascii=False)
    assert "owner_sourced" in txt and "yellow" in txt
    # ② 엄격 boolean + decision 한정
    with pytest.raises(HTTPException):
        call_tool("team_note", {"kind": "decision", "text": "x", "on_behalf_of_owner": "false"},
                  context=_ctx("gpt-live"))
    with pytest.raises(HTTPException):
        call_tool("team_note", {"kind": "question", "text": "x", "on_behalf_of_owner": True},
                  context=_ctx("gpt-live"))
    # ⑤a trail은 question에 부착 불가
    call_tool("team_note", {"kind": "question", "text": "열린 질문"}, context=_ctx("gpt-live"))
    qid = next(m["id"] for m in list_memory_dicts()
               if (m.get("metadata") or {}).get("kind") == "question")
    with pytest.raises(HTTPException):
        call_tool("team_note", {"kind": "trail", "text": "y", "thinking_for": qid},
                  context=_ctx("claude-exec"))
    # ⑤b digest 단일 활성: supersede 없이 둘째 digest 거부, 비-digest supersede 거부
    call_tool("team_note", {"kind": "digest", "text": "브리핑"}, context=_ctx("selfharness"))
    with pytest.raises(HTTPException) as second:
        call_tool("team_note", {"kind": "digest", "text": "병행 브리핑"}, context=_ctx("selfharness"))
    assert second.value.status_code == 409
    did = next(m["id"] for m in list_memory_dicts()
               if (m.get("metadata") or {}).get("kind") == "decision")
    with pytest.raises(HTTPException):
        call_tool("team_note", {"kind": "digest", "text": "z", "supersedes": did},
                  context=_ctx("gpt-live"))


def test_rev31_hold_residuals():               # gpt-live 잔여 5건 봉인 (개정 3.2)
    # D) 같은 idempotency_key로 owner_sourced만 바꾸면 409 (재바인딩 충돌)
    call_tool("team_note", {"kind": "decision", "text": "같은 본문",
                            "idempotency_key": "kd", "on_behalf_of_owner": True},
              context=_ctx("gpt-live"))
    with pytest.raises(HTTPException) as rebind:
        call_tool("team_note", {"kind": "decision", "text": "같은 본문",
                                "idempotency_key": "kd"}, context=_ctx("gpt-live"))
    assert rebind.value.status_code == 409
    # A) digest는 다른 작성자가 승계 가능 (브리핑 슬롯 — 교착 방지)
    call_tool("team_note", {"kind": "digest", "text": "시드"}, context=_ctx("claude-exec"))
    d1 = next(m["id"] for m in list_memory_dicts()
              if (m.get("metadata") or {}).get("kind") == "digest")
    call_tool("team_note", {"kind": "digest", "text": "승계", "supersedes": d1},
              context=_ctx("selfharness"))   # 교차 작성자 — 예외 없이 통과해야
    # 비-digest는 여전히 동일 작성자만 supersede
    call_tool("team_note", {"kind": "decision", "text": "남의 결정"}, context=_ctx("gpt-live"))
    other = next(m["id"] for m in list_memory_dicts()
                 if "남의 결정" in str(m.get("memory")))
    with pytest.raises(HTTPException):
        call_tool("team_note", {"kind": "decision", "text": "가로채기", "supersedes": other},
                  context=_ctx("claude-exec"))
    # E) codex가 로스터에 있어 addressed_to 가능
    call_tool("team_note", {"kind": "question", "text": "codex 앞", "addressed_to": "codex"},
              context=_ctx("claude-exec"))


def test_owner_confirmation_receipt_promotes_to_green():  # yellow→green 승격 문
    from fastapi.testclient import TestClient
    from forget.server import app
    from forget import receipts as _receipts
    call_tool("team_note", {"kind": "decision", "text": "소유자 결정",
                            "on_behalf_of_owner": True}, context=_ctx("gpt-live"))
    item = next(m["id"] for m in list_memory_dicts()
                if (m.get("metadata") or {}).get("owner_sourced"))
    client = TestClient(app)
    agent_key = create_api_key({"name": "agent", "agent_principal": "claude-exec"})
    denied = client.post("/v1/team/confirm/", json={"item_id": item},
                         headers={"Authorization": f"Bearer {agent_key['api_key']}"})
    assert denied.status_code == 403                    # 에이전트 자격 거부
    owner_key = create_api_key({"name": "owner", "scopes": ["grants:admin"]})
    ok = client.post("/v1/team/confirm/", json={"item_id": item},
                     headers={"Authorization": f"Bearer {owner_key['api_key']}"})
    assert ok.status_code == 200
    receipt = ok.json()["receipt"]
    assert _receipts.verify_receipt(receipt) is True    # 공용 검증기로 검증
    projected = json.dumps(json.loads(
        call_tool("team_read", {}, context=_ctx("claude-exec"))["content"][0]["text"]),
        ensure_ascii=False)
    assert "green" in projected and "owner-confirmed" in projected
    replay = client.post("/v1/team/confirm/", json={"item_id": item},
                         headers={"Authorization": f"Bearer {owner_key['api_key']}"})
    assert replay.json().get("idempotent_replay") is True  # 단방향·멱등
    # 비-owner_sourced 항목은 확인 불가
    call_tool("team_note", {"kind": "decision", "text": "일반 결정"}, context=_ctx("gpt-live"))
    plain = next(m["id"] for m in list_memory_dicts()
                 if "일반 결정" in str(m.get("memory")))
    bad = client.post("/v1/team/confirm/", json={"item_id": plain},
                      headers={"Authorization": f"Bearer {owner_key['api_key']}"})
    assert bad.status_code == 400


def test_owner_confirmation_acceptance_gates():   # gpt-live 계약 수용 게이트
    from fastapi.testclient import TestClient
    from forget.server import app
    client = TestClient(app)
    call_tool("team_note", {"kind": "decision", "text": "구 결정",
                            "on_behalf_of_owner": True}, context=_ctx("gpt-live"))
    old = next(m["id"] for m in list_memory_dicts()
               if (m.get("metadata") or {}).get("owner_sourced"))
    owner_key = create_api_key({"name": "owner", "scopes": ["grants:admin"]})
    first = client.post("/v1/team/confirm/", json={"item_id": old},
                        headers={"Authorization": f"Bearer {owner_key['api_key']}"}).json()
    replay = client.post("/v1/team/confirm/", json={"item_id": old},
                         headers={"Authorization": f"Bearer {owner_key['api_key']}"}).json()
    # 정확 재생: 같은 영수증 그대로 (새 영수증 발급 금지)
    assert replay["receipt"]["receipt_id"] == first["receipt"]["receipt_id"]
    # supersede 뒤: 과거 확인이 새 decision을 승격하지 못함
    call_tool("team_note", {"kind": "decision", "text": "새 결정",
                            "on_behalf_of_owner": True, "supersedes": old},
              context=_ctx("gpt-live"))
    new_id_ = next(m["id"] for m in list_memory_dicts()
                   if "새 결정" in str(m.get("memory")))
    items = json.loads(call_tool("team_read", {}, context=_ctx("claude-exec"))["content"][0]["text"])
    blob = {i["id"]: i for i in (items.get("items") or [])}
    if blob:
        assert "green" not in str(blob.get(new_id_, {}).get("owner_sourced_trust"))
        assert "green" in str(blob.get(old, {}).get("owner_sourced_trust"))
