#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""oracle replay — 조용한 회상 실패의 사후 재생 대조 (헌장 백로그 #8).

**이 파일이 왜 사이클 접두어를 갖지 않는가.** 전임자 `c121_obs68_oracle_replay.py`는
`CYCLES = [116..120]`을 **모듈 상수**로 박았다. 그 결과 임무는 매 회고에 열리는데
계기는 c116~c120에만 열렸고, 재사용에 손이 들어 **c125·c135·c145·c155 네 회고가
연속 미이행**했다(amendment-155 §4-⑧ 진단). 이 파일의 유일한 설계 변경은
**정의역을 상수에서 인자로 옮긴 것**이다 — 관행 ⑥(처치를 계기에 놓되 그 계기가
열리는 주기가 쓰기 주기와 같아야 한다)의 이행이며, 그래서 이름에 사이클이 없다.

**검색 계약은 c121에서 한 글자도 바꾸지 않았다.** recall=low · top_k=10 ·
질의=work[:300] · 적격 = created_at < 직전 사이클 수확 커밋 시각 · trace 미전달.
바꾸면 c36·c57·c58·c59·c121의 `silent_miss=0` 계열과 비교 불가가 되기 때문이다
(대조군 보존이 정의역 확장보다 우선한다 — 원칙 1).

설계 규약 (c117/c118/c121 승계):
- 읽기 전용: `search_memories`만. trace 미전달(피드백 원장 오염 방지), recall=low는
  게이트 LLM 미경유(관측 65의 high 경로 회피, 비용 $0).
- 질의 원문 무인쇄 (관측 36·37): 산출물에는 sha8+길이만. 결과 본문도 stdout head만.
- 적격 필터: 서버측 `filters` + 클라이언트측 재검증 이중화(서버 필터 불신).
- 계기 검색은 recall 계상 밖 (c68 선언).

판정 기준 (선행 선언 — frictions.md 관측 68 수용 기준 ① 문면 그대로, 무변경):
- 차집합 0 → (b) 수요 소멸 지지. >0 → 항목별로 "작업을 바꿨을 것인가"를 **세션이**
  채점하고 silent_miss 계수만 원장에 싣는다. 채점 근거는 처분 문단에 항목별 한 줄.

계기 한계 (선언, c121 문면 승계):
1. top_k=10·단일 질의 절단 조건이라 **재현율 하한 표본**이다 — 차집합 0은 "이 조건에서
   0"이지 스토어 전수 조사가 아니다.
2. **배달 대조는 기계가 못 한다.** 캡슐·task_state가 그 사이클에 실제로 무엇을
   배달했는지는 사후에 재구성되지 않으므로, 이 계기는 *후보*를 인쇄하고 차집합
   판정은 손이 한다. 그 손이 곧 채점자이므로 순환이며, 한계로 병기한다.
3. `--cycles` 기본값은 원장 마지막 5사이클이다. 기본값으로 돌리면 **매번 다른 창**을
   보므로, 계열 비교 시에는 창을 명시할 것.

사용:
    .venv/bin/python research/devloop/scripts/oracle_replay.py                 # 최근 5
    .venv/bin/python research/devloop/scripts/oracle_replay.py --cycles 160-164
    .venv/bin/python research/devloop/scripts/oracle_replay.py --cycles 116,117,118
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_guard import ProbeFailure  # noqa: E402  하드 실패 — 폴백 금지

FORGET_URL = os.environ.get("FORGET_MCP_URL", "http://localhost:8000/mcp/forget/http/junghunkim")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
LEDGER = os.path.join(HERE, "..", "metrics.jsonl")

QUERY_CAP = 300  # 훅 원문 절단 상한 재사용 (합성 조건) — c121 무변경
TOP_K = 10       # c121 무변경
REQ_TIMEOUT = 30.0
HEAD_CHARS = 160  # stdout 전용 — 커밋 산출물에는 싣지 않는다


def sha8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def parse_cycles(spec: str) -> list[int]:
    """'160-164' 또는 '116,117' 또는 '160-162,164'. 빈 결과는 하드 실패."""
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            lo_i, hi_i = int(lo), int(hi)
            if hi_i < lo_i:
                raise ProbeFailure(f"--cycles 구간 역순: {part}")
            out.extend(range(lo_i, hi_i + 1))
        else:
            out.append(int(part))
    if not out:
        raise ProbeFailure(f"--cycles 파싱 결과가 비었다: {spec!r}")
    return sorted(dict.fromkeys(out))


