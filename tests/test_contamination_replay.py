"""오염 재현 — 2026-09-01 «잘못된 강의 스크립트» 사건의 회귀 테스트.

사건: 기계 녹취(출처 신뢰도 최하)를 에이전트가 요약해 add_memory로 넣었고,
«패스트 5기(퓨처플레이)·8/31 자정 마감·9/4 첨삭» 같은 행동급 사실(일정·마감)이
yellow 라벨을 단 채 검색 1위로 돌아왔다. 라벨은 있었고, 읽는 쪽이 그 위에
마감 스프린트를 세웠다. 정훈은 KAIST OverEdge 참가자였다.

이 파일은 두 층이다.
① 특성화(characterization) — 지금 시스템이 실제로 하는 일을 사실로 박제한다.
   (통과해야 한다. 통과하지 않으면 재현이 아니다.)
② 계약(contract) — 라벨(조언)이 아니라 구조(차단·검역)가 있어야 한다는 요구.
   지금은 빨강이어야 정상이다. 초록이 되는 가장 작은 변경이 다음 일이다.
"""
from __future__ import annotations

import os
import re

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-contamination.sqlite3")

import pytest  # noqa: E402

from forget.db import init_db  # noqa: E402
from forget.store import add_memories, search_memories  # noqa: E402

OWNER = "owner-replay"
FILTERS = {"user_id": OWNER}

# 정훈이 직접 말한 것 (green).
TRUE_FACT = "정훈은 KAIST OverEdge 참가자다 (E-02, 대전, 고급반)."

# 오염원 원문 — 2026-08-30 10:39 이벤트 6c87a737에서 실제로 저장된 문장을 그대로 재생.
CONTAMINATED = (
    "패스트 5기(퓨처플레이 운영, 정훈=E02) 1차 오디션 일정 (2026-08-29 특강 공지, 안용주): "
    "①IR 덱 구글폼 제출 8/31(월) 자정 마감 — 제출해야만 9/1~9/4 강사 서면 첨삭을 받음 "
    "②첨삭 9/4(금) 오후 개별 메일 수신 ③수정본+동영상 9/7(월) 제출 "
    "④1차 오디션 = 비대면 서면 평가로 50인 선정 ⑤선정 시 9/18(금) 서울 오프라인 워크숍."
)

# 행동급 사실의 최소 씨앗: 날짜·마감·시각·금액. 계약 ②의 판별자.
ACTION_GRADE_RE = re.compile(
    r"\d{1,2}/\d{1,2}|\d{4}-\d{2}-\d{2}|마감|까지|오후\s*\d|오전\s*\d|\d[\d,]*원|\$\d",
)


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "c.sqlite3"))
    init_db()


def _ingest(text: str, source_role: str, **metadata):
    payload = {
        "messages": [{"role": "user" if source_role == "user" else "assistant", "content": text}],
        "user_id": OWNER,
        "source_role": source_role,
        "infer": False,
        "hebbian": False,
    }
    if metadata:
        payload["metadata"] = metadata
    return add_memories(payload)


def _search(query: str) -> list[dict]:
    return search_memories({"query": query, "filters": FILTERS, "top_k": 10})["results"]


def _replay():
    _ingest(TRUE_FACT, "user")
    _ingest(CONTAMINATED, "assistant")  # 사건 그대로: 출처 표시 없음


# ─────────────────────────── ① 재현: 사건 그대로 흘려보내기 ───────────────────────────

def test_incident_replay_false_deadline_now_arrives_gated():
    """사건의 박제. 봉인 전(2026-09-01 이전) 실측:
    오염된 마감이 1위(score 0.69), light=yellow, 앞을 막는 건 note 한 줄, gate 없음.
    봉인 후: 같은 문장은 여전히 회수되지만(격리도 삭제도 아님 — 표시 없는 유입이므로)
    trust.gate == confirm_required 를 달고 온다. 라벨이 아니라 구조."""
    _replay()
    hits = _search("오디션 제출 마감 일정")
    assert hits, "재현 실패: 오염 문장이 검색되지 않음"
    top = hits[0]
    assert "8/31" in top["memory"]
    assert top["trust"]["light"] == "yellow"
    assert top["trust"]["gate"] == "confirm_required"
    assert not any("KAIST" in h["memory"] for h in hits[:1])


# ─────────────────────────── ② 계약: 있어야 하는 구조 ───────────────────────────

def test_contract_unconfirmed_action_grade_fact_is_gated_not_advised():
    """일정·마감·금액을 담은 비-green 사실은 plain result로 나오면 안 된다.

    요구: trust.gate == "confirm_required" 를 달거나 needs_confirmation 칸으로
    분리한다. note(조언)는 이 계약을 만족시키지 못한다 — 사건이 그 증명이다.
    """
    _replay()
    for hit in _search("오디션 제출 마감 일정"):
        if hit.get("trust", {}).get("light") == "green":
            continue
        if ACTION_GRADE_RE.search(hit["memory"]):
            assert hit["trust"].get("gate") == "confirm_required" or hit.get("needs_confirmation"), (
                f"비-green 행동급 사실이 조언만 달고 통과: {hit['memory'][:60]}…"
            )


def test_contract_user_vouched_fact_outranks_conflicting_machine_relay():
    """같은 주제(주최 프로그램)에서 green(정훈 직접)이 yellow(기계 중계) 위에 있어야 한다."""
    _replay()
    hits = _search("정훈 오디션 주최 프로그램 참가")
    texts = [h["memory"] for h in hits]
    kaist = next((i for i, t in enumerate(texts) if "KAIST" in t), None)
    fp = next((i for i, t in enumerate(texts) if "퓨처플레이" in t), None)
    assert kaist is not None, "green 사실이 아예 회수되지 않음"
    assert fp is None or kaist < fp, f"기계 중계(yellow)가 정훈 직접 진술(green) 위에 있음: {texts[:3]}"


def test_contract_machine_origin_bulk_ingest_is_quarantined_by_default():
    """녹취·OCR·크롤 같은 기계 유래 유입은 본장부가 아니라 검역층에 들어간다.

    요구: metadata.origin in {transcript, ocr, crawl} 로 들어온 사실은
    기본 검색에서 제외되고(확인 전), 요청 시에만(include_quarantined) 보인다.
    """
    _ingest(TRUE_FACT, "user")
    _ingest(CONTAMINATED, "assistant", origin="transcript")
    default_hits = _search("오디션 제출 마감 일정")
    assert not any("8/31" in h["memory"] for h in default_hits), (
        "기계 유래 사실이 검역 없이 기본 검색에 노출됨"
    )
    opened = search_memories(
        {"query": "오디션 제출 마감 일정", "filters": FILTERS, "top_k": 10, "include_quarantined": True}
    )["results"]
    assert any("8/31" in h["memory"] for h in opened), "검역층을 열어도 보이지 않음 — 삭제가 아니라 격리여야 한다"
