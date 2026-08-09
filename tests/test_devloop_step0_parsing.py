"""c48_step0_check의 part_a/part_b 파싱 — c64→c81 재이월 부채의 잔여 상환 (c82).

audit-80 §3-(b): "루프의 번호·모드·몸 지문·검산 전부가 이 스크립트 출력에 의존하는데
파서의 절반이 무감시다." c71이 순수 함수 4종(part_n 산술·recall 검산 2종·needle_reach·
compare_fingerprint)을 감시 아래 넣었고, 이 파일이 나머지 둘을 넣는다:

  1. porcelain_changed_paths — 절차 2(영토 검사)의 눈. c64 결함(strip이 첫 행의 X열
     공백을 먹어 변경 1건이 '깨끗함'으로 읽히는 거짓 음성)의 방향을 회귀로 고정한다.
  2. capsule_char_budget — part_b 도달 계측의 자[尺]. 예산을 잘못 읽으면 truncated
     판정과 니들 도달 분모가 통째로 어긋난다.

정직 규약 이력: 거짓 음성 2종(스테이지된 리네임 행 · core.quotepath 8진 이스케이프,
c82 관측 38)은 c82가 **현행 동작 그대로** 단언해 두었고(고치기 전에 기록, 원칙 2),
c83이 처치하면서 그 단언들을 정상 동작 단언으로 교체했다 — 울리라고 둔 종이 울린
기록은 git 이력(5fb80c5)에 있다. 선례: test_crypto의 하위호환 불변식(c73).
"""
import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "devloop" / "scripts" / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_parsing", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)


# ---- porcelain_changed_paths: 정상 경로 ---------------------------------------

def test_unstaged_first_line_keeps_leading_space_column():
    # c64 회귀 그대로: 미스테이지 변경(` M path`)이 첫 행 — X열 공백이 살아 있어야
    # line[3:]이 경로를 온전히 돌려준다. 이것이 run_raw(무-strip)가 존재하는 이유다.
    raw = " M research/devloop/metrics.jsonl\n?? new-note.md\n"
    assert c48.porcelain_changed_paths(raw) == [
        "research/devloop/metrics.jsonl", "new-note.md"]


def test_stripped_input_reproduces_c64_false_negative_direction():
    # 반대 방향 고정: strip된 원문을 주면 첫 행의 경로 첫 글자가 먹힌다 —
    # 존재하지 않는 경로가 되어 하류에서 조용히 탈락(변경 1건 → '깨끗함')하는
    # 바로 그 결함. 이 단언은 "그러니 무-strip 원문을 넣어라"를 기계로 남긴다.
    raw = " M research/devloop/metrics.jsonl\n"
    assert c48.porcelain_changed_paths(raw.strip()) == ["esearch/devloop/metrics.jsonl"]


def test_staged_and_mixed_status_codes():
    raw = "M  a.py\nMM b.py\nA  c.py\nD  d.py\n"
    assert c48.porcelain_changed_paths(raw) == ["a.py", "b.py", "c.py", "d.py"]


def test_untracked_and_quoted_path_with_spaces():
    raw = '?? plain.md\n?? "with space.md"\n'
    assert c48.porcelain_changed_paths(raw) == ["plain.md", "with space.md"]


def test_blank_lines_skipped_and_empty_input_is_empty():
    assert c48.porcelain_changed_paths("") == []
    assert c48.porcelain_changed_paths("\n \n") == []
    assert c48.porcelain_changed_paths("?? x.md\n\n?? y.md\n") == ["x.md", "y.md"]


# ---- porcelain_changed_paths: 관측 38 처치 (c83) — 거짓 음성 2종의 정상 동작 단언 ----

def test_staged_rename_splits_into_both_paths():
    # 관측 38-① 처치: `R  old -> new`는 양쪽 경로로 갈라진다. old는 디스크에 없어
    # 하류 exists에서 걸러지고(D 행과 같은 취급), new가 mtime 검사에 들어간다 —
    # 리네임된 미커밋 WIP가 영토 검사에 보인다. (c82의 현행 단언을 교체한 종.)
    raw = "R  old-name.md -> new-name.md\n"
    assert c48.porcelain_changed_paths(raw) == ["old-name.md", "new-name.md"]


def test_copy_line_also_splits():
    raw = "C  src.md -> dup.md\n"
    assert c48.porcelain_changed_paths(raw) == ["src.md", "dup.md"]


def test_arrow_in_filename_without_rename_code_is_not_split():
    # 상태 코드에 R/C가 없으면 ` -> `가 있어도 가르지 않는다 — 화살표를 품은
    # 평범한 파일명이 리네임으로 오인되는 반대 방향 오류를 막는다.
    raw = " M notes -> plan.md\n"
    assert c48.porcelain_changed_paths(raw) == ["notes -> plan.md"]


