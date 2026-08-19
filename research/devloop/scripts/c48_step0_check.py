#!/usr/bin/env python3
"""사이클 48 계측 — step 0 규약을 문장이 아니라 **실행 가능한 검사**로 (읽기 전용).

두 가지를 잰다.

  (A) 규약 (ii) "HEAD보다 새로운 미커밋 파일" 검사의 **구현 의존성**
      이 체크아웃은 git worktree라 `.git`이 디렉터리가 아니라 포인터 **파일**이다.
      따라서 `find . -newer .git/HEAD`는 참조 파일이 없어 조용히 실패하고 0건을 낸다 —
      즉 항상 "깨끗함"이라고 답하는 거짓 음성 기계다. 워크트리 안전형과 나란히 낸다.

  (B) 규약 도달 계측의 **니들 판본 대조**
      c47이 (iii)의 니들에 "tail 금지"를 추가한 뒤 3/3을 보고했다. 대조군(c46·c47 초측
      1/3)은 확장 전 니들로 쟀으므로, 같은 캡슐을 두 판본으로 재서 확장분을 분리한다.

      **c64 확장 (P19, 가산적 — 기존 자를 치우지 않는다).** V1·V2의 니들은 규약의
      *내용*이 아니라 c47이 목격한 *어휘*를 고정했고, 루프가 같은 지시를 다른 말로 옮겨
      적을 때마다 계측이 조용히 0으로 내려앉았다(거짓 음성 6종째, c62 발견·c64 재확인:
      캡슐이 "번호·모드는 … c48_step0_check.py 첫 줄"을 실제로 날라 그 손이 준수했는데
      capsule_reach=1/3). 방향이 위험한 쪽이다 — **해결된 것을 미해결로 보고**한다.
      그래서 셋을 더한다: V3 의미 니들(표현의 논리합) · **캡슐 원문 인쇄** · sha256.
      V1·V2는 문면 그대로 둔다 — c46~c64 시계열의 비교 가능성이 그 자에 걸려 있다.
      한계(정직): V3도 리터럴의 논리합이라 표류를 늦출 뿐 없애지 못한다. 드리프트에
      대한 실제 방어는 원문 인쇄이고 V3는 시계열 숫자를 잇기 위한 보조다.

규약: 결론 문장을 상수로 인쇄하지 않는다. 숫자와 원문만 낸다.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
INSTALLED_HOOKS = os.path.expanduser("~/.forget/hooks")
FORGET_URL = "http://localhost:8000/mcp/forget/http/junghunkim"
FINGERPRINT_BASELINE = os.path.join(REPO, "research", "devloop", "body-fingerprint.json")
FORGET_DB = os.path.expanduser("~/.forget/forget.sqlite3")
UNKNOWN = "미확인"


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True).stdout.strip()


def run_raw(cmd: list[str]) -> str:
    """strip() 없이 stdout 그대로.

    c64 발견: `git status --porcelain`의 행 형식은 `XY<space><path>`이고 미스테이지
    변경의 X는 **공백**이다(` M path`). `run()`의 `.strip()`은 그 선행 공백을
    **첫 행에서만** 지워 `line[3:]`이 경로의 첫 글자를 먹고, 존재하지 않는 경로가 되어
    조용히 `continue`된다 — 즉 **변경 파일 목록의 첫 항목이 언제나 보이지 않았다**.
    변경 파일이 정확히 1개면 검사는 `0`을 답한다: 절차 2가 막으려는 바로 그 상황
    (타 세션 WIP 1건이 있는데 "깨끗함"으로 읽고 코드 사이클 진입)에서 침묵한다.
    part_a가 폭로하려던 `.git/HEAD` 거짓 음성 기계와 같은 종류의 결함을 part_a 자신이
    갖고 있었다. 형식이 열(column)로 정의된 출력은 strip하지 않는다.
    """
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True).stdout


def call(name: str, arguments: dict) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    req = urllib.request.Request(FORGET_URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    body = json.loads(urllib.request.urlopen(req, timeout=20).read())
    return json.loads(body["result"]["content"][0]["text"])


def cycle_number_and_mode(cycles: list[int]) -> tuple[int, str]:
    """cycle 필드 max+1과 모드. **순수 함수** — part_n의 산술을 테스트 가능하게 분리 (c71).

    part_n/part_a/part_b 파싱 테스트 미커버가 c64→c70 7회 재이월된 부채의 부분 상환:
    번호·모드 산술이 처음으로 회귀 감시 아래 들어간다. 출력 문면은 불변이다.
    """
    n = max(cycles) + 1
    mode = "적대 감사" if n % 10 == 0 else ("회고" if n % 5 == 0 else "일반")
    return n, mode


def task_state_lag(ledger_last: int, summary: str) -> tuple[int | None, str]:
    """원장 마지막 사이클과 task_state 세대의 사이클을 대조한다. **순수 함수** (c93).

    두 원장은 서로 독립이다: metrics.jsonl은 git이 지키는 불변 기록이고, task_state는
    스토어의 유동층이다. 둘이 어긋나는 유일한 정상 구간은 "이번 사이클이 아직 절차 5를
    돌지 않았다"인데, 그 구간은 N-1 == ledger_last로 나타난다. ledger_last보다 **뒤진**
    세대는 정상 구간이 없다 — 그 사이 어느 사이클의 쓰기가 착지하지 못한 것이다.
    """
    match = re.search(r"사이클\s*(\d+)", summary)
    if not match:
        return None, "판정 불가(세대 문면에 사이클 번호 없음)"
    state_cycle = int(match.group(1))
    if state_cycle == ledger_last:
        return state_cycle, "일치"
    if state_cycle < ledger_last:
        return state_cycle, "지연"
    return state_cycle, "앞섬(원장 미기재 — 절차 5 미완주 의심)"


#: 절차 5의 재조회 확인을 보고하는 원장 필드. **구조적으로 영수증이 아니다** — 이 필드가
#: 사는 원장 행은 `원장 append → 커밋 → push → record_task_state → 재조회` 순서(관측 55
#: 수용 기준 ②, c96)에서 **재조회보다 먼저** 쓰인다. 그래서 값은 의도 선언이며, 진위는
#: 다음 사이클의 파트 S만이 판정할 수 있다 (관측 88 · P47).
REVERIFY_FIELD = "step5_write_reverified"

#: 유보 = **주장을 하지 않은 값**(c162~ 서식). 반증될 주장이 없으므로 고발 대상이 아니다.
#: 이 술어는 계열 함수와 라이브 고발 블록이 **함께** 쓴다 — c167 이전에는 사본이 둘이었고,
#: 계열은 유보를 면책하는데 라이브 블록은 같은 행에 `★ 모순`을 찍었다(P47 판정 거짓 양성).
#: 벌한 대상이 하필 **정직**이었다: 유보 서식은 맨 `True`를 쓰지 않으려고 도입된 것인데
#: 그 정직한 유보가 c155·c161의 거짓 `True`와 같은 도장을 받았다. 사본을 하나로 만든다.
DEFERRAL_MARKERS = ("미정", "유보")


def is_deferred(val: object) -> bool:
    """자기보고 값이 **유보**(주장 없음)인가. bool은 주장이므로 유보가 아니다."""
    return not isinstance(val, bool) and any(k in str(val) for k in DEFERRAL_MARKERS)


def reverify_claim_mark(claim: object) -> str:
    """라이브 고발 블록이 누락 구간 각 행에 찍을 도장. 순수 함수 (c167, P51).

    함수로 뺀 이유는 **회귀 아래 두기 위해서**다. c162~c166 동안 이 판단은 인쇄문 안에
    인라인으로 살았고 계열 함수와 사본 관계였다 — 그래서 조용히 갈라졌고, 갈라진 것을
    아무 테스트도 잡지 못했다. 이제 두 경로가 `is_deferred` 하나를 공유하고, 그 공유를
    `tests/test_devloop_step0_reverify.py`가 고정한다.
    """
    if not claim or claim == "**필드 없음**":
        return "  (주장 없음)"
    if is_deferred(claim):
        return "  (유보 — 주장 없음)"
    return "★ 모순"

#: N+1의 restore_note에 인쇄된 파트 S 판정을 읽는 눈. 문면이 바뀌면 **거짓 음성**이고,
#: 그 경우 '무결'이 아니라 '미측정'으로 계상해야 한다 (P47 한계 ③).
RE_PART_S_VERDICT = re.compile(r"판정\s*=\s*(일치|지연|앞섬)")


def reverify_contradictions(rows: list[dict]) -> dict:
    """`step5_write_reverified` 자기보고를 **외부 관측**과 대조한다. 순수 함수 (c162, P47).

    외부 앵커. 사이클 N의 `record_task_state`가 실제로 착지했는지 N 자신은 알 수 없다 —
    보고가 곧 자기 보고이기 때문이다. 아는 것은 **N+1의 파트 S**다(`ledger_last` vs
    `task_state_cycle`). 그 판정은 N+1의 `restore_note`에 인쇄돼 원장에 남는다. 따라서
    원장 하나만으로 자기보고 대 관측의 대조가 가능하다 — 손 증분 없이(P46 (a)의 계승).

    반환의 `unmeasured`가 핵심이다. 파트 S는 c93 처치 이후에만 인쇄되므로 그 이전 행들은
    **모순이 없는 것이 아니라 잴 수 없는 것**이다. 둘을 섞으면 이 계기가 바로 자기가
    고발하는 병(자기보고의 존재를 검사의 존재로 읽기)에 걸린다.

    **`지연`만이 N의 자기보고를 반증한다** (c162 자기 수정). 첫 판본은 "판정 != 일치"를
    모순으로 셌고 c95를 고발했다 — 오판이다. `앞섬`은 `task_state_cycle > ledger_last`,
    즉 세대가 **존재하고 앞서** 있다는 뜻이므로 N의 쓰기는 착지했고, 병은 N+1 세션의
    완주 선기재다(관측 55, c96 실전 첫 발화가 바로 그 자리다). 남의 병으로 N을 고발하면
    관측 74의 모양 — 파서의 거짓 값이 손 판정을 통과해 사실로 굳는다. 그래서 `앞섬`은
    모순이 아니라 **별도 계상**한다.
    """
    by_cycle = {int(r["cycle"]): r for r in rows}
    field_rows = sorted(c for c in by_cycle if REVERIFY_FIELD in by_cycle[c])
    # 값은 세 종류다. bool = **의도 선언**(구조적으로 영수증 불가, 관측 88).
    # 산문 = c93·c94의 claim/epoch id — 그 시점 순서에서는 재조회가 원장 append보다
    # **앞**이었으므로 진짜 영수증이었다. 유보 = 주장을 하지 않은 행(c162~).
    # 셋을 한 칸에 세면 이 계기가 자기가 고발하는 병에 걸린다.
    deferred, prose = [], []
    for c in field_rows:
        val = by_cycle[c][REVERIFY_FIELD]
        if isinstance(val, bool):
            continue
        (deferred if is_deferred(val) else prose).append(c)

    checked = agree = unmeasured = 0
    contradictions: list[tuple[int, str]] = []
    ahead: list[int] = []
    pending: int | None = None
    for c in field_rows:
        nxt = by_cycle.get(c + 1)
        if nxt is None:
            pending = c  # 후속 행이 아직 없다 = 이 세션이 그 후속이다
            continue
        m = RE_PART_S_VERDICT.search(str(nxt.get("restore_note") or ""))
        if not m:
            unmeasured += 1
            continue
        checked += 1
        verdict = m.group(1)
        if verdict == "앞섬":
            ahead.append(c + 1)  # 병은 N+1의 선기재다 — N의 자기보고와 무관
            agree += 1
        elif c in deferred:
            agree += 1  # 주장하지 않은 행은 반증될 주장이 없다
        elif by_cycle[c][REVERIFY_FIELD] and verdict != "일치":
            contradictions.append((c, verdict))
        else:
            agree += 1
    return {
        "field_rows": field_rows,
        "prose_receipts": prose,
        "deferred": deferred,
        "checked": checked,
        "agree": agree,
        "contradictions": contradictions,
        "ahead": ahead,
        "unmeasured": unmeasured,
        "pending": pending,
    }


def part_s() -> None:
    """[S] 유동층 대조 — 원장과 task_state가 같은 사이클을 가리키는가 (c93 처치, 관측 49).

    왜. c92는 완주·커밋했고 원장 c92 행은 "record_task_state를 호출했고 응답의 배열이
    비어 있지 않음을 눈으로 확인했다"고 적었다. 그러나 스토어에 c92 세대는 없었다
    (그 세션 창의 TASK_STATE 이벤트 0건 — c93 1차 증거). 다음 세션은 c91 완주본을
    **현재로** 받았고, 그 문면이 정확하고 최신처럼 보였기에 실패는 소리를 내지 않았다.

    조용한 실패의 방어는 자기 보고가 아니라 계기다: 두 원장이 어긋나면 턴2에 소리가 난다.
    한계(정직): 이 검사는 **직전 사이클의 실패**만 잡는다. 이번 사이클 자신의 절차 5
    쓰기가 착지했는지는 호출 뒤 재조회로만 확인되며, 그 규약을 아래에 함께 인쇄한다.
    """
    ledger_rows = []
    with open(os.path.join(REPO, "research", "devloop", "metrics.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                ledger_rows.append(json.loads(line))
    cycles = [int(r["cycle"]) for r in ledger_rows]
    ledger_last = max(cycles)
    by_cycle = {int(r["cycle"]): r for r in ledger_rows}
    print("[S. 유동층 대조 — 원장 마지막 사이클 vs task_state 세대 (c93 처치, 관측 49)]")
    try:
        rows = (call("get_task_state", {"task_id": "devloop", "limit": 1}) or {}).get("results") or []
    except Exception as exc:  # noqa: BLE001 — 도달 실패도 관측이며 침묵보다 낫다
        print(f"  판정 불가 — get_task_state 도달 실패: {type(exc).__name__}: {exc}")
        return
    if not rows:
        print(f"  ledger_last={ledger_last}  task_state=**세대 없음**")
        print("  ★ devloop 유동층이 통째로 비었다 — 복원은 저장소만으로 해야 한다.")
        return
    row = rows[0]
    summary = " ".join(str(row.get("summary") or "").split())
    state_cycle, verdict = task_state_lag(ledger_last, summary)
    print(f"  ledger_last={ledger_last}  task_state_cycle={state_cycle}  "
          f"valid_from={row.get('valid_from')}  판정={verdict}")
    if verdict == "지연":
        span = f"{state_cycle + 1}~{ledger_last}" if state_cycle is not None else "?"
        print(f"  ★ 불일치: 사이클 {span}의 record_task_state가 스토어에 세대를 남기지 않았다.")
        print("    → 이 세션의 restore_grade(task_state 채널)는 **stale**이다. 해당 원장 행이")
        print("      완주를 주장한다면 그 주장은 이 대조로 반증된다(관측 49의 기전).")
        # 그 원장 행이 실제로 무엇을 주장했는지 **여기서 인쇄한다** — 위 문장이 84사이클간
        # 조건문으로만 있었고 피고발인의 이름을 부른 적이 없다 (관측 88, P47 (a)).
        if state_cycle is not None:
            for miss in range(state_cycle + 1, ledger_last + 1):
                claim = (by_cycle.get(miss) or {}).get(REVERIFY_FIELD, "**필드 없음**")
                print(f"    {reverify_claim_mark(claim)}  c{miss}.{REVERIFY_FIELD} = {claim!r}")
            print("    → 자기보고는 원장 행에 살고 그 행은 record_task_state보다 **먼저** 쓰인다")
            print("      (순서 = 원장 append → 커밋 → push → 호출 → 재조회, 관측 55 수용 기준 ②).")
            print("      구조적으로 영수증이 아니라 의도 선언이다 — 관측 88.")

    # ── 직전 세션 사망 의심 — 파트 S의 사각 (c168 2세션 신설, 관측 97 · P53) ──────────
    # `일치`는 무결의 증거가 아니다. 위 대조는 두 채널을 **서로** 재므로 함께 낡으면
    # 침묵하고, 원장 append 전에 죽은 세션이 정확히 그 창이다. 그 창의 유일한 증거는
    # **작업 트리**이며 파트 A가 이미 인쇄해 왔다 — 오늘 붙이는 것은 두 인쇄의 연결이다.
    try:
        dd = predecessor_death_evidence(
            blockade_rows(changed_entries(), int(run(["git", "log", "-1", "--format=%ct"])),
                          time.time()))
    except Exception as exc:  # noqa: BLE001 — 검사 불가도 관측이며 침묵보다 낫다
        print(f"  [직전 세션 사망 의심] 판정 불가 — {type(exc).__name__}: {exc}")
    else:
        ev, unk = dd["evidence"], dd["unknown"]
        print("  [직전 세션 사망 의심 — devloop 소유 미커밋 ∩ HEAD보다 새로움"
              " (c168 신설, 관측 97 · P53)]")
        if ev:
            print(f"    ★★ 증거 {len(ev)}건 — 직전 세션이 **원장 append 전에** 죽었을 수 있다."
                  f" 위 판정({verdict})은 이 사망을 배제하지 않는다.")
            for path, since_now, vs_head in ev:
                since = f"{since_now:8.1f}h" if since_now is not None else f"{'?':>9s}"
                print(f"       {since} {vs_head:+9.1f}h  {path}")
            print("    → 확인 순서: ① 그 산출물이 어느 사이클 것인지 파일 안에서 직독")
            print("      ② tmp/cNNN_* 산출물 ③ 원장에 그 사이클 행이 있는가. 있으면 c166형")
            print("      (원장 착지·커밋 실패) · 없으면 c168형(원장 미착지 = 이 눈의 표적).")
        else:
            print(f"    증거 0건(devloop 소유 미커밋 없음) · 판정 불가 {len(unk)}건"
                  f"{' ' + str(unk) if unk else ''}")
        print("    ※ 이 눈은 **step 0에서만** 유효하다 — 사이클 도중 재실행하면 내 편집분이")
        print("      같은 조건에 걸린다(파트 A의 같은 주의와 동일한 이유).")

    # 자기보고 대 외부 관측의 **계열**. 손 증분 0 — 원장에서 매 사이클 재계산한다 (P47 (b)).
    rv = reverify_contradictions(ledger_rows)
    print(f"  [자기보고 대조 — `{REVERIFY_FIELD}` (c162 신설, 관측 88 · P47)]")
    n_bare = len(rv["field_rows"]) - len(rv["prose_receipts"]) - len(rv["deferred"])
    print(f"    필드 등장 {len(rv['field_rows'])}행"
          f"(c{rv['field_rows'][0]}~c{rv['field_rows'][-1]}) · "
          f"산문 영수증 {len(rv['prose_receipts'])}행 {rv['prose_receipts']} · "
          f"유보 {len(rv['deferred'])}행 {rv['deferred']} · "
          f"맨 True(의도 선언) {n_bare}행")
    print(f"    외부 대조 가능 {rv['checked']}행 · 일치 {rv['agree']} · "
          f"**모순 {len(rv['contradictions'])}** · 미측정 {rv['unmeasured']}행")
    for c, v in rv["contradictions"]:
        print(f"      !! c{c}: 자기보고 True 인데 c{c + 1} 파트 S = {v}")
    if rv["ahead"]:
        print(f"    ※ `앞섬` {len(rv['ahead'])}건 {rv['ahead']} = **모순 아님** — 세대가 앞서면"
              " 직전 쓰기는 착지했고")
        print("      병은 그 사이클 자신의 완주 선기재다(관측 55). 남의 병으로 고발하지 않는다.")
    if rv["pending"] is not None:
        print(f"    ※ c{rv['pending']}은 후속 원장 행이 없다 — **이 세션의 위 판정이 그 대조다**.")
    print("    ※ 미측정은 무결이 아니다(파트 S는 c93 처치 이후에만 인쇄) · 문면이 바뀌면")
    print("      정규식이 거짓 음성을 낸다 — P47 한계 ③.")

    print("  [쓰기 규약] 절차 5의 record_task_state는 호출로 끝나지 않는다 — 호출 뒤")
    print("    get_task_state로 **재조회**해 이번 사이클 번호가 돌아오는지 확인할 것.")
    print("    c92는 '눈으로 확인했다'고 적었고 세대는 없었다. 확인은 재조회로만 성립한다.")


def part_n() -> None:
    """c52 재배선(F-절차0 처치): 사이클 번호 N을 이 스크립트가 인쇄한다.

    근본 원인(c52 발견): 지시서 절차 0의 문면("metrics.jsonl 마지막 줄에서 N = 마지막+1")이
    tail류 접근을 사실상 지시하고, 'cycle 필드만·tail 금지' 규약은 그림자 채널에만 있어
    문면과 충돌한다 — '알고도' 위반 4연속(c49~c52)의 기전. 금지문 대신 물리 경로를 바꾼다:
    이미 의무인 영토 검사가 번호를 함께 배달하면 metrics.jsonl을 열 동기 자체가 사라진다.
    번호는 cycle 필드의 max+1 — 마지막 줄이 아니라 전체 파싱(순서 오염에도 안전).

    c61 추가 배선(F-절차0 10회차 처치, 무-게이트): 금지문 자체를 이 출력에 싣는다.
    c61 실측 — 캡슐 병행 트랙 슬롯이 90자에서 끊겨 도착분 마지막 토큰이 `metrics`,
    금지 술어 `열지 마라`의 시작 인덱스는 91(컷 밖 1문자)이었다. 캡슐은 목적어를
    배달하고 술어를 버렸고, 도착분만 읽으면 위반이 지시로 오독된다. 산문 채널(캡슐·
    지시서)이 절단·충돌로 실패하므로 P14 교훈("규약은 도구 채널로 보내라")을 적용:
    번호를 얻으려 이 스크립트를 실행하는 손은 금지문을 절단 불가능한 형태로 함께 받는다.
    한계(정직): 이 처치는 **절단 축**만 다룬다. 지시서 절차 0 문면("마지막 줄에서 N")은
    A-55.1 게이트 대기 중이라 살아 있고, step0을 병렬 배선하면 규약 도착과 위반이 같은
    턴에 고정되는 축도 남는다 — c62~c66 재발 시 남은 원인은 문면 단독으로 확정한다.
    """
    cycles = []
    with open(os.path.join(REPO, "research", "devloop", "metrics.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                cycles.append(int(json.loads(line)["cycle"]))
    n, mode = cycle_number_and_mode(cycles)
    print("[!] metrics.jsonl을 직접 열지 말 것 — 번호·모드는 아래 한 줄이 정본이다.")
    print("    (tail/cat/head 계열 0회. 이 스크립트가 이미 전체를 파싱했다.")
    print("     지시서 절차 0의 '마지막 줄에서 N' 문면은 A-55.1 게이트 대기 중인 구본이며,")
    print("     감사 사이클의 metrics 정독 임무는 번호 결정 단계와 별개로 허용된다.)")
    print(f"[N. 사이클 번호 — cycle 필드 max+1]")
    print(f"  last_cycle={max(cycles)}  N={n}  mode={mode} (N%10={n % 10}, N%5={n % 5})")
    print("[T. 턴 배치 규약 — audit-90 R1 (ii) 이중화 (c91 집행)]")
    print("    턴1 = LOOP.md+cycle-prompt.md Read + ToolSearch(5스키마) 같은 응답에 묶음")
    print("    턴2 = get_task_state + 이 스크립트 + git status 병렬 / 턴3 = 첫 유효 행동")
    print("    ※ 이 인쇄는 턴2에 열리므로 **턴1 규약을 집행할 수 없다**(관측 47).")
    print("       턴1 이전 채널은 저장소 루트 CLAUDE.md와 캡슐이다 — 판정은 P29.")
    print("[H. 절차 5 — 다음 HAND 분모는 손으로 옮겨적지 않는다 (audit-150 R6, P42)]")
    print("    수확 커밋 직후: .venv/bin/python research/devloop/scripts/harvest_stat.py"
          f" --cycle {n}")
    print("    출력 말미의 붙여넣기 블록을 task_state에 **그대로** 넣는다. 손 계산 금지 —")
    print("    계열 실측 c147 Δ−1 · c149 Δ±1 · c150 Δ−19, 문면 처치 3회 실효 0.")


def compare_fingerprint(live: dict[str, str], baseline: dict[str, str]) -> tuple[str, list[str], list[str]]:
    """live와 baseline을 대조한다. **순수 함수** — I/O 없음, 그래서 테스트된다.

    설계의 핵심 성질 하나: **채취하지 못한 항목을 '일치'로 보고하지 않는다.**
    관측 30의 병리가 조용한 흡수였으므로, 미채취(`UNKNOWN`)는 '일치'가 아니라
    **판정 불가**로 격리한다. baseline에 없는 신규 키도 미채취와 같게 다룬다 —
    지문 정의를 넓히는 것은 자[尺] 변경이고, 그 변경은 baseline 커밋으로만 승인된다.

    반환: (verdict, changed, unknown)
      changed 있으면 "재교정 필요" (몸이 바뀌었다)
      changed 없고 unknown 있으면 "판정 불가" (모른다 — 위양성으로 계상하지 않는다)
      둘 다 없으면 "일치"
    """
    changed: list[str] = []
    unknown: list[str] = []
    for key in sorted(set(live) | set(baseline)):
        got, want = live.get(key, UNKNOWN), baseline.get(key, UNKNOWN)
        if got == UNKNOWN or want == UNKNOWN:
            unknown.append(key)
        elif got != want:
            changed.append(key)
    verdict = "재교정 필요" if changed else ("판정 불가" if unknown else "일치")
    return verdict, changed, unknown


def _installed_dist_info() -> str:
    di = glob.glob(os.path.expanduser(
        "~/.forget/venv/lib/python3*/site-packages/forget_ai-*.dist-info"))
    return os.path.basename(di[0]).replace(".dist-info", "") if di else UNKNOWN


def _installed_vs_repo() -> str:
    """설치본과 저장소본의 최상위 .py 해시 대조 (c66_body_identity.py에서 이식)."""
    inst = glob.glob(os.path.expanduser("~/.forget/venv/lib/python3*/site-packages/forget"))
    repo_pkg = os.path.join(REPO, "forget")
    if not inst or not os.path.isdir(repo_pkg):
        return UNKNOWN

    def digest(path: str) -> str:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    rfiles = {f for f in os.listdir(repo_pkg) if f.endswith(".py")}
    ifiles = {f for f in os.listdir(inst[0]) if f.endswith(".py")}
    both = rfiles & ifiles
    same = sum(1 for f in both
               if digest(os.path.join(repo_pkg, f)) == digest(os.path.join(inst[0], f)))
    # 분모는 합집합이다 — 교집합을 분모로 쓰면 한쪽에만 있는 파일이 사라진다 (c64 규율).
    return f"{same}/{len(rfiles | ifiles)}"


def _store_vec() -> str:
    """스토어 임베딩의 형식·우세 차원. 디코드 없이 byte length만 집계한다.

    행 수는 싣지 않는다 — 매 사이클 증가하므로 위양성 기계가 된다 (P21 (b)).
    dim = (len - 4) // 4  (MEB1 = 4바이트 매직 + little-endian float32).
    """
    if not os.path.exists(FORGET_DB):
        return UNKNOWN
    try:
        con = sqlite3.connect(f"file:{FORGET_DB}?mode=ro", uri=True)
        try:
            # 매직 비교는 **hex 리터럴**이어야 한다: embedding은 BLOB이고 SQLite에서
            # BLOB은 TEXT 리터럴('MEB1')과 절대 같지 않다(저장 클래스가 다르면 불일치).
            # 첫 배선에서 이 비교가 항상 거짓이라 1540바이트 MEB1 행을 JSON으로 보고했고,
            # baseline 대조가 같은 사이클 안에서 그것을 잡았다 — 계측기가 자기 결함을
            # 자기 첫 런에서 검출한 표본이다. x'4D454231' = b"MEB1".
            rows = con.execute(
                "select substr(embedding,1,4)=x'4D454231', length(embedding), count(*) "
                "from memories where deleted=0 and embedding is not null and embedding != '' "
                "group by 1, 2 order by count(*) desc limit 1").fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return UNKNOWN
    if not rows:
        return UNKNOWN
    is_meb1, blen, _ = rows[0]
    return f"MEB1:{(int(blen) - 4) // 4}" if is_meb1 else f"JSON:len{int(blen)}"


def _effective_stack() -> tuple[str, str, str]:
    """살아 있는 몸에게 직접 묻는다 — 디스크가 아니라 **적재된 런타임**의 자기 보고.

    두 필드를 함께 낸다. `checks.embeddings`는 **저장된 설정**의 거울이라
    폴백 이름(deterministic-128)을 들고 있고, `effective`가 실제 실행 스택이다
    (provider_runtime.py:779-784). 불일치 자체가 지문의 일부다.
    """
    try:
        health = call("get_provider_health", {})
    except Exception:  # noqa: BLE001 — 서버 정지도 데이터다. 조용히 '일치'가 되지만 않으면 된다.
        return UNKNOWN, UNKNOWN, UNKNOWN
    eff = health.get("effective") or {}
    chk = (health.get("checks") or {}).get("embeddings") or {}
    effective = (f"{eff.get('embedding_provider')}:{eff.get('embedding_model')}"
                 if eff.get("embedding_model") else UNKNOWN)
    checks = (f"{chk.get('provider')}:{chk.get('model')}" if chk.get("model") else UNKNOWN)
    return effective, str(eff.get("resolution") or UNKNOWN), checks


def part_body() -> None:
    """P21 처치 (c67 배선) — 몸 지문을 step 0의 첫 화면에 세운다.

    계기: 관측 30 / notes/cycle-66. c59 oracle replay가 무수정 재실행에서 재현되지
    않았고 원인은 어휘가 아니라 **12시간 전에 교체된 몸**이었다. 루프는 c61~c65
    다섯 사이클을 새 몸에서 돌면서 그 사실을 원장에 적지 못했다(검출 지연 5사이클).
    step 0 스크립트를 고른 이유: F-절차0 처치가 만든 **절단 불가능 채널**이고,
    관측 29가 실측한 대로 그 채널에 없는 규약은 산다는 보장이 없다.

    등록본 이탈 1건(선언): ②'프로세스 기동 시각'을 빼고 **effective 스택 + resolution**을
    넣었다 — lsof/ps가 샌드박스 승인에 의존해 승인 없는 런에서 지문이 조용히 미지로
    내려앉기 때문이다. 근거와 대안은 body-fingerprint.json의 `_omitted_process_start`.

    출력은 **3줄 고정** (P21 정직 병기 ②: 늘어나면 F-절차0 재발로 계상한다).
    """
    effective, resolution, checks = _effective_stack()
    live = {"dist_info": _installed_dist_info(),
            "installed_vs_repo": _installed_vs_repo(),
            "effective_embedding": effective,
            "embedding_resolution": resolution,
            "checks_embedding": checks,
            "store_vec": _store_vec()}
    try:
        with open(FINGERPRINT_BASELINE, encoding="utf-8") as fh:
            baseline = json.load(fh).get("fingerprint", {})
    except (OSError, json.JSONDecodeError):
        baseline = {}
    verdict, changed, unknown = compare_fingerprint(live, baseline)

    mark = "**재교정 필요**" if changed else verdict
    print(f"[Body. 몸 지문 — 게이트 상수 의존 계기의 유효 전제 (P21, baseline=body-fingerprint.json)]")
    print(f"  {live['dist_info']} inst_vs_repo={live['installed_vs_repo']} "
          f"eff={live['effective_embedding']} res={resolution.split(' (')[0]} "
          f"checks={live['checks_embedding']} store={live['store_vec']}")
    print(f"  대조: {mark}"
          + (f" — 변경 {changed}" if changed else "")
          + (f" / 미채취 {unknown}" if unknown else "")
          + ("  → oracle replay 계열·gate_audit·score_weight_* 를 재교정 전 판정 금지"
             if changed else ""))


def recall_components(note: str) -> dict[str, int] | None:
    """recall_note에서 성분 4값(능동 hit/miss · 주입 hit/miss)을 추출한다. **순수 함수**.

    정본 형식(P15 (b)): `능동 X회(hit a·miss b) / 주입 Y건(hit c·miss d)`.
    관측된 의역(c70: "능동 검색 0회", "주입 4건 = … hit 1 + … 3건 miss")도 받되,
    값이 **유일하게** 정해지지 않으면 None을 반환한다 — '추출 불가'는 P24 (b)의
    계상 대상이지 조용히 0으로 접을 값이 아니다(compare_fingerprint와 같은 규율:
    모르는 것을 '일치'로 보고하지 않는다).
    """
    text = note.replace("*", "")
    inj = re.search(r"주입\s*(\d+)\s*건", text)
    act = re.search(r"능동[^0-9]{0,12}?(\d+)\s*회", text)
    if not inj or not act:
        return None

    def hitmiss(seg: str) -> tuple[int | None, int | None]:
        h = re.search(r"hit\s*(\d+)", seg)
        m = re.search(r"miss\s*(\d+)", seg) or re.search(r"(\d+)\s*건[^0-9]{0,8}?miss", seg)
        return (int(h.group(1)) if h else None), (int(m.group(1)) if m else None)

    act_seg, inj_seg = text[:inj.start()], text[inj.start():]
    a_cnt, i_cnt = int(act.group(1)), int(inj.group(1))
    a_hit, a_miss = hitmiss(act_seg)
    if a_hit is None and a_miss is None and a_cnt == 0:
        a_hit = a_miss = 0  # "능동 0회"는 분해 생략이 유일 해석이다
    if a_hit is None or a_miss is None:
        return None
    i_hit, i_miss = hitmiss(inj_seg)
    # 한쪽만 명시돼도 총계로 닫히면 유일 결정이다 (예: "주입 4건 = hit 1 + 3건 miss")
    if i_hit is None and i_miss is not None and i_miss <= i_cnt:
        i_hit = i_cnt - i_miss
    elif i_miss is None and i_hit is not None and i_hit <= i_cnt:
        i_miss = i_cnt - i_hit
    if i_hit is None or i_miss is None:
        return None
    return {"active_hits": a_hit, "active_misses": a_miss, "active_total": a_cnt,
            "injected_hits": i_hit, "injected_misses": i_miss, "injected_total": i_cnt}


def recall_identity(row: dict) -> tuple[str, str]:
    """원장 행의 recall 필드가 성분 합과 일치하는지 검산한다. **순수 함수** (P24 처치 ②).

    반환 (verdict, detail). verdict ∈ {일치, 불일치, 추출 불가}.
    audit-70 §1-a가 적발한 c64형 결함(필드=구정의·산문=신정의, 무선언 분열)을
    다음 사이클의 step 0이 기계로 잡는다. 결론 문장은 만들지 않는다 — 값과 판정만.
    """
    comp = recall_components(str(row.get("recall_note", "")))
    if comp is None:
        return "추출 불가", "성분 4값 유일 추출 실패 — P24 (b) 계상 대상"
    want = (comp["active_hits"] + comp["injected_hits"],
            comp["active_misses"] + comp["injected_misses"])
    got = (int(row.get("recall_hits", -1)), int(row.get("recall_misses", -1)))
    detail = (f"fields(hits={got[0]}·misses={got[1]}) vs "
              f"성분(능동 {comp['active_hits']}·{comp['active_misses']} / "
              f"주입 {comp['injected_hits']}·{comp['injected_misses']})")
    return ("일치" if got == want else "불일치"), detail


def part_recall() -> None:
    """P15 (a) 반증 처방의 배선 (c71, P24) — 정의 A를 절단 불가능 채널로 인쇄하고
    직전 원장 행의 `성분 합 = 필드 값` 항등식을 검산한다.
    """
    rows = []
    with open(os.path.join(REPO, "research", "devloop", "metrics.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    last = max(rows, key=lambda r: r["cycle"])
    verdict, detail = recall_identity(last)
    print("\n[R. recall 계상 — 정의 A 정본 출력 (P15 (a) 반증 → P24 배선, c71)]")
    print("  계상 대상 = 이 사이클에 표면화된 회상 전체: 능동 검색 + 주입(캡슐·task_state·훅).")
    print("  계기의 검색 호출은 계상 제외(c68 선언). hit = 행동을 바꾼 신규 정보이며, 도착")
    print("  시각이 행동을 바꾸면 hit(c64 확장의 성문화 — 노출이지 승인 아님, audit-70 N7).")
    print("  필드 항등식: recall_hits = 능동hit+주입hit · recall_misses = 능동miss+주입miss.")
    print("  recall_note 병기 형식: '능동 X회(hit a·miss b) / 주입 Y건(hit c·miss d)'.")
    print("  [공표 가드 — audit-140 R3, c141 성문] hit_rate 구간 집계는 계상 체제 변화(c64·c71)에 걸치고 hit 주 원천이 task_state 재귀다 — 단일 체제 구간·재귀 성분 제외 없이는 제품 개선으로 공표 불가.")
    print(f"  [직전 행 검산] cycle={last['cycle']}: {detail} → {verdict}")


def _dequote_c_style(path: str) -> str:
    """git이 인용한 경로(`"..."`)를 C 스타일 이스케이프까지 디코드한다. **순수 함수** (c83).

    관측 38-② 처치. core.quotepath 기본값(true)에서 비ASCII 바이트는 8진 이스케이프로
    온다 — `"\\355\\225\\234\\352\\270\\200.md"` → `한글.md`. 디코드는 바이트로 모은 뒤
    surrogateescape로 되돌린다: 비UTF-8 파일명도 os.path.exists가 그대로 통과하는
    유일한 복원이다(strict는 죽고 replace는 디스크에 없는 다른 경로를 만든다 —
    거짓 음성을 고치려다 같은 방향의 거짓 음성을 재생산하지 않는다).
    인용부호가 없으면 원문 그대로 — 정상 경로의 무해 통과를 보존한다.
    """
    if not (len(path) >= 2 and path.startswith('"') and path.endswith('"')):
        return path
    inner = path[1:-1]
    simple = {"\\": ord("\\"), '"': ord('"'), "n": ord("\n"), "t": ord("\t"),
              "r": ord("\r"), "a": 7, "b": 8, "f": 12, "v": 11}
    out = bytearray()
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\" and i + 1 < len(inner):
            nxt = inner[i + 1]
            if nxt in "01234567":
                j = i + 2
                while j < min(i + 4, len(inner)) and inner[j] in "01234567":
                    j += 1
                out.append(int(inner[i + 1:j], 8) & 0xFF)
                i = j
                continue
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
                continue
        out.extend(ch.encode("utf-8"))
        i += 1
    return out.decode("utf-8", "surrogateescape")


def _split_rename_columns(rest: str) -> list[str]:
    """리네임/카피 행의 `old -> new` 열을 양쪽 경로로 가른다. **순수 함수** (c83).

    관측 38-① 처치. old가 인용된 경우(`"a -> b.md" -> c.md`)는 닫는 인용부호를
    스캔해 인용 속 화살표를 경로의 일부로 지킨다. 한계(정직): porcelain v1은
    무인용 경로 속 ` -> `를 진짜 구분자와 가릴 수 없다(근본 처치는 -z NUL 형식) —
    여기서는 첫 ` -> `에서 가른다. 그 모호성은 경로가 인용되지 않는 평문 ASCII
    파일명에 화살표가 실제로 들어간 경우에만 남는다.
    """
    if rest.startswith('"'):
        i = 1
        while i < len(rest):
            if rest[i] == "\\":
                i += 2
                continue
            if rest[i] == '"':
                break
            i += 1
        head, tail = rest[:i + 1], rest[i + 1:]
        if tail.startswith(" -> "):
            return [head, tail[4:]]
        return [rest]
    if " -> " in rest:
        old, new = rest.split(" -> ", 1)
        return [old, new]
    return [rest]


def porcelain_changed_paths(raw: str) -> list[str]:
    """`git status --porcelain` 원문(무-strip)에서 경로 열을 뽑는다. **순수 함수** (c82).

    part_a 인라인이던 파싱의 분리 — "part_n/part_a/part_b 파싱 미커버" 부채(c64 등재,
    c71 부분 상환, audit-80 §3-(b) 재지적)의 잔여 상환. 행 형식 `XY<space><path>`에서
    `line[3:]`, 공백 행 무시. 입력은 run_raw의 무-strip 원문이어야 한다 — strip된
    원문을 주면 첫 행의 X열(공백)이 사라져 경로 첫 글자를 먹는다(run_raw 독스트링의
    c64 결함, 테스트가 방향을 고정).

    거짓 음성 2종 처치 (c82 관측 38 → c83 수리, frictions.md 수용 기준 ②):
      ① 상태 코드에 R/C가 있는 행은 `old -> new`를 양쪽 경로로 가른다 — old는
         디스크에 없어 하류 exists에서 걸러지고(D 행과 같은 취급), new가 mtime
         검사에 들어간다. 리네임된 미커밋 WIP가 영토 검사에 보인다.
      ② 인용 경로는 8진 이스케이프까지 디코드한다 — 한국어 파일명이 디스크에
         실재하는 문자열로 돌아온다.
    두 처치 모두 "변경 있음→'깨끗함'" 방향의 침묵을 막는다(절차 2가 막으려는 상황).
    c82가 현행 동작으로 고정해 둔 단언 2건은 이 처치와 함께 정상 동작 단언으로
    교체됐다 — 울리라고 둔 종이 울렸고, 종을 새 자리에 다시 걸었다.
    """
    paths: list[str] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        xy, rest = line[:2], line[3:]
        segs = _split_rename_columns(rest) if ("R" in xy or "C" in xy) else [rest]
        paths.extend(_dequote_c_style(seg.strip()) for seg in segs)
    return paths


# 코드 사이클 큐 — 절차 2에서 "봉쇄를 풀 증명"에 쓰이는 쪽 피연산자 (audit-150 §3, c151).
#
# 루프가 매 사이클 인쇄해 온 무교집합은 `이번 사이클의 변경분 ∩ 봉쇄 경로 = ∅`였다.
# 그것은 **"내가 남의 파일을 밟지 않았다"**만 증명한다. 봉쇄를 풀려면 반대 방향이
# 필요하다: **"내가 하려는 일이 남의 파일과 무관하다"** = `코드 큐 ∩ 봉쇄 경로 = ∅`.
# 43사이클 동안 전자만 인쇄됐고 후자는 c150 감사가 손으로 한 번 쟀다. 여기 싣는다.
#
# 이 상수는 손으로 유지된다(큐의 정본은 task_state next_actions와 frictions 대장이며,
# 기계가독 형식이 아직 없다). 매 사이클 인쇄되므로 표류는 **눈에 보이는 채로** 썩는다 —
# 조용히 틀리는 것보다 낫다. 큐가 바뀌면 이 줄을 바꾸고 사이클 보고에 선언한다.
CODE_QUEUE_PATHS = ("forget/store.py",)

#: 봉쇄 계측의 판정 어휘. **문자열도 분류다** — 두 곳에서 리터럴로 쓰면 조용히 갈라지고,
#: 갈라진 쪽이 고발을 담당한다(관행 ㊷, 관측 94의 교훈). 파트 S의 사망 의심 검사는 이
#: 판정을 재계산하지 않고 **그대로 재사용**한다.
TOUCHED_AFTER_HARVEST = "수확 이후 접촉"
UNTOUCHED_AFTER_HARVEST = "수확 이후 무접촉"

#: devloop 루프가 **소유한** 경로. 이 경로의 미커밋 변경은 타 트랙 WIP가 아니라 이 루프
#: 자신의 산출이므로, step 0 시점에 존재한다면 그것을 만든 세션은 커밋에 도달하지 못했다.
#: 손 유지 상수 — 소유 범위가 바뀌면 이 줄을 고치고 사이클 보고에 선언한다
#: (CODE_QUEUE_PATHS·ORDINAL_ANCHORS·DEFERRAL_MARKERS와 같은 규율).
DEVLOOP_OWNED_PREFIXES = ("research/devloop/", "tests/test_devloop_")


def blockade_rows(entries: list[tuple[str, float | None]], head_ct: float,
                  now_ts: float) -> list[tuple[str, float | None, float | None, str]]:
    """(경로, mtime|None)을 (경로, now대비h, HEAD대비h, 판정) 행으로. **순수 함수** (c151).

    핵심 성질: mtime을 못 읽은 경로를 **버리지 않는다.** 목록에서 조용히 빠지면
    "봉쇄 3건 전부 무접촉" 같은 거짓 전수 주장이 만들어진다 — compare_fingerprint와
    같은 규율이고, 자기규율 8회차("0건은 '없음'과 '못 봄'을 구별하지 않는다")의 적용이다.
    못 읽은 행은 '판정 불가'로 **인쇄에 남는다**.

    판정 어휘는 두 개뿐이고 결론을 만들지 않는다(이 스크립트의 상시 규약):
    HEAD 커밋 시각보다 mtime이 뒤면 '수확 이후 접촉', 아니면 '수확 이후 무접촉'.
    무접촉이 곧 "죽은 WIP"라는 추론은 **여기서 하지 않는다** — 그 판단은 사람 몫이고,
    frictions.md:515-516의 비-WIP 시험(장기 mtime 불변)이 그 자[尺]다.
    """
    rows: list[tuple[str, float | None, float | None, str]] = []
    for path, mt in entries:
        if mt is None:
            rows.append((path, None, None, "판정 불가(stat 실패·경로 부재)"))
            continue
        rows.append((path, (now_ts - mt) / 3600.0, (mt - head_ct) / 3600.0,
                     TOUCHED_AFTER_HARVEST if mt > head_ct else UNTOUCHED_AFTER_HARVEST))
    return rows


def queue_intersection(changed: list[str], queue: tuple[str, ...] = CODE_QUEUE_PATHS) -> list[str]:
    """코드 큐 ∩ 봉쇄 경로. **순수 함수** (c151).

    경로 문자열 동일성으로만 잰다 — 디렉터리 포함 관계는 세지 않는다. 큐 항목이
    디렉터리가 되면 이 함수도 함께 바뀌어야 하고, 그 전까지 여기서 짐작하지 않는다.
    """
    return sorted(set(changed) & set(queue))


def changed_entries(changed: list[str] | None = None) -> list[tuple[str, float | None]]:
    """(미커밋 경로, mtime|None) 목록. 파트 A와 파트 S가 **함께** 쓴다 (c168 2세션).

    한 벌로 두는 이유는 관행 ㊷다 — 같은 개념(무엇이 미커밋이고 언제 손댔는가)의 계산이
    두 파트에 사본으로 살면 조용히 갈라지고, 갈라진 쪽이 판정을 담당하게 된다. mtime을
    못 읽은 경로를 **버리지 않는다**(None으로 남긴다) — blockade_rows와 같은 규율.
    """
    if changed is None:
        changed = porcelain_changed_paths(run_raw(["git", "status", "--porcelain"]))
    entries: list[tuple[str, float | None]] = []
    for rel in changed:
        full = os.path.join(REPO, rel)
        try:
            if os.path.isdir(full):
                mt = max((os.path.getmtime(os.path.join(r, f))
                          for r, _, fs in os.walk(full) for f in fs), default=None)
            else:
                mt = os.path.getmtime(full)
        except OSError:
            mt = None
        entries.append((rel, mt))
    return entries


def predecessor_death_evidence(
    rows: list[tuple[str, float | None, float | None, str]],
    owned: tuple[str, ...] = DEVLOOP_OWNED_PREFIXES,
) -> dict:
    """직전 세션이 **원장 append 전에** 죽었다는 증거. 순수 함수 (c168 2세션, 관측 97 · P53).

    왜 파트 S가 이것을 못 보는가. 파트 S는 원장과 task_state를 **서로** 잰다. 그래서 두
    채널이 **함께** 낡으면 `일치`가 나온다 — 절차 5의 첫 걸음(원장 append) 전에 죽은
    세션은 둘 다 건드리지 않았으므로 그 대조는 무증상이다.

    사망의 지문은 세 종류이고 **쓰기 순서가 그것을 정한다**(관측 97):
      c96  — task_state를 먼저 써서 `앞섬`   → 파트 S가 잡았다
      c166 — 원장까지 쓰고 커밋 전에 죽어 `지연` → 파트 S가 잡았다
      c168 1세션 — 원장 append 직전에 죽어 `일치` → **파트 S가 못 봤다**
    셋째가 조용한 것은 우연이 아니라 관측 55 처치의 대가다: '완주 선기재'를 막으려
    record_task_state를 맨 뒤로 밀자, 맨 앞에서 죽는 창이 두 채널을 같은 세대로 남겼다.

    증거는 이미 인쇄되고 있었다 — 파트 A의 `uncommitted_paths_newer_than_HEAD`. 없던 것은
    계측이 아니라 **두 인쇄의 연결**이다. `unknown`을 따로 돌려주는 이유는 이 파일의 상시
    규약: mtime을 못 읽은 행을 버리면 "증거 0건"이 거짓 전수 주장이 된다.
    """
    evidence: list[tuple[str, float | None, float | None]] = []
    unknown: list[str] = []
    for path, since_now, vs_head, verdict in rows:
        if not path.startswith(tuple(owned)):
            continue
        if vs_head is None:
            unknown.append(path)
        elif verdict == TOUCHED_AFTER_HARVEST:
            evidence.append((path, since_now, vs_head))
    return {"evidence": evidence, "unknown": unknown}


def part_a() -> None:
    print("[A. 규약 (ii) — 구현 의존성]")
    dotgit = os.path.join(REPO, ".git")
    kind = "dir" if os.path.isdir(dotgit) else ("file(worktree pointer)" if os.path.isfile(dotgit) else "missing")
    print(f"  .git kind={kind}")

    naive_ref = os.path.join(REPO, ".git", "HEAD")
    print(f"  naive_ref_exists={os.path.exists(naive_ref)}  ref={naive_ref}")

    safe_ref = os.path.join(REPO, run(["git", "rev-parse", "--git-path", "HEAD"]))
    print(f"  safe_ref_exists={os.path.exists(safe_ref)}   ref={safe_ref}")

    head_ct = int(run(["git", "log", "-1", "--format=%ct"]))
    print(f"  head_commit_epoch={head_ct}  ({run(['git', 'log', '-1', '--format=%ci'])})")

    # 참조 파일 mtime이 아니라 **커밋 시각**과 비교한다 — .git/HEAD의 mtime은
    # 체크아웃·페치 같은 무관한 조작으로도 갱신되므로 커밋 시각이 더 정확한 기준이다.
    newer: list[tuple[str, int]] = []
    changed = porcelain_changed_paths(run_raw(["git", "status", "--porcelain"]))
    print(f"  changed_paths_total={len(changed)}")  # c64: 분모를 병기해 침묵 절단을 드러낸다
    for rel in changed:
        full = os.path.join(REPO, rel)
        if os.path.isdir(full):
            mt = max((os.path.getmtime(os.path.join(r, f))
                      for r, _, fs in os.walk(full) for f in fs), default=0.0)
        elif os.path.exists(full):
            mt = os.path.getmtime(full)
        else:
            continue
        if int(mt) > head_ct:
            newer.append((rel, int(mt) - head_ct))

    print(f"  uncommitted_paths_newer_than_HEAD={len(newer)}")
    for rel, delta in newer:
        print(f"    +{delta:5d}s  {rel}")

    # ── 봉쇄 계측 (audit-150 R1, c151 배선) ──────────────────────────────────
    # git status는 파일의 **존재**를 증명하고 **활성**을 증명하지 않는다. 그 구별이
    # 없어서 영토 봉쇄의 전제('타 세션의 진성 WIP')가 43사이클간 무검증으로 지나갔고,
    # 검증법은 루프가 c31에 자기 손으로 써 놓은 채였다(frictions.md:515-516,
    # "장기 mtime 불변" = 비-WIP 시험). 여기 세 줄이 그 시험을 상시화한다.
    if changed:
        # 경로·mtime 수집은 `changed_entries` 한 벌이다 — 파트 S의 사망 의심 검사가 같은
        # 함수를 쓴다(c168 2세션, 관행 ㊷). 사본이 둘이면 조용히 갈라진다.
        rows = blockade_rows(changed_entries(changed), head_ct, time.time())
        print("  [미커밋 경로의 활성 계측 — 존재가 아니라 활성 (audit-150 R1)]")
        print("    now 대비 = 마지막 손댐 이후 경과. 사이클 ≈ 1일 — 판단은 사람 몫이다.")
        print("    ※ 이 목록은 '타 트랙 WIP'가 아니라 **미커밋 전체**다. step 0(턴2)에는")
        print("      둘이 같지만, 사이클 도중 재실행하면 자기 편집분이 ~0.0h로 함께 뜬다.")
        for rel, since_now, vs_head, verdict in rows:
            if since_now is None:
                print(f"    {'':>9s} {'':>10s}  {rel}  ← {verdict}")
            else:
                print(f"    {since_now:8.1f}h {vs_head:+9.1f}h  {rel}  ← {verdict}")
        inter = queue_intersection(changed)
        print(f"    코드 큐 {list(CODE_QUEUE_PATHS)} ∩ 미커밋 {len(changed)}건"
              f" = {len(inter)}건 {inter if inter else '(교집합 없음)'}")
        print("    ※ 이 교집합이 절차 2의 '봉쇄를 풀 증명' 쪽 피연산자다 — 매 사이클")
        print("      인쇄되던 무교집합(내 변경분 ∩ 봉쇄)은 방향이 반대였다(audit-150 §3).")


def needle_reach(capsule: str, rules: dict[str, list[str]]) -> tuple[int, dict[str, int]]:
    detail = {k: int(any(nd in capsule for nd in v)) for k, v in rules.items()}
    return sum(detail.values()), detail


def capsule_char_budget(src: str) -> int:
    """훅 소스에서 CAPSULE_CHAR_BUDGET 정수를 뽑는다. **순수 함수** (c82).

    part_b 인라인 정규식의 분리 — 같은 부채의 잔여 상환. 예산은 truncated 판정과
    니들 도달의 분모를 정한다: 이 값을 잘못 읽으면 part_b 전체가 통째로 어긋난다.
    `1_600` 같은 밑줄 리터럴을 허용한다(현행 동작 보존). 마커 부재 시 AttributeError로
    **시끄럽게** 죽는다 — 조용히 기본값으로 접혀 거짓 음성이 되는 것보다 낫고,
    그 성질도 테스트가 고정한다(compare_fingerprint의 규율: 모르는 것을 '일치'로
    보고하지 않는다).
    """
    return int(re.search(r"CAPSULE_CHAR_BUDGET\s*=\s*([0-9_]+)", src).group(1).replace("_", ""))


def part_b() -> None:
    print("\n[B. 규약 도달 — 니들 판본 대조]")
    sys.path.insert(0, INSTALLED_HOOKS)
    from forget_project import layered_filter, project_key_for_path, scope_disabled  # noqa: E402

    src = open(os.path.join(INSTALLED_HOOKS, "forget_sessionstart.py"), encoding="utf-8").read()
    budget = capsule_char_budget(src)

    project = None if scope_disabled() else project_key_for_path(REPO)
    args = {"query": f"session startup in {REPO} — active tasks, open loops, recent decisions",
            "include_debug": False}
    pf = layered_filter(project)
    if pf:
        args["filters"] = pf
        args["project"] = project
    capsule = str(call("prepare_context_autopilot", args).get("capsule_text") or "").strip()
    shown = capsule[:budget]
    print(f"  budget={budget} capsule_chars={len(capsule)} truncated={len(capsule) > budget}")

    v1 = {"(i)": ["devloop-self"], "(ii)": ["mtime"], "(iii)": ["cycle` 필드", "cycle 필드"]}
    v2 = {"(i)": ["devloop-self"], "(ii)": ["mtime"], "(iii)": ["cycle` 필드", "cycle 필드", "tail 금지"]}
    # V3 (c64, P19): 어휘가 아니라 **규약의 내용**을 노린다. 각 항은 그 규약을 나르는
    # 알려진 표현들의 논리합이며, 새 표현이 관측되면 여기에 더한다(그 추가는 자[尺]
    # 변경이므로 사이클 보고에 선언한다). 넓히되 **규약 간 경계는 넘지 않는다** —
    # 아무 캡슐이나 3/3으로 통과시키는 자가 되면 P19 (a)가 반증된다.
    v3 = {
        "(i)": ["devloop-self", "devloop_self"],
        "(ii)": ["mtime", "미커밋", "HEAD보다", "newer", "영토 규약"],
        "(iii)": ["cycle` 필드", "cycle 필드", "tail 금지", "tail/cat/head",
                  "c48_step0_check", "번호·모드", "열지 마"],
    }
    for label, rules in (("V1 (c46 원본 니들)", v1), ("V2 (c47 확장 니들)", v2),
                         ("V3 (c64 의미 니들)", v3)):
        hits, detail = needle_reach(shown, rules)
        print(f"  {label:22s} capsule_reach={hits}/3  {detail}")

    for lit in ("tail 금지", "cycle 필드", "cycle` 필드", "mtime", "devloop-self",
                "c48_step0_check", "번호·모드"):
        print(f"    literal {lit!r:18s} in_capsule={int(lit in shown)}")

    # 원문 인쇄 (c64, P19 ②) — 관측 23이 명시한 수용 기준의 직접 이행.
    # 니들 판본은 표류하지만 원문은 표류하지 않는다. 다음 손이 육안으로 대조한다.
    # 주의: 이 캡슐은 SessionStart 주입본과 **같은 질의·다른 시각**의 별개 응답이다.
    print(f"  capsule_sha256={hashlib.sha256(capsule.encode('utf-8')).hexdigest()[:16]}"
          f"  shown_chars={len(shown)}")
    print("  [캡슐 원문 — SessionStart 주입본의 재취득본, 동일 질의·다른 시각]")
    for line in shown.splitlines():
        print(f"  | {line}")


FRICTIONS = os.path.join(REPO, "research", "devloop", "frictions.md")

# 상태 헤더 규약 — 이 어휘가 파트 F의 눈이다 (A-95.1 루프 몫, P34 ②③):
#   원본  `## [미분류 ]관측 N — 제목 (사이클 C, …)` — 괄호절에 '회부'/'후보'면 계상 대상
#   갱신  `## 관측 N 보강|재발… (사이클 C, …)` — 최근 사이클만 갱신
#   처분  `## 관측 N 처분 …` 헤더 또는 절 안 행 첫머리 `**처분 (사이클` 문단.
#         처분 문단에 "종결" 또는 "회부 상태를 벗"이 있어야 회부 이탈 —
#         없으면 부분 처분으로 존속한다(관측 55·58이 실측 반례: 하위 항목/계열 표기만).
OBS_HEADER = re.compile(r"^##\s+(?:미분류\s+)?관측\s+(\d+)(?:\s+(보강|재발|처분))?")
# 관측 76 처치 (c131 적용, audit-130 R1 승인). OBS_HEADER는 번호 **바로 다음** 어절만
# 종류로 읽어 `## 관측 74 수용 기준 ③ 최초 집행 …` 같은 어순을 원본으로 오분류했고,
# 원본 분기가 tagged를 괄호절로 덮어써 살아 있는 관측이 인덱스에서 무공지 소멸했다
# (c129 실측: 38→37, Δ 게이트가 잡음). 처치 ① 어순 둔감: 번호 뒤 대시(—) 전 구간에서
# 처분/보강/재발을 탐색. 처치 ② 태그 단조성: 원본 분기가 기존 tagged=True를 내리지
# 못한다 — 태그는 원본 등재로만 켜지고, 처분은 exited로만 끈다.
# 자[尺] 교체 선언 (관측 28 규율 — 무공지 교체 금지): 반사실 영수증은 실물 파서 대조
# 2회 — audit-130 §4 (c130, open 39/39·차집합 ∅) + c131 재발행 (open 40/40·차집합 ∅,
# 재해석 헤딩 전수 1건 = c128 `관측 71 잔여 하자 처분` → 처분, 71은 기이탈이라 무영향.
# 무태그 목록만 71 제외로 이동). 소급 이동 Δ0 확인 후 적용했다.
_OBS_KIND_SEG = re.compile(r"^##\s+(?:미분류\s+)?관측\s+\d+([^—\n]*)")
_OBS_CYCLE = re.compile(r"사이클\s*(\d+)")
_INLINE_DISPOSAL = re.compile(r"^\*\*처분\s*\(사이클")
_EXIT_MARKS = ("종결", "회부 상태를 벗")

# 관측 63 처치 (c126). 순수 부분문자열 탐색은 부정 문맥을 격발어와 구별하지 못했다 —
# "이 처분은 ①의 이행 기록이지 종결이 아니다"(관측 61 c113)가 이탈로 읽혀 존속 선언
# 자체가 관측을 인덱스에서 지웠다. 처치는 **발생 단위** 판정이다: 마커 직후 창에
# 부정어가 오면 그 발생만 무효이고, 같은 문단의 다른 발생이 긍정이면 이탈은 성립한다
# (관측 53 처분 문단이 반례 — "→ **종결.**" 뒤 문장에 "…아니다"가 온다).
#
# 창은 **문장 종결 전 3어절**이다. 글자 수가 아니라 어절로 세는 이유: 부정 종결어미는
# 마커 뒤 1~3어절에 붙고("종결이 아니다" 2 · "회부 상태를 벗어나지 않는다" 2 ·
# "종결로 보지 않는다" 3), 그 너머의 부정어는 **다른 절의 것**이다. 창을 넓히면
# "종결이며 더 이상 보정하지 않는다"류의 긍정 선언이 뒤 절 부정어에 오염돼 거짓
# 음성(존속 과계상)이 난다 — 이 예에서 부정어는 6어절 뒤라 3어절 창 밖이다.
# 대장 실측 8개 발생 전수에서 이 창은 부정 1건(관측 61 c113)만 배제한다.
# 한계(정직): 휴리스틱이다. 4어절 이상 떨어진 부정 종결("종결이라고 이 절이 말하지는
# 않는다")은 여전히 위양성으로 남는다. 어휘·거리가 표류하면 P34 (b) 채널 팔로 계상하고
# 자[尺] 변경을 선언한 뒤 넓힌다 — V3 니들과 같은 규율.
_NEG_TOKENS = 3
_SENT_END = re.compile(r"[.。\n]")
_NEGATION = re.compile(r"(아니|않|못하|없)")


def _exit_declared(para: str) -> bool:
    """이탈 마커가 **부정 문맥이 아닌 자리에** 한 번이라도 나오면 이탈. **순수 함수**."""
    for mark in _EXIT_MARKS:
        pos = 0
        while True:
            i = para.find(mark, pos)
            if i < 0:
                break
            pos = i + len(mark)
            window = para[pos:]
            cut = _SENT_END.search(window)
            if cut:
                window = window[:cut.start()]
            if not _NEGATION.search(" ".join(window.split()[:_NEG_TOKENS])):
                return True
    return False


def _obs_paragraph(lines: list[str], start: int) -> str:
    """start 행부터 첫 공백 행 전까지 — 처분 문단의 이탈 마커 탐색 범위. **순수 함수**."""
    out = []
    for line in lines[start:]:
        if not line.strip():
            break
        out.append(line)
    return " ".join(out)


def parse_observations(text: str) -> dict[int, dict]:
    """frictions.md의 실재 표기 관행에서 관측별 상태를 파생한다. **순수 함수** (c108, P34).

    별도 인덱스 파일을 두지 않는 이유: 두 번째 원장은 대장과 어긋나며 썩는다
    (관측 57 상속 계수의 파일판). 대장이 단일 정본으로 남고, 위 상태 헤더 규약이
    A-95.1이 요구한 "기계가독 상태 마커"의 실행형이다.
    한계(정직): 처분이 amendment 문서에만 있고 대장에 주석되지 않으면 이 눈에는
    보이지 않는다 — amendment-105 §5의 "판정 집행은 frictions.md 주석" 관행이 전제다.
    이탈 마커 어휘가 표류하면 P34 (b) 채널 팔로 계상하고 어휘를 넓힌다(자[尺] 변경
    선언 동반 — V3 니들과 같은 규율).
    """
    obs: dict[int, dict] = {}
    current: int | None = None
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        m = OBS_HEADER.match(line)
        if m:
            num, kind = int(m.group(1)), (m.group(2) or "원본")
            if kind == "원본":
                # 관측 76 처치 ①: 어순 둔감 — 대시 전 구간에서 종류 어휘 탐색
                seg_m = _OBS_KIND_SEG.match(line)
                seg = seg_m.group(1) if seg_m else ""
                for k in ("처분", "보강", "재발"):
                    if k in seg:
                        kind = k
                        break
            entry = obs.setdefault(num, {
                "opened": None, "last": None, "tagged": False,
                "exited": False, "partial_disposal": False, "title": ""})
            cycles = _OBS_CYCLE.findall(line)
            if cycles:
                entry["last"] = max(entry["last"] or 0, int(cycles[-1]))
            if kind == "원본":
                entry["opened"] = int(cycles[-1]) if cycles else None
                tail = line[line.rfind("(사이클"):] if "(사이클" in line else line
                # 관측 76 처치 ②: 태그 단조성 — 원본 분기는 기존 태그를 내리지 못한다
                entry["tagged"] = entry["tagged"] or ("회부" in tail) or ("후보" in tail)
                body = line[m.end():].replace("**", "")
                cut = body.rfind("(사이클")
                entry["title"] = (body[:cut] if cut >= 0 else body).strip(" —·:")
            elif kind == "처분":
                para = _obs_paragraph(lines, idx)
                if _exit_declared(para):
                    entry["exited"] = True
                else:
                    entry["partial_disposal"] = True
            current = num
            continue
        if line.startswith("## "):
            current = None
            continue
        if current is not None and _INLINE_DISPOSAL.match(line):
            para = _obs_paragraph(lines, idx)
            if _exit_declared(para):
                obs[current]["exited"] = True
            else:
                obs[current]["partial_disposal"] = True
            cycles = _OBS_CYCLE.findall(line)
            if cycles:
                obs[current]["last"] = max(obs[current]["last"] or 0, int(cycles[-1]))
    return obs


def open_observation_numbers(obs: dict[int, dict]) -> list[int]:
    """계상 대상(회부/후보 태그) 중 회부 이탈하지 않은 번호. **순수 함수**."""
    return sorted(n for n, o in obs.items() if o["tagged"] and not o["exited"])


# c123 정독(관측 69 수용 기준 ①)이 확정한 정직 재고 범위. **빈티지 상수**다 —
# 자동 인쇄가 36이던 시점의 값이고, 이 범위의 무번호 성분(20/16 + 무태그 c41 1건
# − 중복 후보 4)만이 상수의 몫이다. 자동 성분이 움직이면 범위도 그만큼 움직이므로,
# 재정독 없이 갱신하지 않고 **빈티지를 병기해** 현재값으로 위장하지 않는다.
C123_HONEST_RANGE = (48, 57)
C123_AUTO_AT_VINTAGE = 36


def unnumbered_blind_spot() -> tuple[int, int]:
    """무번호 관측 절 수 · 그중 회부/후보 태그 수 (관측 69 ② 처치, c126).

    c123 계수 규칙을 **재구현하지 않고 재사용**한다 — 규칙을 두 벌 두면 그것이 바로
    관측 30·34(자[尺]가 선언 없이 갈라지면 시점 간 비교가 소멸)의 다음 표본이 된다.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from c123_unnumbered_obs import NUMBERED, sections, tagged
    with open(FRICTIONS, encoding="utf-8") as fh:
        secs = sections(fh.read())
    obs_secs = [s for s in secs if "관측" in s[0]]
    unnum = [s for s in obs_secs if not NUMBERED.match(s[0])]
    return len(unnum), sum(1 for s in unnum if tagged(s[0]))


