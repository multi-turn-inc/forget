#!/usr/bin/env python3
"""c121 — 관측 68 수용 기준 ① 판별 실측: 최근 5사이클 작업 선언문의 oracle replay (읽기 전용).

질문: 능동 검색이 유익했을 자리가 실재했는가 — c116~c120 각 사이클의 작업 선언문
(원장 work 필드)으로 스토어를 사후 재생 검색해, "그 사이클 시작 전에 스토어에
있었고" ∧ "작업-관련"인데 "캡슐+task_state가 배달하지 않은" 기억의 차집합을 뜬다.
차집합 0 → 가설 (b) 수요 소멸 지지. >0 → (a) 적응 회피 / (c) 습관 표류 심문 계속,
그리고 차집합 중 작업을 바꿨을 항목만 silent_miss 후보 (판정은 세션이 수행, 근거 병기).

설계 규약 (c117/c118 계기 승계):
- 읽기 전용: search_memories만. trace 미전달(피드백 원장 오염 방지), 게이트 원장 행
  생성 없음(recall=low는 게이트 LLM 미경유 — 관측 65의 high 경로 회피, 비용 $0).
- 질의 원문 무인쇄 (관측 36·37): 원장·아티팩트에는 sha8+길이만. 결과 기억의 본문도
  stdout에 head 160자만 — 커밋되는 산출물은 이 스크립트 자신뿐이고, 판정 근거는
  frictions.md 처분 문단에 기억 id·계수로만 기재한다.
- 질의 = work[:300] (훅 원문 절단 상한과 동일 — forget_turnrecall.py의 300자 규약을
  재사용해 "그 사이클이 실제 낼 수 있었던 질의"에 근사. 합성 조건임을 병기).
- 적격 필터: created_at < 직전 사이클 수확 커밋 시각 (git log에서 loop(cycle N-1)
  커밋 epoch 추출). 사이클 N 중·후에 쓰인 기억은 "찾을 수 있었던 기억"이 아니다.
  서버측 filters + 클라이언트측 재검증 이중화.
- 계기 검색은 계상 밖 (c68 선언) — 이 스크립트의 호출은 recall 필드에 넣지 않는다.

판정 기준 (선행 선언 — frictions.md 관측 68 수용 기준 ①의 문면 그대로):
- 차집합 0 → (b) 지지. >0 → 항목별로 "작업을 바꿨을 것인가"를 세션이 채점하고
  silent_miss 계수만 원장에 실는다. 채점 근거는 처분 문단에 항목별 한 줄.
계기 한계 (선언): top_k=10·단일 질의 절단 조건이라 재현율 하한 표본이다 — 차집합 0은
"이 조건에서 0"이지 스토어 전수 조사가 아니다. 이 한계는 판정문에 병기한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.request
from datetime import datetime, timezone

FORGET_URL = os.environ.get("FORGET_MCP_URL", "http://localhost:8000/mcp/forget/http/junghunkim")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
LEDGER = os.path.join(HERE, "..", "metrics.jsonl")
CYCLES = [116, 117, 118, 119, 120]
QUERY_CAP = 300  # 훅 원문 절단 상한 재사용 (합성 조건)
TOP_K = 10
REQ_TIMEOUT = 30.0
HEAD_CHARS = 160  # stdout 전용 — 커밋 산출물에는 싣지 않는다


def sha8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def rpc(name: str, arguments: dict) -> tuple[dict | None, str]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    req = urllib.request.Request(FORGET_URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        body = json.loads(urllib.request.urlopen(req, timeout=REQ_TIMEOUT).read())
        return json.loads(body["result"]["content"][0]["text"]), ""
    except Exception as exc:
        return None, type(exc).__name__


def harvest_epochs() -> dict[int, int]:
    out = subprocess.run(["git", "log", "--format=%ct %s", "-n", "400"],
                         cwd=REPO, capture_output=True, text=True, check=True).stdout
    epochs: dict[int, int] = {}
    for line in out.splitlines():
        m = re.match(r"^(\d+) loop\(cycle (\d+)\)", line)
        if m:
            epochs.setdefault(int(m.group(2)), int(m.group(1)))  # 최신 우선 — 첫 등장 유지
    return epochs


def parse_created(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return float("inf")  # 파싱 불가면 부적격 처리 (보수적)


def main() -> None:
    with open(LEDGER, encoding="utf-8") as fh:
        rows = {r["cycle"]: r for r in (json.loads(l) for l in fh if l.strip())}
    epochs = harvest_epochs()
    print("[A. 표본 — 사이클별 작업 선언문 (원문 무인쇄: sha8+길이) · 적격 상한 epoch]")
    plan = []
    for n in CYCLES:
        work = rows[n].get("work", "")
        cutoff = epochs.get(n - 1)
        if not work or cutoff is None:
            print(f"  c{n}: 결측 (work {len(work)}자 · cutoff {cutoff}) — 제외")
            continue
        q = work[:QUERY_CAP]
        plan.append((n, q, cutoff))
        cut_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"  c{n}: work {len(work)}자 → 질의 {len(q)}자 sha8={sha8(q)} · 적격 < {cut_iso} (loop(cycle {n-1}) 수확)")

    print(f"\n[B. 재생 — recall=low · top_k={TOP_K} · trace 미전달 · 서버측 created_at<cutoff + 클라 재검증]")
    seen_ids: dict[str, list[int]] = {}
    per_cycle: dict[int, list[dict]] = {}
    for n, q, cutoff in plan:
        cut_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        result, err = rpc("search_memories", {
            "query": q, "top_k": TOP_K, "recall": "low",
            "filters": {"created_at": {"lt": cut_iso}},
        })
        items = (result or {}).get("results") or []
        kept = []
        for it in items:
            mid = str(it.get("id") or "")[:8]
            created = str(it.get("created_at") or "")
            if parse_created(created) >= cutoff:
                continue  # 서버 필터 불신 재검증 — 부적격 탈락
            text = str(it.get("memory") or it.get("text") or "")
            kept.append({"id": mid, "created": created[:19], "score": it.get("score"),
                         "cats": it.get("categories"), "head": text[:HEAD_CHARS].replace("\n", " ")})
            seen_ids.setdefault(mid, []).append(n)
        per_cycle[n] = kept
        print(f"\n  ── c{n} (err={err or '없음'} · 반환 {len(items)} · 적격 {len(kept)})")
        for k in kept:
            print(f"    {k['id']} {k['created']} score={k['score']} cats={k['cats']}")
            print(f"      | {k['head']}")

    print("\n[C. 교차 요약 — 판정 입력 (배달 대조·silent_miss 채점은 세션 몫, 처분 문단에 근거 병기)]")
    print(f"  고유 기억 {len(seen_ids)}건 / 사이클×적격 연 {sum(len(v) for v in per_cycle.values())}건")
    for mid, ns in sorted(seen_ids.items(), key=lambda kv: -len(kv[1])):
        print(f"    {mid}: c{','.join(map(str, ns))}")
    print("  [주의] 이 계기는 재현율 하한이다 — 차집합 0은 '이 조건에서 0'이며 전수 부재 증명이 아니다.")


if __name__ == "__main__":
    main()