def rpc(name: str, arguments: dict) -> tuple[dict | None, str]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    req = urllib.request.Request(FORGET_URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        body = json.loads(urllib.request.urlopen(req, timeout=REQ_TIMEOUT).read())
        return json.loads(body["result"]["content"][0]["text"]), ""
    except Exception as exc:
        # 통신 실패는 값이 아니라 표기로 남긴다 — 빈 결과와 구별되어야 한다.
        return None, type(exc).__name__


def harvest_epochs() -> dict[int, int]:
    out = subprocess.run(["git", "log", "--format=%ct %s", "-n", "400"],
                         cwd=REPO, capture_output=True, text=True, check=True).stdout
    epochs: dict[int, int] = {}
    for line in out.splitlines():
        m = re.match(r"^(\d+) loop\(cycle (\d+)\)", line)
        if m:
            epochs.setdefault(int(m.group(2)), int(m.group(1)))  # 최신 우선
    return epochs


def parse_created(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("inf")  # 파싱 불가 = 부적격(보수적). 조용한 통과가 아니다.


def main() -> int:
    ap = argparse.ArgumentParser(description="oracle replay (백로그 #8) — 읽기 전용")
    ap.add_argument("--cycles", default="", help="예: 160-164 / 116,117 (기본: 원장 마지막 5)")
    ap.add_argument("--top-k", type=int, default=TOP_K)
    args = ap.parse_args()

    with open(LEDGER, encoding="utf-8") as fh:
        rows = {r["cycle"]: r for r in (json.loads(l) for l in fh if l.strip())}

    if args.cycles:
        cycles = parse_cycles(args.cycles)
        src = f"--cycles {args.cycles}"
    else:
        cycles = sorted(rows)[-5:]
        src = "기본값(원장 마지막 5)"
    missing = [n for n in cycles if n not in rows]
    if missing:
        raise ProbeFailure(f"원장에 없는 사이클: {missing} — 값을 지어내지 않는다")

    epochs = harvest_epochs()
    print(f"[정의역] {src} → c{cycles[0]}~c{cycles[-1]} {len(cycles)}건 · top_k={args.top_k}")
    print("[A. 표본 — 사이클별 작업 선언문 (원문 무인쇄: sha8+길이) · 적격 상한 epoch]")
    plan = []
    for n in cycles:
        work = rows[n].get("work", "")
        cutoff = epochs.get(n - 1)
        if not work or cutoff is None:
            print(f"  c{n}: 결측 (work {len(work)}자 · cutoff {cutoff}) — 제외")
            continue
        q = work[:QUERY_CAP]
        plan.append((n, q, cutoff))
        cut_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"  c{n}: work {len(work)}자 → 질의 {len(q)}자 (피복 {len(q) / len(work) * 100:.1f}%)"
              f" sha8={sha8(q)} · 적격 < {cut_iso} (loop(cycle {n-1}) 수확)")
    if not plan:
        raise ProbeFailure("적격 표본 0건 — 재생할 것이 없다")

    # ── 피복률 (c171 신설, 관측 91 수용 기준 (i)) ────────────────────────────
    # 왜. 이 계기의 검색 계약은 c121과 한 글자도 다르지 않은데(`QUERY_CAP=300` 고정)
    # `work`가 4.18배 자라는 동안 질의 피복률이 3.69배 줄었다. 계기는 터지지도
    # 침묵하지도 않고 **같은 단위로 계속 인쇄**했으므로 6개의 `silent_miss=0`이
    # 서로 다른 감도의 0인 채로 한 계열에 섞였다. 그 감도를 산출에 싣는다.
    covs = [len(q) / len(rows[n]["work"]) * 100 for n, q, _ in plan]
    mean_cov = sum(covs) / len(covs)
    mean_len = sum(len(rows[n]["work"]) for n, _, _ in plan) / len(plan)
    print(f"\n  [피복률 — c171 신설 (관측 91 수용 기준 (i)) · QUERY_CAP={QUERY_CAP} 고정]")
    print(f"    창 평균 work {mean_len:.1f}자 · 창 평균 피복 **{mean_cov:.1f}%**"
          f" (최소 {min(covs):.1f}% · 최대 {max(covs):.1f}%)")
    print("    ★ `silent_misses`를 원장에 적을 때 이 수를 **함께** 적어라 — 값 단독")
    print("      기재는 계열 오염이다(관측 91 수용 기준 (ii)).")
    print("    기지 대조: c116~c120 창 44.8% (c121 실행) vs c160~c164 창 12.2% (c165 실행)")
    print("      → 같은 코드가 다른 감도의 자[尺]였다. 소급 산출 = 관측 91 (iii)"
          " 처분 문단의 표.")

    print(f"\n[B. 재생 — recall=low · top_k={args.top_k} · trace 미전달 "
          f"· 서버측 created_at<cutoff + 클라 재검증]")
    seen_ids: dict[str, list[int]] = {}
    per_cycle: dict[int, list[dict]] = {}
    errors: list[tuple[int, str]] = []
    for n, q, cutoff in plan:
        cut_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        result, err = rpc("search_memories", {
            "query": q, "top_k": args.top_k, "recall": "low",
            "filters": {"created_at": {"lt": cut_iso}},
        })
        if err:
            errors.append((n, err))
        items = (result or {}).get("results") or []
        kept = []
        for it in items:
            mid = str(it.get("id") or "")[:8]
            created = str(it.get("created_at") or "")
            if parse_created(created) >= cutoff:
                continue  # 서버 필터 불신 재검증 — 부적격 탈락
            text = str(it.get("memory") or it.get("text") or "")
            kept.append({"id": mid, "created": created[:19], "score": it.get("score"),
                         "cats": it.get("categories"),
                         "head": text[:HEAD_CHARS].replace("\n", " ")})
            seen_ids.setdefault(mid, []).append(n)
        per_cycle[n] = kept
        print(f"\n  ── c{n} (err={err or '없음'} · 반환 {len(items)} · 적격 {len(kept)})")
        for k in kept:
            print(f"    {k['id']} {k['created']} score={k['score']} cats={k['cats']}")
            print(f"      | {k['head']}")

    print("\n[C. 교차 요약 — 판정 입력 (배달 대조·silent_miss 채점은 세션 몫, "
          "처분 문단에 근거 병기)]")
    print(f"  고유 기억 {len(seen_ids)}건 / 사이클×적격 연 {sum(len(v) for v in per_cycle.values())}건")
    for mid, ns in sorted(seen_ids.items(), key=lambda kv: -len(kv[1])):
        print(f"    {mid}: c{','.join(map(str, ns))}")
    if errors:
        print(f"  !! 통신 실패 {len(errors)}건: {errors} — 이 사이클의 0은 '없음'이 아니라 '못 봄'이다")
    print("  [주의] 이 계기는 재현율 하한이다 — 차집합 0은 '이 조건에서 0'이며 전수 부재 증명이 아니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
