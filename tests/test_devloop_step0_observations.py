"""c48_step0_check 파트 F — 미해소 관측 인덱스의 대장 파생 (c108, A-95.1 루프 몫 · P34).

open_observations는 c105 정의 이후 세 사이클 연속 수기 재계수로만 산출됐다(c107 자기
기재: "상설화 필요성 3번째 실례"). 파트 F가 frictions.md의 실재 표기 관행에서 값을
파생하고, 이 파일이 그 파서를 회귀 감시 아래 넣는다.

두 층으로 고정한다:
  1. 합성 표본 — 표기 관행 각각(태그/무태그 원본 · 보강/재발 갱신 · 처분 헤더 ·
     절 내 처분 문단 · 이탈 마커 유무 · 절 경계)의 방향을 결정적으로 단언.
  2. 실제 대장 — **불변 역사만** 단언한다(원본 헤더의 태그·개시 사이클, 이미 기재된
     처분). 미래 사이클이 관측을 추가·처분해도 깨지지 않는 술어(⊆/⊇/서로소)로 쓴다 —
     open 값 자체(스냅숏 29)는 여기 고정하지 않는다: 그 대조는 P34 소급 자기 시험이
     1회 수행했고(c107 수기 계수 재현), 이후는 매 사이클 파트 F의 Δ 인쇄가 잰다.

이탈 마커 판정의 방향 고정이 핵심이다: 관측 55·58의 실측 반례(처분 문단은 있으나
하위 항목/계열 표기만 — 회부 존속)가 "처분 문단 존재 = 이탈"이라는 값싼 규칙을
기각시켰다. 그 방향을 합성·실제 양쪽에서 단언한다.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "devloop" / "scripts" / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_obs", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)


# ---- 합성 표본: 표기 관행별 방향 고정 ------------------------------------------

SAMPLE = """\
## 미분류 관측 3 — 태그 있는 원본 (사이클 10, 유형 판정 회부)

본문. **처분 조항**이라는 어휘는 처분 문단이 아니다.

## 관측 4 — 무태그 원본: 유형이 태어날 때 귀속됐다 (사이클 11, F1 귀속)

본문.

## 관측 5 — 후보 태그도 계상 대상이다 (사이클 12, 신규류 'F99 어쩌구' 후보)

본문.

**처분 (사이클 13, amendment-13 §1) — 하위 항목만 재분류.** 이탈 마커가 없다.

## 관측 3 보강 (사이클 14, 신규 번호 아님) — 최근 사이클 갱신

본문.

## 관측 6 — 처분 헤더로 닫힐 원본 (사이클 12, 유형 판정 회부)

본문.

## 관측 6 처분 (사이클 15, amendment-15 §2) — 전항 이행, 종결

본문.

## 관측 7 — 절 내 문단으로 닫힐 원본 (사이클 13, 유형 판정 회부)

본문.

**처분 (사이클 16) — 귀속 완료.** 관측 7은 회부 상태를 벗어난다.

## 무관한 절 제목

**처분 (사이클 17) — 주인 없는 문단.** 절 경계 밖이라 어느 관측에도 귀속되지 않는다.

## 관측 8 재발 2호 (사이클 18, 자기 위반 기재) — 재발도 갱신이다
"""


def _parsed():
    return c48.parse_observations(SAMPLE)


def test_tagged_and_candidate_originals_are_counted_open():
    obs = _parsed()
    assert obs[3]["tagged"] and obs[5]["tagged"]
    assert c48.open_observation_numbers(obs) == [3, 5]


def test_untagged_original_is_out_of_scope_from_birth():
    obs = _parsed()
    assert obs[4]["tagged"] is False
    assert 4 not in c48.open_observation_numbers(obs)


def test_partial_disposal_without_exit_mark_stays_open():
    # 관측 55·58 실측 반례의 합성판: 처분 문단 존재 ≠ 회부 이탈.
    obs = _parsed()
    assert obs[5]["partial_disposal"] is True
    assert obs[5]["exited"] is False
    assert 5 in c48.open_observation_numbers(obs)


def test_disposal_header_with_exit_mark_closes():
    obs = _parsed()
    assert obs[6]["exited"] is True
    assert 6 not in c48.open_observation_numbers(obs)


def test_inline_disposal_paragraph_with_exit_mark_closes():
    # 이탈 마커("회부 상태를 벗")가 문단 **후속 행**에 있어도 잡아야 한다 —
    # 실제 관측 56의 이탈 문구는 **처분 행이 아니라 문단 3행째에 있다.
    obs = _parsed()
    assert obs[7]["exited"] is True
    assert 7 not in c48.open_observation_numbers(obs)


def test_unrelated_section_header_resets_ownership():
    # "## 무관한 절 제목" 아래의 처분 문단은 직전 관측(7)에 귀속되면 안 된다 —
    # 7은 이미 닫혔으니 여기서 오귀속이 나면 last 갱신(사이클 17)으로 드러난다.
    obs = _parsed()
    assert obs[7]["last"] == 16


def test_bogang_and_recurrence_update_last_cycle_only():
    obs = _parsed()
    assert obs[3]["opened"] == 10 and obs[3]["last"] == 14
    assert obs[8]["last"] == 18
    assert obs[8]["opened"] is None  # 원본 헤더 없이 재발 행만 있는 결손도 조용히 접지 않는다


def test_title_extraction_strips_markup_and_cycle_paren():
    obs = _parsed()
    assert obs[3]["title"] == "태그 있는 원본"
    assert obs[5]["title"] == "후보 태그도 계상 대상이다"


# ---- ㉸ (c268): 제목 추출의 어순 둔감화 — 괄호절-선행 헤더 -----------------------
# 관측 79·80 실측 어순 `## 관측 N (사이클 C, 날짜) — 회부: 제목`에서 구판은
# `body[:rfind("(사이클")]`이 제목 전체를 버려 빈 제목을 인쇄했다(audit-220 §7 ·
# c224 판별). 계약: ① 괄호절 앞이 비면 뒤에서 취한다 ② 태그 어휘(회부/후보)는
# 벗긴다 ③ 표준 어순의 기존 제목은 전건 무접촉 ④ 계상(tagged)은 어순 불문 유지.

PAREN_FIRST = """\
## 관측 79 (사이클 148, 2026-08-17) — 회부: 계기의 사망과 오염 — 보고가 원인을 복제한다

