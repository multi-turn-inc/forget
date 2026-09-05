"""c88 계기 — 측정 ② rate–distortion 곡선의 x축 실측: top-k 페이로드 토큰 스윕.

[선등록 헤더 — 이 파일은 **실행 전에 커밋**된다. 관측 39 수용 기준 ① 첫 집행:
 판정 규칙의 선등록 매체 = 저장소 파일 + git 타임스탬프(사전성 증명), add_memory
 결정 기록은 프로브 **후**에만 쓴다. 선등록을 회상 표면(add_memory)에 두지 않는
 이유 = c87에서 선등록 기억이 같은 세션 프로브 결과 창 2/8을 점유(변위)했다.]

── R3 능동 프로브 (need-aligned, 관측 36: 질의 원문은 이 헤더에만) ──────────────
need (실제 필요, 제조 아님): rate-distortion.svg의 forget 점(78.4%±0.4, 3시드,
  exp №0003)의 컨피그 좌표 — top_k·granularity·run 파일. 스윕의 앵커 k(c14 추정
  1.2–2k tok과 대조할 지점) 결정에 필요하고, 이 무기억 세션은 №0003이 runs/의
  어느 런인지 모른다. 차트 스크립트·기준선 문서는 "№0003 3시드"라는 포인터만
  배달한다(c84·c87 hit 조건과 동형 — 포인터만 배달된 문면).
PROBE_QUERY = "№0003 실험 3시드 78.4% — rate-distortion 차트 forget 점의 컨피그:
               top_k, granularity, run 파일 위치"
  (search_memories, top_k=8, trace="c88_need_probe", score_breakdown 생략)
판정 규칙 (선등록 — 이 커밋의 타임스탬프가 프로브 이전임을 증명한다):
  hit  = 저장소 정독 **전에** №0003의 컨피그 좌표(top_k 값 / run 파일 경로·이름 /
         granularity 중 최소 하나)를 배달하는 신규 정보 도착 **그리고** 1차 증거
         (runs/ 파일 또는 실험 대장) 교차 검증 통과.
  miss = 차트 문면 수준 재배달(78.4%±0.4 · 1.2–2k 추정 · "№0003 3시드" 포인터 —
         이 세션이 이미 아는 것), 또는 무관/무결과.
  병기 의무: 결과 창의 self-echo(이번 세션 생성 행) 개수 (관측 39 ② — 이번
  세션은 프로브 전 add_memory 0건이어야 하고, 그 준수 여부도 함께 적는다).
순서: 이 파일 커밋 → 프로브 → 1차 증거 정독(gtm/·runs/) → add_memory는 그 후.

── 스윕 스펙 (선등록) ───────────────────────────────────────────────────────────
목적: c14가 "정직한 x가 없는 점은 그리지 않는다"로 비워 둔 곡선의 x축 —
  회상 페이로드 토큰을 top-k별로 **실측**한다 (추정 1.2–2k의 실측 대체 + 중간점).
  y축(정확도)은 이 사이클 스코프 밖: GPT-4o 팔은 비용(>$2, 원칙 6 게이트),
  로컬 reader 팔은 별도 사이클. **아카이브 y와의 무단 결합 금지** — dev-session-k10
  59.5% 등의 y는 7월 몸의 측정이고 몸 패리티 미검증이므로 (x,y) 쌍으로 병합하지
  않는다.
몸 (원칙 3 — 스택 선언):
  격리 인스턴스 http://localhost:8602, MEM1_DB_PATH=/tmp/c88_bench_payload.sqlite3
  (신규 생성·종료 후 폐기). 코드 = 이 저장소 워킹트리(editable install), 즉
  **신척도 몸**(c72 아핀 제거 vector=max(0,cos) + c81 phrase 자격 토큰) — :8000
  구척도와 다른 몸, 숫자 혼용 금지. :8000(도그푸드)·8600/8601(LME-V2 트랙 영토)
  무접촉.
  몸 검증 (LME-V2 run-1 계보 — "어떤 몸으로 시험을 쳤는지"): 실행 시작 시 MCP
  get_provider_health의 effective가 fastembed:BAAI/bge-small-en-v1.5가 아니면
  즉시 중단(deterministic-128 폴백 위 측정 금지). effective/resolution/checks와
  repo HEAD를 산출물 JSON에 동봉한다.
표본: longmemeval_s_cleaned, dev-42 = harness.stratified_sample(n=42, seed=42) —
  기존 dev 런과 동일 추출법(레거시 dev 표본, held-out 아님 — held-out 오염 없음).
스윕: K_LIST = [1, 2, 5, 10, 20, 42, 84] · granularity=turn · temporal_rerank=True
  (harness 기본 경로 그대로 — ingest_instance/retrieve/_context_lines를 import).
측정 (질문별·k별):
  payload_tokens       = _context_lines(memories)의 o200k_base 토큰 수
                         (차트 x축 정의 = 회상 페이로드; c14 추정과 동일 대상)
  reader_prompt_tokens = READER_SYS_V3 + user prompt 전체 토큰 수 (참고 부기)
  n_retrieved, stored  = 회수 건수, 스코프 저장 건수
대조군·정합성 (원칙 1):
  (i) 외부 대조점: c14 문서화 추정 1.2–2k tok — №0003 앵커 k(프로브+1차 증거로
      확정; 확정 실패 시 k=10·42 둘 다 병기하고 '앵커 미확정'을 명기)의 실측
      중앙값과 대조. 몸이 다르므로(7월 몸 vs 신척도) 대조는 "추정의 자릿수 검증"
      이지 동일-몸 재현이 아니다 — 이 캐비앗을 결과에 병기한다.
  (ii) 내부 정합성 (자동 검사, 실패 시 해당 행 flag): 질문별 payload_tokens는
      k에 단조 비감소여야 하고, n_retrieved == min(k, stored)여야 한다.
LLM 0 · 외부 API $0 (reader/judge 미호출 — 검색은 로컬 fastembed).
산출물: research/devloop/notes/c88_payload_sweep.json (메타+질문×k 원시+집계),
  노트 notes/cycle-88-*.md 요약. 실행:
  .venv/bin/python research/devloop/scripts/c88_topk_payload_sweep.py

── 선등록 이탈 선언 (실행 전 개정 e43e80a 이후, 결과 관측 전) ───────────────────
  등록본의 몸은 "격리 인스턴스 :8602 (uvicorn)"이었다. 이 비대화형 런에서 서버
  기동은 승인 게이트에 걸려 실행 불가 — 승인 의존 채널은 승인 없는 런에서 조용히
  죽는다(body-fingerprint _omitted_process_start 선례). 대체: **인프로세스 엔진**,
  같은 저장소 워킹트리 코드 + 전용 MEM1_DB_PATH(/tmp). HTTP 핸들러(server.py
  memories_create / memories_search_v3 / memories_delete_all)는 add_memories /
  search_memories / delete_memories의 얇은 래퍼이므로 채점·저장 경로는 등록본과
  동일하고, 이탈은 수송층(HTTP↔인프로세스)뿐이다. harness의 ingest_instance /
  retrieve 코드는 클라이언트 셤(shim)으로 무수정 재사용한다. 몸 검증은 MCP 대신
  동일 내부 함수(provider_runtime.provider_health_payload)로 수행하고, 스토어
  벡터 차원(MEB1:384) 검사를 추가한다(폴백 이중 감시). 직렬 실행(스레드 풀 제거)
  — 인프로세스 sqlite 동시성 리스크 회피, 표본 규모(42문항 ~21k턴)는 직렬로 충분.
  DB 경로도 /tmp → 저장소 tmp/(.gitignore 26행)로: /tmp 파일은 샌드박스에서 삭제
  불가라 폐기 의무를 지킬 수 없다. 전용 신규 DB라는 격리 본질은 불변.

── 선등록 이탈 선언 ② (재실행 세션, 결과 관측 전) ───────────────────────────────
  1차 실행은 25/42 인스턴스에서 세션 사망으로 중단(산출물 0). 재실행분 2건 개정,
  둘 다 채점 규칙 아님 — 격리와 몸 검증에만 관계한다:
  (a) DB_PATH 파일명 → c88_bench_payload_r2.sqlite3. 중단 런의 DB에는 사망 시점
      인스턴스(c88-b29f3365)의 live 행 80개가 남아 있어, 같은 스코프 재인제스트가
      중복을 만든다(해당 문항의 payload 오염). 신규 파일로 격리 본질 복원.
      중단본은 tmp/에 보존(mv 차단 — 파일명 분리로 대체).
  (b) store_vec_check 호출 시점 → 인스턴스 1의 **DELETE 이전**으로 이동. 1차 실행이
      "no-vector"를 낸 원인은 폴백이 아니라 계기 결함이었다: 검사가 deleted=0을
      요구하는데 호출 지점이 스코프 DELETE 뒤였다. 중단 DB 사후 실측이 이를 확증
      (embedding 12,621행 전부 MEB1·length 1540 → 384차원). 검사는 이제 live 행을
      본다 — 폴백 이중 감시가 실제로 감시하게 된다.
"""
from __future__ import annotations

