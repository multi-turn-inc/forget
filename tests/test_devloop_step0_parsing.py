"""c48_step0_check의 part_a/part_b 파싱 — c64→c81 재이월 부채의 잔여 상환 (c82).

audit-80 §3-(b): "루프의 번호·모드·몸 지문·검산 전부가 이 스크립트 출력에 의존하는데
파서의 절반이 무감시다." c71이 순수 함수 4종(part_n 산술·recall 검산 2종·needle_reach·
compare_fingerprint)을 감시 아래 넣었고, 이 파일이 나머지 둘을 넣는다:

  1. porcelain_changed_paths — 절차 2(영토 검사)의 눈. c64 결함(strip이 첫 행의 X열
     공백을 먹어 변경 1건이 '깨끗함'으로 읽히는 거짓 음성)의 방향을 회귀로 고정한다.
  2. capsule_char_budget — part_b 도달 계측의 자[尺]. 예산을 잘못 읽으면 truncated
     판정과 니들 도달 분모가 통째로 어긋난다.

정직 규약: 알려진 거짓 음성 2종(스테이지된 리네임 행 · core.quotepath 8진 이스케이프,
c82 관측 — frictions.md 미분류 관측 38)은 **현행 동작을 그대로 단언**한다. 고치기 전에
기록(원칙 2)이고, 처치가 오면 이 단언이 울리는 것이 의도다(선례: test_crypto의
하위호환 불변식, c73).
"""
import importlib.util
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


# ---- porcelain_changed_paths: 알려진 거짓 음성 2종 (c82 관측, 현행 동작 단언) ----

def test_known_false_negative_staged_rename_yields_nonpath():
    # 관측 38-①: `R  old -> new`는 통짜 문자열이 되어 os.path.exists에서 조용히
    # 탈락한다. 처치(양쪽 경로 분리) 시 이 단언을 갱신하라 — 울리라고 둔 종이다.
    raw = "R  old-name.md -> new-name.md\n"
    assert c48.porcelain_changed_paths(raw) == ["old-name.md -> new-name.md"]


def test_known_false_negative_quotepath_octal_escape_survives():
    # 관측 38-②: core.quotepath 기본값에서 비ASCII 경로는 8진 이스케이프로 온다.
    # 반환값은 디스크에 없는 문자열이라 하류에서 조용히 탈락 — 한국어 파일명
    # 저장소에서 실질 위험. 처치(-c core.quotepath=off 또는 디코딩) 시 갱신하라.
    raw = '?? "\\355\\225\\234\\352\\270\\200.md"\n'
    assert c48.porcelain_changed_paths(raw) == ["\\355\\225\\234\\352\\270\\200.md"]


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
