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

규약: 결론 문장을 상수로 인쇄하지 않는다. 숫자만 낸다.
"""

from __future__ import annotations

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


def call(name: str, arguments: dict) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    req = urllib.request.Request(FORGET_URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    body = json.loads(urllib.request.urlopen(req, timeout=20).read())
    return json.loads(body["result"]["content"][0]["text"])


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
    for line in run(["git", "status", "--porcelain"]).splitlines():
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
    for label, rules in (("V1 (c46 원본 니들)", v1), ("V2 (c47 확장 니들)", v2)):
        hits, detail = needle_reach(shown, rules)
        print(f"  {label:22s} capsule_reach={hits}/3  {detail}")

    for lit in ("tail 금지", "cycle 필드", "cycle` 필드", "mtime", "devloop-self"):
        print(f"    literal {lit!r:16s} in_capsule={int(lit in shown)}")


if __name__ == "__main__":
    part_a()
    part_b()