import json
import os
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

# /tmp는 이 샌드박스에서 삭제 불가(작업 디렉토리 밖) — 저장소 tmp/(.gitignore 26행)로.
# 등록본 경로와의 차이는 격리성에 무영향(전용 신규 DB라는 본질 유지). 이탈 선언에 병기.
DB_PATH = str(Path(__file__).resolve().parents[3] / "tmp" / "c88_bench_payload_r2.sqlite3")
os.environ["MEM1_DB_PATH"] = DB_PATH  # forget import 전에 — 격리 DB 바인딩

import tiktoken  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "research" / "longmemeval"))
sys.path.insert(0, str(ROOT))
import harness  # noqa: E402  (ingest_instance / retrieve / _context_lines / READER_SYS_V3)
from forget.db import init_db  # noqa: E402
from forget.provider_runtime import provider_health_payload  # noqa: E402
from forget.store import add_memories, delete_memories, search_memories  # noqa: E402

OUT = ROOT / "research" / "devloop" / "notes" / "c88_payload_sweep.json"
K_LIST = [1, 2, 5, 10, 20, 42, 84]
N, SEED = 42, 42
EXPECTED_EFFECTIVE = "fastembed:BAAI/bge-small-en-v1.5"

enc = tiktoken.get_encoding("o200k_base")


