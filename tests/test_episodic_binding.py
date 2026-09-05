"""Episodic binding: atomization must not strip the topic off a fact.

The disease, measured on the real ledger (2026-08-23): "캐시 배치 실측 완료 (…):
10턴 누적 A 3674 vs B 4601 = 20.1% 절감" was stored as the tail alone — no '캐시',
no '배치', no A/B referent. 21 of 40 recent memories (52%) were fragments like that,
unreachable by topic and undecodable once recalled.

The fix binds the topic back on two surfaces only — the embedding input and the
rendered line. The stored text and the hash stay bare, so dedup, supersede, and
every existing consumer keep their meaning. These tests pin that boundary.
"""
import json
import os
import uuid

import pytest

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-episode.sqlite3")

from forget import store  # noqa: E402
from forget.db import get_db, init_db  # noqa: E402
from forget.memory_engine import anchor_applies, episode_anchor  # noqa: E402
from forget.utils import content_hash  # noqa: E402

LEDGER_STYLE = (
    '캐시 배치 실측 완료 — "안정도가 위치를 정한다"가 증명됐다 (2026-08-23 새벽, /loop 3회차): '
    "10턴 누적 A 3674 vs B 4601 토큰 = 20.1% 절감. 재현은 슬롯 캐시로 확인했다."
)


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "episode.sqlite3"))
    init_db()
    yield


def _rows(user: str) -> list[tuple[str, dict]]:
    with get_db() as conn:
        return [
            (str(r[0]), json.loads(r[1] or "{}"))
            for r in conn.execute(
                "SELECT memory, metadata FROM memories WHERE user_id = ? AND deleted = 0", (user,)
            )
        ]


def _add(text: str, user: str, **extra) -> dict:
    return store.add_memories(
        {"messages": [{"role": "user", "content": text}], "user_id": user,
         "infer": True, "hebbian": False, **extra}
    )


# ── 앵커 유도 (결정적, LLM 없음) ────────────────────────────────────────────

def test_anchor_is_the_topic_declaration_before_the_colon():
    assert episode_anchor(LEDGER_STYLE).startswith("캐시 배치 실측 완료")
    assert "20.1%" not in episode_anchor(LEDGER_STYLE)   # 상세는 앵커가 아니다


def test_colon_inside_parentheses_is_not_a_boundary():
    # 실사례: 첫 콜론이 괄호 안에 있어 경계로 잡으면 앵커가 문장 전체가 된다.
    text = ('DGX Spark(GB10 121GB)은 당분간 다른 실험 전용 — forget 작업에서 쓰지 않는다 '
            '(정훈 지시: "다른 실험중이니까"). 하나의 몸이 내려갔다.')
    anchor = episode_anchor(text)
    assert anchor and "정훈 지시" not in anchor
    assert anchor.startswith("DGX Spark")


def test_single_sentence_gets_no_anchor():
    # 자족적인 원문에는 결합할 맥락이 따로 없다.
    assert episode_anchor("정훈은 매일 아침 드립 커피를 내려 마신다") == ""


def test_one_incidental_word_still_binds():
    # "재현은 슬롯 캐시로 확인했다"가 우연히 '캐시'를 품었다는 이유로 주제를 잃었던 버그.
    anchor = "캐시 배치 실측 완료"
    assert anchor_applies("재현은 슬롯 캐시로 확인했다.", anchor) is True
    assert anchor_applies("캐시 배치는 20.1% 절감이었다", anchor) is False   # 둘 이상 = 자족


# ── 저장 경계: 표시 텍스트와 hash는 불변 ───────────────────────────────────

def test_fragment_carries_its_episode_metadata():
    user = f"ep-{uuid.uuid4().hex[:8]}"
    result = _add(LEDGER_STYLE, user)
    rows = _rows(user)
    assert len(rows) >= 2, "원자화가 일어나지 않았다 — infer=True 경로가 아니다"
    bound = [(text, meta) for text, meta in rows if (meta.get("episode") or {}).get("bound")]
    assert bound, "주제를 잃은 조각이 앵커를 받지 못했다"
    text, meta = bound[0]
    episode = meta["episode"]
    assert episode["event_id"] == result["event_id"]      # 원문으로 돌아가는 길
    assert episode["n"] == len(rows) and 0 <= episode["idx"] < episode["n"]
    assert "캐시 배치" not in text, "저장본에 앵커가 새어 들어갔다 — 렌더에서만 붙어야 한다"


def test_hash_is_derived_from_the_bare_fact_so_dedup_still_works():
    # 결합은 부호화와 렌더에만 실린다. hash가 결합된 텍스트에서 나오면 중복 판정 의미가
    # 바뀌고, 같은 사실을 다시 말한 것이 새 기억으로 쌓인다.
    user = f"ep-{uuid.uuid4().hex[:8]}"
    _add(LEDGER_STYLE, user, sanitize=True)
    rows = _rows(user)
    assert any((meta.get("episode") or {}).get("bound") for _, meta in rows)
    with get_db() as conn:
        stored = list(conn.execute(
            "SELECT memory, hash FROM memories WHERE user_id = ? AND deleted = 0", (user,)))
    for text, digest in stored:
        assert digest == content_hash(text, user, None, None, None)

    # 같은 원문을 다시 넣으면 중복으로 걸러진다 (결합이 dedup을 깨지 않았다).
    # 중복 검사는 sanitize 경로에서만 돌므로 두 번 다 켜서 비교한다.
    again = _add(LEDGER_STYLE, user, sanitize=True)
    assert again["accounting"]["memories_created"] == 0
    assert again["accounting"]["duplicate_skipped"] == len(stored)


def test_binding_can_be_turned_off():
    user = f"off-{uuid.uuid4().hex[:8]}"
    _add(LEDGER_STYLE, user, episode_binding=False)
    assert all(not meta.get("episode") for _, meta in _rows(user))


# ── 읽는 쪽: 렌더가 결합을 복원한다 ────────────────────────────────────────

def test_assembled_line_restores_the_topic():
    user = f"ep-{uuid.uuid4().hex[:8]}"
    _add(LEDGER_STYLE, user)
    result = store.assemble_context(
        {"query": "캐시 배치 실측 결과", "filters": {"user_id": user}, "record_trace": False}
    )
    context = result.get("context") or ""
    assert context, "조립 결과가 비었다"
    fragments = [t for t, m in _rows(user) if (m.get("episode") or {}).get("bound")]
    if fragments and any(f in context or f[:24] in context for f in fragments):
        assert "캐시 배치 실측 완료" in context, "조각이 주제 없이 렌더됐다 — 읽는 쪽이 해독 불가"
