"""계기 ㉮(범위∖계수 검산)의 계약 — c188 신설, 관측 117 수용 기준 ③.

왜 이 파일이 있는가. 관측 117은 «corpus(168)~(179) **11본**»이 여섯 절에 재인쇄되는
동안 아무도 `179−168+1`을 계산하지 않아서 났다. 계기가 그 파생을 대신하되, 계기 자신이
조용히 망가지면 같은 병이 한 층 아래에서 재발한다. 이 파일이 그 층을 잡는다.

**실-원장 값을 상수로 박지 않는다** — 관측 100(«회귀가 자기 사이클의 수확에 붉어진다»)과
관측 106(«회귀가 결함을 기대 상태로 잠갔다»)의 선례. 전부 합성 문자열로 검사한다.

계약 넷:
① 동격 서식의 **불일치를 잡는다** — 이것이 관측 117의 실제 서식이다.
② 동격 서식의 **일치를 통과시킨다** — 정정된 문면이 붉어지면 계기가 정직을 벌한다.
③ **내용 주장을 대조하지 않는다** — «범위에 N건»은 b−a+1과 같을 이유가 없다.
   v1이 이것을 대조해 179짝 중 123을 오고발했다(신호:소음 1:2).
④ **맨숫자 범위를 보지 않는다** — v0가 날짜 파편(`08-13`)·행번호 범위를 범위로 읽어
   258짝 중 195를 오고발했다. 거짓 음성을 골랐고 그 선택이 여기 고정된다.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "devloop" / "scripts" / "c188_range_count.py"


def _load():
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("c188_range_count", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    assert SCRIPT.exists(), f"계기 정본이 없다: {SCRIPT}"
    return _load()


def _scan(mod, text):
    return mod.scan_text(text, "합성")


# ── 계약 ① 동격 불일치를 잡는다 (관측 117의 실제 서식) ──────────────────────
@pytest.mark.parametrize("text,span,n", [
    ("분모 정직 병기: corpus(168)~(179) 11본 영구 미감사", 12, 11),
    ("원장 tests 필드 c174~c186 12행 직독", 13, 12),
])
def test_apposition_mismatch_is_flagged(mod, text, span, n):
    rows = _scan(mod, text)
    assert len(rows) == 1, f"동격 짝을 못 떴다: {rows}"
    r = rows[0]
    assert r["span"] == span and r["n"] == n
    assert r["match"] is False


# ── 계약 ② 동격 일치를 통과시킨다 (정정된 문면을 벌하지 않는다) ─────────────
@pytest.mark.parametrize("text", [
    "분모 정직 병기: corpus(168)~(179) 12본 영구 미감사",
    "원장 tests 필드 c174~c186 13행 직독",
    "기적재 하네스 c112~c123 12사이클 연속 3",
])
def test_apposition_match_passes(mod, text):
    rows = _scan(mod, text)
    assert len(rows) == 1, f"동격 짝을 못 떴다: {rows}"
    assert rows[0]["match"] is True


# ── 계약 ③ 내용 주장은 대조하지 않는다 (한계 ④ 처치, v1의 지배적 오탐) ──────
@pytest.mark.parametrize("text", [
    "c157~c160에 승계 채널의 경과값 불일치가 0건",
    "그 감사가 c130~c133 중 3회 열렸다",
    "c165~c170의 «0건 6연속»은 그 6사이클이 안 틀렸다는 뜻이다",
])
def test_containment_claims_are_not_compared(mod, text):
    assert _scan(mod, text) == [], "내용 주장을 크기 주장으로 대조했다 — v1 회귀"


# ── 계약 ④ 맨숫자 범위는 보지 않는다 (v0의 소음원, 거짓 음성을 골랐다) ──────
@pytest.mark.parametrize("text", [
    "세션1(회고 본문 필자, 08-13 13:35 개시) 35개",
    "workspace dup을 admit한다(6280-6285, turnrecall과 정반대) 1건",
])
def test_bare_numeric_ranges_are_ignored(mod, text):
    assert _scan(mod, text) == [], "맨숫자 범위를 계열 범위로 읽었다 — v0 회귀"


# ── 자기 서술 계약: 선언된 한계가 문서에 살아 있는가 (관행 ⑮) ───────────────
def test_declared_limits_are_present(mod):
    doc = mod.__doc__ or ""
    for mark in ["한계", "닫힌 범위", "고발이 아니라", "맨숫자 범위"]:
        assert mark in doc, f"선언된 한계가 문서에서 사라졌다: {mark}"