class _Resp:
    """httpx.Response의 최소 표면 — harness가 쓰는 두 메서드만."""

    def __init__(self, data: dict):
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._data


class InProcClient:
    """harness의 httpx.Client 자리에 꽂는 인프로세스 셤.

    server.py 핸들러가 하는 일을 그대로 한다 — 래퍼 로직(text→messages 봉투,
    filters 통과)만 복제하고 엔진 함수는 동일한 것을 호출한다.
    """

    def post(self, path: str, json: dict) -> _Resp:  # noqa: A002 — httpx 시그니처 유지
        payload = json
        if path == "/v1/memories/":
            text = payload.get("text")
            wrapped = {**payload,
                       "messages": [{"role": "user", "content": str(text)}],
                       "infer": False}
            wrapped.pop("text", None)
            return _Resp(add_memories(wrapped))
        if path == "/v3/memories/search/":
            return _Resp({"results": search_memories(payload).get("results", [])})
        raise ValueError(f"unmapped path: {path}")

    def request(self, method: str, path: str, json: dict) -> _Resp:  # noqa: A002
        assert method == "DELETE" and path == "/v1/memories/"
        return _Resp(delete_memories({k: v for k, v in json.items() if v}))


def verify_body() -> dict:
    health = provider_health_payload()
    eff = health.get("effective") or {}
    chk = (health.get("checks") or {}).get("embeddings") or {}
    effective = f"{eff.get('embedding_provider')}:{eff.get('embedding_model')}"
    fp = {
        "effective_embedding": effective,
        "embedding_resolution": str(eff.get("resolution")),
        "checks_embedding": f"{chk.get('provider')}:{chk.get('model')}",
        "repo_head": subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                    cwd=ROOT, capture_output=True, text=True).stdout.strip(),
        "arithmetic": "신척도 (c72 affine 제거 + c81 phrase 자격 — 워킹트리 editable)",
        "transport": "in-process (선등록 이탈 선언 참조 — 서버 기동 승인 불가)",
        "db": DB_PATH,
    }
    if effective != EXPECTED_EFFECTIVE:
        raise SystemExit(f"몸 검증 실패 — effective={effective!r} != {EXPECTED_EFFECTIVE!r}: "
                         "deterministic-128 폴백 위 측정 금지 (선등록 스펙). 중단.")
    return fp


def store_vec_check() -> str:
    """폴백 이중 감시 — 첫 인제스트 후 스토어 벡터 형식 실측 (기대 MEB1:384).

    SQL은 c48_step0_check._store_vec의 정본을 그대로 — 매직 비교는 hex 리터럴
    (x'4D454231' = b"MEB1"): BLOB은 TEXT 리터럴과 저장 클래스가 달라 절대 같지 않다.

    호출 지점은 인스턴스 1의 스코프 DELETE **이전**이어야 한다 — deleted=0을 요구
    하므로 DELETE 뒤에 부르면 폴백 여부와 무관하게 no-vector가 나온다(이탈 선언 ② (b)).
    """
    import sqlite3
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "select substr(embedding,1,4)=x'4D454231', length(embedding), count(*) "
            "from memories where deleted=0 and embedding is not null and embedding != '' "
            "group by 1, 2 order by count(*) desc limit 1").fetchall()
    finally:
        conn.close()
    if not rows:
        return "no-vector"
    is_meb1, blen, _ = rows[0]
    return f"MEB1:{(int(blen) - 4) // 4}" if is_meb1 else f"JSON:len{int(blen)}"


def tok(s: str) -> int:
    return len(enc.encode(s))


