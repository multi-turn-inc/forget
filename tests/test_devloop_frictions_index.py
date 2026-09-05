"""계기 큐 ㉻ — frictions 인덱스 생성기 회귀 (c272 집행).

계약 (합성 픽스처만 — 관측 100·106 경계: 실대장 값을 상수로 잠그지 않는다):
① header_kind 단일 술어 — 표준/처분/어순-변형 헤더 3종 판별 (c48 추출분)
② origin_lines — 원본 헤더만 등재·어순-변형 처분 헤더 미등재 (관측 76 승계)
③ build_index 상태 3값 — 존속/이탈/무태그가 parse_observations·open과 정합
④ format_index 머리말 계약 — 비정본 선언·생성 시각·원본 sha 3요소 강제
⑤ 결정성 — 같은 입력·같은 인자면 바이트 동일 (재생성 가능 술어의 실행형)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                "research", "devloop", "scripts"))
from c48_step0_check import header_kind  # noqa: E402
from frictions_index import build_index, format_index, origin_lines  # noqa: E402

SYNTH = """\
## 관측 1 — 첫 관측 (사이클 10, 회부: 유형 A)

본문.

## 관측 2 (사이클 11) — 회부: 괄호절 선행 제목

본문.

**처분 (사이클 12): 종결.** 근거.

## 관측 3 수용 기준 ③ 처분 — 어순 변형 (사이클 13)

이 헤더는 원본이 아니다.

## 관측 3 — 실제 원본 (사이클 12, 후보)

본문 있음.

**처분 (사이클 13): 이행 기록이지 종결이 아니다.**

## 관측 4 — 무태그 관측 (사이클 14)

계상 밖.
"""


def test_header_kind_three_shapes():
    assert header_kind("## 관측 1 — 제목 (사이클 10, 회부)") == (1, "원본")
    assert header_kind("## 관측 3 수용 기준 ③ 처분 — 변형 (사이클 13)") == (3, "처분")
    assert header_kind("## 관측 5 보강 (사이클 20)") == (5, "보강")
    assert header_kind("본문 행") is None


def test_origin_lines_skip_disposal_order_variant():
    lines = origin_lines(SYNTH)
    assert lines[1] == 1
    assert lines[2] == 5
    # 관측 3: 어순-변형 처분 헤더(11행)가 아니라 실제 원본(15행)이 등재된다
    assert lines[3] == 15
    assert lines[4] == 21


def test_build_index_status_three_values():
    rows = {r["num"]: r for r in build_index(SYNTH)}
    assert rows[1]["status"] == "회부 존속"
    assert rows[2]["status"] == "회부 이탈"
    # 관측 3: 부정 문맥 처분("종결이 아니다")은 이탈 아님 — 존속·처분文有
    assert rows[3]["status"] == "회부 존속·처분文有"
    assert rows[4]["status"] == "무태그"
    assert rows[2]["title"] == "괄호절 선행 제목"


def test_format_index_header_contract():
    doc = format_index(build_index(SYNTH), "abc123", "2026-01-01T00:00:00Z",
                       "research/devloop/frictions.md", 30)
    head = doc.splitlines()[:7]
    joined = "\n".join(head)
    assert "정본 아님" in joined and "재생성 가능" in joined
    assert "sha256 `abc123`" in joined
    assert "2026-01-01T00:00:00Z" in joined
    assert "A-245.1" in joined  # 감사 사용 금지 문면 — 승인 전 규율의 배달 채널


def test_format_deterministic():
    args = (build_index(SYNTH), "abc123", "2026-01-01T00:00:00Z", "x.md", 30)
    assert format_index(*args) == format_index(*args)
