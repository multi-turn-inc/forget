"""텍스트 세계모델 v0 — 상태 코어 계약 테스트.

핵심 계약: 분리 원칙 A(관측 ↔ 상태) — tick()은 관측 없이 시간만으로 전이하고,
문턱은 반열림이 아니라 '이상(≥)' — 정확히 STALE_AFTER_S 초에 낡음이 된다
(시각 경계 규율: 경계 포함 여부를 테스트가 문서화한다).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from forget.worldmodel import STALE_AFTER_S, dismiss, expectations, rebuild, tick

NOW = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def _ledger(tmp_path, rows):
    path = str(tmp_path / "ledger.sqlite3")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE memories (id TEXT, memory TEXT, metadata TEXT,"
        " created_at TEXT, updated_at TEXT, deleted INTEGER DEFAULT 0)"
    )
    for r in rows:
        conn.execute("INSERT INTO memories VALUES (?,?,?,?,?,?)", r)
    conn.commit()
    conn.close()
    return path


def _mem(mid, text, light, created, superseded=False, kind="action_report", deleted=0):
    meta = {"trust": {"kind": kind, "light": light}}
    if superseded:
        meta["superseded_by"] = "x"
    return (mid, text, json.dumps(meta), created, created, deleted)


def test_rebuild_opens_yellow_and_closes_green_red(tmp_path):
    ledger = _ledger(tmp_path, [
        _mem("m1", "배포했다고 보고", "yellow", "2026-08-20T00:00:00Z"),
        _mem("m2", "확정된 완료", "green", "2026-08-20T00:00:00Z"),
        _mem("m3", "철회된 주장", "yellow", "2026-08-20T00:00:00Z", superseded=True),
        _mem("m4", "지워진 행", "yellow", "2026-08-20T00:00:00Z", deleted=1),
        _mem("m5", "고리 아님(fact)", "yellow", "2026-08-20T00:00:00Z", kind="fact"),
    ])
    world = str(tmp_path / "world.sqlite3")
    stats = rebuild(world, ledger, now=NOW)
    assert stats["seen"] == 3  # m4 deleted, m5 kind 불일치 제외
    conn = sqlite3.connect(world)
    status = dict(conn.execute("SELECT id, status FROM loops"))
    assert status == {"loop-m1": "open", "loop-m2": "closed_confirmed",
                      "loop-m3": "closed_retracted"}


def test_tick_time_transition_boundary_is_inclusive(tmp_path):
    just_stale = NOW - timedelta(seconds=STALE_AFTER_S)          # 정확히 문턱
    not_yet = NOW - timedelta(seconds=STALE_AFTER_S - 1)          # 1초 모자람
    ledger = _ledger(tmp_path, [
        _mem("old", "14일 된 주장", "yellow", just_stale.strftime("%Y-%m-%dT%H:%M:%SZ")),
        _mem("new", "13일23시간 주장", "yellow", not_yet.strftime("%Y-%m-%dT%H:%M:%SZ")),
    ])
    world = str(tmp_path / "world.sqlite3")
    # 재구축 시점을 과거로 두어 둘 다 open으로 태어나게 한다
    rebuild(world, ledger, now=not_yet + timedelta(seconds=1))
    moved = tick(world, now=NOW)
    assert moved == 1
    conn = sqlite3.connect(world)
    status = dict(conn.execute("SELECT id, status FROM loops"))
    assert status["loop-old"] == "stale"
    assert status["loop-new"] == "open"
    causes = list(conn.execute(
        "SELECT cause FROM transitions WHERE loop_id='loop-old' AND to_status='stale'"))
    assert causes == [("time",)]  # 관측 없는 전이 — 원인이 명시 기록된다


def test_rebuild_is_idempotent_and_preserves_opened_at(tmp_path):
    ledger = _ledger(tmp_path, [_mem("m1", "주장", "yellow", "2026-08-01T00:00:00Z")])
    world = str(tmp_path / "world.sqlite3")
    rebuild(world, ledger, now=NOW)
    rebuild(world, ledger, now=NOW + timedelta(hours=1))
    conn = sqlite3.connect(world)
    rows = list(conn.execute("SELECT opened_at FROM loops"))
    assert rows == [("2026-08-01T00:00:00Z",)]
    # 상태 불변 재구축은 전이를 다시 쌓지 않는다 (최초 rebuild 1건뿐)
    n_tr = conn.execute("SELECT count(*) FROM transitions").fetchone()[0]
    assert n_tr == 1


def test_observation_closes_after_time_staled(tmp_path):
    """시간으로 낡은 고리가 관측(green 확정)으로 종결되는 전체 생애주기."""
    ledger = _ledger(tmp_path, [_mem("m1", "주장", "yellow", "2026-07-01T00:00:00Z")])
    world = str(tmp_path / "world.sqlite3")
    rebuild(world, ledger, now=NOW)  # 54일 경과 → 곧바로 stale로 태어남
    conn = sqlite3.connect(world)
    assert conn.execute("SELECT status FROM loops").fetchone()[0] == "stale"
    conn.close()
    ledger2 = _ledger(tmp_path.joinpath("2").mkdir() or tmp_path / "2",
                      [_mem("m1", "주장", "green", "2026-07-01T00:00:00Z")])
    rebuild(world, ledger2, now=NOW + timedelta(hours=1))
    conn = sqlite3.connect(world)
    assert conn.execute("SELECT status FROM loops").fetchone()[0] == "closed_confirmed"
    tr = list(conn.execute("SELECT from_status, to_status, cause FROM transitions ORDER BY at"))
    assert tr[-1] == ("stale", "closed_confirmed", "observation")


def test_expectations_rank_oldest_first_and_skip_closed(tmp_path):
    ledger = _ledger(tmp_path, [
        _mem("a", "오래된 주장", "yellow", "2026-07-01T00:00:00Z"),
        _mem("b", "새 주장", "yellow", "2026-08-23T00:00:00Z"),
        _mem("c", "끝난 주장", "green", "2026-07-01T00:00:00Z"),
    ])
    world = str(tmp_path / "world.sqlite3")
    rebuild(world, ledger, now=NOW)
    exps = expectations(world, now=NOW)
    assert [e["loop_id"] for e in exps] == ["loop-a", "loop-b"]
    assert exps[0]["days_open"] == 54
    assert "증거 확인 또는 정정" in exps[0]["expectation"]


# ---- 사건 기관 v0 (시간축 절반: t·정밀도·부분순서) ----

from forget.worldmodel import (add_order_edge, count_events, interval_days,
                               order_of, timeline)


def _event_ledger(tmp_path):
    return _ledger(tmp_path, [
        ("e1", "우쿨렐레 공연 연습 시작", json.dumps({"episode": {"anchor": "우쿨렐레 연습 개시 (2026-07-01)"}}),
         "2026-07-01T09:00:00Z", "2026-07-01T09:00:00Z", 0),
        ("e2", "우쿨렐레 공연 본무대", "{}", "2026-07-15T18:00:00Z", "2026-07-15T18:00:00Z", 0),
        ("e3", "하와이 여행 출발", "{}", "2026-08-01T07:00:00Z", "2026-08-01T07:00:00Z", 0),
    ])


def test_events_rebuild_anchor_title_and_precision(tmp_path):
    world = str(tmp_path / "world.sqlite3")
    stats = rebuild(world, _event_ledger(tmp_path), now=NOW)
    assert stats["events"] == 3
    evs = timeline(world)
    assert [e["id"] for e in evs] == ["ev-e1", "ev-e2", "ev-e3"]  # 시간 오름차순
    assert evs[0]["title"].startswith("우쿨렐레 연습 개시")          # 앵커가 제목
    assert evs[0]["t_precision"] == "second"


def test_timeline_window_is_half_open(tmp_path):
    world = str(tmp_path / "world.sqlite3")
    rebuild(world, _event_ledger(tmp_path), now=NOW)
    # [7/01 09:00, 7/15 18:00) — 시작 포함, 끝 배제 (경계 의미 명시)
    evs = timeline(world, since="2026-07-01T09:00:00Z", until="2026-07-15T18:00:00Z")
    assert [e["id"] for e in evs] == ["ev-e1"]
    assert count_events(world, like="우쿨렐레") == 2


def test_dismiss_requires_receipt_and_hides_expectation(tmp_path):
    # 마찰 #1 수리 계약: 결정 해소는 사유+영수증 의무, 해소된 기대는 밴드에서 사라진다.
    ledger = _ledger(tmp_path, [_mem("m1", "show hn 준비", "yellow",
                                     "2026-07-28T00:00:00Z")])
    world = str(tmp_path / "world.sqlite3")
    rebuild(world, ledger, now=NOW)
    assert len(expectations(world, now=NOW)) == 1
    import pytest
    with pytest.raises(ValueError):
        dismiss(world, "loop-m1", "", "ref")          # 빈 사유 거부
    with pytest.raises(ValueError):
        dismiss(world, "loop-m1", "사유", "  ")       # 빈 영수증 거부
    out = dismiss(world, "loop-m1", "dsh-forget 보류 결정으로 실효",
                  "docs/personal-world-model-design.md 게이트 결정", now=NOW)
    assert out["changed"] and out["status"] == "closed_dismissed"
    assert expectations(world, now=NOW) == []          # 밴드에서 소멸
    conn = sqlite3.connect(world)
    assert conn.execute("SELECT reason FROM dismissals WHERE loop_id='loop-m1'").fetchone()
    assert conn.execute("SELECT cause FROM transitions WHERE loop_id='loop-m1' "
                        "AND to_status='closed_dismissed'").fetchone()[0] == "decision"
    conn.close()


def test_rebuild_preserves_dismissal_until_real_evidence(tmp_path):
    # 관측 > 결정: 원장이 침묵(yellow)이면 dismiss 보존, 진짜 증거(green)가
    # 도착하면 dismiss를 이기고 closed_confirmed로 전이한다.
    ledger = _ledger(tmp_path, [_mem("m2", "미검증 주장", "yellow",
                                     "2026-07-28T00:00:00Z")])
    world = str(tmp_path / "world.sqlite3")
    rebuild(world, ledger, now=NOW)
    dismiss(world, "loop-m2", "결정으로 해소", "결정 기록", now=NOW)
    rebuild(world, ledger, now=NOW)                    # 원장 그대로 → 부활 금지
    conn = sqlite3.connect(world)
    assert conn.execute("SELECT status FROM loops WHERE id='loop-m2'").fetchone()[0] \
        == "closed_dismissed"
    conn.close()
    led = sqlite3.connect(ledger)                      # 원장이 green으로 관측 확정
    led.execute("UPDATE memories SET metadata=? WHERE id='m2'",
                (json.dumps({"trust": {"kind": "action_report", "light": "green"}}),))
    led.commit(); led.close()
    rebuild(world, ledger, now=NOW)
    conn = sqlite3.connect(world)
    assert conn.execute("SELECT status FROM loops WHERE id='loop-m2'").fetchone()[0] \
        == "closed_confirmed"
    conn.close()


def test_standing_hands_lifecycle_and_expiry_visible(tmp_path):
    # 유언장 계약 (자기 하네스 헌장 L3): 등기(왜 의무)→기상 목록→해제(사유 의무).
    # 만료는 조용히 사라지지 않고 expired로 표시된다 — 만료도 정보다.
    from forget.worldmodel import arm_hand, release_hand, standing_hands
    import pytest
    world = str(tmp_path / "world.sqlite3")
    with pytest.raises(ValueError):
        arm_hand(world, "h1", "watch", "감시한다", "", "ref")      # why 없는 손 거부
    with pytest.raises(ValueError):
        arm_hand(world, "h1", "poke", "x", "y", "ref")             # 미정의 kind 거부
    arm_hand(world, "h1", "watch", "llama-server 재기동 억제", "GRPO 훈련이 VRAM 점유 중",
             "run_w2b.sh", expires_at="2026-08-25T06:00:00Z", now=NOW)
    arm_hand(world, "h2", "intent", "판정 후 llama-server 재개", "L2 트랙이 추론 서버 필요",
             "self-harness charter", now=NOW)
    hands = standing_hands(world, now=NOW)
    assert [h["id"] for h in hands] == ["h1", "h2"]
    assert hands[0]["expired"] is False
    late = datetime(2026, 8, 25, 7, 0, tzinfo=timezone.utc)
    assert standing_hands(world, now=late)[0]["expired"] is True   # 만료 표시, 잔존
    with pytest.raises(ValueError):
        release_hand(world, "h1", "  ")                            # 빈 사유 거부
    out = release_hand(world, "h1", "훈련 완주 — 가드 소멸 확인", now=late)
    assert out["changed"] is True
    assert [h["id"] for h in standing_hands(world, now=late)] == ["h2"]
    # 재등기 = 새 생애 (해제 이력 소거)
    arm_hand(world, "h1", "watch", "다시 감시", "새 훈련 시작", "run3", now=late)
    assert "h1" in [h["id"] for h in standing_hands(world, now=late)]
    # DB 없는 읽기 경로는 빈 목록·파일 생성 금지
    ghost = str(tmp_path / "no-world.sqlite3")
    assert standing_hands(ghost) == []
    import os
    assert not os.path.exists(ghost)


def test_strict_events_gate_and_t_rebase(tmp_path):
    # P-WM-3 계약: v1은 ①사건 술어 게이트(선호·프레임 탈락) ②세션 캡처 제외
    # ③본문 발생일로 t 재사상(t_source='body') ④재파생이 탈락분을 지운다.
    ledger = _ledger(tmp_path, [
        ("e1", "P-X 판정을 기각했다 (2026-07-01에 실측)", "{}",
         "2026-08-20T10:00:00Z", "2026-08-20T10:00:00Z", 0),
        ("e2", "정훈은 커피를 좋아한다", "{}",
         "2026-08-21T10:00:00Z", "2026-08-21T10:00:00Z", 0),
        ("e3", "세션 캡처 요약: 서버를 재기동했다",
         json.dumps({"hook": "PreCompact"}),
         "2026-08-22T10:00:00Z", "2026-08-22T10:00:00Z", 0),
    ])
    world = str(tmp_path / "world.sqlite3")
    stats0 = rebuild(world, ledger, now=NOW)               # v0: 전부 사건
    assert stats0["events"] == 3
    stats1 = rebuild(world, ledger, now=NOW, strict_events=True)
    assert stats1["events"] == 1                           # 게이트: e1만
    assert stats1["events_removed"] == 2                   # v0 잔존분 청소
    assert stats1["t_rebased"] == 1
    from forget.worldmodel import timeline
    evs = timeline(world)
    assert [e["id"] for e in evs] == ["ev-e1"]
    assert evs[0]["t"][:10] == "2026-07-01"                # 저장 8/20 → 발생 7/1


def test_dispositions_gate_and_llm_failopen(tmp_path, monkeypatch):
    # P-PF-2 계약: ①결정론 후보 = 선호 어휘 AND (source=user 또는 사용자 주어)
    # ②hook·superseded 제외 ③LLM 게이트 실패 시 후보 그대로(fail-open).
    from forget import worldmodel as wm
    ledger = _ledger(tmp_path, [
        ("d1", "사용자는 아침에 간결한 요약을 선호한다", "{}",
         "2026-08-01T00:00:00Z", "2026-08-01T00:00:00Z", 0),
        ("d2", "파서 어휘 재사용 금지 — 위양성 상속 방지", "{}",     # 주어 없음 → 탈락
         "2026-08-02T00:00:00Z", "2026-08-02T00:00:00Z", 0),
        ("d3", "커피 얘기",
         json.dumps({"trust": {"source": "user"}}),                  # source=user지만 선호 어휘 없음
         "2026-08-03T00:00:00Z", "2026-08-03T00:00:00Z", 0),
        ("d4", "사용자는 팝업을 싫어한다", json.dumps({"hook": "x"}),  # hook → 제외
         "2026-08-04T00:00:00Z", "2026-08-04T00:00:00Z", 0),
    ])
    cards = wm.dispositions(ledger_db=ledger)
    assert [c["stance"] for c in cards] == ["likes"]
    assert "간결한 요약" in cards[0]["text"]
    # LLM 죽음 = fail-open (후보 그대로)
    monkeypatch.setenv("MEM1_HARNESS_DISTILL_URL", "http://127.0.0.1:1/x")
    gated = wm.dispositions(ledger_db=ledger, llm_gate=True)
    assert len(gated) == 1


def test_rumination_guard_blocks_echo_of_released_hand(tmp_path):
    # 되새김 가드 계약 (실측 2026-08-25: 해제 13초 뒤 같은 의도 부활):
    # 시간창 안의 유사 재등기는 새 증거가 아니라 메아리 — 차단된다.
    from forget.worldmodel import arm_hand, recently_released_similar, release_hand
    world = str(tmp_path / "world.sqlite3")
    arm_hand(world, "h1", "intent", "Verify commit 131deb1 exists in the git log",
             "persist 확인", "sess", now=NOW)
    release_hand(world, "h1", "verified — commit exists", now=NOW)
    echo = "Verify the existence of commit 131deb1 using git log"
    assert recently_released_similar(world, echo, now=NOW) == "h1"
    # 무관한 의도는 통과
    assert recently_released_similar(world, "내일 llama-server 온도 로그 수집", now=NOW) is None
    # 시간창(6h) 밖이면 메아리가 아니다 — 재등기 허용
    later = NOW + timedelta(hours=7)
    assert recently_released_similar(world, echo, now=later) is None
    # DB 없음 = 조용히 None (읽기 경로 파일 생성 금지)
    assert recently_released_similar(str(tmp_path / "no.sqlite3"), echo) is None


def test_rebuild_user_scope_isolation(tmp_path):
    # P-WM-2 파생 계약: 다중 스코프 원장(벤치)에서 user_id를 주면 그 스코프의
    # 세계만 파생된다 — 문항 간 사건 누수는 곧 오염된 기대다.
    path = str(tmp_path / "multi.sqlite3")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE memories (id TEXT, memory TEXT, metadata TEXT,"
        " created_at TEXT, updated_at TEXT, deleted INTEGER DEFAULT 0, user_id TEXT)"
    )
    conn.executemany(
        "INSERT INTO memories VALUES (?,?,?,?,?,?,?)",
        [("a1", "user: went hiking at dawn", "{}", "2023-05-01", "2023-05-01", 0, "lme-A"),
         ("a2", "user: hiking again with Sam", "{}", "2023-05-08", "2023-05-08", 0, "lme-A"),
         ("b1", "user: hiking in another world", "{}", "2023-06-01", "2023-06-01", 0, "lme-B")],
    )
    conn.commit()
    conn.close()
    world = str(tmp_path / "world_scoped.sqlite3")
    stats = rebuild(world, path, now=NOW, user_id="lme-A")
    assert stats["events"] == 2
    assert count_events(world, like="hiking") == 2  # lme-B의 사건이 새면 3
    # 무필터는 종전 동작(전체) 유지
    world_all = str(tmp_path / "world_all.sqlite3")
    assert rebuild(world_all, path, now=NOW)["events"] == 3


def test_interval_days_signed_floor(tmp_path):
    world = str(tmp_path / "world.sqlite3")
    rebuild(world, _event_ledger(tmp_path), now=NOW)
    assert interval_days(world, "ev-e1", "ev-e2") == 14
    assert interval_days(world, "ev-e2", "ev-e1") == -14
    assert interval_days(world, "ev-e1", "ev-없음") is None


def test_partial_order_edges_beat_missing_dates(tmp_path):
    world = str(tmp_path / "world.sqlite3")
    rebuild(world, _event_ledger(tmp_path), now=NOW)
    assert order_of(world, "ev-e1", "ev-e2") == "before"   # 시각 비교
    add_order_edge(world, "ev-e3", "ev-e1", source="사용자 진술")
    assert order_of(world, "ev-e3", "ev-e1") == "before"   # 명시 간선이 1순위
    assert order_of(world, "ev-e1", "ev-e3") == "after"
    assert order_of(world, "ev-없음1", "ev-없음2") is None    # 모르는 순서는 지어내지 않음


# ---- 엔티티 기관 v0 (현황 카드 + 무소식 기대) ----

from datetime import timedelta as _td

from forget.worldmodel import entity_card, stale_entities


def _substrate(tmp_path, entities, mentions):
    path = str(tmp_path / "substrate.sqlite3")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE entities (name TEXT, type_id INTEGER, freq INTEGER)")
    conn.execute("CREATE TABLE mentions (memory_id TEXT, entity TEXT)")
    conn.execute("CREATE TABLE edges (src TEXT, relation TEXT, dst TEXT, fact TEXT,"
                 " valid_at TEXT, episode_key TEXT)")
    conn.executemany("INSERT INTO entities VALUES (?,?,?)", entities)
    conn.executemany("INSERT INTO mentions VALUES (?,?)", mentions)
    conn.execute("INSERT INTO edges VALUES ('forget','FUNDED_BY','yc','forget는 yc에 지원했다',"
                 " '2026-07-23', 'ep1')")
    conn.commit()
    conn.close()
    return path


def test_entity_card_latest_facts_exclude_superseded(tmp_path):
    sub = _substrate(tmp_path, [("forget", 2, 3)],
                     [("m1", "forget"), ("m2", "forget"), ("m3", "forget")])
    ledger = _ledger(tmp_path, [
        ("m1", "forget 피봇 확정", "{}", "2026-07-13T00:00:00Z", "2026-07-13T00:00:00Z", 0),
        ("m2", "구판 전략(폐기됨)", json.dumps({"superseded_by": "x"}),
         "2026-07-20T00:00:00Z", "2026-07-20T00:00:00Z", 0),
        ("m3", "세계모델 방향 확정", "{}", "2026-08-24T00:00:00Z", "2026-08-24T00:00:00Z", 0),
    ])
    card = entity_card("forget", substrate_db=sub, ledger_db=ledger)
    assert card["entity"] == "forget"
    facts = [f["fact"] for f in card["current_facts"]]
    assert facts[0] == "세계모델 방향 확정"          # 최신 우선
    assert all("구판" not in f for f in facts)        # superseded 제외
    assert card["relations"][0]["other"] == "yc"      # 간선 카드 병기
    assert card["last_seen"] == "2026-08-24T00:00:00Z"


def test_entity_card_unknown_returns_none(tmp_path):
    sub = _substrate(tmp_path, [("forget", 2, 3)], [])
    ledger = _ledger(tmp_path, [])
    assert entity_card("없는것", substrate_db=sub, ledger_db=ledger) is None


def test_stale_entities_threshold_inclusive_and_ranked(tmp_path):
    quiet_25 = (NOW - _td(days=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    quiet_21 = (NOW - _td(days=21)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fresh = (NOW - _td(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sub = _substrate(tmp_path, [("alpha", 1, 30), ("beta", 1, 20), ("gamma", 1, 15), ("tiny", 1, 2)],
                     [("a1", "alpha"), ("b1", "beta"), ("g1", "gamma"), ("t1", "tiny")])
    ledger = _ledger(tmp_path, [
        ("a1", "alpha 소식", "{}", quiet_25, quiet_25, 0),
        ("b1", "beta 소식", "{}", quiet_21, quiet_21, 0),
        ("g1", "gamma 소식", "{}", fresh, fresh, 0),
        ("t1", "tiny 소식", "{}", quiet_25, quiet_25, 0),
    ])
    out = stale_entities(min_freq=10, stale_days=21, substrate_db=sub,
                         ledger_db=ledger, now=NOW)
    names = [e["entity"] for e in out]
    assert names == ["alpha", "beta"]      # 25일 > 21일(경계 포함) · gamma 신선 · tiny 저빈도 제외
    assert out[0]["days_quiet"] == 25
    assert "무소식" in out[0]["expectation"]


def test_dismiss_entity_hides_from_stale_and_requires_receipt(tmp_path):
    # 마찰 #1의 원 사례가 엔티티 무소식('show hn')이었다 — 결정 해소가
    # stale_entities에서 걸러지고, 영수증 없는 해소는 거부된다.
    from forget.worldmodel import dismiss_entity
    quiet = (NOW - _td(days=27)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sub = _substrate(tmp_path, [("show hn", 1, 30)], [("s1", "show hn")])
    ledger = _ledger(tmp_path, [("s1", "show hn 준비", "{}", quiet, quiet, 0)])
    world = str(tmp_path / "world.sqlite3")
    assert [e["entity"] for e in stale_entities(
        min_freq=10, stale_days=21, substrate_db=sub, ledger_db=ledger,
        now=NOW, world_db=world)] == ["show hn"]
    import pytest
    with pytest.raises(ValueError):
        dismiss_entity(world, "show hn", "사유", "")
    dismiss_entity(world, "show hn", "dsh-forget 보류 결정으로 실효", "게이트 결정 기록", now=NOW)
    assert stale_entities(min_freq=10, stale_days=21, substrate_db=sub,
                          ledger_db=ledger, now=NOW, world_db=world) == []
    # 세계 DB가 아예 없어도 읽기 경로는 조용히 무해소 취급 (파일 생성 금지)
    assert [e["entity"] for e in stale_entities(
        min_freq=10, stale_days=21, substrate_db=sub, ledger_db=ledger,
        now=NOW, world_db=str(tmp_path / "no-such.sqlite3"))] == ["show hn"]
    assert not (tmp_path / "no-such.sqlite3").exists()


# ---- 루틴 기관 v0 (주기 검출 + 부재 기대) ----

from forget.worldmodel import detect_routines, routine_expectations


def _daily_ledger(tmp_path, n_days, start_hour=22, skip_last=0, jitter_min=(0, 5, -3, 8, 2)):
    rows = []
    for i in range(n_days - skip_last):
        t = (NOW - _td(days=(n_days - 1 - i), hours=NOW.hour - start_hour,
                       minutes=NOW.minute - jitter_min[i % len(jitter_min)]))
        ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append((f"hb{i}", f"심장박동 갱신 ({ts[:10]})", "{}", ts, ts, 0))
    rows.append(("noise1", "일회성 사건 하나", "{}", "2026-08-20T03:00:00Z", "2026-08-20T03:00:00Z", 0))
    return _ledger(tmp_path, rows)


def test_daily_routine_detected_with_kst_hour(tmp_path):
    world = str(tmp_path / "world.sqlite3")
    rebuild(world, _daily_ledger(tmp_path, 8), now=NOW)
    routines = detect_routines(world)
    assert len(routines) == 1
    r = routines[0]
    assert r["period"] == "daily" and r["n"] == 8
    assert r["typical_hour_kst"] == (22 + 9) % 24      # UTC 22시 = KST 7시
    assert "심장박동" in r["key"]


def test_routine_absence_becomes_expectation(tmp_path):
    world = str(tmp_path / "world.sqlite3")
    # 마지막 2일 결측(최종 회차 22시Z → 경과 1.58일) → 주기+유예(1.5일) 초과 → 부재 기대
    rebuild(world, _daily_ledger(tmp_path, 9, skip_last=2), now=NOW)
    exps = routine_expectations(world, now=NOW)
    assert len(exps) == 1
    assert exps[0]["missed_cycles"] >= 1
    assert "부재" in exps[0]["expectation"]


def test_irregular_and_sparse_series_are_not_routines(tmp_path):
    rows = []
    for i, days in enumerate([0, 1, 5, 6, 20, 21]):    # 불규칙 간격
        ts = (NOW - _td(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows.append((f"x{i}", "불규칙 회의 기록", "{}", ts, ts, 0))
    rows.append(("s1", "희소 패턴", "{}", "2026-08-01T00:00:00Z", "2026-08-01T00:00:00Z", 0))
    world = str(tmp_path / "world.sqlite3")
    rebuild(world, _ledger(tmp_path, rows), now=NOW)
    assert detect_routines(world) == []
