"""c48_step0_check — 오류 봉투 번역과 **파트 격리** (c192 신설, 관측 121 · P67).

왜 이 파일이 있는가. c192 턴1에 step 0 계기가 파트 B에서 `KeyError: 'result'`로
죽었고 **뒤의 5파트(F·D·P·X·O)가 통째로 실행되지 않았다.** stdout에는 앞 5파트의
정상 출력만 남아 정상 종료와 구별되지 않았다 — 무기억으로 태어나는 손은 «파트 O가
없다»를 알아채려면 «파트 O가 있어야 한다»를 미리 알아야 하는데 그것이 없다.
LOOP 원칙 7(*«사이클 N+1의 0단계가 실패하면 그것이 최우선 버그다»*)이 문자 그대로
발화한 첫 사이클이다.

두 결함이 루프 소유였다.
① `call()`이 `body["result"]`를 무조건 인덱싱 → 서버가 규격대로 보낸 `error`(코드
   −32603, 메시지 'list index out of range')가 **전부 버려지고** 클라이언트 자신의
   `KeyError`로 오역됐다. 오역은 두 번 손해다 — 진단을 잃고, 엉뚱한 곳을 파게 한다.
② `main()`에 파트 격리가 없어 한 파트의 예외가 나머지를 데려갔다.

관행 ⑯: 능력은 **합성 표본**으로 고정한다. 실 서버·실 원장에 의존하지 않는다 —
이 테스트가 데몬 상태에 걸리면 진단해야 할 사건이 테스트 실패로 위장된다.

★ P67 한계 ①(격리가 사망을 정상화할 위험)이 이 파일의 설계를 정한다: 격리만
고정하면 «조용히 넘어가는» 계기를 회귀로 **못박는** 셈이 된다. 그래서 사망의
**시끄러움**(배너·요약·exit 1)과 **정상 경로의 무변화**를 함께 건다.
"""
import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "devloop" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_part_isolation", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)


# ─────────────────────────── ① 오류 봉투 번역 (P67 (a)) ───────────────────────────

class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _urlopen_returning(body: dict):
    return lambda req, timeout=None: _FakeResponse(json.dumps(body).encode("utf-8"))


def test_call_raises_typed_error_on_error_envelope():
    """c192 실물 봉투 — KeyError가 아니라 ForgetRpcError, 코드·메시지 보존."""
    envelope = {"jsonrpc": "2.0", "id": 1,
                "error": {"code": -32603, "message": "list index out of range"}}
    with mock.patch.object(c48.urllib.request, "urlopen", _urlopen_returning(envelope)):
        with pytest.raises(c48.ForgetRpcError) as caught:
            c48.call("prepare_context_autopilot", {"query": "x"})
    err = caught.value
    assert err.code == -32603
    assert err.message == "list index out of range"
    assert err.tool == "prepare_context_autopilot"
    # 메시지가 화면에 **원문 그대로** 보여야 한다 — 진단을 삼키지 않는다.
    assert "list index out of range" in str(err)
    assert "prepare_context_autopilot" in str(err)


def test_call_does_not_raise_keyerror_on_error_envelope():
    """구판의 실패 서식이 재발하지 않는지 명시적으로 못박는다."""
    envelope = {"jsonrpc": "2.0", "id": 1, "error": {"code": -1, "message": "boom"}}
    with mock.patch.object(c48.urllib.request, "urlopen", _urlopen_returning(envelope)):
        with pytest.raises(c48.ForgetRpcError):
            c48.call("search_memories", {"query": "x"})
        try:
            c48.call("search_memories", {"query": "x"})
        except Exception as exc:  # noqa: BLE001
            assert not isinstance(exc, KeyError)


def test_call_reports_envelope_without_result_or_error():
    """result도 error도 없는 봉투 — 모르는 것을 그럴듯한 기본값으로 접지 않는다."""
    with mock.patch.object(c48.urllib.request, "urlopen",
                           _urlopen_returning({"jsonrpc": "2.0", "id": 1})):
        with pytest.raises(c48.ForgetRpcError) as caught:
            c48.call("get_task_state", {"task_id": "devloop"})
    assert caught.value.code == c48.UNKNOWN
    assert "result·error 둘 다 없음" in caught.value.message


def test_call_unwraps_success_envelope_unchanged():
    """정상 경로는 종전과 동일 — 처치가 성공 경로를 바꾸지 않았다."""
    inner = {"capsule_text": "안녕", "status": "sufficient"}
    envelope = {"jsonrpc": "2.0", "id": 1,
                "result": {"content": [{"text": json.dumps(inner, ensure_ascii=False)}]}}
    with mock.patch.object(c48.urllib.request, "urlopen", _urlopen_returning(envelope)):
        assert c48.call("prepare_context_autopilot", {"query": "x"}) == inner


# ─────────────────────────── ② 파트 격리 (P67 (b)) ───────────────────────────

def _run_parts(parts):
    """run_part를 파트 목록에 걸어 실행하고 (출력, deaths)를 돌려준다."""
    deaths: list[tuple[str, str]] = []
    buf = io.StringIO()
    with redirect_stdout(buf):
        for label, fn in parts:
            c48.run_part(label, fn, deaths)
    return buf.getvalue(), deaths