본문.

## 관측 80 (사이클 149, 2026-08-17) — 후보: 검색은 읽기가 아니다

본문.
"""


def test_paren_first_header_title_is_not_empty_and_tag_stripped():
    obs = c48.parse_observations(PAREN_FIRST)
    assert obs[79]["title"] == "계기의 사망과 오염 — 보고가 원인을 복제한다"
    assert obs[80]["title"] == "검색은 읽기가 아니다"


def test_paren_first_header_tagged_accounting_unaffected():
    obs = c48.parse_observations(PAREN_FIRST)
    assert obs[79]["tagged"] is True and obs[80]["tagged"] is True
    assert obs[79]["opened"] == 148 and obs[80]["opened"] == 149


def test_obs_title_pure_function_orders():
    # 표준 어순(앞 구간 우선 — 기존 동작 무접촉) · 무괄호 · 볼드 마커.
    assert c48.obs_title(" — 제목이다 (사이클 10, 유형 판정 회부)") == "제목이다"
    assert c48.obs_title(" — 괄호 없는 제목") == "괄호 없는 제목"
    assert c48.obs_title(" (사이클 12) — **회부: 굵은 제목**") == "굵은 제목"


# ---- 실제 대장: 불변 역사만 단언 (미래 사이클에도 깨지지 않는 술어) ------------------

def _real():
    text = (ROOT / "research" / "devloop" / "frictions.md").read_text(encoding="utf-8")
    return c48.parse_observations(text)


def test_real_obs_79_80_titles_not_empty():
    # ㉸ 판정 채널의 회귀형 — 79·80 원본 헤더는 불변 역사(c148·c149 기재)이므로
    # 제목 비-빈 단언은 미래 사이클에 깨지지 않는다(관측 100 경계 준수).
    obs = _real()
    assert obs[79]["title"] != ""
    assert obs[80]["title"] != ""


def test_real_ledger_has_contiguous_observation_numbers_24_to_59():
    obs = _real()
    assert set(range(24, 60)) <= set(obs)


def test_real_ledger_untagged_originals_are_exactly_the_c107_four_below_60():
    # 원본 헤더는 불변 역사다 — 24~59 구간의 무태그 집합은 영원히 이 넷이다.
    obs = _real()
    untagged = {n for n, o in obs.items() if n < 60 and not o["tagged"]}
    assert untagged == {27, 42, 49, 52}


def test_real_ledger_recorded_exits_stay_recorded():
    # 이미 기재된 회부 이탈(53 헤더 · 56/57 절 내 문단)은 소급 소멸하지 않는다.
    obs = _real()
    exited = {n for n, o in obs.items() if o["exited"]}
    assert {53, 56, 57} <= exited


def test_real_ledger_open_excludes_untagged_and_exited():
    obs = _real()
    opened = set(c48.open_observation_numbers(obs))
    assert opened.isdisjoint({27, 42, 49, 52})
    assert opened.isdisjoint({n for n, o in obs.items() if o["exited"]})


def test_real_ledger_known_partial_disposals_survive():
    # 관측 55(쓰기 규약 하위 항목 재분류)·58(계열 표기, 정식 귀속은 동결에 막힘) —
    # 처분 문단이 실재하되 이탈 마커가 없어 존속하는 실측 반례. 이 문단들은 역사라 불변.
    obs = _real()
    assert obs[55]["partial_disposal"] is True
    assert obs[58]["partial_disposal"] is True


def test_real_ledger_opening_cycles_are_immutable_history():
    obs = _real()
    assert obs[24]["opened"] == 63
    assert obs[52]["opened"] == 94
    assert obs[59]["opened"] == 105
