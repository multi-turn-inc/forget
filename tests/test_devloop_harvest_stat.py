"""수확 --stat 계기의 자[尺] — harvest_stat.py 순수 함수 (c151, audit-150 R6).

이 계기는 손 옮겨적기를 대체하러 왔다. 그러므로 **이 계기가 틀리면 계열이 낫는 게
아니라 오차가 기계화된다** — 손 오차는 다음 사이클 HAND가 잡았지만(그래서 Δ−19가
기록에 남았다), 기계 오차는 양쪽에서 같은 값으로 나와 조용해진다.

그래서 여기서 고정하는 것은 두 가지다:
  ① 모르는 값(바이너리)을 0으로 접지 않는다 — 총계에 거짓 사실을 섞지 않는다.
  ② corpus() 스코프 분류가 c129의 정본 상수를 따라간다 — 자[尺] 두 벌 금지.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "devloop" / "scripts" / "harvest_stat.py"
spec = importlib.util.spec_from_file_location("harvest_stat", SCRIPT)
hs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hs)


# ---- parse_numstat -------------------------------------------------------------

def test_numstat_reads_paths_untruncated():
    """`--stat`이 아니라 `--numstat`을 읽는 이유의 회귀 고정.

    `--stat`은 넓은 트리에서 파일명을 `...`로 줄인다 — 옮겨적기 오류를 고치러 와서
    파싱 오류를 심지 않기 위해 탭 구분 기계 형식을 읽는다.
    """
    text = "47\t0\tresearch/devloop/frictions.md\n243\t0\tresearch/devloop/audits/audit-150.md\n"
    assert hs.parse_numstat(text) == [
        (47, 0, "research/devloop/frictions.md"),
        (243, 0, "research/devloop/audits/audit-150.md"),
    ]


def test_binary_files_stay_unknown_instead_of_zero():
    """`-\t-\t경로`를 0으로 접으면 '삽입 0'이라는 거짓 사실이 총계에 섞인다."""
    rows = hs.parse_numstat("-\t-\tresearch/devloop/img.png\n5\t2\ta.md\n")
    assert rows[0][:2] == (None, None)
    assert rows[1][:2] == (5, 2)


def test_blank_and_malformed_lines_are_skipped_not_guessed():
    assert hs.parse_numstat("\n\n5\t2\ta.md\ngarbage\n") == [(5, 2, "a.md")]


# ---- parse_shortstat: 독립 2차 읽기 --------------------------------------------

def test_shortstat_matches_the_c150_harvest_receipt():
    """c150 실측 영수증 문면 그대로 — '3 files changed, 291 insertions(+)'."""
    assert hs.parse_shortstat(" 3 files changed, 291 insertions(+)") == (3, 291, 0)


def test_shortstat_absent_clause_is_a_real_zero():
    """삭제 절 부재는 git이 명시한 '없음'이라 접어도 안전하다 — '못 봄'과 다르다."""
    assert hs.parse_shortstat(" 1 file changed, 4 insertions(+), 2 deletions(-)") == (1, 4, 2)
    assert hs.parse_shortstat(" 1 file changed, 2 deletions(-)") == (1, 0, 2)


# ---- classify_scope: 사각의 크기 -----------------------------------------------

def test_scope_split_reproduces_the_c150_blind_spot():
    """c150 = 감사문 +243행 **전량이 코퍼스 밖**이었다. 그 형상을 자[尺]로 고정한다."""
    rows = [(47, 0, "research/devloop/frictions.md"),
            (243, 0, "research/devloop/audits/audit-150.md"),
            (1, 0, "research/devloop/metrics.jsonl")]
    inside, outside = hs.classify_scope(rows, hs.CORPUS_PATHS)
    assert [p for _, _, p in inside] == ["research/devloop/frictions.md"]
    assert [p for _, _, p in outside] == ["research/devloop/audits/audit-150.md",
                                          "research/devloop/metrics.jsonl"]


def test_scope_constant_is_imported_not_redeclared():
    """정본은 c129.CORPUS_PATHS 하나다 — 두 벌이면 관측 30·34의 다음 표본이 된다."""
    from c129_negative_claims import CORPUS_PATHS as canonical
    assert hs.CORPUS_PATHS is canonical


# ---- format_denominator_block: R6의 산출물 -------------------------------------

def test_paste_block_carries_the_line_is_not_a_sentence_caveat():
    """행≠문장(SENT_SPLIT 재분절)은 c146·c148이 실측한 함정이다 — 블록이 달고 나간다."""
    block = hs.format_denominator_block(
        "abc1234def", "loop(cycle 150): ...",
        [(47, 0, "research/devloop/frictions.md"),
         (243, 0, "research/devloop/audits/audit-150.md")],
        hs.CORPUS_PATHS, 151)
    assert "행 수는 문장 수가 아니다" in block
    assert "corpus(151) 직호출" in block
    assert "총 290 삽입" in block
    assert "abc1234" in block and "abc1234def" not in block


def test_paste_block_names_the_blind_spot_explicitly():
    block = hs.format_denominator_block(
        "0000000", "s", [(1, 0, "research/devloop/metrics.jsonl")], hs.CORPUS_PATHS, None)
    assert "코퍼스 내 = 없음" in block
    assert "metrics.jsonl +1" in block
    assert "corpus(N) 직호출" in block