def test_one_part_death_does_not_take_the_rest():
    """c192 실물 배치의 축소판 — 6번째가 죽어도 뒤의 5개가 전부 돈다."""
    ran: list[str] = []

    def ok(name):
        return lambda: ran.append(name)

    def dies():
        ran.append("B")
        raise c48.ForgetRpcError("prepare_context_autopilot", -32603, "list index out of range")

    parts = [("N", ok("N")), ("S", ok("S")), ("Body", ok("Body")),
             ("R", ok("R")), ("A", ok("A")), ("B", dies),
             ("F", ok("F")), ("D", ok("D")), ("P", ok("P")),
             ("X", ok("X")), ("O", ok("O"))]
    out, deaths = _run_parts(parts)

    assert ran == ["N", "S", "Body", "R", "A", "B", "F", "D", "P", "X", "O"]
    # 구조 이전에는 여기서 F·D·P·X·O가 통째로 없었다.
    assert [label for label, _ in deaths] == ["B"]
    assert "list index out of range" in out


def test_multiple_deaths_all_recorded_and_rest_still_run():
    ran: list[str] = []

    def ok(name):
        return lambda: ran.append(name)

    def boom(name, exc):
        def _fn():
            raise exc
        return _fn

    parts = [("N", ok("N")),
             ("S", boom("S", ValueError("계기 버그"))),
             ("A", ok("A")),
             ("B", boom("B", c48.ForgetRpcError("search_memories", -32603, "list index out of range"))),
             ("O", ok("O"))]
    out, deaths = _run_parts(parts)

    assert ran == ["N", "A", "O"]
    assert [label for label, _ in deaths] == ["S", "B"]
    assert "계기 버그" in out


def test_server_and_instrument_deaths_are_labelled_differently():
    """★ 남의 오류와 내 오류를 화면에서 구별한다 — 오역이 이 사이클의 병이었다."""
    out_server, _ = _run_parts(
        [("B", lambda: (_ for _ in ()).throw(c48.ForgetRpcError("x", -32603, "boom")))])
    out_self, _ = _run_parts(
        [("B", lambda: (_ for _ in ()).throw(ValueError("boom")))])

    assert "서버측" in out_server
    assert "계기측" not in out_server
    assert "계기측" in out_self
    assert "서버측" not in out_self


def test_healthy_parts_add_no_output(capsys):
    """★ P67 (c) 반증 팔 — 사망 0이면 run_part는 문면을 한 글자도 더하지 않는다.

    격리 처치가 매 사이클 화면에 노이즈를 더하면 그 자체가 새 마찰이고, 관측 121이
    고발한 «화면을 읽는 손»을 또 무디게 한다.
    """
    out, deaths = _run_parts([("N", lambda: print("[N. 배너]")),
                              ("O", lambda: print("[O. 서수]"))])
    assert deaths == []
    assert out == "[N. 배너]\n[O. 서수]\n"


# ─────────────────── ③ 사망의 시끄러움 — 격리의 자기 위협 방어 ───────────────────

def test_death_banner_names_the_part_and_says_rest_continue():
    out, _ = _run_parts(
        [("O", lambda: (_ for _ in ()).throw(c48.ForgetRpcError("x", -32603, "boom")))])
    assert "파트 O 사망" in out
    assert "뒤의 파트는 계속 실행된다" in out


def test_main_block_wires_all_eleven_parts_through_run_part():
    """실 소스 항등식 — 파트가 늘거나 줄어도 **전수가** 격리를 통과해야 한다.

    수를 상수로 박지 않는다(관측 106의 자물쇠): 파트를 추가하는 손이 벌받지 않도록
    «정의된 파트 수 == run_part로 감싼 수»라는 프레임 독립 항등식만 건다.
    """
    import re

    src = SCRIPT.read_text(encoding="utf-8")
    main_block = src.split('if __name__ == "__main__":')[1]

    defined = set(re.findall(r"^def (part_[a-z_]+)\(", src, re.M))
    wrapped = set(re.findall(r"run_part\(\s*\"[^\"]+\"\s*,\s*(part_[a-z_]+)\s*,", main_block))

    assert defined, "파트가 하나도 정의되지 않았다 — 정규식이 표류했다"
    assert wrapped == defined, f"격리 밖 파트: {sorted(defined - wrapped)}"
    # 무보호 직접 호출이 남아 있으면 그 파트는 여전히 나머지를 데려간다.
    bare = re.findall(r"^\s{4}(part_[a-z_]+)\(\)\s*$", main_block, re.M)
    assert bare == [], f"무보호 호출 잔존: {bare}"


def test_main_block_exits_nonzero_and_summarises_on_death():
    """말미 요약 + exit 1이 소스에 실제로 걸려 있는지 (격리 정상화 방지)."""
    src = SCRIPT.read_text(encoding="utf-8")
    main_block = src.split('if __name__ == "__main__":')[1]
    assert "if deaths:" in main_block
    assert "sys.exit(1)" in main_block
    assert "사망 파트" in main_block
    # 사망 요약은 **조건부**여야 한다 — 무조건 인쇄하면 P67 (c)가 죽는다.
    assert main_block.index("if deaths:") < main_block.index("sys.exit(1)")


# ─────────────────── ④ 캡슐 판정 불가 — miss로 계상되지 않는다 ───────────────────

def test_part_b_prints_undecidable_not_miss_when_capsule_channel_dies():
    """관측 121 수용 기준 ④ — 못 본 것과 봤는데 무용한 것은 다른 사건이다."""
    src = SCRIPT.read_text(encoding="utf-8")
    body = src.split("def part_b()")[1].split("\ndef ")[0]
    assert "except ForgetRpcError:" in body
    assert "판정 불가" in body
    assert "miss를 더하지 말 것" in body
    # 조용히 빈 캡슐로 접히면 그 사이클이 miss로 계상된다 — 반드시 위로 올린다.
    assert "raise" in body.split("except ForgetRpcError:")[1].split("shown =")[0]
