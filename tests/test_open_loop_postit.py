"""Open-loop post-its: aged unverified action claims surface at session start.

Regression guard for incident #0 (2026-07-22): "문의 발송" was recorded on
7/15 and sat unchallenged for a week — an open loop nobody chased — until the
agent built a false "reply pending → send a reminder" chain on top of it.
The post-it makes staleness itself visible: an agent-reported completion
claim (modality "reported") that stays open past MEM1_OPEN_LOOP_DAYS shows
up in the session-start capsule until the loop is closed by correction.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from forget import db as app_db
from forget.db import get_db, init_db
from forget.server import app

_DB_COUNTER = 0
USER = f"postit-user-{uuid.uuid4().hex[:8]}"
APP = "postit-app"
MCP_PATH = f"/mcp/{APP}/http/{USER}"

STALE_CLAIM = "오버엣지 지분/IP 조건 문의 발송했음."
FRESH_CLAIM = "YC 원서 초안 제출했음."


def _client() -> TestClient:
    global _DB_COUNTER
    _DB_COUNTER += 1
    path = Path(f"/tmp/mem1-postit-test-{os.getpid()}-{_DB_COUNTER}.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()
    return TestClient(app, base_url="http://testserver")


def _call(client: TestClient, name: str, arguments: dict, request_id: int = 1) -> dict:
    response = client.post(
        MCP_PATH,
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert response.status_code == 200, response.text
    return json.loads(response.json()["result"]["content"][0]["text"])


def _capsule_text(client: TestClient) -> str:
    result = _call(
        client,
        "prepare_context_autopilot",
        {"query": "session startup — active tasks, open loops", "include_debug": False},
        request_id=9,
    )
    return str(result.get("capsule_text") or "")


def _backdate_reported_claim(claim_text: str, days: int) -> None:
    stale = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db() as conn:
        conn.execute(
            "UPDATE claims SET created_at = ? WHERE modality = 'reported' AND claim_text = ?",
            (stale, claim_text),
        )


def test_aged_reported_claim_surfaces_and_correction_clears_it() -> None:
    client = _client()
    _call(client, "add_memory", {"text": STALE_CLAIM, "infer": False})
    _call(client, "add_memory", {"text": FRESH_CLAIM, "infer": False}, request_id=2)
    _backdate_reported_claim(STALE_CLAIM, days=5)

    capsule = _capsule_text(client)
    assert "열린 루프" in capsule, capsule
    assert STALE_CLAIM[:20] in capsule, capsule
    # fresh claims are not nagging material — only aged ones surface
    assert FRESH_CLAIM[:10] not in capsule, capsule

    # closing the loop by correction (supersede) removes the post-it
    results = _call(client, "search_memories", {"query": "오버엣지 문의 발송", "top_k": 1}, request_id=3)["results"]
    assert results
    _call(client, "supersede_memory", {"memory_id": results[0]["id"], "reason": "발송된 적 없음 — 사용자 정정"}, request_id=4)
    capsule_after = _capsule_text(client)
    assert STALE_CLAIM[:20] not in capsule_after, capsule_after


def test_confirm_clears_postit_and_promotes_to_green() -> None:
    # A TRUE unverified claim must not require supersede (="it was wrong") to
    # silence its post-it — confirm attaches the receipt and promotes it.
    client = _client()
    _call(client, "add_memory", {"text": STALE_CLAIM, "infer": False})
    _backdate_reported_claim(STALE_CLAIM, days=5)
    assert "열린 루프" in _capsule_text(client)

    results = _call(client, "search_memories", {"query": "오버엣지 문의 발송", "top_k": 1}, request_id=3)["results"]
    memory_id = results[0]["id"]

    # no receipt, no confirmation
    response = client.post(
        MCP_PATH,
        json={"jsonrpc": "2.0", "id": 4, "method": "tools/call",
              "params": {"name": "confirm_memory", "arguments": {"memory_id": memory_id}}},
    )
    assert "evidence" in response.text

    _call(client, "confirm_memory", {"memory_id": memory_id, "evidence": "발송 메일이 보낸편지함에서 확인됨"}, request_id=5)
    assert STALE_CLAIM[:20] not in _capsule_text(client)
    confirmed = _call(client, "search_memories", {"query": "오버엣지 문의 발송", "top_k": 1}, request_id=6)["results"][0]
    assert confirmed["trust"]["light"] == "green"
    assert "verified" in confirmed["trust"]["note"]
    with get_db() as conn:
        row = conn.execute("SELECT modality FROM claims WHERE memory_id = ?", (memory_id,)).fetchone()
    assert row["modality"] == "asserted"


def test_korean_negation_sets_negative_polarity() -> None:
    client = _client()
    _call(client, "add_memory", {"text": "오버엣지 문의는 발송된 적 없음.", "infer": False})
    with get_db() as conn:
        row = conn.execute("SELECT polarity FROM claims ORDER BY created_at DESC LIMIT 1").fetchone()
    assert row["polarity"] == "negative"


def test_parallel_tracks_keep_shadowed_task_visible() -> None:
    # Taste-test finding 2026-07-23: the newest task epoch hijacked the
    # morning capsule; other in-flight tasks (the actual deadline) vanished.
    client = _client()
    _call(client, "record_task_state", {
        "task_id": "deadline-task",
        "status": "in_progress",
        "summary": "마감 태스크",
        "next_actions": ["수요일 아침: 계정 생성"],
    })
    _call(client, "record_task_state", {
        "task_id": "late-night-task",
        "status": "in_progress",
        "summary": "밤샘 기술 태스크",
        "next_actions": ["다음 조각 구현"],
    }, request_id=2)
    capsule = _capsule_text(client)
    # 불변식: 어느 쪽이 "현재 목표"로 뽑히든, 다른 활성 스레드가 병행 트랙으로 보인다
    assert "병행 트랙" in capsule, capsule
    assert "마감 태스크" in capsule or "deadline-task" in capsule, capsule
    assert "밤샘 기술 태스크" in capsule or "late-night-task" in capsule, capsule


def test_github_route_does_not_fall_back_to_workspace_search() -> None:
    # Dogfood finding 2026-07-26: a next action to monitor GitHub PR #92 was
    # routed to web_or_github, but its first tool hint searched the local repo.
    client = _client()
    _call(client, "record_task_state", {
        "task_id": "oss:dgx-spark-playbooks-92",
        "status": "in_progress",
        "summary": "DGX Spark playbooks PR #92 is open and merge-clean.",
        "next_actions": ["Monitor GitHub PR #92 and respond to maintainer feedback."],
        "evidence_files": ["forget/store.py"],
    })
    result = _call(client, "prepare_context_autopilot", {
        "query": "What is the current DGX Spark open-source contribution and next action?",
        "include_debug": False,
    }, request_id=2)
    capsule = result["use_now"]

    assert capsule["source_route"]["source_class"] == "web_or_github"
    assert capsule["source_route"]["required_tools"] == ["web", "mcp__github"]
    assert capsule["action_hints"] == []


def test_local_repository_wording_keeps_workspace_route() -> None:
    client = _client()
    _call(client, "record_task_state", {
        "task_id": "oss:local-review",
        "status": "in_progress",
        "summary": "Review the local repository implementation.",
        "next_actions": ["Inspect forget/store.py before changing the routing fallback."],
    })
    result = _call(client, "prepare_context_autopilot", {
        "query": "Continue the local repository implementation review.",
        "include_debug": False,
    }, request_id=2)
    capsule = result["use_now"]

    assert capsule["source_route"]["source_class"] == "repo_inspection"
    assert capsule["action_hints"]
    assert capsule["action_hints"][0]["source"] == "query_keyword_fallback"


def test_goals_render_as_why_layer_not_parallel_tracks() -> None:
    # goal: 접두 task_state는 "상위 목표" 줄로 — 병행 트랙(작업 항목)과 분리
    client = _client()
    _call(client, "record_task_state", {
        "task_id": "goal:yc-fall-2026",
        "status": "in_progress",
        "summary": "YC Fall 2026 합격",
        "next_actions": ["7/27 제출"],
    })
    _call(client, "record_task_state", {
        "task_id": "work-task",
        "status": "in_progress",
        "summary": "실무 태스크",
        "next_actions": ["다음 조각"],
    }, request_id=2)
    capsule = _capsule_text(client)
    assert "상위 목표" in capsule and "YC Fall 2026 합격" in capsule and "7/27 제출" in capsule, capsule
    # 병행 트랙에 goal:이 섞이면 안 됨
    parallel_line = next((line for line in capsule.splitlines() if line.startswith("병행 트랙")), "")
    assert "goal:" not in parallel_line, capsule


def test_no_reported_claims_means_no_postit_line() -> None:
    client = _client()
    _call(client, "add_memory", {"text": "사용자는 로컬-퍼스트 아키텍처를 선호함.", "infer": False})
    capsule = _capsule_text(client)
    assert "열린 루프" not in capsule, capsule


def test_stance_renders_as_posture_line_when_fresh() -> None:
    # Assistant-authored feature (user zero, 2026-07-25): the capsule restores
    # task state but not posture — a hand that wakes as a function needs to be
    # told "remember who you were". stance:* task_states render as a 자세 line.
    client = _client()
    _call(client, "record_task_state", {
        "task_id": "stance:assistant",
        "status": "in_progress",
        "summary": "사관으로 깨어날 것 — 비서 아님. 아름다운 이야기일수록 영수증.",
    })
    _call(client, "record_task_state", {
        "task_id": "real-work",
        "status": "in_progress",
        "summary": "실무 태스크",
        "next_actions": ["다음 조각"],
    }, request_id=2)
    capsule = _capsule_text(client)
    assert "자세: 사관으로 깨어날 것" in capsule, capsule
    # 자세는 작업 항목이 아니다: 병행 트랙·현재 목표를 납치하면 안 됨
    assert "현재 목표: 실무 태스크" in capsule or "실무 태스크" in capsule.split("자세:")[0], capsule
    parallel_line = next((line for line in capsule.splitlines() if line.startswith("병행 트랙")), "")
    assert "stance:" not in parallel_line, capsule


def test_stale_stance_does_not_render() -> None:
    # A stale stance would fossilize a dead persona — worse than waking blank.
    client = _client()
    _call(client, "record_task_state", {
        "task_id": "stance:assistant",
        "status": "in_progress",
        "summary": "8일 전의 자세 — 렌더되면 안 됨",
    })
    stale = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db() as conn:
        # the task listing reads updated_at from workspace_epochs.valid_from
        conn.execute(
            "UPDATE workspace_epochs SET valid_from = ? WHERE task_id LIKE 'stance:%'",
            (stale,),
        )
        conn.execute(
            "UPDATE claims SET created_at = ?, updated_at = ? WHERE subject_key LIKE 'task:stance:%'",
            (stale, stale),
        )
    capsule = _capsule_text(client)
    assert "자세:" not in capsule, capsule


def test_capsule_layers_honor_requesting_scope() -> None:
    # Demo-taste find (2026-07-26, pre-0.3.1): a demo-user capsule rendered
    # the real user's goals and the assistant's stance — cross-scope leak
    # that would have put private strategy on a screen recording. Every
    # capsule layer that lists the ledger must honor the requesting scope.
    client = _client()
    # 실사용자 스코프의 목표·자세·병행·열린루프
    _call(client, "record_task_state", {
        "task_id": "goal:private-strategy", "status": "in_progress",
        "summary": "비공개 전략 목표", "next_actions": ["비밀 이정표"],
    })
    _call(client, "record_task_state", {
        "task_id": "stance:assistant", "status": "in_progress",
        "summary": "비공개 자세 — 유출 금지",
    }, request_id=2)
    _call(client, "record_task_state", {
        "task_id": "private-work", "status": "in_progress",
        "summary": "비공개 병행 작업", "next_actions": ["다음 조각"],
    }, request_id=3)
    _call(client, "add_memory", {"text": "보고서 발송했음.", "infer": False}, request_id=4)
    _backdate_reported_claim("보고서 발송했음.", days=5)

    # 다른 스코프(demo)에서 캡슐 요청
    other_path = f"/mcp/other-app/http/other-user-{uuid.uuid4().hex[:6]}"
    response = client.post(other_path, json={
        "jsonrpc": "2.0", "id": 9, "method": "tools/call",
        "params": {"name": "prepare_context_autopilot",
                   "arguments": {"query": "session startup", "include_debug": False}},
    })
    capsule = json.loads(response.json()["result"]["content"][0]["text"]).get("capsule_text") or ""
    assert "비공개 전략 목표" not in capsule, capsule
    assert "비공개 자세" not in capsule, capsule
    assert "비공개 병행 작업" not in capsule, capsule
    assert "보고서 발송했음" not in capsule, capsule

    # 원 스코프에서는 전부 보여야 함 (회귀 방지)
    own = _capsule_text(client)
    assert "비공개 전략 목표" in own and "자세: 비공개 자세" in own, own


def test_context_outcome_feedback_accepts_claim_backed_result_ids() -> None:
    # Live Codex dogfood finding: capsule provenance exposes task states as
    # claim:<uuid>, but record_context_outcome only matched memories.id. The
    # returned ID was warned as unknown and never reached the ranking loop.
    client = _client()
    state = _call(client, "record_task_state", {
        "task_id": "oss:quack-cutlass",
        "status": "in_progress",
        "summary": "QuACK Cutlass compatibility task",
        "next_actions": ["Inspect the published pull request."],
    })
    claim_result_id = f"claim:{state['claim_id']}"

    def task_score(request_id: int) -> float:
        result = _call(client, "search_memories", {
            "query": "QuACK Cutlass compatibility task",
            "top_k": 10,
            "threshold": 0.0,
        }, request_id=request_id)
        match = next(item for item in result["results"] if item["id"] == claim_result_id)
        return float(match["score"])

    score_before = task_score(request_id=2)
    context = _call(client, "prepare_context_autopilot", {
        "query": "Restore the QuACK Cutlass compatibility task.",
        "top_k": 10,
        "threshold": 0.0,
        "include_debug": True,
    }, request_id=3)
    assert claim_result_id in context["evidence"]["memory_ids"]

    outcome = _call(client, "record_context_outcome", {
        "trace_id": context["context_trace_id"],
        "harmful_memory_ids": [claim_result_id],
        "first_action_productive": False,
        "failure_stage": "selection_failure",
    }, request_id=4)

    assert outcome["unmatched_memory_ids"] == []
    assert outcome["harmful_memory_ids"] == [claim_result_id]
    assert outcome["warnings"] == []
    with get_db() as conn:
        feedback = conn.execute(
            "SELECT feedback, metadata FROM feedback WHERE memory_id = ?",
            (claim_result_id,),
        ).fetchone()
    assert feedback is not None and feedback["feedback"] == "NEGATIVE"
    assert json.loads(feedback["metadata"])["source"] == "context_outcome"
    assert task_score(request_id=5) == round(score_before - 0.15, 4)
