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
import types
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

def _recall_module(monkeypatch, tmp_path, results, memories_by_id=None, calls=None):
    module = _load("forget_turnrecall")
    monkeypatch.setattr(module, "STATE_DIR", str(tmp_path))

    def fake_rpc(name, arguments, timeout=5):
        if name == "search_memories":
            if calls is not None:
                calls.append(arguments)
            # 서버처럼 깊이를 지킨다 — 훅이 요청한 top_k 이상은 오지 않는다 (c63)
            return {"results": results[:int(arguments.get("top_k") or len(results))]}
        if name == "get_memory":
            return (memories_by_id or {})[arguments["memory_id"]]
        raise AssertionError(name)

    monkeypatch.setattr(module, "_rpc", fake_rpc)
    return module


def test_conflict_pair_uses_looser_threshold(monkeypatch, tmp_path, capsys):
    # 0.325 clears the conflict gate (0.32) but NOT the plain gate (0.33) —
    # the exact shape of the silent-alert bug. (문턱은 2026-08-23 mpnet 보정치 —
    # repo/배포 훅 동본화(2026-08-30)로 수치 갱신)
    results = [
        {"id": "new-1", "score": 0.325, "memory": "정정: 발송된 적 없음",
         "metadata": {"supersedes": ["old-1"]}, "trust": {"light": "yellow"}},
        {"id": "plain-1", "score": 0.325, "memory": "평범한 기억", "metadata": {}},
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
    assert "(green·" in (_out3 := capsys.readouterr().out) and "로컬-퍼스트" in _out3
    ledger = json.loads((tmp_path / "s3.json").read_text(encoding="utf-8"))
    assert "m-1" in ledger["memory_ids"] and any("로컬-퍼스트" in line for line in ledger["capsule_lines"])
    # 같은 세션 두 번째 턴 → 억제
    _run_main(module, {"session_id": "s3", "prompt": "아키텍처 어떻게 가기로 했지?"}, monkeypatch)
    assert capsys.readouterr().out == ""


def test_search_error_row_carries_error_kind(monkeypatch, tmp_path, capsys):
    # 관측 59: 24h 창의 search_error 13건에 원인이 없어 귀속 불가였다.
    # 실패 행에는 예외 종류가 실리고, fail-open(컨텍스트 무출력)은 유지된다.
    module = _load("forget_turnrecall")
    monkeypatch.setattr(module, "STATE_DIR", str(tmp_path))

    def broken_rpc(name, arguments, timeout=5):
        raise TimeoutError("timed out")

    monkeypatch.setattr(module, "_rpc", broken_rpc)
    _run_main(module, {"session_id": "s21", "prompt": "아키텍처 어떻게 가기로 했지?"}, monkeypatch)
    assert capsys.readouterr().out == ""
    rows = [json.loads(line) for line in
            (tmp_path / "turnrecall_gate.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["action"] == "search_error"
    assert rows[-1]["error"].startswith("TimeoutError")


def test_gate_rows_without_error_keep_schema(monkeypatch, tmp_path, capsys):
    # error 필드는 실패 행에만 붙는다 — 성공 행은 기존 원장 파서와 스키마 동일.
    module = _recall_module(monkeypatch, tmp_path, [])
    _run_main(module, {"session_id": "s22", "prompt": "아키텍처 어떻게 가기로 했지?"}, monkeypatch)
    rows = [json.loads(line) for line in
            (tmp_path / "turnrecall_gate.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["action"] == "silent_scores"
    assert "error" not in rows[-1]


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
    assert "(green·" in out and "임베더는 e5로" in out
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


def test_deeper_fetch_leaves_the_measured_spread_unchanged(monkeypatch, tmp_path, capsys):
    """P18 (a) — 깊이 인상은 자[尺]를 바꾸지 않는다 (c61 실측 배치로 고정).

    창을 5로 고정하면 `len//2`가 4에서도 5에서도 2이므로, 자격 4개였던 배치에
    하위 후보를 덧붙여도 중앙값이 같은 자리에 남고 spread가 그대로다.
    실측에서도 그랬다: 같은 질의가 깊이 5/10에서 0.0454→0.0454
    (`c63_depth_invariance.py`, 20건 전부 spread 변화 0).
    """
    injected = []
    for tag, extra in (("s-shallow", []), ("s-deep", [0.60, 0.55, 0.50, 0.46, 0.45])):
        results = _claim_then_memories(_C61_SCORES) + [
            {"id": f"deep-{i}", "score": score, "memory": f"깊은 자리 기억 {i}",
             "metadata": {}, "trust": {"light": "yellow"}}
            for i, score in enumerate(extra)]
        module = _recall_module(monkeypatch, tmp_path, results)
        _run_main(module, {"session_id": tag, "prompt": "devloop 사이클을 정확히 한 바퀴 실행하라"}, monkeypatch)
        capsys.readouterr()
        injected.append(json.loads((tmp_path / f"{tag}.turns.json").read_text(encoding="utf-8"))["injected"])
    assert injected[0] == injected[1] == ["m-0", "m-1", "m-2"], f"깊이가 판정을 바꿨다: {injected}"


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


def test_thin_eligible_pool_still_unmeasurable_but_now_leaves_a_row(monkeypatch, tmp_path, capsys):
    """c62가 고정한 경계의 c63 처치 후 상태 — 여전히 못 재지만 **무공지가 아니다**.

    스토어가 깊이 CANDIDATE_TOP_K에도 자격 후보 3개밖에 내놓지 못하면 평탄도는
    표본 부족으로 재지 못하고, 그 턴은 게이트 없이 통과한다(전량 주입). 처치는
    이 통과를 막지 않는다 — 못 잰 것을 잰 척하는 것이 더 나쁘다. 대신 원장에
    한 행을 남겨 감사가 빈도를 셀 수 있게 한다(P18 (b)의 2차 판정 채널).
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
    rows = [json.loads(line) for line in
            (tmp_path / "flatness_unmeasured.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["eligible"] == 3 and rows[0]["injected"] == 3
    assert rows[0]["min_samples"] == module.FLATNESS_MIN_SAMPLES


def test_deep_fetch_fills_the_window_so_a_flat_pool_still_silences(monkeypatch, tmp_path, capsys):
    """c63 처치의 본체: 무자격 후보 2개로 게이트가 꺼지지 않는다.

    상위 5개에 무자격이 2개면 얕은 인출(5)에서는 자격 3개 → 게이트 정지 →
    평지여도 전량 주입이었다. 깊이 CANDIDATE_TOP_K로 창(5)을 채우면 자격끼리
    평지임이 보이고 침묵이 돌아온다.
    """
    calls: list = []
    results = [
        {"id": "claim:one", "score": 1.0, "memory": "장부 행 1",
         "metadata": {"assertion_kind": "task_state"}, "trust": {"light": "yellow"}},
        {"id": "cap-1", "score": 0.99, "memory": "세션 캡처 포인터",
         "metadata": {"hook": "session_capture"}, "trust": {"light": "yellow"}},
    ] + [{"id": f"m-{i}", "score": score, "memory": f"무관한 기억 {i}",
          "metadata": {}, "trust": {"light": "yellow"}}
         for i, score in enumerate((0.62, 0.615, 0.61, 0.605, 0.60, 0.598))]
    module = _recall_module(monkeypatch, tmp_path, results, calls=calls)
    _run_main(module, {"session_id": "s-deep", "prompt": "프로토타입 어디까지 갔지?"}, monkeypatch)
    assert capsys.readouterr().out == "", "자격 후보 5개가 평지 → 침묵이어야 한다"
    assert calls[0]["top_k"] == module.CANDIDATE_TOP_K > module.PICK_POOL
    assert not (tmp_path / "flatness_unmeasured.jsonl").exists()  # 재었으므로 원장 행 없음


def test_deep_fetch_does_not_widen_the_injection_pool(monkeypatch, tmp_path, capsys):
    """입력 집합 불변 — 깊이는 분포 표본용이고 주입 후보는 여전히 상위 PICK_POOL개.

    깊은 자리(6~10위)의 기억도 문턱을 넘지만 주입되지 않는다. 이것이 c63 처치를
    '자[尺] 변경'이 아니라 '표본 수 조건 수리'로 유지하는 경계다.
    """
    results = [
        {"id": "claim:one", "score": 1.0, "memory": "장부 행", "metadata": {"assertion_kind": "task_state"}},
        {"id": "cap-1", "score": 0.99, "memory": "캡처 포인터", "metadata": {"hook": "SessionEnd"}},
        {"id": "m-0", "score": 0.80, "memory": "상위 5위 안의 기억", "metadata": {}, "trust": {"light": "green"}},
        {"id": "claim:two", "score": 0.78, "memory": "장부 행 2", "metadata": {"assertion_kind": "task_state"}},
        {"id": "cap-2", "score": 0.77, "memory": "캡처 포인터 2", "metadata": {"hook": "SessionEnd"}},
    ] + [{"id": f"deep-{i}", "score": score, "memory": f"6위 이하 기억 {i}",
          "metadata": {}, "trust": {"light": "yellow"}}
         for i, score in enumerate((0.76, 0.60, 0.55, 0.50, 0.46))]
    module = _recall_module(monkeypatch, tmp_path, results)
    _run_main(module, {"session_id": "s-pool", "prompt": "그 기억 어디까지 갔지?"}, monkeypatch)
    out = capsys.readouterr().out
    assert "상위 5위 안의 기억" in out and "6위 이하" not in out
    turns = json.loads((tmp_path / "s-pool.turns.json").read_text(encoding="utf-8"))
    assert turns["injected"] == ["m-0"]
    # 창은 깊은 자리로 채워져 **재였다** — 표본 부족 원장 행이 없다
    assert not (tmp_path / "flatness_unmeasured.jsonl").exists()


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
    monkeypatch.setattr(module, "forget_digest", None)  # 플러시는 별도 테스트 — 여기선 차단
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
    monkeypatch.setattr(module, "forget_digest", None)  # 플러시는 별도 테스트 — 여기선 차단
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


# --- forget_digest (P4 — 롤링 응고 1단계 ①) ------------------------------------

def _digest_module(monkeypatch, tmp_path, calls=None, fail=False, window=5, batch=3):
    module = _load("forget_digest")
    monkeypatch.setattr(module, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(module, "RECENT_WINDOW_TURNS", window)
    monkeypatch.setattr(module, "DIGEST_BATCH_TURNS", batch)

    def fake_rpc(name, arguments, timeout=30):
        if fail:
            raise OSError("server down")
        if calls is not None:
            calls.append((name, arguments))

    monkeypatch.setattr(module, "_rpc", fake_rpc)
    return module


def _append_turns(tmp_path, start, count) -> Path:
    """턴 텍스트는 전 역할 15자 고정("turn NN content") — 문자 상한 테스트가 산술에 기댄다."""
    path = tmp_path / "digest-transcript.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        for i in range(start, start + count):
            role = "user" if i % 2 else "assistant"
            text = f"turn {i:02d} content"
            content = text if role == "user" else [{"type": "text", "text": text}]
            fh.write(json.dumps({"type": role, "message": {"role": role, "content": content}}) + "\n")
    return path


def test_digest_protects_active_window_and_records_range(monkeypatch, tmp_path):
    calls: list = []
    module = _digest_module(monkeypatch, tmp_path, calls=calls)
    transcript = _append_turns(tmp_path, 1, 10)  # window=5 → 숙성분은 1..5뿐
    _run_main(module, {"session_id": "d1", "transcript_path": str(transcript)}, monkeypatch)
    assert len(calls) == 1
    name, args = calls[0]
    assert name == "add_memory" and args["infer"] is True
    assert [m["content"] for m in args["messages"]] == [f"turn {i:02d} content" for i in range(1, 6)]
    assert args["metadata"]["turn_range"] == [1, 5] and args["metadata"]["session_id"] == "d1"
    # metadata.hook이 붙으면 회상 스킵 + ×0.5 강등 — 소화 기억은 일반 기억이어야 한다
    assert "hook" not in args["metadata"]
    state = json.loads((tmp_path / "digest-d1.json").read_text(encoding="utf-8"))
    assert state["digested_upto"] == 5 and state["digested_turns"] == 5


def test_digest_below_batch_threshold_makes_no_call(monkeypatch, tmp_path):
    calls: list = []
    module = _digest_module(monkeypatch, tmp_path, calls=calls)
    transcript = _append_turns(tmp_path, 1, 7)  # 숙성분 2 < batch 3
    _run_main(module, {"session_id": "d2", "transcript_path": str(transcript)}, monkeypatch)
    assert calls == [] and not (tmp_path / "digest-d2.json").exists()


def test_digest_failure_keeps_offset_then_retries(monkeypatch, tmp_path):
    transcript = _append_turns(tmp_path, 1, 10)
    module = _digest_module(monkeypatch, tmp_path, fail=True)
    _run_main(module, {"session_id": "d3", "transcript_path": str(transcript)}, monkeypatch)
    assert not (tmp_path / "digest-d3.json").exists()  # 실패 비전진
    calls: list = []
    module = _digest_module(monkeypatch, tmp_path, calls=calls)
    _run_main(module, {"session_id": "d3", "transcript_path": str(transcript)}, monkeypatch)
    assert [m["content"] for m in calls[0][1]["messages"]] == [f"turn {i:02d} content" for i in range(1, 6)]


def test_digest_offset_advances_and_never_redigests(monkeypatch, tmp_path):
    calls: list = []
    module = _digest_module(monkeypatch, tmp_path, calls=calls)
    transcript = _append_turns(tmp_path, 1, 10)
    _run_main(module, {"session_id": "d4", "transcript_path": str(transcript)}, monkeypatch)  # 1..5 소화
    _append_turns(tmp_path, 11, 8)  # 총 18턴 → 신규 6..18 중 숙성분 6..13
    _run_main(module, {"session_id": "d4", "transcript_path": str(transcript)}, monkeypatch)
    assert len(calls) == 2
    assert [m["content"] for m in calls[1][1]["messages"]] == [f"turn {i:02d} content" for i in range(6, 14)]
    assert calls[1][1]["metadata"]["turn_range"] == [6, 13]
    state = json.loads((tmp_path / "digest-d4.json").read_text(encoding="utf-8"))
    assert state["digested_turns"] == 13 and state["digested_upto"] == 13


def test_digest_char_cap_advances_only_past_sent_turns(monkeypatch, tmp_path):
    calls: list = []
    module = _digest_module(monkeypatch, tmp_path, calls=calls)
    monkeypatch.setattr(module, "BATCH_CHAR_LIMIT", 30)  # 15자 메시지 정확히 2개 몫
    transcript = _append_turns(tmp_path, 1, 10)
    _run_main(module, {"session_id": "d5", "transcript_path": str(transcript)}, monkeypatch)
    assert [m["content"] for m in calls[0][1]["messages"]] == ["turn 01 content", "turn 02 content"]
    state = json.loads((tmp_path / "digest-d5.json").read_text(encoding="utf-8"))
    assert state["digested_upto"] == 2  # 나머지 몫은 다음 Stop이 이어받는다


def test_digest_skips_machine_payloads_but_passes_their_offset(monkeypatch, tmp_path):
    calls: list = []
    module = _digest_module(monkeypatch, tmp_path, calls=calls)
    transcript = tmp_path / "digest-transcript.jsonl"
    lines = []
    for i in range(1, 11):
        role = "user" if i % 2 else "assistant"
        text = "<command-name>/loop</command-name>" if i == 3 else f"turn {i:02d} content"
        content = text if role == "user" else [{"type": "text", "text": text}]
        lines.append(json.dumps({"type": role, "message": {"role": role, "content": content}}))
    transcript.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _run_main(module, {"session_id": "d6", "transcript_path": str(transcript)}, monkeypatch)
    assert [m["content"] for m in calls[0][1]["messages"]] == [f"turn {i:02d} content" for i in (1, 2, 4, 5)]
    state = json.loads((tmp_path / "digest-d6.json").read_text(encoding="utf-8"))
    assert state["digested_upto"] == 5 and state["digested_turns"] == 5  # 기계 페이로드도 오프셋은 지나간다


# --- P4 순서 2 — ② PreCompact 플러시 + ③ 임계 감시 (c79) -----------------------

def test_digest_sets_near_threshold_flag_without_a_call(monkeypatch, tmp_path):
    """③ — 소화할 것이 없어도(배치 미달) 임계 추정은 매 Stop 갱신된다."""
    calls: list = []
    module = _digest_module(monkeypatch, tmp_path, calls=calls)
    monkeypatch.setattr(module, "CONTEXT_WINDOW_TOKENS", 100)  # 컷 = 70 tokens ≈ 224 bytes
    monkeypatch.setattr(module, "OVERHEAD_TOKENS", 0)
    transcript = _append_turns(tmp_path, 1, 7)  # 숙성분 2 < batch 3 → 소화 없음, 크기 ~700B
    _run_main(module, {"session_id": "d7", "transcript_path": str(transcript)}, monkeypatch)
    assert calls == []  # RPC 0회 — 플래그는 계기이지 소화가 아니다
    state = json.loads((tmp_path / "digest-d7.json").read_text(encoding="utf-8"))
    assert state["near_threshold"] is True and state["est_tokens"] > 0
    assert state["backlog_turns"] == 2 and "digested_upto" not in state


def test_flush_ignores_the_window_and_caps_its_batches(monkeypatch, tmp_path):
    """② — 플러시는 활성 창 보호를 해제하되 FLUSH_MAX_BATCHES로 비용을 묶는다."""
    calls: list = []
    module = _digest_module(monkeypatch, tmp_path, calls=calls)
    monkeypatch.setattr(module, "BATCH_CHAR_LIMIT", 30)  # 15자 메시지 정확히 2개 몫
    transcript = _append_turns(tmp_path, 1, 10)
    (tmp_path / "digest-f1.json").write_text(json.dumps(
        {"near_threshold": True, "near_threshold_advised": True}), encoding="utf-8")
    module.flush(str(transcript), "f1")
    assert len(calls) == 4  # 2턴×4배치 = 8턴 — window=5여도 보호 없음
    assert [m["content"] for m in calls[0][1]["messages"]] == ["turn 01 content", "turn 02 content"]
    assert calls[0][1]["metadata"]["digest_trigger"] == "precompact_flush"
    assert "hook" not in calls[0][1]["metadata"]
    state = json.loads((tmp_path / "digest-f1.json").read_text(encoding="utf-8"))
    assert state["digested_upto"] == 8 and state["backlog_turns"] == 2  # 잔여는 다음 Stop 몫
    assert state["compacted_at_bytes"] == transcript.stat().st_size
    assert state["near_threshold"] is False and "near_threshold_advised" not in state


def test_flush_failure_advances_only_past_sent_batches_but_baselines_anyway(monkeypatch, tmp_path):
    """② — 오프셋은 전송분까지만(손실 불가), 기준선은 사건 기록이라 실패해도 남는다."""
    module = _digest_module(monkeypatch, tmp_path)
    monkeypatch.setattr(module, "BATCH_CHAR_LIMIT", 30)
    sent: list = []

    def flaky_rpc(name, arguments, timeout=30):
        sent.append(arguments)
        if len(sent) >= 3:
            raise OSError("server down")

    monkeypatch.setattr(module, "_rpc", flaky_rpc)
    transcript = _append_turns(tmp_path, 1, 10)
    module.flush(str(transcript), "f2")
    state = json.loads((tmp_path / "digest-f2.json").read_text(encoding="utf-8"))
    assert state["digested_upto"] == 4 and state["backlog_turns"] == 6  # 배치 2개만 전진
    assert state["compacted_at_bytes"] == transcript.stat().st_size


def test_estimator_resets_at_the_compaction_baseline(monkeypatch, tmp_path):
    """③ — 컴팩션 후 추정은 성장분만 잰다: 같은 크기의 트랜스크립트가 플래그를 못 세운다."""
    module = _digest_module(monkeypatch, tmp_path, calls=[])
    monkeypatch.setattr(module, "CONTEXT_WINDOW_TOKENS", 100)
    monkeypatch.setattr(module, "OVERHEAD_TOKENS", 0)
    transcript = _append_turns(tmp_path, 1, 7)
    _run_main(module, {"session_id": "d8", "transcript_path": str(transcript)}, monkeypatch)
    assert json.loads((tmp_path / "digest-d8.json").read_text(encoding="utf-8"))["near_threshold"] is True
    module.flush(str(transcript), "d8")  # 컴팩션 — 기준선 기록 + 플래그 강하
    _run_main(module, {"session_id": "d8", "transcript_path": str(transcript)}, monkeypatch)
    state = json.loads((tmp_path / "digest-d8.json").read_text(encoding="utf-8"))
    assert state["near_threshold"] is False  # 성장분 0 → 추정 = 오버헤드뿐


def test_precompact_flushes_digest_before_handoff(monkeypatch, tmp_path):
    """② — 캡처 훅은 PreCompact에서만 플러시를 위임한다 (SessionEnd는 아님)."""
    module = _load("forget_capture")
    monkeypatch.setattr(module, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(module, "_rpc", lambda *a, **k: None)
    flushed: list = []
    monkeypatch.setattr(module, "forget_digest", types.SimpleNamespace(
        flush=lambda transcript_path, session_id: flushed.append((transcript_path, session_id))))
    transcript = _write_transcript(tmp_path)
    _run_main(module, {"session_id": "s15", "transcript_path": str(transcript),
                       "hook_event_name": "PreCompact", "trigger": "auto"}, monkeypatch)
    assert flushed == [(str(transcript), "s15")]
    assert (tmp_path / "handoff.json").exists()  # 플러시가 인수장을 막지 않는다
    _run_main(module, {"session_id": "s15", "transcript_path": str(transcript),
                       "hook_event_name": "SessionEnd", "reason": "exit"}, monkeypatch)
    assert flushed == [(str(transcript), "s15")]  # SessionEnd는 플러시하지 않는다


def test_near_threshold_advisory_prints_once_even_with_zero_picks(monkeypatch, tmp_path, capsys):
    """③ — 회상 0건이어도 권고 1줄은 나가고, 에피소드당 한 번으로 끝난다."""
    module = _recall_module(monkeypatch, tmp_path, [])
    (tmp_path / "digest-s16.json").write_text(json.dumps(
        {"near_threshold": True, "est_tokens": 145_000, "est_ratio": 0.725, "backlog_turns": 0}),
        encoding="utf-8")
    _run_main(module, {"session_id": "s16", "prompt": "다음 단계 계속 진행해줘"}, monkeypatch)
    out = capsys.readouterr().out
    assert "임계" in out and "재부팅" in out and "72%" in out and "소화 완료" in out
    assert "피드백 주소" not in out  # 회상 0건이면 feedback footer도 없다
    state = json.loads((tmp_path / "digest-s16.json").read_text(encoding="utf-8"))
    assert state["near_threshold_advised"] is True
    _run_main(module, {"session_id": "s16", "prompt": "다음 단계 계속 진행해줘"}, monkeypatch)
    assert capsys.readouterr().out == ""  # 두 번째 턴은 침묵


def test_near_threshold_advisory_rides_along_and_admits_backlog(monkeypatch, tmp_path, capsys):
    """③ — 회상과 동승하고, 미소화 잔여가 있으면 '소화 완료'를 주장하지 않는다."""
    results = [{"id": "m-9", "score": 0.6, "memory": "관련 기억", "metadata": {}, "trust": {"light": "green"}}]
    module = _recall_module(monkeypatch, tmp_path, results)
    (tmp_path / "digest-s17.json").write_text(json.dumps(
        {"near_threshold": True, "est_ratio": 0.71, "backlog_turns": 12}), encoding="utf-8")
    _run_main(module, {"session_id": "s17", "prompt": "그 기억 관련해서 뭐가 있었지?"}, monkeypatch)
    out = capsys.readouterr().out
    assert "(green·" in out and "관련 기억" in out and "임계" in out
    assert "12턴" in out and "소화 완료" not in out