# 어휘 위반의 **기지(旣知)** 기지국 — 손 유지 상수 (파트 A의 CODE_QUEUE_PATHS와 같은 규율:
# 바뀌면 이 줄을 고치고 보고에 선언한다). P39는 두 트랙 이중 주조(관측 77)이고 처치는
# 개명 패킷(§6 서열 9) 게이트 대기다 — 신규 위반과 섞이면 이 인쇄가 늑대소년이 된다.
KNOWN_VOCAB_OFFENDERS = ("P39",)


def part_p() -> None:
    """[P] 예측 대장 어휘 게이트 — **매 사이클** (c155 신설, 관측 83 처치).

    왜. c125가 "어휘 밖 값은 하드 에러"라고 선언했고 그 검사는 c124_retro_prep에만
    있었다. 그런데 **등록은 매 사이클 열리고 그 계기는 10사이클에 한 번 열린다** —
    관측 82(상신 매 사이클 / 편입 10사이클)와 같은 주기 불일치이며, 실제로 c151이
    어휘 밖 값 '미판정'을 발급하자 P42·P43이 그대로 베껴 **4사이클(c151~c154)간
    7개 팔**이 무검출로 통과했다. 검사를 쓰기와 같은 주기의 채널로 옮긴다.

    자[尺]는 옮기지 않는다 — 어휘의 정본은 여전히 c124_retro_prep.VOCAB 하나이며
    여기서는 **import해서 쓴다**. 어휘를 복사하면 정본이 둘이 되고, 그것이 바로 이
    처치가 진단한 병이다.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from c124_retro_prep import VOCAB, predictions  # noqa: PLC0415
        p = predictions()
    except Exception as exc:  # 계기 고장이 step 0을 죽이지 않는다 — 강등 후 계속
        print("\n[P. 예측 대장 어휘 게이트]")
        print(f"  !! 게이트 자체가 돌지 않았다: {type(exc).__name__}: {exc}")
        print("     → 이 사이클의 어휘 판정은 **미측정**이다. '위반 0'으로 읽지 말 것.")
        return

    errors = p["errors"]
    total = len(p["records"])
    fresh = [(pid, errs) for pid, errs in errors if pid not in KNOWN_VOCAB_OFFENDERS]
    known = [(pid, errs) for pid, errs in errors if pid in KNOWN_VOCAB_OFFENDERS]

    print("\n[P. 예측 대장 어휘 게이트 — 매 사이클 (c155 신설, 관측 83 처치)]")
    print(f"  대장 {total}건 · 위반 절 {len(errors)}건 (신규 {len(fresh)} · 기지 {len(known)})")
    print(f"  어휘 정본 = c124_retro_prep.VOCAB ({len(VOCAB)}값) — 이 파일은 사본을 갖지 않는다.")
    if fresh:
        print("  !! 신규 위반 — 등록한 사이클이 처치한다 (어휘 밖 값은 하드 에러):")
        for pid, errs in fresh:
            for e in errs:
                print(f"       {pid}: {e}")
        print("     ※ 판정 미도래를 뜻하려면 `시계-미시작`(창 미개시) 또는 `시계-가동`(창 개시)이다.")
    else:
        print("  신규 위반 0 — 어휘 클린.")
    for pid, errs in known:
        print(f"  [기지·게이트 대기] {pid}: {len(errs)}건 — 손 유지 상수 KNOWN_VOCAB_OFFENDERS 등재분")


def part_x() -> None:
    """[X] 일회용 프로브 인구조사 — 매 사이클 (c158 신설, P45, c157 HAND 별건 3).

    왜. c157의 프로브가 `hits = NC.scan(i) if hasattr(NC, "scan") else []`로 쓰였고
    `scan`은 없었다. `[]`가 조용히 반환돼 "검출기 hit = 0건"으로 인쇄됐다(실제 35).
    계기 본체는 전부 하드 가드를 갖췄고 **일회용 프로브만 갖추지 않았다**.

    자[尺]는 옮기지 않는다 — 탐지 규칙의 정본은 `probe_guard.PATTERNS` 하나이며
    여기서는 **import해서 쓴다**(파트 P의 VOCAB과 같은 규율).

    위상 병기: 이 인쇄는 턴2에 열리므로 **직전 사이클까지의 프로브**만 본다.
    당 사이클 프로브의 실시간 차단은 `probe_guard.need()`뿐이고 그것은 프로브가
    import해야 작동한다 — 이 파트는 (a)의 집행자가 아니라 준수 계수기다(P45 한계 ①).
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from probe_guard import (  # noqa: PLC0415
            PATTERNS, cycle_of, probe_paths, scan_probes,
        )
        rep = scan_probes(probe_paths(REPO))
    except Exception as exc:  # 계기 고장이 step 0을 죽이지 않는다 — 강등 후 계속
        print("\n[X. 일회용 프로브 인구조사]")
        print(f"  !! 계기 자체가 돌지 않았다: {type(exc).__name__}: {exc}")
        print("     → 이 사이클의 프로브 판정은 **미측정**이다. '위반 0'으로 읽지 말 것.")
        print("     (P45 (c): 미측정이 2사이클 이상이면 (b)는 판정 불가가 아니라 반증이다.)")
        return

    viol, unparsed = rep["violations"], rep["unparsed"]
    print("\n[X. 일회용 프로브 인구조사 — 매 사이클 (c158 신설, P45)]")
    print(f"  tmp/*.py {len(rep['scanned'])}본 검사 · 위반 {len(viol)}건 ·"
          f" **미검사 {len(unparsed)}본** · probe_guard 채택 {len(rep['guarded'])}본")
    print(f"  탐지 규칙 정본 = probe_guard.PATTERNS ({len(PATTERNS)}종: {' · '.join(PATTERNS)})"
          f" — 이 파일은 사본을 갖지 않는다.")
    print("  ※ 침묵은 '이 4종이 없다'이지 '조용한 거짓이 없다'가 아니다 (P45 한계 ③).")
    if unparsed:
        print("  !! 미검사분 — 이 수는 '위반 0'에 섞이지 않는다:")
        for u in unparsed:
            print(f"       {os.path.relpath(u['path'], REPO)}  {u['why']}")
    if viol:
        print("  !! 위반 — 폴백이 실패를 값으로 위장할 수 있는 자리:")
        for v in viol:
            c = cycle_of(v["path"])
            print(f"       c{c if c is not None else '??'}  "
                  f"{os.path.relpath(v['path'], REPO)}:{v['line']}  [{v['kind']}]  {v['src']}")
        print("     → 당 사이클 산출이면 처치하고, 과거분이면 **사유를 원장에 적을 것**")
        print("       (P45 (b) 반증 조건 = 인쇄됐는데 처치도 사유 기재도 없이 이월).")
    else:
        print("  위반 0 — 4패턴 클린.")