def run_instance(inst: dict, vec_check: bool = False) -> dict:
    scope = f"c88-{inst['question_id']}"
    q, qdate = inst["question"], inst.get("question_date", "")
    row = {"question_id": inst["question_id"], "question_type": inst["question_type"],
           "by_k": {}, "flags": []}
    client = InProcClient()
    stored = harness.ingest_instance(client, scope, inst, granularity="turn")
    row["stored"] = stored
    prev_payload = -1
    for k in K_LIST:
        mems = harness.retrieve(client, scope, q, k, temporal_rerank=True)
        context = harness._context_lines(mems)
        user_prompt = (f"Today's date: {qdate}\n\nRetrieved memories "
                       f"(each tagged with its date):\n{context}\n\nQuestion: {q}")
        payload = tok(context)
        row["by_k"][str(k)] = {
            "n_retrieved": len(mems),
            "payload_tokens": payload,
            "reader_prompt_tokens": tok(harness.READER_SYS_V3) + tok(user_prompt),
        }
        if len(mems) != min(k, stored):
            row["flags"].append(f"k={k}: n_retrieved {len(mems)} != min(k, stored {stored})")
        if payload < prev_payload:
            row["flags"].append(f"k={k}: payload {payload} < 직전 k {prev_payload} (단조성 위반)")
        prev_payload = payload
    if vec_check:  # DELETE 전에 — live 행이 있어야 검사가 성립한다 (이탈 선언 ② (b))
        row["store_vec"] = store_vec_check()
    client.request("DELETE", "/v1/memories/", json={"user_id": scope, "app_id": "lme"})
    return row


def main() -> None:
    t0 = time.time()
    init_db()
    fp = verify_body()
    print("몸 검증 통과:", json.dumps(fp, ensure_ascii=False))

    data = json.loads((ROOT / "research" / "longmemeval-data" / "longmemeval_s_cleaned.json")
                      .read_text(encoding="utf-8"))
    sample = harness.stratified_sample(data, N, random.Random(SEED))
    print(f"표본: dev-{N} (seed {SEED}) — {len(sample)}문항, K={K_LIST}")

    rows: list[dict] = []
    for i, inst in enumerate(sample, 1):
        row = run_instance(inst, vec_check=(i == 1))
        if i == 1:
            fp["store_vec_first_instance"] = row.pop("store_vec", "n/a")
            print("스토어 벡터 검사(1문항, DELETE 전):", fp["store_vec_first_instance"])
        rows.append(row)
        print(f"  [{i}/{len(sample)}] {row['question_id']} stored={row['stored']} "
              f"k84={row['by_k']['84']['payload_tokens']}tok "
              f"{'FLAGS:' + str(row['flags']) if row['flags'] else ''}", flush=True)

    agg = {}
    for k in K_LIST:
        vals = [r["by_k"][str(k)]["payload_tokens"] for r in rows]
        rp = [r["by_k"][str(k)]["reader_prompt_tokens"] for r in rows]
        qs = statistics.quantiles(vals, n=10)
        agg[str(k)] = {
            "payload_median": statistics.median(vals),
            "payload_mean": round(statistics.mean(vals), 1),
            "payload_p10": qs[0], "payload_p90": qs[8],
            "payload_min": min(vals), "payload_max": max(vals),
            "reader_prompt_median": statistics.median(rp),
            "n_retrieved_mean": round(statistics.mean(
                [r["by_k"][str(k)]["n_retrieved"] for r in rows]), 1),
        }

    flagged = [r["question_id"] for r in rows if r["flags"]]
    out = {
        "meta": {
            "cycle": 88, "date": "2026-08-09", "body": fp,
            "dataset": "longmemeval_s_cleaned", "sample": f"dev-{N} seed {SEED} (stratified)",
            "granularity": "turn", "temporal_rerank": True, "k_list": K_LIST,
            "tokenizer": "o200k_base", "llm_calls": 0, "external_cost_usd": 0,
            "elapsed_s": round(time.time() - t0, 1),
            "pairing_caveat": ("x(k)만 실측. 아카이브 정확도(y)와의 결합 금지 — "
                               "몸 패리티 미검증 (선등록 헤더 참조)."),
        },
        "aggregate_by_k": agg,
        "flagged_questions": flagged,
        "rows": rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}  ({out['meta']['elapsed_s']}s, flags={len(flagged)})")
    print(f"{'k':>4} {'median':>8} {'mean':>8} {'p10':>7} {'p90':>8} {'reader_median':>14}")
    for k in K_LIST:
        a = agg[str(k)]
        print(f"{k:>4} {a['payload_median']:>8} {a['payload_mean']:>8} "
              f"{a['payload_p10']:>7.0f} {a['payload_p90']:>8.0f} {a['reader_prompt_median']:>14}")


if __name__ == "__main__":
    main()
