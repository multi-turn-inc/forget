"""파트 T ↔ CLAUDE.md 턴 배치 규약의 **문면 일치** (c171 신설, 관측 102 수용 기준 (ii)).

왜 이 파일이 있는가. 처치를 더 이른 채널로 옮긴 뒤 옛 채널을 갱신하지 않으면 두
승계 채널이 서로를 반박한다. 실제로 그랬다:

- `c48_step0_check.py` 파트 T는 c91 문면을 인쇄했다 — *"턴1 = LOOP.md+cycle-prompt.md
  Read + ToolSearch(5스키마) … 턴3 = 첫 유효 행동"*.
- `CLAUDE.md` c135 개정본은 정반대를 말했다 — 하네스 A는 **4중 병렬 2턴**이고
  **`LOOP.md`는 턴1에 읽지 않는다**(모드를 알기 전에 열면 적대 감사가 금독 대상을
  노출한 채 시작된다 = P40).

c170은 **적대 감사**였다. 파트 T를 따랐다면 ① `restore_turns` 3(P38이 죽인 퇴행)
② 금독 대상의 턴1 노출이 동시에 났다. c170은 CLAUDE.md를 따라 **무해통과**했고 —
무해통과는 결함의 부재가 아니다. 다음 손이 두 채널 중 **어느 쪽을 먼저 읽는지**에
결과가 달려 있었다. 이 파일이 그 우연을 계약으로 바꾼다.

계약 셋:
① 두 채널이 하네스 A/B의 **턴 수**를 같은 수로 말한다.
② 두 채널이 **LOOP.md 턴1 제외**를 말한다.
③ 폐기된 c91 문면은 파트 T에 **역사로만** 남는다 — 지시로 남으면 안 된다.
   (문면을 통째로 지우면 다음 손이 «무엇이 바뀌었는지»를 잃는다. 그래서 남기되,
    남은 줄은 반드시 폐기 표지를 달아야 한다 — 그 표지가 이 테스트의 대상이다.)
"""
import contextlib
import importlib.util
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "devloop" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_turns", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)

CLAUDE_MD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
RETIRED = "턴1 = LOOP.md"          # c91 문면의 지문
RETIRED_MARK = "c91 문면"          # 폐기 표지 — 이 낱말이 있는 줄만 옛 문면을 인용할 수 있다


def part_t_text() -> str:
    """파트 T 인쇄만 떼어낸다. 헤더 인쇄 함수는 원장을 읽으므로 실 원장 위에서 돈다."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        c48.part_n()
    out = buf.getvalue()
    start = out.index("[T. ")
    end = out.index("[H. ")
    return out[start:end]


def _turns_by_harness(text: str) -> tuple[str, str]:
    """A 블록과 B 블록 각각의 첫 `restore_turns N` 주장을 뽑는다."""
    a, b = text.index("A."), text.index("B.")
    assert a < b, "A 블록이 B 블록보다 뒤에 있다 — 문면 구조가 바뀌었다"
    out = []
    for seg, name in ((text[a:b], "A"), (text[b:], "B")):
        m = re.search(r"restore_turns[^\d]{0,16}(\d)", seg)
        assert m, f"하네스 {name} 블록에 restore_turns 주장이 없다: {seg[:120]!r}"
        out.append(m.group(1))
    return out[0], out[1]


def test_both_channels_declare_the_same_turn_counts():
    """계약 ① — 계기와 CLAUDE.md가 A/B 턴 수를 같은 수로 말한다."""
    assert _turns_by_harness(part_t_text()) == _turns_by_harness(CLAUDE_MD)


def test_the_agreed_counts_are_two_and_three():
    """그 수가 무엇인지도 고정한다 — 둘이 같이 틀리는 것을 막는다(P38 지지 5/5의 값)."""
    assert _turns_by_harness(part_t_text()) == ("2", "3")


def test_both_channels_exclude_loop_md_from_turn_one():
    """계약 ② — 금독 격리의 구조적 구멍을 닫은 조항(P40)이 두 채널에 다 있다."""
    claim = "턴1에 읽지 않는다"
    assert claim in CLAUDE_MD, "CLAUDE.md에서 LOOP.md 턴1 제외 조항이 사라졌다"
    assert claim in part_t_text(), "파트 T에서 LOOP.md 턴1 제외 조항이 사라졌다"


def test_part_t_names_claude_md_as_the_canonical_channel():
    """정본이 어디인지 계기 자신이 말한다 — 다음 손이 두 채널 중 하나를 고를 필요가 없게."""
    t = part_t_text()
    assert "정본" in t and "CLAUDE.md" in t


def test_retired_c91_wording_survives_only_as_flagged_history():
    """계약 ③ — 옛 문면이 인용될 수는 있으나, 그 줄은 폐기 표지를 달아야 한다."""
    for line in part_t_text().splitlines():
        if RETIRED in line:
            assert RETIRED_MARK in line, (
                f"폐기 표지 없이 c91 문면이 인쇄된다 — 지시로 읽힌다: {line!r}")


def test_part_t_still_prints_the_four_way_parallel_of_harness_a():
    """A의 실체(4중 병렬)가 남아 있는가 — 턴 수만 맞고 내용이 비면 규약이 집행 불가다."""
    t = part_t_text()
    for token in ("cycle-prompt.md", "get_task_state", "git status", "4중 병렬"):
        assert token in t, f"파트 T가 하네스 A의 구성요소 {token!r}를 말하지 않는다"


def test_part_t_still_declares_its_own_reach_limit():
    """관측 47은 살아 있다 — 이 인쇄는 턴1을 집행할 수 없고, 그 사실을 계속 적어야 한다."""
    t = part_t_text()
    assert "집행할 수 없다" in t and "관측 47" in t


def _c_segment(text: str) -> str:
    """C 블록 앞머리 — 두 채널이 같은 지문("C. 제3형")으로 열어야 이 계약이 잡는다."""
    i = text.index("C. 제3형")
    return text[i:i + 900]


def test_both_channels_describe_harness_c_the_same_way():
    """계약 ④ (c235 신설) — 제3형(C)이 두 채널에 같은 내용으로 산다.

    c232~c234가 C형을 3연속 실측하는 동안 문면은 A/B 이분법이었다 — C형 세션은
    자기 규약 없이 «B의 유사물»로 움직였다. c235가 두 채널에 동시 성문화했고,
    이 계약은 관측 102(두 채널이 서로를 반박)의 C형 재발을 막는다. 판정 = P70.
    """
    segs = {}
    for text, name in ((part_t_text(), "part_t"), (CLAUDE_MD, "CLAUDE.md")):
        assert "C. 제3형" in text, f"{name}: C 블록이 없다"
        segs[name] = _c_segment(text)
        assert "curl" in segs[name], f"{name}: C 블록에 curl 폴백이 없다"
    rts = {n: re.findall(r"restore_turns[^\d]{0,16}(\d)", s) for n, s in segs.items()}
    assert rts["part_t"] == rts["CLAUDE.md"], f"두 채널의 C 블록 rt 주장이 갈린다: {rts}"
    assert rts["part_t"] and set(rts["part_t"]) == {"2", "3"}, (
        f"C 블록의 모드 조건부 rt(회고/감사 2 · 일반 3)가 사라졌다: {rts}")