# ── ㉠ 서수 1종 고정 (c161 집행, P46 · 관측 85 수용 기준 ③ / 처치 설계 = c153 별건 1) ──
#: 자[尺]는 **하나**다: "N사이클째" = `N − start + 1` (당 사이클 **포함**).
#: 이 표는 **손 유지 상수**다 — `CODE_QUEUE_PATHS`·`KNOWN_VOCAB_OFFENDERS`와 같은 등급.
#: 값은 원장 계열의 최빈 앵커에서 역산했고(`tmp/c161_ordinal_series.py`), 파트 O가 매
#: 사이클 그 역산을 다시 돌려 이 상수와 대조한다. 계열이 열리거나 닫히면 이 표를 고치고
#: **보고에 선언**할 것. 기계가 된 것은 **산술**이고 앵커의 개시 판단은 아니다(P46 한계 ②).
#:
#: `A-106.1`은 **의도적으로 없다** — 그 라벨의 정규식이 40자 창 안의 원터치 값을 흡입해
#: 계열이 오염됐다(c151 행 직독으로 확인, 관측 74와 같은 모양). 오염된 계열을 감시하는
#: 것보다 감시하지 않는다고 **적는 것**이 정직하다.
ORDINAL_ANCHORS = (
    ("봉쇄(타 트랙 미커밋 잔존)", 127, r"(?:미커밋|잔존|영토)[^\n]{0,80}?(\d+)사이클째"),
    ("게이트 서비스율 0", 116, r"서비스율[^\n]{0,40}?(\d+)사이클째"),
    ("인스턴스 원터치 대기", 142, r"원터치[^\n]{0,60}?(\d+)사이클째"),
)

