"""c48_step0_check — 계기 질량 계열 + ㉺·㉷ 어휘 등재 (c271 · audit-270 R2 · F-A 반증 조건).

왜 이 파일이 있는가. audit-270 F-A: 자기 수리 선례의 경계 감시가 계기 큐 계수
(줄어드는 수)만 보는 동안 계기 질량(상설 모듈·회귀 본수 — 늘어나는 수)은 자[尺]
없이 자랐고, 같은 감사가 ㉺·㉷의 `PERMANENT_INSTRUMENT_VOCAB` 미등재(㉶절 «어휘
미등록» 2사이클 인쇄)를 실측했다. 이 파일은 그 두 처치의 계약을 합성 픽스처로 잠근다
(관측 100·106 경계 — 실원장 값을 상수로 박지 않는다).

가장 중요한 단언 셋.

① **질량 자[尺]는 순수 함수다** — `instrument_mass`는 인자 경로만 읽고 값만 잰다.
   문턱·판정 필드가 없다는 것 자체가 계약이다(상수를 발명하면 규약이 된다, c174).

② **정의역 경계** — scripts 축은 `*.py`만, tests 축은 `test_devloop_*.py`만.
   비-devloop 테스트·비-py 파일이 질량에 승차하면 계열이 다른 것을 재게 된다.

③ **어휘 등재는 상태 전이로 검증한다** — ㉺·㉷ 키 존재만이 아니라, 등재 후
   `instrument_citation`이 «어휘 미등록»이 아닌 «적혀 있었다»/«안 적었다»를
   내는지를 합성 roster로 확인한다(등재의 목적이 그 전이다).
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "devloop" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_instrument_mass", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)


def _mkdirs(tmp_path):
    scripts = tmp_path / "scripts"
    tests = tmp_path / "tests"
    scripts.mkdir()
    tests.mkdir()
    return scripts, tests


def test_mass_counts_scripts_and_devloop_tests(tmp_path):
    """계약 ①: 세 축(scripts 본수·회귀 파일 수·test 함수 수)을 값 그대로 잰다."""
    scripts, tests = _mkdirs(tmp_path)
    (scripts / "a.py").write_text("x = 1\n", encoding="utf-8")
    (scripts / "b.py").write_text("y = 2\n", encoding="utf-8")
    (tests / "test_devloop_one.py").write_text(
        "def test_a():\n    pass\n\n\ndef test_b():\n    pass\n", encoding="utf-8")
    (tests / "test_devloop_two.py").write_text(
        "class TestX:\n    def test_c(self):\n        pass\n", encoding="utf-8")
    mass = c48.instrument_mass(str(scripts), str(tests))
    assert mass == {"scripts": 2, "test_files": 2, "test_funcs": 3}


def test_mass_domain_boundary(tmp_path):
    """계약 ②: 비-py·비-devloop 파일은 정의역 밖 — 헬퍼 def는 계수하지 않는다."""
    scripts, tests = _mkdirs(tmp_path)
    (scripts / "a.py").write_text("", encoding="utf-8")
    (scripts / "notes.md").write_text("not code", encoding="utf-8")
    (tests / "test_other_track.py").write_text(
        "def test_alien():\n    pass\n", encoding="utf-8")
    (tests / "test_devloop_one.py").write_text(
        "def helper():\n    pass\n\n\ndef test_a():\n    pass\n", encoding="utf-8")
    mass = c48.instrument_mass(str(scripts), str(tests))
    assert mass == {"scripts": 1, "test_files": 1, "test_funcs": 1}


def test_mass_has_no_verdict_fields(tmp_path):
    """계약 ③: 값 전용 — 문턱·판정·추세 필드가 없다(있으면 상수가 규약이 된다)."""
    scripts, tests = _mkdirs(tmp_path)
    mass = c48.instrument_mass(str(scripts), str(tests))
    assert set(mass) == {"scripts", "test_files", "test_funcs"}


def test_vocab_registered_for_promoted_instruments():
    """계약 ④: ㉺·㉷가 어휘 정본에 등재됐다 — audit-270 R2의 등재 의무 소비."""
    assert "㉺" in c48.PERMANENT_INSTRUMENT_VOCAB
    assert "㉷" in c48.PERMANENT_INSTRUMENT_VOCAB
    # 어휘 규율 승계: ㉮·㉭과 같은 9종 · 마커 자신 포함(느슨 — 과잉 매치 방향)
    for marker in ("㉺", "㉷"):
        vocab = c48.PERMANENT_INSTRUMENT_VOCAB[marker]
        assert len(vocab) == 9
        assert marker in vocab


def test_citation_transitions_after_registration():
    """계약 ⑤: 등재의 효과 — «어휘 미등록»이 아니라 매치 여부로 갈린다."""
    roster = [{"marker": "㉺", "content": "", "disposal": "cN 집행·해소", "embedded": False},
              {"marker": "㉷", "content": "", "disposal": "cN 집행·해소", "embedded": False}]
    row_cited = {"work": "harvest_stat 영수증 블록 발화 · 이동기 재계산 드리프트 0"}
    by_marker = {r["marker"]: r for r in c48.instrument_citation(row_cited, roster)}
    assert by_marker["㉺"]["status"] == "적혀 있었다"
    assert by_marker["㉷"]["status"] == "적혀 있었다"
    row_silent = {"work": "무관한 산문"}
    for rec in c48.instrument_citation(row_silent, roster):
        assert rec["status"] == "안 적었다"
