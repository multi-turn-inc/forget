"""oracle_replay.parse_cycles — 정의역을 상수에서 인자로 옮긴 부분의 회귀 (c165, 백로그 #8).

왜 이 파일이 있는가. 전임자 `c121_obs68_oracle_replay.py`는 `CYCLES = [116..120]`을
**모듈 상수**로 박았다. 임무(백로그 #8)는 매 회고에 열리는데 계기는 다섯 사이클에만
열렸고, 재사용에 손이 들어 **c125·c135·c145·c155 네 회고가 연속 미이행**했다.
c165가 바꾼 것은 **정의역 하나**이며 검색 계약(recall=low·top_k=10·work[:300]·적격
컷오프)은 한 글자도 건드리지 않았다 — 바꾸면 c36·c57·c58·c59·c121의 `silent_miss=0`
계열과 비교 불가가 되기 때문이다.

따라서 이 파일이 지키는 것은 **그 한 군데**다. 가장 중요한 단언 둘:

① **빈 정의역은 값이 아니라 죽음이다.** `--cycles`가 빈 문자열·쉼표뿐이면 `[]`를
   반환해 "재생할 것이 없다 = 차집합 0 = 지지"로 조용히 읽히면 안 된다. `silent_miss=0`은
   이 루프에서 **6연속 나온 값**이라 특히 위험하다 — 계기가 침묵해도 계열과 구별되지
   않는다. `ProbeFailure`로 터진다(probe_guard 규약).

② **구간과 열거가 같은 자[尺]를 쓴다.** `160-164`와 `160,161,162,163,164`는 같은
   정의역이어야 하고, 중복·역순은 조용히 통과하지 않아야 한다.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "devloop" / "scripts"
# 명시 삽입 — 모듈이 내부에서 넣어주는 것에 기대면 테스트 순서에 의존한다.
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "oracle_replay.py"
spec = importlib.util.spec_from_file_location("oracle_replay_under_test", SCRIPT)
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)

from probe_guard import ProbeFailure  # noqa: E402


def test_range_form_expands_inclusive():
    assert oracle.parse_cycles("160-164") == [160, 161, 162, 163, 164]


def test_enumeration_and_range_agree():
    assert oracle.parse_cycles("160,161,162,163,164") == oracle.parse_cycles("160-164")


def test_mixed_forms_merge_and_sort():
    assert oracle.parse_cycles("164,160-162") == [160, 161, 162, 164]


def test_duplicates_collapse_rather_than_double_count():
    # 같은 사이클을 두 번 재생하면 '고유 기억' 분모가 조용히 부풀 수 있다.
    assert oracle.parse_cycles("160,160,160-161") == [160, 161]


def test_single_cycle_is_a_domain():
    assert oracle.parse_cycles("121") == [121]


def test_whitespace_is_tolerated():
    assert oracle.parse_cycles(" 160 - 162 , 164 ") == [160, 161, 162, 164]


@pytest.mark.parametrize("spec_str", ["", "   ", ",", " , , "])
def test_empty_domain_dies_instead_of_returning_empty(spec_str):
    # 핵심 단언 ① — 빈 결과가 'silent_miss 0'으로 읽히는 경로를 막는다.
    with pytest.raises(ProbeFailure):
        oracle.parse_cycles(spec_str)


def test_reversed_range_dies():
    with pytest.raises(ProbeFailure):
        oracle.parse_cycles("164-160")


def test_non_numeric_dies_rather_than_being_skipped():
    with pytest.raises(ValueError):
        oracle.parse_cycles("160-16x")


def test_search_contract_constants_are_unchanged_from_c121():
    """c121과의 비교 가능성이 이 계기의 값어치다 — 상수가 바뀌면 계열이 끊긴다.

    바꿔야 할 이유가 생기면 이 테스트를 고치는 손이 곧 계열 단절을 선언하는 손이며,
    그 선언을 원장에 적어야 한다. 조용히 고치지 말 것.
    """
    assert oracle.QUERY_CAP == 300
    assert oracle.TOP_K == 10