#: 계열이 같은 낱말을 다른 시기의 다른 사건에 재사용하면 한 라벨에 두 계열이 섞인다.
#: 최근 창으로 잘라 **당대 에피소드**만 본다 — 창 밖 표본은 계열이 아니라 동음이의다.
ORDINAL_WINDOW = 20

#: ㉠ 집행 사이클. 이 경계 **이후**의 계열 이탈이 P46 (a)의 반증 사건이다 — 이전 이탈은
#: 처치의 근거(기지)이고 반증이 아니다. 둘을 한 수로 합치면 처치가 자기 근거로 반증된다.
ORDINAL_TREATMENT_CYCLE = 161

#: c168 신설 (관측 96 처치 · P52). P46이 기계화한 것은 **산술형** 계수기 셋뿐이었다
#: (`ORDINAL_ANCHORS` — 값 = `N − start + 1`). 원장 산문에는 **상태형** 계수기가 따로
#: 살고 있었고 그 둘은 계기 밖에서 손이 증분했다. c168 실측: `fixed` 연속 0은 참값보다
#: **3 적게**(주장 22 · 참 25), 캡슐 miss 연속은 **29 많게**(주장 77 · 참 48) 인쇄됐다.
#: 방향이 반대라 한 사이클의 행만 보면 어느 쪽도 틀려 보이지 않는다 — P46이 산술형에서
#: 잡은 보상 오류와 같은 모양이다.
#:
#: 상태형은 앵커 상수가 **필요 없다**: 원장 필드 자신이 개시 시점을 안다. 그래서 이 표에는
#: `start`가 없고, 손이 유지할 값도 없다. 넷째 원소는 **손 인쇄 대조용** 정규식이다.
STREAK_COUNTERS = (
    ("`frictions_fixed` 0 연속", "frictions_fixed", 0,
     r"(?:fixed|`fixed`)[^0-9]{0,14}?(\d+)\s*연속"),
    ("캡슐 miss 연속", "restore_grade_capsule", "miss",
     r"캡슐[^0-9]{0,20}?(\d+)\s*연속"),
)


