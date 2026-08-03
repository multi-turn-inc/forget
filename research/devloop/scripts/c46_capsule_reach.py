#!/usr/bin/env python3
"""사이클 46 계측 — step 0 전달 채널의 도달률 (읽기 전용).

측정 대상: 무료 채널(SessionStart 캡슐)이 스토어의 task_state.next_actions 중
얼마를 실제로 다음 손에게 전달하는가. 두 단계로 나눠 잰다.

  단계 A (서버 조립)  prepare_context_autopilot 가 capsule_text 에 무엇을 담는가
  단계 B (문자 예산)  훅이 capsule_text[:CAPSULE_CHAR_BUDGET] 로 자른 뒤 무엇이 남는가

훅과 동일한 인자를 쓰기 위해 설치본 hooks 디렉터리의 forget_project 를 import 한다.
handoff 소비(_consume_handoff)는 부작용이므로 재현하지 않는다 — 캡슐 본문만 잰다.

규약: 이 스크립트는 결론 문장을 상수로 인쇄하지 않는다. 숫자만 낸다.
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
PROBE_LEN = 40  # next_actions 항목 식별용 접두 길이


def sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def call(name: str, arguments: dict) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    req = urllib.request.Request(
        FORGET_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    body = json.loads(urllib.request.urlopen(req, timeout=20).read())
    return json.loads(body["result"]["content"][0]["text"])


def main() -> None:
    # --- 1. 계측 대상이 실제로 돈 코드인지 확인 (P8 유령 전례) ---
    repo_hook = os.path.join(REPO, "hooks", "forget_sessionstart.py")
    inst_hook = os.path.join(INSTALLED_HOOKS, "forget_sessionstart.py")
    print("[hook identity]")
    for label, path in (("repo", repo_hook), ("installed", inst_hook)):
        print(f"  {label:9s} size={os.path.getsize(path):6d} sha256_16={sha(path)} path={path}")
    print(f"  identical={sha(repo_hook) == sha(inst_hook)}")
    src = open(inst_hook, encoding="utf-8").read()
    m = re.search(r"CAPSULE_CHAR_BUDGET\s*=\s*([0-9_]+)", src)
    budget = int(m.group(1).replace("_", ""))
    print(f"  CAPSULE_CHAR_BUDGET(installed)={budget}")

    # --- 2. 훅과 동일한 인자로 캡슐 조립 (단계 A) ---
    sys.path.insert(0, INSTALLED_HOOKS)
    from forget_project import layered_filter, project_key_for_path, scope_disabled  # noqa: E402

    cwd = REPO
    source = "startup"
    project = None if scope_disabled() else project_key_for_path(cwd)
    args = {
        "query": f"session {source} in {cwd} — active tasks, open loops, recent decisions",
        "include_debug": False,
    }
    pf = layered_filter(project)
    if pf:
        args["filters"] = pf
        args["project"] = project
    result = call("prepare_context_autopilot", args)
    capsule = str(result.get("capsule_text") or "").strip()
    shown = capsule[:budget]
    print("\n[capsule]")
    print(f"  project={project}")
    print(f"  capsule_text_chars={len(capsule)}")
    print(f"  shown_chars={len(shown)}  truncated={len(capsule) > budget}  dropped_chars={max(0, len(capsule) - budget)}")

    # --- 3. 스토어에 있던 next_actions 전량 (분모) ---
    print("\n[store next_actions]")
    items: list[tuple[str, int, str]] = []
    for task_id in ("devloop", "devloop-self"):
        st = call("get_task_state", {"task_id": task_id})
        cur = (st.get("current") or {})
        nas = cur.get("next_actions") or []
        for i, na in enumerate(nas):
            items.append((task_id, i, na))
        print(f"  {task_id:13s} items={len(nas):2d} chars={sum(len(x) for x in nas):6d}")
    print(f"  TOTAL         items={len(items):2d} chars={sum(len(x) for _, _, x in items):6d}")

    # --- 4. 도달률: 각 항목이 단계 A / 단계 B 를 통과했는가 ---
    print("\n[reach per item]  A=in capsule_text  B=in shown(after truncation)")
    reach_a = reach_b = 0
    for task_id, i, na in items:
        probe = na[:PROBE_LEN]
        in_a = probe in capsule
        in_b = probe in shown
        reach_a += in_a
        reach_b += in_b
        print(f"  A={int(in_a)} B={int(in_b)}  {task_id}[{i}]  {probe!r}")
    n = len(items)
    print(f"\n  stage_A_reach={reach_a}/{n}  stage_B_reach={reach_b}/{n}")

    # --- 4b. 전달된 항목은 통째로 전달됐는가 (항목 수가 아니라 문자 기준) ---
    print("\n[delivered fraction of the items that did reach]")
    delivered_chars = 0
    for task_id, i, na in items:
        if na[:PROBE_LEN] not in shown:
            continue
        k = len(na)
        while k > 0 and na[:k] not in shown:
            k -= 1
        delivered_chars += k
        print(f"  {task_id}[{i}] delivered_prefix_chars={k}/{len(na)}  cut_at={na[max(0,k-18):k]!r}")
    total_chars = sum(len(x) for _, _, x in items)
    print(f"  next_actions_chars_delivered={delivered_chars}/{total_chars}")

    # --- 4c. 캡슐 원문 (구조 확인용) ---
    print("\n[capsule verbatim]")
    for line in capsule.splitlines():
        print(f"  | {line}")

    # --- 5. 이번 사이클이 실제로 집행한 step 0 규약 3건의 출처 ---
    print("\n[step0 shadow rules — presence in official docs]")
    official = ""
    for rel in ("LOOP.md", "research/devloop/cycle-prompt.md"):
        official += open(os.path.join(REPO, rel), encoding="utf-8").read()
    rules = {
        "(i) both task_states": ["devloop-self"],
        "(ii) uncommitted mtime vs HEAD": ["mtime"],
        # 사이클 47: 규약 (iii)의 문구가 바뀌자 원래 니들이 거짓 음성을 냈다. 니들을 새 문구에
        # 맞추면 계측을 텍스트에 맞추는 것이므로, 두 판본 모두에 등장하는 **금지 자체**를 니들로
        # 삼는다("tail 금지"). c46·c47의 과거 판정(캡슐 0)은 이 확장으로 바뀌지 않는다 —
        # 그 사이클들에서는 90자 컷 때문에 어느 문구도 캡슐에 닿지 못했다.
        "(iii) cycle field not tail": ["cycle` 필드", "cycle 필드", "tail 금지"],
    }
    for label, needles in rules.items():
        in_official = any(nd in official for nd in needles)
        in_store = any(any(nd in na for nd in needles) for _, _, na in items)
        in_capsule = any(nd in shown for nd in needles)
        print(f"  official={int(in_official)} store={int(in_store)} capsule={int(in_capsule)}  {label}")

    # --- 6. 절차 0 장부 비용 (F-절차0 추세) ---
    print("\n[metrics.jsonl cost of step 0]")
    mpath = os.path.join(REPO, "research", "devloop", "metrics.jsonl")
    lines = [l for l in open(mpath, encoding="utf-8") if l.strip()]
    print(f"  rows={len(lines)} total_bytes={os.path.getsize(mpath)}")
    print(f"  tail_1_bytes={len(lines[-1].encode())}  tail_3_bytes={sum(len(l.encode()) for l in lines[-3:])}")
    cheap = len(json.dumps(json.loads(lines[-1])['cycle']).encode())
    print(f"  cycle_field_only_bytes={cheap}")

    # --- 6b. 항목 내 규약 위치 대 병행 트랙 컷 (사이클 47 추가) ---
    # 병행 트랙은 next_actions[0][:90] 이므로, 규약이 항목 어디에 있느냐가 도착 여부를 정한다.
    print("\n[rule offset within item vs parallel-track cut]")
    for task_id, i, na in items:
        if i != 0:
            continue
        for label, needle in (("(iii) cycle field", "cycle` 필드"), ("(ii) mtime", "mtime")):
            pos = na.find(needle)
            if pos >= 0:
                print(f"  {task_id}[0] {label:18s} starts_at={pos:4d} vs_cut_90={pos - 90:+5d} len={len(na)}")

    # --- 7. 영토 봉쇄 나이 (다른 세션 WIP) ---
    print("\n[territory block age]")
    head_ct = int(subprocess.run("git log -1 --format=%ct", shell=True, cwd=REPO,
                                 capture_output=True, text=True).stdout.strip())
    porc = subprocess.run("git status --porcelain", shell=True, cwd=REPO,
                          capture_output=True, text=True).stdout.splitlines()
    for line in porc:
        p = line[3:].strip().strip('"')
        full = os.path.join(REPO, p)
        if os.path.isdir(full):
            mt = max((os.path.getmtime(os.path.join(r, f))
                      for r, _, fs in os.walk(full) for f in fs), default=0)
        elif os.path.exists(full):
            mt = os.path.getmtime(full)
        else:
            continue
        print(f"  {p:34s} mtime_epoch={int(mt)}  head_minus_mtime_seconds={head_ct - int(mt)}")


    # --- 8. 슬롯 소유: 어느 태스크가 전량 슬롯을 갖는가 (사이클 47 추가, 진단 전용) ---
    # store.py 는 workspace_current(= 최신 활성 비-goal 태스크)에게 "현재 목표"+"다음 행동"을
    # 통째로 주고, 나머지는 _parallel_track_lines 가 next_actions[0][:90] 로 자른다.
    # 즉 마지막에 쓴 태스크가 전량 슬롯을 갖는다 — 순서가 지렛대다.
    print("\n[slot ownership — listing order decides who gets the full slot]")
    # 캡슐 조립은 _capsule_scope_filters 를 거치므로 같은 project 스코프로 물어야 일치한다
    listing = call("get_task_state", {"limit": 12, **({"project": project} if project else {})})
    for i, item in enumerate(listing.get("results") or []):
        if not isinstance(item, dict):
            continue
        print(f"  [{i}] {str(item.get('task_id')):26s} status={str(item.get('status')):12s}"
              f" valid_from={item.get('valid_from')}")
    print(f"  current={(listing.get('current') or {}).get('task_id')}")


if __name__ == "__main__":
    main()
