"""#2 회귀: 인용쌍 내부에서 조각이 갈리지 않는다."""
from forget.memory_engine import split_sentences


def test_korean_quote_stays_atomic() -> None:
    # 이슈 재현 형태: `"<인용>. <인용>"는 <서술>` — 인용 내부 마침표에서 갈리던 케이스
    text = '그는 "관측이 답이다. 검증은 절차다"는 가설을 세웠다.'
    parts = split_sentences(text)
    assert len(parts) == 1, parts
    assert '"관측이 답이다. 검증은 절차다"는' in parts[0]
    assert not any(p.startswith("검증은 절차다\"") for p in parts)


def test_english_quote_stays_atomic() -> None:
    text = 'She said "It failed. Retry later" and moved on. The second sentence is here.'
    parts = split_sentences(text)
    assert len(parts) == 2, parts
    assert '"It failed. Retry later"' in parts[0]


def test_curly_and_cjk_bracket_quotes() -> None:
    assert len(split_sentences("그가 “좋다. 가자”라고 했다.")) == 1
    assert len(split_sentences("보고서는 「검증. 봉인」 원칙을 따른다.")) == 1


def test_normal_splitting_unaffected() -> None:
    assert len(split_sentences("First sentence. Second sentence. Third one!")) == 3


def test_apostrophes_do_not_break_splitting() -> None:
    parts = split_sentences("Don't stop here. It's the second sentence.")
    assert len(parts) == 2


def test_unbalanced_quote_still_terminates() -> None:
    # 닫히지 않은 따옴표가 스플리터를 무한 병합으로 몰지 않는지 — 전체가 한 조각이어도 반환은 된다
    parts = split_sentences('He said "unterminated. And more text. Even more.')
    assert parts and "".join(parts)
