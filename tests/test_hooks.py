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