def field_streak(rows: list[dict], field: str, value: object) -> dict:
    """원장 역순으로 `field == value`가 끊길 때까지 센다. **순수 함수.**

    자[尺] 선언 (관측 85 · 96). 이 계수기의 프레임은 파트 O 산술형과 **다르다**:
    산술형은 실행 사이클을 포함하지만(`N − start + 1`), 상태형이 세는 것은 **원장에
    이미 쓰인 행**이고 실행 사이클의 행은 아직 없다. 두 자[尺]를 한 수로 합치면
    그것이 관측 96이 잡은 병이므로, 값과 프레임을 **항상 같이** 인쇄한다.

    `domain`(필드를 가진 행 수)을 함께 돌려주는 이유가 관측 96의 정중앙이다:
    c161~c167 **7사이클** 동안 손이 *"캡슐 miss N연속"*으로 인쇄한 수는 실제로 이
    `domain`이었다(c161 71·c163 73·…·c167 77 = 정의역과 매 사이클 정확히 일치, 참
    연속값은 42·44·…·48). 라벨은 *연속*이라 말하고 값은 *정의역*을 말했다 — 두 수를
    계기가 **나란히** 인쇄하면 그 갈라짐이 화면에서 드러난다(관행 ㊴).

    `off_value`는 정의역 안에서 값이 다른 행이다. *"도입 이래 전부 miss"*류 주장은
    이 목록이 비어야 참이며, c168 실측으로 **거짓**이었다(c91~c94·c119 = `partial` 5건).
    """
    ordered = sorted((r for r in rows if field in r), key=lambda r: int(r["cycle"]))
    domain = [int(r["cycle"]) for r in ordered]
    off_value = [int(r["cycle"]) for r in ordered if r.get(field) != value]
    streak, brk = 0, None
    for r in reversed(ordered):
        if r.get(field) == value:
            streak += 1
        else:
            brk = (int(r["cycle"]), r.get(field))
            break
    return {
        "streak": streak,
        "break": brk,
        "domain": len(domain),
        "span": (domain[0], domain[-1]) if domain else None,
        "off_value": off_value,
        "frame_last": domain[-1] if domain else None,
    }


