"""c48_step0_check._ordinal_series — 서수 계열 추출의 필드 경계 (c166 수리, 관측 93 · P50).

왜 이 파일이 있는가. 파트 O(P46 처치)는 원장에서 "N사이클째" 계열을 뽑아 선언 앵커와
자기 대조하고 이탈을 인쇄한다. 그 추출이 **`json.dumps(row)` 한 줄을 스캔**했다.

직렬화는 값 안의 개행을 `\\n` **2문자**로 이스케이프한다 — 즉 직렬화본에는 실개행이
**0개**다. 앵커 패턴들은 하나같이 `[^\\n]{0,N}` 창으로 "같은 줄 안에서만 본다"를
표현했는데, 그 창이 종료 조건을 잃고 **필드 경계를 자유롭게 넘었다.**

실측 피해(c166 발견): 원장 c164 행에서 `predictions_note` 말미의 낱말 **"영토"**가
다음 필드 `gate_pending` 서두의 **서비스율 값 49**를 삼켜, 봉쇄 라벨(start c127)에
함의 앵커 c116짜리 **유령 이탈 1건**을 인쇄했다. 그 유령은 c165 `task_state`를 거쳐
c166에게 *"P46 (a)는 반증이다"*로 인계됐다 — 관측 74의 모양(파서의 거짓 값이 손
판정을 통과해 사실로 굳는다). 판정 직전에 잡혔고, 이 파일이 그 자리를 고정한다.

이 테스트가 지키는 계약 둘:
① **필드 경계는 넘지 않는다** — 앵커 낱말과 서수가 다른 필드면 매치 아님.
② **행당 1표본** — 한 행의 여러 필드가 같은 라벨을 인쇄해도 첫 매치만 쓴다.
   (구판과 동일한 계약이다. 행 수로 정규화되지 않으면 앵커 최빈값이 왜곡된다.)
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "devloop" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_ordinals", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)

BLOCKADE = c48.ORDINAL_ANCHORS[0][2]   # (?:미커밋|잔존|영토)…(\d+)사이클째
SERVICE = c48.ORDINAL_ANCHORS[1][2]    # 서비스율…(\d+)사이클째


def test_anchor_word_does_not_reach_across_fields():
    """c164 회귀 — 앵커 낱말과 서수가 다른 필드에 있으면 계열에 들어가지 않는다."""
    row = {
        "cycle": 164,
        "predictions_note": "…해당 절은 영토, 무수정).",
        "gate_pending": "**c164 정산 = 신규 상신 0 · 서비스율 0(49사이클째)**",
    }
    assert c48._ordinal_series([row], BLOCKADE) == []


def test_the_swallowed_value_still_belongs_to_its_own_label():
    """같은 행에서 서비스율 라벨은 제 값을 정상 인쇄한다 — 삼켜진 쪽은 피해자가 아니다."""
    row = {
        "cycle": 164,
        "predictions_note": "…해당 절은 영토, 무수정).",
        "gate_pending": "**c164 정산 = 신규 상신 0 · 서비스율 0(49사이클째)**",
    }
    assert c48._ordinal_series([row], SERVICE) == [(164, 49)]


def test_in_field_match_is_still_found():
    """수리가 참 양성을 죽이지 않았는지 — c162 실문면."""
    row = {
        "cycle": 162,
        "tests": "**타 트랙 미커밋 5건 동일 구성 = 파트 O 인쇄 36사이클째**[start c127]",
    }
    assert c48._ordinal_series([row], BLOCKADE) == [(162, 36)]


def test_newline_inside_a_field_still_bounds_the_window():
    """필드 **안**의 실개행은 여전히 창을 끊는다 — `[^\\n]`의 본래 의도."""
    row = {"cycle": 200, "work": "미커밋 잔존\n" + "x" * 5 + "77사이클째"}
    assert c48._ordinal_series([row], BLOCKADE) == []


def test_one_sample_per_row_even_when_two_fields_print_it():
    """행당 1표본 계약 — 두 필드가 같은 라벨을 인쇄해도 첫 매치만."""
    row = {
        "cycle": 162,
        "tests": "미커밋 5건 36사이클째",
        "work": "미커밋 5건 36사이클째",
    }
    assert c48._ordinal_series([row], BLOCKADE) == [(162, 36)]


def test_non_string_fields_are_skipped_without_error():
    """원장 행에는 int·null·중첩 객체가 섞인다 — 스캔이 거기서 죽으면 안 된다."""
    row = {
        "cycle": 170,
        "recall_hits": 3,
        "evidence": {"note": "미커밋 잔존 44사이클째"},
        "work": "미커밋 잔존 44사이클째",
    }
    assert c48._ordinal_series([row], BLOCKADE) == [(170, 44)]


def test_real_ledger_c164_has_no_blockade_sample():
    """실 원장 회귀 — 수리 후 c164는 봉쇄 계열에 없다(그 행은 그 라벨을 인쇄하지 않았다)."""
    rows = c48._ledger_rows()
    by_cycle = {int(r["cycle"]): r for r in rows}
    assert 164 in by_cycle, "원장에 c164 행이 없다 — 이 테스트의 전제가 깨졌다"
    series = dict(c48._ordinal_series([by_cycle[164]], BLOCKADE))
    assert series == {}


def test_real_ledger_blockade_series_agrees_with_declared_anchor():
    """수리 후 봉쇄 계열의 모든 표본이 선언 앵커 c127과 일치하는가 — P46 (a)의 기계 확인."""
    label, start, pattern = c48.ORDINAL_ANCHORS[0]
    rows = c48._ledger_rows()
    series = c48._ordinal_series(rows, pattern)
    recent = [(c, o) for c, o in series
              if c > max(x for x, _ in series) - c48.ORDINAL_WINDOW]
    assert recent, "봉쇄 계열이 비었다 — 정규식이 원장 문면과 갈렸다"
    post = [c for c, o in recent
            if c - o + 1 != start and c >= c48.ORDINAL_TREATMENT_CYCLE]
    assert post == [], f"처치({c48.ORDINAL_TREATMENT_CYCLE}) 이후 이탈: {post}"
