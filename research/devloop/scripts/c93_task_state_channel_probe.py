#!/usr/bin/env python3
"""c93 — step0 채널 실패의 1차 증거 진단 (읽기 전용, LOOP.md 원칙 7).

증상. 이 세션(c93)의 `get_task_state(task_id="devloop")`가 **c91 완주본**을 `current`로
서빙했다. 원장의 마지막 행은 c92이고, c92는 커밋 3d1eadc로 완주했으며 그 restore_note는
"record_task_state를 호출했고 배열이 비어 있지 않음을 눈으로 확인했다"고 적고 있다.
셋 중 하나가 참이다:

  (W1) c92가 실제로는 호출하지 않았다      — 원장이 미검증 완료 주장을 실었다(정직 문제)
  (W2) 호출했으나 쓰기가 유실/거부됐다      — 쓰기측 제품 결함
  (W3) 썼으나 읽기가 못 찾는다(스코프/정렬) — 읽기측 제품 결함

부수 증상. `get_task_state(filters={"task_id": {"icontains": "devloop"}})`가 heartbeat·
quant-* 를 포함한 **무필터와 동일한 10행**을 돌려줬다 — 필터가 조용히 무시된다.
그것이 사실이면 (W1)~(W3)을 가르는 진단 도구 자체가 눈이 먼 것이므로 먼저 검사한다.

재현: .venv/bin/python research/devloop/scripts/c93_task_state_channel_probe.py
쓰기 0회. `main()`만 실행하며 실DB(:8000)는 읽기만 한다.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "hooks"))

import forget_turnrecall as hook  # noqa: E402

# c92 완주 시각 앵커 (UTC). 커밋 3d1eadc = 2026-08-10 05:13:20 +0900.
C92_COMMIT_UTC = "2026-08-09T20:13:20Z"
C91_CLAIM_UTC = "2026-08-09T19:31:51Z"


def _states(**args):
    """(rows, err) — 오류 응답도 관측 대상이므로 삼키지 않고 돌려준다."""
    try:
        return (hook._rpc("get_task_state", args, timeout=40) or {}).get("results") or [], None
    except Exception as exc:  # noqa: BLE001 — 거부/무시의 구분이 이 진단의 요지다
        return [], f"{type(exc).__name__}: {exc}"


def _ids(rows):
    return [str(r.get("task_id") or "?") for r in rows]


def part_a():
    """필터가 집행되는가 — 같은 호출, filters만 다르게."""
    print("[A. get_task_state.filters 집행 여부]")
    base, _ = _states(limit=10)
    print(f"  {'무필터':28s} n={len(base):<3} {_ids(base)}")

    cells = [
        ("task_id 평문 'devloop'", {"task_id": "devloop"}),
        ("task_id icontains", {"task_id": {"icontains": "devloop"}}),
        ("task_id 존재하지 않는 값", {"task_id": "__없는태스크__"}),
        ("goal_id 존재하지 않는 값", {"goal_id": "__없는목표__"}),
        ("status(허용 키 아님)", {"status": "completed"}),
        ("완전 미지의 키", {"__nope__": "x"}),
    ]
    for label, flt in cells:
        rows, err = _states(limit=10, filters=flt)
        if err:
            mark = f"**거부됨** ({err[:60]})"
        elif _ids(rows) == _ids(base):
            mark = "**무시됨** (무필터와 동일)"
        else:
            mark = f"집행됨 → {_ids(rows)}"
        print(f"  filters={label:24s} n={len(rows):<3} {mark}")
    print("  ※ 미지의 키는 거부되는데 허용 키가 무시된다면, 그것이 최악의 조합이다 —")
    print("    호출자는 '검증을 통과했으니 적용됐다'고 읽는다(조용한 무집행).")

    print("\n  [대조] 최상위 파라미터 task_id= 는 집행되는가")
    for tid in ("devloop", "heartbeat", "__없는태스크__"):
        rows, err = _states(task_id=tid, limit=5)
        print(f"    task_id={tid:16s} n={len(rows):<3} {err or _ids(rows)}")


def part_b():
    """devloop 상태의 실제 세대 — c92 세대가 스토어에 존재하는가."""
    print("\n[B. devloop task_state 세대 — 무엇이 서빙되는가]")
    rows, _ = _states(task_id="devloop", limit=20)
    print(f"  반환 {len(rows)}건 (c91 claim={C91_CLAIM_UTC} · c92 커밋={C92_COMMIT_UTC})")
    for r in rows:
        summ = " ".join(str(r.get("summary") or "").split())
        cyc = "?"
        for n in (95, 94, 93, 92, 91, 90):
            if f"사이클 {n}" in summ:
                cyc = str(n)
                break
        print(f"    valid_from={r.get('valid_from')}  status={r.get('status'):<10} "
              f"claim={str(r.get('claim_id'))[:8]}  사이클={cyc}")
        print(f"      epoch={r.get('workspace_epoch_id')} pred={r.get('predecessor_epoch_id')}")
        print(f"      summary[:90]={summ[:90]}")
    late = [r for r in rows if str(r.get("valid_from") or "") > C92_COMMIT_UTC]
    print(f"  → c92 커밋 이후에 쓰인 devloop 상태: **{len(late)}건**")
    print("     0건이면 c92의 record_task_state는 스토어에 세대를 남기지 않았다.")


def part_c():
    """스코프 가설 — project 인자가 가리는가."""
    print("\n[C. project 스코프 가설]")
    for proj in (None, "forget", "내-프롬프트를-공유하기-싫어"):
        args = {"task_id": "devloop", "limit": 5}
        if proj is not None:
            args["project"] = proj
        rows, _ = _states(**args)
        vf = [str(r.get("valid_from")) for r in rows]
        print(f"  project={str(proj):24s} n={len(rows):<3} valid_from={vf}")
    print("  ※ 어느 스코프에서도 c92 세대가 안 나오면 '읽기 스코프' 가설은 배제된다.")


def part_d():
    """쓰기 흔적 — c92 시각대에 task_state류 기억/이벤트가 있는가."""
    print("\n[D. c92 시각대의 쓰기 흔적]")
    res = hook._rpc("search_memories", {
        "query": "devloop 사이클 92 얼어붙은 트리오 진단 완주 커밋 3d1eadc",
        "top_k": 40, "recall": "low",
    }, timeout=40).get("results") or []
    c92rows = [r for r in res if "사이클 92" in str(r.get("memory") or "")]
    print(f"  search_memories: 반환 {len(res)}건 · '사이클 92' 포함 {len(c92rows)}건")
    for r in c92rows[:6]:
        m = " ".join(str(r.get("memory") or "").split())
        print(f"    created={r.get('created_at')} len={len(m):<5} {m[:80]}")
    after = [r for r in res if str(r.get("created_at") or "") >= C91_CLAIM_UTC.replace("Z", "")]
    print(f"  c91 claim 이후 생성된 반환행: {len(after)}건 "
          f"(= c92가 add_memory는 성공했다는 독립 증거)")


def part_e():
    """이벤트 원장 — c92 시각대에 task_state 쓰기 시도의 흔적이 있는가.

    (W1) 미호출과 (W2) 호출-후-유실을 가르는 유일한 1차 증거원이다.
    c91 claim의 source_event_ids=[68955ef6…]가 보여주듯 성공한 쓰기는 이벤트를 남긴다.
    """
    print("\n[E. 이벤트 원장 — 호출 흔적]")
    try:
        ev = hook._rpc("list_events", {"page": 1, "page_size": 50}, timeout=40)
    except Exception as exc:  # noqa: BLE001
        print(f"  list_events 거부/실패: {type(exc).__name__}: {exc}")
        return
    rows = ev.get("events") or ev.get("results") or (ev if isinstance(ev, list) else [])
    if not rows:
        print(f"  반환 형태 미상 — 키={list(ev)[:8] if isinstance(ev, dict) else type(ev)}")
        return
    print(f"  반환 {len(rows)}건 · 첫 행 키={list(rows[0])[:10]}")
    win = []
    for r in rows:
        ts = str(r.get("created_at") or r.get("timestamp") or "")
        kind = str(r.get("event_type") or r.get("kind") or r.get("type") or "?")
        print(f"    {ts:26s} {kind:24s} {str(r.get('id'))[:8]}")
        if "2026-08-09T20" <= ts or "2026-08-09T19:3" <= ts:
            win.append((ts, kind))
    print(f"  → c91 claim~현재 창의 이벤트: {len(win)}건")


def main():
    print(f"c93 step0 채널 진단 — 읽기 전용 · 대상 :8000 · 앵커 c92커밋={C92_COMMIT_UTC}\n")
    part_a()
    part_b()
    part_c()
    part_d()
    part_e()
    print("\n[판정 규칙] B가 0건 && D가 add_memory 성공을 보이면:")
    print("  c92는 같은 세션에서 add_memory는 성공하고 record_task_state만 실패/미호출했다.")
    print("  A가 '무시됨'이면 그 실패를 다음 세션이 진단할 도구도 함께 눈이 멀어 있었다.")


if __name__ == "__main__":
    main()
