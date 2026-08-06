"""Hook logic under pytest — pipe tests alone don't guard regressions.

The hooks are standalone scripts (no package import), so they load via
importlib; the network boundary (_rpc) and state dir are stubbed. Tonight's
threshold bug (conflict pairs silently gated out by the plain-recall
threshold) is exactly the class these tests pin down.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parents[1] / "hooks"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, HOOKS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_main(module, hook_input: dict, monkeypatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(hook_input)))
    module.main()


# --- forget_turnrecall -------------------------------------------------------

def _recall_module(monkeypatch, tmp_path, results, memories_by_id=None):
    module = _load("forget_turnrecall")
    monkeypatch.setattr(module, "STATE_DIR", str(tmp_path))

    def fake_rpc(name, arguments, timeout=5):
        if name == "search_memories":
            return {"results": results}
        if name == "get_memory":
            return (memories_by_id or {})[arguments["memory_id"]]
        raise AssertionError(name)

    monkeypatch.setattr(module, "_rpc", fake_rpc)
    return module


def test_conflict_pair_uses_looser_threshold(monkeypatch, tmp_path, capsys):
    # 0.35 clears the conflict gate (0.32) but NOT the plain gate (0.45) —
    # the exact shape of tonight's silent-alert bug.
    results = [
        {"id": "new-1", "score": 0.35, "memory": "정정: 발송된 적 없음",
         "metadata": {"supersedes": ["old-1"]}, "trust": {"light": "yellow"}},
        {"id": "plain-1", "score": 0.35, "memory": "평범한 기억", "metadata": {}},
    ]
    memories = {
        "old-1": {"memory": "문의 발송했음", "metadata": {}},
        "new-1": {"memory": "정정: 발송된 적 없음", "metadata": {}},
    }
    module = _recall_module(monkeypatch, tmp_path, results, memories)
    _run_main(module, {"session_id": "s1", "prompt": "문의 보냈던가? 확인 필요"}, monkeypatch)
    out = capsys.readouterr().out
    assert "충돌지대" in out
    assert "(현재) 정정" in out and "(red/구본) 문의 발송했음" in out
    assert "평범한 기억" not in out  # plain 0.35 < 0.45 → filtered


def test_capture_pointers_never_recalled(monkeypatch, tmp_path, capsys):
    results = [{"id": "cap-1", "score": 0.9, "memory": "세션 캡처 (SessionEnd)...",
                "metadata": {"hook": "SessionEnd"}}]
    module = _recall_module(monkeypatch, tmp_path, results)
    _run_main(module, {"session_id": "s2", "prompt": "지난 세션에서 뭐 했지?"}, monkeypatch)
    assert capsys.readouterr().out == ""


def test_repeat_suppression_and_ledger_extension(monkeypatch, tmp_path, capsys):
    results = [{"id": "m-1", "score": 0.6, "memory": "로컬-퍼스트 아키텍처 선호",
                "metadata": {}, "trust": {"light": "green"}}]
    module = _recall_module(monkeypatch, tmp_path, results)
    # 캡슐 제안 장부가 있으면 회상 주입이 장부를 확장해 outcome 측정 대상이 된다
    (tmp_path / "s3.json").write_text(json.dumps(
        {"trace_id": "t-1", "memory_ids": ["cap-mem"], "capsule_lines": ["현재 목표: X"]}), encoding="utf-8")
    _run_main(module, {"session_id": "s3", "prompt": "아키텍처 어떻게 가기로 했지?"}, monkeypatch)
    assert "(green) 로컬-퍼스트" in capsys.readouterr().out
    ledger = json.loads((tmp_path / "s3.json").read_text(encoding="utf-8"))
    assert "m-1" in ledger["memory_ids"] and any("로컬-퍼스트" in line for line in ledger["capsule_lines"])
    # 같은 세션 두 번째 턴 → 억제
    _run_main(module, {"session_id": "s3", "prompt": "아키텍처 어떻게 가기로 했지?"}, monkeypatch)
    assert capsys.readouterr().out == ""


def test_task_state_claims_never_recalled(monkeypatch, tmp_path, capsys):
    # F2/C2 (cycle 18): fluid-layer task ledger rows farm phrase_bonus with
    # long claim texts and outrank topical memories. They travel via
    # get_task_state/capsule only — turn recall must skip them even at high
    # score, while a plain memory in the same result set still surfaces.
    results = [
        {"id": "claim:c-1", "score": 0.61,
         "memory": "Task heartbeat is in_progress. 상위 목표: devloop...",
         "metadata": {"source": "claim_ledger", "assertion_kind": "task_state",
                      "task_state": {"task_id": "heartbeat"}},
         "trust": {"light": "yellow", "kind": "task_state"}},
        {"id": "m-2", "score": 0.5, "memory": "임베더는 e5로 교체 예정",
         "metadata": {}, "trust": {"light": "green"}},
    ]
    module = _recall_module(monkeypatch, tmp_path, results)
    _run_main(module, {"session_id": "s13", "prompt": "임베더 교체 계획이 뭐였지?"}, monkeypatch)
    out = capsys.readouterr().out
    assert "heartbeat" not in out
    assert "(green) 임베더는 e5로" in out
    # 장부에도 task 클레임은 오르지 않는다 — 억제 상태 오염 방지
    turns = json.loads((tmp_path / "s13.turns.json").read_text(encoding="utf-8"))
    assert turns["injected"] == ["m-2"]


# 아래 두 테스트의 점수는 합성값이 아니라 도그푸드 서버 context_traces에서 꺼낸
# 실측이다 (cycle 62). 동일 질의·동일 훅의 두 런이 top1 하나 때문에 주입 0 대 3으로
# 갈렸고, 그 top1은 양쪽 다 훅이 반드시 버리는 task_state claim이었다.
_C61_SCORES = (0.9172, 0.9149, 0.8967, 0.8696, 0.8519)   # 실측 주입 0 (평지 오판정)
_C62_SCORES = (1.0000, 0.9149, 0.8967, 0.8696, 0.8519)   # 실측 주입 3


def _claim_then_memories(scores):
    """[0]=task_state claim, 나머지=평범한 기억. 실측 배치를 그대로 재현."""
    head, *tail = scores
    results = [
        {"id": "claim:a6bb2d19", "score": head,
         "memory": "[devloop 사이클 61] ... 상위 목표: lmev2-credible-number ...",
         "metadata": {"source": "claim_ledger", "assertion_kind": "task_state",
                      "task_state": {"task_id": "devloop"}},
         "trust": {"light": "yellow", "kind": "task_state"}},
    ]
    for index, score in enumerate(tail):
        results.append({"id": f"m-{index}", "score": score,
                        "memory": f"[devloop] 사이클 4{index} 발견 — 관측 본문",
                        "metadata": {}, "trust": {"light": "yellow"}})
    return results


def test_flatness_ignores_candidates_that_can_never_be_injected(monkeypatch, tmp_path, capsys):
    """평탄도 봉우리가 주입 불가능한 후보면 안 된다 (cycle 62 실측 수리).

    c61 런 실측: top1(task_state claim) 0.9172 − 중앙값 0.8967 = 0.0205 < 0.03 →
    전체 결과로 재면 '평지'라 자격 있는 기억 4개가 전량 침묵했다. 자격 후보
    4개만으로 재면 0.9149 − 0.8696 = 0.0453 ≥ 0.03 → 봉우리가 있다.
    """
    module = _recall_module(monkeypatch, tmp_path, _claim_then_memories(_C61_SCORES))
    _run_main(module, {"session_id": "s-c61", "prompt": "devloop 사이클을 정확히 한 바퀴 실행하라"}, monkeypatch)
    out = capsys.readouterr().out
    assert "회상" in out, "자격 후보 분포엔 봉우리가 있으므로 침묵해선 안 된다"
    assert "claim:a6bb2d19" not in out and "상위 목표" not in out  # claim 자체는 여전히 미주입
    turns = json.loads((tmp_path / "s-c61.turns.json").read_text(encoding="utf-8"))
    assert turns["injected"] == ["m-0", "m-1", "m-2"]  # MAX_RECALLS=3


def test_fresh_claim_peak_does_not_change_injection_count(monkeypatch, tmp_path, capsys):
    """장부 신선도 결합 해제: claim 점수가 0.9172든 1.0이든 주입 수가 같아야 한다.

    수리 전에는 claim이 방금 쓰여 1.0으로 포화하면 주입 3, 하루 묵어 0.9172면
    주입 0이었다 — 푸시 회상의 on/off가 루프 자신의 task_state 신선도에 결합.
    """
    counts = []
    for tag, scores in (("s-a", _C61_SCORES), ("s-b", _C62_SCORES)):
        module = _recall_module(monkeypatch, tmp_path, _claim_then_memories(scores))
        _run_main(module, {"session_id": tag, "prompt": "devloop 사이클을 정확히 한 바퀴 실행하라"}, monkeypatch)
        capsys.readouterr()
        counts.append(len(json.loads((tmp_path / f"{tag}.turns.json").read_text(encoding="utf-8"))["injected"]))
    assert counts == [3, 3], f"claim 신선도가 주입 수를 갈랐다: {counts}"


def test_genuinely_flat_eligible_distribution_still_silences(monkeypatch, tmp_path, capsys):
    """수리가 평탄도 게이트를 무력화하지 않았음을 고정 — 자격 후보끼리 평지면 침묵.

    (자[尺]는 그대로다: FLATNESS_MARGIN·SCORE_THRESHOLD 미변경.)
    """
    flat = [{"id": f"m-{i}", "score": score, "memory": f"무관한 기억 {i}",
             "metadata": {}, "trust": {"light": "yellow"}}
            for i, score in enumerate((0.62, 0.615, 0.61, 0.605, 0.60))]
    module = _recall_module(monkeypatch, tmp_path, flat)
    _run_main(module, {"session_id": "s-flat", "prompt": "프로토타입 어디까지 갔지?"}, monkeypatch)
    assert capsys.readouterr().out == ""


def test_few_eligible_candidates_disable_the_flatness_gate(monkeypatch, tmp_path, capsys):
    """수리의 알려진 경계를 **의도로 고정**한다 (cycle 62 검증에서 발견).

    분포를 자격 후보에서만 재기 때문에 `len(scores_all) >= 4`도 자격 후보 수로
    센다. top_k는 MAX_RECALLS+2=5뿐이라 무자격 후보가 2개면 자격 후보가 3개로
    떨어지고, 그 순간 평탄도 게이트는 **한 마디 없이 완전히 꺼진다** — 아래처럼
    자격 후보끼리 평지여도 전량 주입된다.

    실측 빈도는 0/27 trace(도그푸드 turn_recall 전량, 메타데이터 해석 기준)이고
    devloop 질의 4건이 자격 4개 = 최소 경계에 **정확히** 걸쳐 있다. 즉 지금은
    안 터지지만 무자격 후보 하나만 늘면 터진다. 이 테스트는 그 동작을 '알려진
    것'으로 만들어 두려는 것이고, 처치(top_k 인상 또는 최소 개수를 전체 후보로
    세기)는 자[尺]를 함께 바꾸지 않기 위해 다음 사이클로 미룬다.
    """
    results = [
        {"id": "claim:one", "score": 1.0, "memory": "장부 행 1",
         "metadata": {"assertion_kind": "task_state"}, "trust": {"light": "yellow"}},
        {"id": "cap-1", "score": 0.99, "memory": "세션 캡처 포인터",
         "metadata": {"hook": "session_capture"}, "trust": {"light": "yellow"}},
    ] + [{"id": f"m-{i}", "score": score, "memory": f"무관한 기억 {i}",
          "metadata": {}, "trust": {"light": "yellow"}}
         for i, score in enumerate((0.62, 0.615, 0.61))]
    module = _recall_module(monkeypatch, tmp_path, results)
    _run_main(module, {"session_id": "s-thin", "prompt": "프로토타입 어디까지 갔지?"}, monkeypatch)
    assert "회상" in capsys.readouterr().out, "자격 후보 3개 → 평탄도 게이트 미적용"
    turns = json.loads((tmp_path / "s-thin.turns.json").read_text(encoding="utf-8"))
    assert turns["injected"] == ["m-0", "m-1", "m-2"]


def test_slash_and_short_prompts_stay_silent(monkeypatch, tmp_path, capsys):
    module = _recall_module(monkeypatch, tmp_path, [{"id": "m", "score": 0.9, "memory": "x", "metadata": {}}])
    for prompt in ("/compact", "ㅇㅋ", "# Update Config Skill 문서..."):
        _run_main(module, {"session_id": "s4", "prompt": prompt}, monkeypatch)
        assert capsys.readouterr().out == ""


# --- forget_capture ----------------------------------------------------------

def _write_transcript(tmp_path) -> Path:
    lines = [
        {"type": "user", "timestamp": "2026-07-23T01:00:00Z",
         "message": {"role": "user", "content": "돌다리를 두드리자"}},
        {"type": "user", "timestamp": "2026-07-23T01:01:00Z",
         "message": {"role": "user", "content": "# Update Config Skill\n" + "긴 스킬 확장문 " * 100}},
        {"type": "user", "timestamp": "2026-07-23T01:02:00Z",
         "message": {"role": "user", "content": "[SYSTEM NOTIFICATION] ..."}},
        {"type": "assistant", "timestamp": "2026-07-23T01:03:00Z",
         "message": {"role": "assistant", "content": [{"type": "text", "text": "현재 목표: X 기준으로 진행"}]}},
    ]
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
    return path


def test_digest_filters_machine_payloads(tmp_path):
    module = _load("forget_capture")
    digest = module._digest(str(_write_transcript(tmp_path)))
    assert digest["counts"] == {"user": 3, "assistant": 1}
    assert digest["user_snippets"] == ["돌다리를 두드리자"]  # 스킬 확장문·시스템 알림 제외
    assert "현재 목표: X" in digest["assistant_blob"]


def test_outcome_only_at_session_end(monkeypatch, tmp_path):
    module = _load("forget_capture")
    monkeypatch.setattr(module, "STATE_DIR", str(tmp_path))
    calls = []
    monkeypatch.setattr(module, "_capture", lambda *a, **k: None)
    monkeypatch.setattr(module, "_outcome", lambda digest, sid: calls.append(sid))
    transcript = _write_transcript(tmp_path)
    _run_main(module, {"session_id": "s5", "transcript_path": str(transcript),
                       "hook_event_name": "PreCompact", "trigger": "auto"}, monkeypatch)
    assert calls == []  # 세션 중 compact은 장부를 소진하면 안 됨
    _run_main(module, {"session_id": "s5", "transcript_path": str(transcript),
                       "hook_event_name": "SessionEnd", "reason": "exit"}, monkeypatch)
    assert calls == ["s5"]


def test_outcome_echo_measurement(monkeypatch, tmp_path):
    module = _load("forget_capture")
    monkeypatch.setattr(module, "STATE_DIR", str(tmp_path))
    recorded = []
    monkeypatch.setattr(module, "_rpc", lambda name, args, timeout=5: recorded.append((name, args)))
    (tmp_path / "s6.json").write_text(json.dumps(
        {"trace_id": "t-9", "memory_ids": ["m-a", "m-b"],
         "capsule_lines": ["현재 목표: X 기준으로 진행", "다음 행동: 계정 생성"]}), encoding="utf-8")
    digest = module._digest(str(_write_transcript(tmp_path)))  # assistant가 첫 줄을 메아리침
    module._outcome(digest, "s6")
    assert recorded and recorded[0][0] == "record_context_outcome"
    args = recorded[0][1]
    assert args["used_memory_ids"] == ["m-a", "m-b"] and args["first_action_productive"] is True
    assert (tmp_path / "s6.json.done").exists()


# --- forget_sessionstart -----------------------------------------------------

def test_sessionstart_prints_capsule_and_writes_offer_ledger(monkeypatch, tmp_path, capsys):
    module = _load("forget_sessionstart")
    monkeypatch.setattr(module, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(module, "_rpc", None, raising=False)

    def fake_rpc_response(*args, **kwargs):
        raise AssertionError("sessionstart uses urllib directly")

    payload = {
        "capsule_text": "현재 목표: YC 스프린트\n다음 행동: 계정 생성",
        "context_trace_id": "trace-7",
        "evidence": {"memory_ids": ["m-1", "m-2"]},
    }

    class FakeResponse:
        def read(self):
            return json.dumps({"result": {"content": [{"type": "text", "text": json.dumps(payload)}]}}).encode()

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda req, timeout=8: FakeResponse())
    _run_main(module, {"session_id": "s7", "source": "startup", "cwd": "/tmp"}, monkeypatch)
    out = capsys.readouterr().out
    assert "forget 캡슐" in out and "YC 스프린트" in out
    ledger = json.loads((tmp_path / "s7.json").read_text(encoding="utf-8"))
    assert ledger["trace_id"] == "trace-7" and ledger["memory_ids"] == ["m-1", "m-2"]
    assert any("현재 목표" in line for line in ledger["capsule_lines"])


# --- 교대 인수인계 (PreCompact → SessionStart) --------------------------------

def test_precompact_writes_handoff_note(monkeypatch, tmp_path):
    module = _load("forget_capture")
    monkeypatch.setattr(module, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(module, "_rpc", lambda *a, **k: None)
    transcript = _write_transcript(tmp_path)
    _run_main(module, {"session_id": "s8", "transcript_path": str(transcript),
                       "hook_event_name": "PreCompact", "trigger": "auto"}, monkeypatch)
    note = json.loads((tmp_path / "handoff.json").read_text(encoding="utf-8"))
    assert note["last_user"] == "돌다리를 두드리자"
    assert "현재 목표: X" in note["last_assistant"]
    assert note["transcript_path"] == str(transcript)
    # SessionEnd는 인수장을 쓰지 않는다 — 자연 종료는 사고사가 아님
    (tmp_path / "handoff.json").unlink()
    _run_main(module, {"session_id": "s8", "transcript_path": str(transcript),
                       "hook_event_name": "SessionEnd", "reason": "exit"}, monkeypatch)
    assert not (tmp_path / "handoff.json").exists()


def _sessionstart_with_fake_server(monkeypatch, tmp_path, capsule_text=""):
    module = _load("forget_sessionstart")
    monkeypatch.setattr(module, "STATE_DIR", str(tmp_path))
    payload = {"capsule_text": capsule_text, "context_trace_id": "", "evidence": {}}

    class FakeResponse:
        def read(self):
            return json.dumps({"result": {"content": [{"type": "text", "text": json.dumps(payload)}]}}).encode()

    monkeypatch.setattr(module.urllib.request, "urlopen", lambda req, timeout=8: FakeResponse())
    return module


def test_sessionstart_delivers_handoff_once_then_burns_it(monkeypatch, tmp_path, capsys):
    module = _sessionstart_with_fake_server(monkeypatch, tmp_path, capsule_text="현재 목표: 이어가기")
    (tmp_path / "handoff.json").write_text(json.dumps({
        "session_id": "s9", "cut_at": "2026-07-25T10:00:00Z",
        "last_user": "루프를 넘겨줄게", "last_assistant": "게이트 로그를 시공하는 중이었",
        "transcript_path": "/tmp/t.jsonl",
    }), encoding="utf-8")
    _run_main(module, {"session_id": "s10", "source": "compact", "cwd": "/tmp"}, monkeypatch)
    out = capsys.readouterr().out
    assert "교대 인수인계" in out and "루프를 넘겨줄게" in out and "잘린 손의 마지막 문장" in out
    assert (tmp_path / "handoff.json.done").exists()
    # 두 번째 손은 인수장을 받지 않는다 — 일회성
    _run_main(module, {"session_id": "s11", "source": "startup", "cwd": "/tmp"}, monkeypatch)
    assert "교대 인수인계" not in capsys.readouterr().out


def test_stale_handoff_is_burned_silently(monkeypatch, tmp_path, capsys):
    import os as _os
    module = _sessionstart_with_fake_server(monkeypatch, tmp_path, capsule_text="현재 목표: 새 일")
    path = tmp_path / "handoff.json"
    path.write_text(json.dumps({"last_user": "옛날 실", "transcript_path": "/tmp/t.jsonl"}), encoding="utf-8")
    old = 60 * 60 * 24 * 3  # 3일 전
    _os.utime(path, (path.stat().st_atime - old, path.stat().st_mtime - old))
    _run_main(module, {"session_id": "s12", "source": "startup", "cwd": "/tmp"}, monkeypatch)
    out = capsys.readouterr().out
    assert "교대 인수인계" not in out and "현재 목표: 새 일" in out
    assert (tmp_path / "handoff.json.done").exists()