def test_quoted_old_path_containing_arrow_splits_at_real_arrow():
    # old가 인용돼 있으면 닫는 인용부호까지가 old다 — 인용 속 ` -> `는 경로의 일부.
    raw = 'R  "a -> b.md" -> c.md\n'
    assert c48.porcelain_changed_paths(raw) == ["a -> b.md", "c.md"]


def test_quotepath_octal_escape_decodes_to_korean():
    # 관측 38-② 처치: 8진 이스케이프가 UTF-8 바이트로 복원된다 — 한국어 파일명이
    # 디스크에 실재하는 문자열로 돌아온다. (c82의 현행 단언을 교체한 종.)
    raw = '?? "\\355\\225\\234\\352\\270\\200.md"\n'
    assert c48.porcelain_changed_paths(raw) == ["한글.md"]


def test_rename_with_quoted_korean_new_path():
    raw = 'R  old.md -> "\\355\\225\\234\\352\\270\\200 \\352\\270\\260\\353\\241\\235.md"\n'
    assert c48.porcelain_changed_paths(raw) == ["old.md", "한글 기록.md"]


def test_escaped_quote_backslash_and_tab_decode():
    assert c48.porcelain_changed_paths('?? "a\\"b.md"\n') == ['a"b.md']
    assert c48.porcelain_changed_paths('?? "a\\\\b.md"\n') == ["a\\b.md"]
    assert c48.porcelain_changed_paths('?? "a\\tb.md"\n') == ["a\tb.md"]


def test_invalid_utf8_octal_does_not_crash_and_roundtrips_bytes():
    # 비UTF-8 바이트는 surrogateescape로 보존된다 — strict는 죽고 replace는 디스크에
    # 없는 다른 경로를 만든다. os.fsencode 왕복으로 원본 바이트가 남았음을 단언한다.
    [p] = c48.porcelain_changed_paths('?? "\\377.md"\n')
    assert os.fsencode(p) == b"\xff.md"


# ---- capsule_char_budget --------------------------------------------------------

def test_budget_underscore_literal():
    assert c48.capsule_char_budget("CAPSULE_CHAR_BUDGET = 1_600\n") == 1600


def test_budget_plain_and_embedded_in_source():
    src = "# hook\nTOP_K = 10\nCAPSULE_CHAR_BUDGET=1600\nMAX = 3\n"
    assert c48.capsule_char_budget(src) == 1600


def test_budget_missing_marker_is_loud_not_silent():
    # 마커 부재가 조용히 기본값으로 접히면 truncated 판정이 거짓 음성이 된다 —
    # 시끄럽게 죽는 현행 성질을 고정한다(모르는 것을 '일치'로 보고하지 않는다).
    with pytest.raises(AttributeError):
        c48.capsule_char_budget("# 예산 상수가 없는 소스")


# ---- task_state_lag: 유동층 대조 (c93, 관측 49) ---------------------------------

def test_lag_detects_the_c93_case():
    # 실제 표본: 원장 마지막은 92인데 세대는 c91 완주본이었다. c92의 절차 5 쓰기가
    # 착지하지 않았고, 그 문면이 정확했기 때문에 실패가 조용했다.
    summary = "[devloop 사이클 91 — 2026-08-10, 일반 사이클(91%10=1) — 완주·커밋 e1ab180+59065f4]"
    assert c48.task_state_lag(92, summary) == (91, "지연")


def test_lag_in_sync_is_the_normal_start_of_a_cycle():
    # 정상 구간: N-1 == ledger_last == 세대 사이클. 이번 사이클은 아직 절차 5 전이다.
    assert c48.task_state_lag(92, "[devloop 사이클 92 — 완주]") == (92, "일치")


def test_lag_ahead_means_step5_ran_but_the_ledger_row_is_missing():
    # 반대 방향의 비대칭 실패 — 유동층은 갱신됐는데 원장 append가 빠진 경우.
    assert c48.task_state_lag(92, "[devloop 사이클 93 — 완주]") == (93, "앞섬(원장 미기재 — 절차 5 미완주 의심)")


def test_lag_without_a_cycle_number_is_undecidable_not_ok():
    # 번호를 못 읽으면 '일치'로 접지 않는다 — compare_fingerprint의 UNKNOWN 규율과 같다.
    state_cycle, verdict = c48.task_state_lag(92, "다른 태스크의 요약문입니다")
    assert state_cycle is None
    assert verdict.startswith("판정 불가")
