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

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
INSTALLED_HOOKS = os.path.expanduser("~/.forget/hooks")
FORGET_URL = "http://localhost:8000/mcp/forget/http/junghunkim"


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
    n = max(cycles) + 1
    mode = "적대 감사" if n % 10 == 0 else ("회고" if n % 5 == 0 else "일반")
    print("[!] metrics.jsonl을 직접 열지 말 것 — 번호·모드는 아래 한 줄이 정본이다.")
    print("    (tail/cat/head 계열 0회. 이 스크립트가 이미 전체를 파싱했다.")
    print("     지시서 절차 0의 '마지막 줄에서 N' 문면은 A-55.1 게이트 대기 중인 구본이며,")
    print("     감사 사이클의 metrics 정독 임무는 번호 결정 단계와 별개로 허용된다.)")
    print(f"[N. 사이클 번호 — cycle 필드 max+1]")
    print(f"  last_cycle={max(cycles)}  N={n}  mode={mode} (N%10={n % 10}, N%5={n % 5})")


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
    changed = [ln for ln in run_raw(["git", "status", "--porcelain"]).splitlines() if ln.strip()]
    print(f"  changed_paths_total={len(changed)}")  # c64: 분모를 병기해 침묵 절단을 드러낸다
    for line in changed:
        rel = line[3:].strip().strip('"')
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


def needle_reach(capsule: str, rules: dict[str, list[str]]) -> tuple[int, dict[str, int]]:
    detail = {k: int(any(nd in capsule for nd in v)) for k, v in rules.items()}
    return sum(detail.values()), detail


def part_b() -> None:
    print("\n[B. 규약 도달 — 니들 판본 대조]")
    sys.path.insert(0, INSTALLED_HOOKS)
    from forget_project import layered_filter, project_key_for_path, scope_disabled  # noqa: E402

    src = open(os.path.join(INSTALLED_HOOKS, "forget_sessionstart.py"), encoding="utf-8").read()
    budget = int(re.search(r"CAPSULE_CHAR_BUDGET\s*=\s*([0-9_]+)", src).group(1).replace("_", ""))

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


if __name__ == "__main__":
    part_n()
    part_a()
    part_b()