def _ledger_rows() -> list[dict]:
    rows = []
    with open(os.path.join(REPO, "research", "devloop", "metrics.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        raise SystemExit("[O] FATAL: 원장이 비었다 — 서수를 계산할 근거가 없다.")
    return rows


def _ordinal_series(rows: list[dict], pattern: str) -> list[tuple[int, int]]:
    """원장 행에서 (cycle, 인쇄된 서수) 계열을 뽑는다.

    어느 **필드**에 사는지는 묻지 않되, **필드 경계는 넘지 않는다.**

    c166 수리 (관측 93). 이전 판은 `json.dumps(row)`를 스캔했다. 직렬화는 값 안의
    개행을 `\\n` **2문자**로 이스케이프하므로 직렬화본에는 실개행이 **0개**다 —
    그래서 앵커 패턴의 `[^\\n]{0,80}` 창이 종료 조건을 잃고 필드 경계를 자유롭게
    넘었다. 실측 피해: c164 행에서 `predictions_note` 말미의 낱말 "영토"가 다음 필드
    `gate_pending` 서두의 **서비스율 값 49**를 삼켜, 봉쇄 라벨에 유령 이탈 1건을
    인쇄했다(함의 앵커 c116 = 서비스율 앵커). 그 유령이 c165 `task_state`를 거쳐
    c166에게 *"P46 (a)는 반증"*으로 인계됐다 — 관측 74의 모양(파서 거짓 값이 손
    판정을 통과해 사실로 굳는다)이며, 이번에는 판정 직전에 잡혔다.

    파싱된 값을 **필드별로** 보면 `[^\\n]`이 본래 의도대로 다시 경계가 된다.
    한 행에 여러 필드가 같은 라벨을 인쇄하면 **첫 매치만** 쓴다(구판과 동일한 계약 —
    행당 1표본이어야 앵커 최빈값이 행 수로 정규화된다).
    """
    rx = re.compile(pattern)
    out = []
    for r in rows:
        for value in r.values():
            if not isinstance(value, str):
                continue
            m = rx.search(value)
            if m:
                out.append((int(r["cycle"]), int(m.group(1))))
                break
    return out


def part_o() -> None:
    """[O] 서수 — 자[尺] 1종 고정 + 계기 계산 (c161 ㉠ 집행, P46).

    왜. 같은 낱말 "N사이클째"가 두 규약으로 쓰였다(관측 85 (A)): 계기는 `N − start`,
    손은 `N − start + 1`. 차이는 정확히 1이고 **같은 원장 행에 동거**했다. c153 별건 1이
    처치를 골랐고("서수 1종 고정 + 계기가 원장에서 직접 계산해 인쇄") c154~c160 **7회
    이월**됐다. 관측 85 수용 기준 ③이 c161 미집행을 **회피**로 못박았다.

    무엇이 실제로 바뀌는가. 손이 하던 **+1 산술**이 사라진다. 계열 실측이 그 산술의
    실패를 보였다: 서비스율 계열은 c146~c150 **5사이클 연속** 앵커를 한 칸 놓쳤다가
    c151에 **+2 점프**로 복귀했다 — 보상 오류여서 단일 행만 보면 어느 행도 틀려 보이지
    않는다. 봉쇄 계열은 c152에 Δ−2. 관행 ㉖("산문에만 사는 수는 추세를 만들 수 없다")의
    직접 처치이며, 이 파트가 그 수의 **기계 거처**다.
    """
    rows = _ledger_rows()
    n_exec = max(int(r["cycle"]) for r in rows) + 1
    print("\n[O. 서수 — 자[尺] 1종 고정 + 계기 계산 (c161 ㉠ 집행, P46 · 관측 85 수용 기준 ③)]")
    print('  정의 = "N사이클째" = N − start + 1 (당 사이클 **포함**). 자[尺]는 하나다.')
    print(f"  프레임 N={n_exec} (원장 cycle max {n_exec - 1} +1 = 실행 사이클, **append 전**).")
    print("  ※ 절차 5에서 원장 append 후 재실행하면 프레임이 +1 옮겨가고 값도 +1 된다 —")
    print("    전사 시 프레임을 값과 함께 옮기거나 이 파트를 재실행할 것 (P46 한계 ⑤).")
    print("  [아래 값을 원장·task_state에 **그대로** 전사할 것. 손 증분 금지 = P46 (a).]")

    for label, start, pattern in ORDINAL_ANCHORS:
        val = n_exec - start + 1
        series = _ordinal_series(rows, pattern)
        recent = [(c, o) for c, o in series
                  if series and c > max(x for x, _ in series) - ORDINAL_WINDOW]
        print(f"    {label}  →  **{val}사이클째**  [start c{start} · 프레임 N={n_exec}]")
        if not recent:
            print("       !! 계열 0본 — 정규식이 원장 문면과 다르다. '드리프트 없음'으로"
                  " 읽지 말 것(미측정이다).")
            continue
        anchors = [c - o + 1 for c, o in recent]
        modal = max(set(anchors), key=anchors.count)
        agree = "일치" if modal == start else f"**불일치** (선언 c{start})"
        print(f"       계열 {len(recent)}본(최근 {ORDINAL_WINDOW}창) · 최빈 앵커 c{modal} = {agree}")
        if modal != start:
            print("       !! 선언 상수와 계열 최빈이 갈렸다 — 상수가 틀렸거나 계열이"
                  " 표류했다. 둘 중 무엇인지 정하고 보고에 선언할 것.")
        pre = [c for c, o in recent if c - o + 1 != modal and c < ORDINAL_TREATMENT_CYCLE]
        post = [c for c, o in recent if c - o + 1 != modal and c >= ORDINAL_TREATMENT_CYCLE]
        line = f"       계열 이탈: 처치 전(기지) {len(pre)}본"
        if pre:
            line += f" (c{' c'.join(str(c) for c in pre)})"
        line += f" · **처치 후 {len(post)}본**"
        if post:
            line += f" (c{' c'.join(str(c) for c in post)}) ← P46 (a) 반증"
        print(line)
        if post:
            print("       !! 처치 후 이탈이 있다 — P46 (a)는 반증이다. 원장에 그대로 적을 것.")

    print("  [상태형 계수기 — c168 신설 (관측 96 처치 · P52). 산술형과 **프레임이 다르다**:")
    print("   원장에 이미 쓰인 행만 센다(실행 사이클 행은 아직 없다). 값과 프레임을 같이 전사할 것.]")
    for label, field, value, claim_rx in STREAK_COUNTERS:
        st = field_streak(rows, field, value)
        if st["frame_last"] is None:
            print(f"    {label}  →  !! 필드 `{field}` 보유 행 0 — 미측정이다"
                  " ('연속 0'으로 읽지 말 것).")
            continue
        span = st["span"]
        print(f"    {label}  →  **{st['streak']}연속**"
              f"  [프레임 = 원장 최종 c{st['frame_last']} · 실행 사이클 c{n_exec} **미포함**]")
        print(f"       정의역 {st['domain']}행 (c{span[0]}~c{span[1]}) · "
              f"중단 = {'c%d 값 %r' % st['break'] if st['break'] else '없음(정의역 전체가 연속)'}")
        if st["off_value"] != []:
            shown = " ".join(f"c{c}" for c in st["off_value"][:8])
            print(f"       정의역 내 값 다른 행 {len(st['off_value'])}건: {shown}"
                  f"{' …' if len(st['off_value']) > 8 else ''}"
                  "  ← '도입 이래 전부'류 주장은 이 목록이 비어야 참이다")
        if st["streak"] != st["domain"]:
            print(f"       ※ **연속 {st['streak']} ≠ 정의역 {st['domain']}** — 라벨이"
                  " '연속'인데 정의역을 적으면 관측 96 재발이다(P52 (a) 반증).")
        rx = re.compile(claim_rx)
        claimed = None
        last = max(rows, key=lambda r: int(r["cycle"]))
        for v in last.values():
            if isinstance(v, str) and (m := rx.search(v)):
                claimed = int(m.group(1))
                break
        if claimed is None:
            print(f"       직전 행(c{last['cycle']}) 손 인쇄 = 무기재 (대조 불가)")
        else:
            gap = claimed - st["streak"]
            verdict = "일치" if gap == 0 else f"**어긋남 {gap:+d}**"
            print(f"       직전 행(c{last['cycle']}) 손 인쇄 {claimed} 대 계기 "
                  f"{st['streak']} = {verdict}"
                  + ("" if gap == 0 else
                     f" (정의역 {st['domain']}과의 차 {claimed - st['domain']:+d})"))


def part_f() -> None:
    """[F] 미해소 관측 인덱스 — 대장 파생 (A-95.1 루프 몫, c108 배선 · P34, 관측 52 처치).

    왜. open_observations는 c105 정의 후 세 사이클 연속 수기 재계수로만 산출됐고
    (c107 자기 기재: "상설화 필요성 3번째 실례"), 절차 2의 1순위 입력(미해소 마찰)은
    317KB 대장 통독 불가로 grep 절편으로만 접근됐다(관측 52). 이 인쇄가 A-95.1이
    말한 "상수 크기 조망"이다 — 원문은 여전히 표적 조회로 연다.
    """
    with open(FRICTIONS, encoding="utf-8") as fh:
        obs = parse_observations(fh.read())
    rows = []
    with open(os.path.join(REPO, "research", "devloop", "metrics.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    last = max(rows, key=lambda r: r["cycle"])
    prev = last.get("open_observations")

    opened = open_observation_numbers(obs)
    untagged = sorted(n for n, o in obs.items() if not o["tagged"])
    exited = sorted(n for n, o in obs.items() if o["exited"])
    print("\n[F. 미해소 관측 인덱스 — 대장 파생 (A-95.1 루프 몫, c108 배선 · P34)]")
    print("  정의 = 원본 헤더 회부/후보 태그 − 회부 이탈(처분 문단에 '종결'/'회부 상태를 벗').")
    print("  부분 처분(이탈 마커 없음)은 존속이다. 대장에 주석 없는 처분은 이 눈에 보이지 않는다.")
    if prev is None:
        delta_txt = "직전 원장 행에 open_observations 필드 없음 — Δ 판정 불가"
        delta = None
    else:
        delta = len(opened) - int(prev)
        delta_txt = f"직전 원장 행 c{last['cycle']}={prev}, Δ{delta:+d}"
    print(f"  open_observations={len(opened)}  (번호 있는 회부만 — {delta_txt})")
    if delta:
        print("  ★ Δ≠0 — 신규 관측 또는 처분이 있었다: 이번 원장 행 frictions_note에 귀속을 선언할 것.")

    # 관측 69 ② 처치 (c126) — 인쇄가 자기 사각의 크기를 함께 말한다. 소급 배정은
    # c125가 기각했으므로(참조 무결성), 없는 것은 숫자가 아니라 인쇄의 정직성이었다.
    unnum_total, unnum_tagged = unnumbered_blind_spot()
    lo, hi = C123_HONEST_RANGE
    print(f"  ↳ 사각: 무번호 관측 절 {unnum_total}건 중 회부/후보 {unnum_tagged}건은 이 눈 밖"
          f" (c123 계수 규칙 재사용, 소급 배정은 c125 기각).")
    print(f"     c123 정독 기준 정직 재고 범위 {lo}~{hi} — **빈티지**: 그 시점 자동 인쇄는"
          f" {C123_AUTO_AT_VINTAGE}, 지금 {len(opened)}이므로 자동 성분 이동분"
          f"({len(opened) - C123_AUTO_AT_VINTAGE:+d})은 이 범위에 미반영이다.")

    # audit-120 R2 (c126 이행) — 재고 회전의 크기. 권고 문면은 "처치 식별 완료·집행
    # 대기" 부분집합을 요구하나, 대장에는 그 상태를 가리키는 기계가독 마커가 없다
    # (그 부재 자체가 미등재 규약 공백이다). 여기서 부분문자열로 그 부분집합을 짐작하는
    # 것은 지금 이 사이클이 고치고 있는 결함(관측 63)을 새 자리에 다시 심는 일이므로
    # 하지 않는다 — 분모를 회부 존속 전체로 열고 **상한 근사임을 병기**한다.
    n_now = int(last["cycle"]) + 1
    if opened:
        oldest = max(opened, key=lambda n: n_now - (obs[n]["opened"] or n_now))
        stalest = max(opened, key=lambda n: n_now - (obs[n]["last"] or n_now))
        print(f"  ↳ 처치 대기 (audit-120 R2) — 분모 = 회부 존속 {len(opened)}건 전체."
              f" '처치 식별 완료·집행 대기' 부분집합은 기계가독 마커가 없어 **상한 근사**다.")
        print(f"     최고 등재 경과: 관측 {oldest} c{obs[oldest]['opened']}"
              f" → {n_now - obs[oldest]['opened'] + 1}사이클째 미해소  [프레임 N={n_now}]")
        print(f"     최고 무갱신  : 관측 {stalest} c{obs[stalest]['last']} 마지막 갱신"
              f" → {n_now - obs[stalest]['last'] + 1}사이클째 무갱신  [프레임 N={n_now}]")
        # c161 ㉠: 이 두 값은 c160까지 `N − start`(개시 제외)로 인쇄됐다. 이제 파트 O와
        # **같은 자[尺]**(당 사이클 포함)를 쓰므로 구 계열 대비 +1이다. 원장 소급 편집은
        # 금지(c122)이므로 고치는 대신 경계를 선언한다 — P46 한계 ③의 유일한 거처.
        print("     ※ 서수 = 당 사이클 포함(c161 ㉠ 통일, 파트 O와 동일 자[尺]).")
        print("       c160까지의 인쇄는 개시 제외였으므로 구 계열보다 **+1**이다 —")
        print("       추세를 읽는 손은 c161 경계에서 +1을 알 것(소급 편집 없음, P46 한계 ③).")

    print(f"  무태그(유형 기귀속, 계상 밖): {' '.join(str(n) for n in untagged)}"
          f"   회부 이탈: {' '.join(str(n) for n in exited)}")
    for n in opened:
        o = obs[n]
        mark = " ·처분文有(존속)" if o["partial_disposal"] else ""
        print(f"    관측 {n:>2}  c{o['opened']}→c{o['last']}{mark}  {o['title'][:64]}")


# ── 판정 기한 (파트 D, c164 신설 · P48 · 감사 R5 이관분 = 계기 큐 ㉦) ─────────
#
# 서식 변이는 **세어서** 인쇄한다. 어느 변이가 0일 때 그 0이 "그 서식이 없다"인지
# "정규식이 못 본다"인지를 다음 손이 물을 수 있어야 한다 — P48 한계 ③의 거처.
DEADLINE_VARIANTS = {
    "판정.": re.compile(r"^-\s*\*\*판정\.\*\*\s*\**\s*c(\d+)"),
    "판정 시한": re.compile(r"^-\s*\*\*판정 시한\.?\*\*\s*\**\s*c(\d+)"),
    "판정 채널": re.compile(r"^-\s*\*\*판정 채널\.?\*\*\s*\**\s*c(\d+)"),
}
# 달력 기한 — P36의 `- 예측 (판정: **2026-09-10 마감**` 계열. 사이클 자[尺]와 **다른 축**
# 이므로 따로 센다. 두 축을 한 칸에 합치면 그것이 관측 30·34(자[尺] 무선언 분기)다.
CAL_DEADLINE_RE = re.compile(r"\*\*(\d{4}-\d{2}-\d{2})\s*마감\*\*")

RUNNING_ARM = "시계-가동"
UNSTARTED_ARM = "시계-미시작"
OPEN_ARM_VALUES = (RUNNING_ARM, UNSTARTED_ARM)


def _pred_spans(text: str) -> tuple[list[str], dict[str, tuple[int, int]], dict[str, list[int]]]:
    """(줄 목록, {pid: (시작, 끝)}, {중복 pid: [줄 번호…]}) — 절 경계 계산의 **한 벌**.

    c169 이전에는 이 12줄이 `parse_deadlines` 안에만 있었고, 같은 경계를 필요로 하는
    두 번째 계기(상태줄↔판정문 정합)를 붙이는 순간 사본이 생길 자리였다. 관행 ㊷:
    한 계기 안에서 같은 개념의 분류는 한 벌이어야 한다.

    중복 pid는 **먼저 나온 절**이 이긴다 — `setdefault`의 계약이며 두 호출자가 같은
    절을 보게 하는 것이 목적이다. **그 정책을 반환값으로 드러낸다**: `part_d`의
    `recs = {r["id"]: r for r in …}`는 dict 컴프리헨션이라 **나중 절**이 이기고,
    두 정책은 **정반대**다. 그래서 중복 pid에서는 «한 절의 팔»과 «다른 절의 기한»이
    짝지어진다. c169 실측 = P39(기지, 관측 77) · **P7(신규 — 관측 99)**.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from c124_retro_prep import PSEC_RE  # noqa: PLC0415

    lines = text.splitlines()
    starts = [(i, m.group(1)) for i, l in enumerate(lines) if (m := PSEC_RE.match(l))]
    spans: dict[str, tuple[int, int]] = {}
    occurrences: dict[str, list[int]] = {}
    for k, (i, pid) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        for j in range(i + 1, end):
            if lines[j].startswith("## "):
                end = j
                break
        spans.setdefault(pid, (i, end))
        occurrences.setdefault(pid, []).append(i + 1)
    dups = {pid: at for pid, at in occurrences.items() if len(at) > 1}
    return lines, spans, dups


def parse_deadlines(text: str) -> dict:
    """절별 판정 기한을 뽑는다. **순수 함수** — 인자 텍스트만 본다(합성 표본 검증 가능).

    절 경계는 `_pred_spans`(→ `c124_retro_prep.PSEC_RE`)에 위임한다. 복사하면 절
    경계의 정본이 둘이 되고, 그것이 파트 P가 이미 피한 병이다.
    """
    lines, spans, _dups = _pred_spans(text)

    hits = dict.fromkeys(DEADLINE_VARIANTS, 0)
    cycle: dict[str, int] = {}
    calendar: dict[str, str] = {}
    for pid, (s, e) in spans.items():
        for line in lines[s:e]:
            for name, rx in DEADLINE_VARIANTS.items():
                if (m := rx.match(line)):
                    hits[name] += 1
                    if name == "판정.":
                        cycle.setdefault(pid, int(m.group(1)))
            if (m := CAL_DEADLINE_RE.search(line)):
                calendar.setdefault(pid, m.group(1))
    return {"variant_hits": hits, "cycle": cycle, "calendar": calendar,
            "sections": sorted(spans)}


# ── 상태줄 ↔ 판정문 정합 (c169 신설 · 관측 90 처치 · 관측 98 · P54) ──────────
#
# 판정 표지의 **서식지**다. 순진한 자[尺](`MARK_RE` 단독)로 재면 오늘 대장의 시계 아래
# 38건 중 23건이 "판정문 부재"로 나오고 **그 23건은 전부 판정문을 갖고 있다**(관측 98).
# 서식지를 더할 때마다 23 → 8 → 0. 이 상수가 이 계기의 유일한 정본이며 사본을 갖지
# 않는다 — 네 번째 서식지가 발견되면 고칠 곳은 여기 한 곳이다(P54 한계 ③).
VERDICT_HABITATS = (
    ("불릿", re.compile(r"^\s*-\s*\*{0,2}(결과|판정|처분)")),
    # P44: `- **★ 판정 (사이클 160 적대 감사 …)**` — `★`가 `\*{0,2}`를 넘긴다.
    ("불릿-강조접두", re.compile(r"^\s*-\s*[\*★☆\s]+(결과|판정|처분)")),
    # P15: `### P15 — 판정 (audit-70 위임 판정 …)` — 판정문이 **소제목**으로 산다.
    # `###`는 절을 끊지 않으므로(끊는 것은 `## `) 이 줄은 그 절의 몸 안에 있다.
    ("소제목", re.compile(r"^#{3,}\s.*(판정|처분|결과)")),
)

#: 손 유지 상수 — "도장 있는데 상태줄이 시계 위"가 **참 고발이 아닌** 절.
#: 값은 사유이며, 사유 없는 등재는 면죄부다(P54 (c) 반증 조건). 파트 P의
#: `KNOWN_VOCAB_OFFENDERS`와 같은 계열의 손 유지분 — 늘어나면 보고에 선언할 것.
STAMP_ONLY_ADJUDICATED = {
    "P4": "도장 줄 = `처분 (사이클 78): 집행 시작`이고 절 본문이 "
          "*'이 처분은 판정이 아니라 착공 선언'*이라고 자기가 적는다 (c169 직독)",
}

_UNRECORDED = "무기재"


def status_stamp_reconcile(text: str) -> dict:
    """상태줄과 판정 표지를 마주 세운다. **순수 함수** — 인자 텍스트만 본다.

    왜 (관측 90). 파트 D의 판별 입력은 각 절의 `- 상태:` **한 줄**이고, 그 줄을 쓰는 손과
    판정문을 쓰는 손은 같은 손이되 **다른 줄**이다. 상태줄만 내려가고 판정문이 없으면
    파트 D는 그 예측을 시계에서 내리고 **영원히 침묵한다** — 거짓 음성이며 그 침묵이
    "판정 완료"로 읽힌다. 반대 방향(판정문만 있고 상태줄이 가동)은 `도과`를 불러 손을
    부르므로 **안전한 쪽**이다. 두 실패는 대칭이 아니다.

    고발의 문턱을 «도장 없음»이 아니라 «**표지 자체가 없음**»으로 낮춘 것은 의도다:
    `_is_verdict_line`(도장 판별)은 도장 없는 진짜 처분 줄을 버린다는 것이 c124 손 판정
    (P18·P26·P28·P29)으로 **이미 측정돼 있다.** 그 기지의 오류를 고발로 승격하면
    계기는 첫날 늑대소년이 된다(관측 87의 종착지). 무도장 절은 **고발이 아니라 별도 칸**이다.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from c124_retro_prep import STATUS_RE, _is_verdict_line, parse_status  # noqa: PLC0415

    lines, spans, dups = _pred_spans(text)
    sections: dict[str, dict] = {}
    for pid, (s, e) in spans.items():
        body = lines[s:e]
        field = next((m.group(1) for l in body if (m := STATUS_RE.match(l.strip()))), None)
        arms = parse_status(field)[0] if field is not None else []
        vals = [v for _, v in arms]
        habitat_hits = dict.fromkeys((n for n, _ in VERDICT_HABITATS), 0)
        markers: list[str] = []
        for line in body:
            hit = False
            for name, rx in VERDICT_HABITATS:
                if rx.match(line):
                    habitat_hits[name] += 1
                    hit = True
            if hit:
                markers.append(line.strip())
        sections[pid] = {
            "field": field,
            "open": sum(1 for v in vals if v in OPEN_ARM_VALUES),
            "closed": sum(1 for v in vals
                          if v not in OPEN_ARM_VALUES and v != _UNRECORDED),
            "habitat_hits": habitat_hits,
            "markers": len(markers),
            "stamped": sum(1 for m in markers if _is_verdict_line(m)),
        }

    def _pick(pred) -> list[str]:
        return [pid for pid, r in sections.items() if pred(r)]

    down = _pick(lambda r: r["closed"] and not r["open"])
    stamp_only = _pick(lambda r: r["open"] and not r["closed"] and r["stamped"])
    return {
        # 중복 pid — 이 계기는 **먼저**를, `part_d`의 `recs`는 **나중**을 택한다(정반대).
        "duplicate_pids": dups,
        # 손 유지 상수로 가른다 — 기지분을 매 사이클 고발하면 그 인쇄가 곧 소음이 되고,
        # 소음이 된 인쇄는 다음 손이 읽지 않는다(관측 87). 사유는 상수가 들고 있다.
        "stamp_only_new": [p for p in stamp_only if p not in STAMP_ONLY_ADJUDICATED],
        "stamp_only_known": [p for p in stamp_only if p in STAMP_ONLY_ADJUDICATED],
        "sections": sections,
        "down": down,
        # ★ 조용한 쪽 = 관측 90의 진짜 고발 대상. 상태줄은 내려갔는데 표지가 없다.
        "silent_drop": [p for p in down if sections[p]["markers"] == 0],
        # 팔 일부만 판정났는데 표지가 없다 — 같은 병의 약한 판본.
        "partial_drop": _pick(lambda r: r["closed"] and r["open"] and r["markers"] == 0),
        # 표지는 있으나 무도장 — c124가 이미 잰 v2의 거래. **고발 아님**.
        "unstamped_down": [p for p in down if sections[p]["markers"]
                           and sections[p]["stamped"] == 0],
        "clean_down": [p for p in down if sections[p]["stamped"]],
        # 안전한 쪽 = 도장 달린 판정 줄이 있는데 상태줄 전건이 시계 위.
        "stamp_only": stamp_only,
    }


def part_d() -> None:
    """[D] 예측 판정 기한 — 매 사이클 (c164 신설, P48, 감사 R5 이관분 = 계기 큐 ㉦).

    왜. 판정 기한을 배달하는 채널이 **산문 하나**였다. c163의 P45 기한은 `task_state`
    산문에만 실려 있었고 그 채널은 c161처럼 꼬리에서 죽으면 통째로 사라진다 —
    c163이 P45를 제때 판정한 것은 규율이 아니라 운이며 c163 자신이 그렇게 적었다.
    관행 ⑥의 적용: 처치를 규약 문면이 아니라 계기에 놓되, 그 계기가 열리는 주기(매
    사이클 step 0)가 기한이 도래하는 주기와 같아야 한다.

    이 파트는 인쇄하고 `exit 0`이다(P48 한계 ①). 강제는 다음 손의 몫이고, 그 몫을
    안 하면 P48 (c)가 반증된다 — 함정을 미리 파 두었다.
    """
    print("\n[D. 예측 판정 기한 — 매 사이클 (c164 신설, P48 · 감사 R5 이관 = 계기 큐 ㉦)]")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from c124_retro_prep import PRED, predictions  # noqa: PLC0415
        parsed = parse_deadlines(PRED.read_text(encoding="utf-8"))
        recs = {r["id"]: r for r in predictions()["records"] if r["habitat"] == "절"}
    except Exception as exc:  # 계기 고장이 step 0을 죽이지 않는다 — 강등 후 계속
        print(f"  !! 파트 자체가 돌지 않았다: {type(exc).__name__}: {exc}")
        print("     → 이 사이클의 기한 판정은 **미측정**이다. '기한 없음'으로 읽지 말 것.")
        return

    rows = []
    with open(os.path.join(REPO, "research", "devloop", "metrics.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    n_now = max(int(r["cycle"]) for r in rows) + 1
    today = time.strftime("%Y-%m-%d")

    hits = parsed["variant_hits"]
    print("  서식 변이별 적중: " + " · ".join(f"'{k}' {v}건" for k, v in hits.items())
          + f"   달력 기한 {len(parsed['calendar'])}건")
    print("  ※ 0인 변이는 '그 서식이 없다'와 '정규식이 못 본다'를 구별하지 않는다 —"
          " P48 한계 ③.")

    # 시계 위 = 팔에 미도래 어휘가 하나라도 있는 절. 가동/미시작을 **가르지 않으면**
    # (a)의 표본 크기가 부풀려진다: 미시작은 기한 무기재가 정상이다.
    open_arms = {pid: [(a, v) for a, v in r["arms"] if v in OPEN_ARM_VALUES]
                 for pid, r in recs.items()}
    pending = {pid: arms for pid, arms in open_arms.items() if arms}
    running = {pid: arms for pid, arms in pending.items()
               if any(v == RUNNING_ARM for _, v in arms)}
    unstarted = sorted(set(pending) - set(running), key=_pid_key)

    print(f"  시계 위 {len(pending)}건 = **가동 {len(running)}** · 미시작 {len(unstarted)}"
          f"  [프레임 N={n_now}, 원장 cycle max +1]")

    due, overdue, future, no_deadline = [], [], [], []
    for pid in sorted(pending, key=_pid_key):
        cyc = parsed["cycle"].get(pid)
        cal = parsed["calendar"].get(pid)
        is_running = pid in running
        if cyc is not None:
            (due if cyc == n_now else overdue if cyc < n_now else future).append(
                (pid, f"c{cyc}", cyc - n_now, is_running))
        elif cal is not None:
            over = cal < today
            (overdue if over else future).append((pid, cal, None, is_running))
        else:
            no_deadline.append((pid, is_running))

    if due:
        print("  ★★ 오늘이 기한이다 — 절차 2의 선택은 이 판정이다:")
        for pid, d, _, is_run in due:
            print(f"       {pid}  기한 {d}  ({'가동' if is_run else '미시작'})"
                  f"  → predictions.md `## {pid}` 절의 팔 전건을 판정하고 상태줄을 갱신할 것")
    else:
        print("  오늘 기한인 예측 0건.")
    for pid, d, gap, is_run in overdue:
        tail = f" → {-gap}사이클 초과" if gap is not None else " → 달력 기한 도과"
        print(f"  !! **도과** {pid} 기한 {d}{tail} ({'가동' if is_run else '미시작'})")
        print("       → 판정하거나, 이월이면 **사유를 원장에 적을 것** (P48 (c) 반증 조건).")
    if not overdue:
        print("  도과 0건 — 다만 이 0은 '검출기가 돈다'의 증거가 아니다(관행 ㉕).")
    for pid, d, gap, is_run in future:
        when = f"{gap}사이클 뒤" if gap is not None else "달력 기한"
        print(f"     예정 {pid} → {d} ({when})")
    if no_deadline:
        run_blind = [pid for pid, is_run in no_deadline if is_run]
        print(f"  ↳ 사각: 기한 무기재 {len(no_deadline)}건 — 그중 **가동 {len(run_blind)}건**"
              f"{' (' + ' '.join(run_blind) + ')' if run_blind else ''}"
              f" · 미시작 {len(no_deadline) - len(run_blind)}건(무기재가 정상).")
        print("     트리거형 예측은 원리적으로 이 눈 밖이다 — 정의역 선언(P48 한계 ②).")

    # ── 상태줄 ↔ 판정문 정합 (c169 신설 · 관측 90 처치 · P54) ─────────────────
    # 파트 D 안에 둔 것은 의도다: 이 파트의 판별 입력이 곧 상태줄이므로, 그 입력의
    # 신뢰도는 판별 결과와 **같은 화면**에 있어야 한다(관행 ㉘).
    try:
        _print_status_stamp(status_stamp_reconcile(PRED.read_text(encoding="utf-8")))
    except Exception as exc:
        # 미측정을 **인쇄하고 계속한다** — 아래 문서 시계는 이 계기와 독립이므로
        # 여기서 return하면 무관한 인쇄가 함께 죽는다(계기 고장의 전파).
        print(f"\n  [상태줄↔판정문 정합] !! 미측정: {type(exc).__name__}: {exc}")
        print("     → '정합 위반 0'으로 읽지 말 것.")

    # 회고·감사 시계는 예측 대장이 아니라 사이클 번호가 정한다. 같은 화면에 둔다 —
    # 기한을 만나는 손이 "그 판정을 쓸 문서가 언제 열리는가"도 함께 알아야 한다(관행 ⑧).
    try:
        from c124_retro_prep import next_audit, next_retro  # noqa: PLC0415
        print(f"  문서 시계: 다음 회고 c{next_retro(n_now)} · 다음 적대 감사 c{next_audit(n_now)}")
    except Exception as exc:
        print(f"  문서 시계 미측정: {type(exc).__name__}: {exc}")


def _print_status_stamp(rec: dict) -> None:
    """정합 인쇄 — 계산(`status_stamp_reconcile`)과 가른다.

    가르는 이유: 계산은 순수 함수여서 합성 표본으로 회귀에 걸리고, 인쇄는 그렇지
    않다. 둘을 한 함수에 두면 회귀가 인쇄 문자열에 묶여 서식 변경마다 깨진다.
    """
    down, silent = rec["down"], rec["silent_drop"]
    print("\n  [상태줄↔판정문 정합 — c169 신설 (관측 90 처치 · 관측 98 · P54)]")
    print(f"    시계 아래(전건 판정 선언) {len(down)}건"
          f" — 도장 있음 {len(rec['clean_down'])}"
          f" · 표지만(무도장) {len(rec['unstamped_down'])}"
          f" · **표지 자체 없음 {len(silent)}**")
    habitats = {n: sum(r["habitat_hits"][n] for r in rec["sections"].values())
                for n, _ in VERDICT_HABITATS}
    print("    표지 서식지별 적중: "
          + " · ".join(f"'{k}' {v}건" for k, v in habitats.items()))
    print("    ※ 서식지 목록은 **오늘 실측한 3종**이지 전수가 아니다 — 넷째가 있으면 이 눈은"
          " 다시 오고발한다(P54 한계 ③). 순진한 자[尺] 단독이면 오늘 오고발 23건(관측 98).")
    if silent:
        print("    !! **상태줄 단독 하강(판정문 부재)** — 조용한 거짓 음성, 관측 90의 고발 대상:")
        for pid in sorted(silent, key=_pid_key):
            print(f"         {pid}  상태: {rec['sections'][pid]['field']}")
        print("       → 판정문을 쓰거나, 상태줄을 되돌릴 것. 침묵이 '판정 완료'로 읽힌다.")
    else:
        print("    상태줄 단독 하강 0건 — 다만 이 0은 서식지 목록이 전수일 때만 참이다.")
    if rec["partial_drop"]:
        print("    !! 부분 하강(팔 일부 판정 + 표지 부재): "
              + " ".join(sorted(rec["partial_drop"], key=_pid_key)))
    if rec["stamp_only_new"]:
        print("    !! **상태줄 미갱신(도장 단독)** — 안전한 쪽 거짓 양성 방향, 손을 부른다:")
        for pid in sorted(rec["stamp_only_new"], key=_pid_key):
            print(f"         {pid}  상태: {rec['sections'][pid]['field']}"
                  f"  (도장 {rec['sections'][pid]['stamped']}건)")
    for pid in sorted(rec["stamp_only_known"], key=_pid_key):
        print(f"    [기지·손 유지 상수] {pid} — {STAMP_ONLY_ADJUDICATED[pid]}")
    print("    ※ 두 갈래를 **둘 다** 인쇄한다 — 어느 쪽도 침묵이 아니다(관측 90 기대 동작).")
    if rec["duplicate_pids"]:
        print("    !! **중복 pid — 두 계기의 해소 정책이 정반대다** (관측 99 · 77 계열):")
        for pid, at in sorted(rec["duplicate_pids"].items(), key=lambda kv: _pid_key(kv[0])):
            where = " · ".join(f"L{n}" for n in at)
            print(f"         {pid}  절 {len(at)}본 ({where})"
                  f"  → 이 눈·기한 파서 = **먼저**(L{at[0]}) / 파트 D 팔 = **나중**(L{at[-1]})")
        print("       → 한 절의 팔과 다른 절의 기한이 짝지어진다. 정책을 고르기 전에"
              " 번호를 가르는 것이 정본 처치다(개명 패킷 = 게이트 대기).")


def _pid_key(pid: str) -> tuple[int, str]:
    return (int(re.sub(r"\D", "", pid) or 0), pid)


if __name__ == "__main__":
    part_n()
    # part_n을 1행에 남긴다 — 그 배너가 F-절차0 처치이고 P16 (a)가 5/5로 성립한
    # 작동 중인 처치다. 몸 지문은 그 **직후**(여전히 첫 화면)에 세운다.
    # part_s는 그 바로 다음 — 복원의 신뢰성 판정이 몸 지문보다 앞선다(c93).
    part_s()
    part_body()
    part_recall()
    part_a()
    part_b()
    # part_f는 말미다 — part_n 배너 1행·Body 첫 화면(P21)의 기존 계약을 건드리지 않고,
    # 인덱스는 절차 2(선택) 직전에 읽히는 마지막 화면이 된다.
    part_f()
    # part_d는 part_f 바로 뒤 — 기한이 오늘이면 그 판정이 **절차 2의 선택**이므로,
    # 선택 입력(미해소 관측 조망)과 같은 화면에 인접해야 한다. 파트 F의 '조망 =
    # 마지막' 계약은 c161에 파트 P·X가 아래에 붙어 실질 종료됐다(그 사실은 파트 O
    # 주석에 이미 적혀 있다).
    part_d()
    # part_p는 part_f 뒤 — 대장 위생은 절차 2의 선택 입력이 아니라 절차 3의 등록
    # 직전에 읽혀야 한다. 파트 F의 조망 계약(마지막 화면)을 깨지 않으려 그 아래 붙인다.
    part_p()
    # part_x는 말미 — 프로브 위생은 절차 3(수행) 직전에 읽히면 된다. 파트 P와 같은
    # 이유로 파트 F의 조망 계약 아래에 둔다.
    part_x()
    # part_o는 맨 마지막 — 서수는 절차 5(수확)에서 쓰이므로 마지막 화면이 곧 그 자리에
    # 가장 가까운 화면이다. 파트 F의 '조망 = 마지막' 계약은 c161에 파트 P·X가 이미
    # 아래에 붙어 실질 종료됐고(그 사실을 여기 적는다), 서수는 F의 경과값과 **같은
    # 자[尺]**를 쓰므로 둘이 인접해 대조되는 편이 낫다.
    part_o()
