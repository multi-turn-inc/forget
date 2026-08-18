"""c48_step0_check.parse_deadlines — 예측 판정 기한의 기계 파싱 (c164, P48 · 계기 큐 ㉦).

왜 이 파일이 있는가. 판정 기한을 배달하는 채널이 **산문 하나**였다. c163의 P45 기한은
`task_state` 산문에만 실려 있었고 그 채널은 c161처럼 세션이 꼬리에서 죽으면 통째로
사라진다 — c163이 P45를 제때 판정한 것은 규율이 아니라 운이다. 처치를 계기로 옮겼으니
그 계기의 파싱을 회귀 아래 둔다.

가장 중요한 단언 두 개.

① **판정 *기한*과 판정 *결과*를 가른다.** 대장에는 `- **판정.** c166(표본 …)`(미래 기한)과
   `- **판정 (c76, 2026-08-08 …)**: 적중`(과거 결과), 그리고 `- **판정.** (a) 팔은 …
   시한(c102) 도달까지 …`(기한이 아니라 판정문 본문에 사이클이 등장)이 **동거**한다.
   셋을 한 칸에 섞으면 이 계기는 이미 판정된 예측을 매 사이클 "오늘 기한"으로 인쇄하는
   늑대소년이 된다.

② **서식 변이 0을 부재로 읽지 않는다.** `판정 시한`·`판정 채널` 변이가 0건인 것은 그
   서식이 대장에 없다는 뜻일 수도, 정규식이 못 본다는 뜻일 수도 있다. 계기가 변이별
   적중 수를 **인쇄하므로** 다음 손이 그 물음을 던질 수 있다 — P48 한계 ③의 거처이며,
   이 파일은 그 계수가 실제로 변이를 가른다는 것만 고정한다.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "devloop" / "scripts"
# 명시 삽입 — parse_deadlines가 내부에서 넣어주는 것에 기대면 테스트 순서에 의존한다.
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_deadlines", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)


def test_plain_cycle_deadline_is_parsed():
    text = "## P46 — 제목 (등록 사이클 161)\n\n- 상태: (a) 시계-가동\n\n- **판정.** c166(표본 c162~c166).\n"
    out = c48.parse_deadlines(text)
    assert out["cycle"] == {"P46": 166}
    assert out["variant_hits"]["판정."] == 1


def test_bold_wrapped_cycle_deadline_is_parsed():
    """`- **판정.** **c130**(…` — 대장에 실재하는 강조 판본."""
    text = "## P30 — 제목 (등록 사이클 92)\n\n- **판정.** **c130**(다음 적대 감사와 동주).\n"
    assert c48.parse_deadlines(text)["cycle"] == {"P30": 130}


def test_verdict_result_line_is_not_a_deadline():
    """도장 달린 판정 **결과** 줄은 기한이 아니다 — 섞이면 판정된 예측이 매일 호출된다."""
    text = ("## P28 — 제목 (등록 사이클 91)\n\n"
            "- **판정 (c76, 2026-08-08 — 시계 c72~c76 종료, 기한 내 기재)**: **적중 (비반증)**.\n")
    out = c48.parse_deadlines(text)
    assert out["cycle"] == {}
    assert out["variant_hits"]["판정."] == 0


def test_cycle_inside_verdict_prose_is_not_a_deadline():
    """`- **판정.** (a) 팔은 … 시한(c102) 도달까지 …` — 본문의 사이클을 기한으로 읽지 않는다."""
    text = ("## P21 — 제목 (등록 사이클 66)\n\n"
            "- **판정.** (a) 팔은 등록 문면의 시한(c102) 도달까지 유효 표본 0 — 표본 부재로 마감한다.\n")
    assert c48.parse_deadlines(text)["cycle"] == {}


def test_calendar_deadline_is_a_separate_axis():
    """달력 기한은 사이클 자[尺]와 다른 축이므로 따로 담긴다 (P36 계열)."""
    text = ("## P36 — 제목 (등록 2026-08-13)\n\n"
            "- 예측 (판정: **2026-09-10 마감** · 처분 조항 동봉):\n")
    out = c48.parse_deadlines(text)
    assert out["calendar"] == {"P36": "2026-09-10"}
    assert out["cycle"] == {}


def test_deadline_is_attributed_to_its_own_section():
    """절 경계를 넘어 앞 절에 귀속되지 않는다 — PSEC_RE 위임의 계약."""
    text = ("## P46 — 제목 (등록 사이클 161)\n\n- **판정.** c166(표본).\n\n"
            "## P47 — 제목 (등록 사이클 162)\n\n- **판정.** c167(표본).\n")
    assert c48.parse_deadlines(text)["cycle"] == {"P46": 166, "P47": 167}


def test_non_prediction_heading_closes_the_section():
    """`## `로 시작하는 비-P 헤딩도 절을 끊는다 — 그 아래 기한은 앞 절 것이 아니다."""
    text = ("## P46 — 제목 (등록 사이클 161)\n\n- 상태: (a) 시계-가동\n\n"
            "## 게이트 종속 상태표\n\n- **판정.** c999(스냅샷 부기).\n")
    out = c48.parse_deadlines(text)
    assert out["cycle"] == {}, "비-P 헤딩 아래 기한이 P46에 귀속되면 거짓 기한이 인쇄된다"


def test_first_deadline_wins_when_a_section_has_two():
    """한 절에 기한 줄이 둘이면 **먼저 쓰인 것**이 기한이다(등록 판본 우선)."""
    text = ("## P44 — 제목 (등록 사이클 155)\n\n- **판정.** c160(표본).\n\n"
            "- 부기: **판정.** c161(오기).\n")
    out = c48.parse_deadlines(text)
    assert out["cycle"] == {"P44": 160}


def test_variant_counters_separate_the_formats():
    """변이 계수기가 서식을 실제로 가른다 — 0을 부재로 읽지 않기 위한 최소 계약."""
    text = ("## P1 — 제목 (등록 사이클 1)\n\n- **판정 시한.** c10(표본).\n\n"
            "## P2 — 제목 (등록 사이클 2)\n\n- **판정 채널** c20(표본).\n")
    hits = c48.parse_deadlines(text)["variant_hits"]
    assert hits["판정 시한"] == 1
    assert hits["판정 채널"] == 1
    assert hits["판정."] == 0
    # 사이클 기한 사전에는 `판정.` 변이만 담긴다 — 다른 변이는 계수만 하고 승격하지 않는다.
    assert c48.parse_deadlines(text)["cycle"] == {}


def test_live_ledger_has_the_two_known_deadlines():
    """실 대장 대조 — 합성 표본만으로는 정규식이 현실을 못 본다는 사실을 못 잡는다.

    c164 실측: P46 = c166 · P47 = c167. 이 단언은 두 기한이 **판정될 때** 깨지는데,
    그때 이 파일을 고치는 손은 곧 그 판정을 낸 손이다(그것이 P48 (c)의 표본이다).
    """
    from c124_retro_prep import PRED  # noqa: PLC0415
    out = c48.parse_deadlines(PRED.read_text(encoding="utf-8"))
    assert out["cycle"].get("P46") == 166
    assert out["cycle"].get("P47") == 167
    assert out["variant_hits"]["판정 시한"] == 0, "새 서식이 생겼으면 파트 D를 확장할 것"
