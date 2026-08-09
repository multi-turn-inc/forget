"""c89 계기 — 측정 ②-b: dual 파이프라인(№0003 앵커 컨피그)의 회상 페이로드 실측.

[선등록 헤더 — 이 파일은 **실행 전에 커밋**된다. 관측 39 수용 기준 ① 두 번째 집행:
 판정 규칙의 선등록 매체 = 저장소 파일 + git 타임스탬프(사전성 증명). add_memory는
 결과 관측 **후**에만 쓴다. c88에서 이 순서 교정의 효과가 확인됐다(self-echo 2/8 → 0/8).]

── 이 사이클이 갚는 부채 ────────────────────────────────────────────────────────
c88이 곡선의 x축을 turn-raw 경로로 실측했으나, 차트의 forget 점(№0003)은 **dual**
파이프라인이다 — 항목의 정체가 달라 c14 추정(1.2–2k tok)과 대조 불가로 판정했다.
c88 노트 §4가 남긴 사양을 그대로 집행한다: 같은 dev-42·같은 몸에서 dual 경로의
페이로드를 실측한다. observer 출력은 observations/에 캐시되어 있으므로 LLM 0·$0.

대상 공표 숫자 (1차 증거로 확인한 문면 — 이 사이클의 판정 대상):
  compression-baseline.md:66  "forget: 회상 페이로드 ~1.2k~2k 토큰으로 78.4% ± 0.4"
  compression-baseline.md:67  헤드라인 "**2%를 남기고 더 잘 답한다.**"
  rate_distortion_chart.py:28 FORGET = {"tok_lo": 1_200, "tok_hi": 2_000, ...}

── 앵커 컨피그의 재구성 (1차 증거 + 코드에서 유도) ───────────────────────────────
№0003 = runs/local-v3-{probe,r2,r3-merged} · mode=dual · observer=qwen2.5:14b-instruct-q4_K_M
 · reader=gpt-4o · n=500 · overall_accuracy 0.784/0.788/0.780 · 전 문항 n_ctx=**102 상수**.
summary는 top_k를 저장하지 않지만(관측 40), 102는 observer.py:149-154에서 유도된다:
  obs_slots = obs_k = 60 · raw_slots = top_k - top_k//2 = 84 - 42 = **42** · 합 **102**.
README:12-13의 "top-k 84, obs-k 60"과 일치 — 즉 102는 우연이 아니라 이 컨피그의 항등식이다.
따라서 dual 페이로드 = obs 60건 + raw 42건.

── 선등록 판정 규칙 (결과 관측 전 확정) ─────────────────────────────────────────
J1 (주 판정 — 공표 숫자의 운명): dual 페이로드 **중앙값**이 [1200, 2000] tok에 드는가.
    드는 경우  → c14 추정은 실측으로 승격, 차트의 x는 구간이 아니라 점이 된다.
    안 드는 경우 → 공표된 x는 **정정 대상**이다(원칙 1 — 자기 정정). 헤드라인 "2%"의
    분자도 함께 재계산해 정정 사양을 노트에 남긴다. 차트/문서 실제 수정은 이번
    사이클 스코프에 포함(저장소 내부 문서이며 배포·외부 발신 아님).
J2 (관측층 압축률): obs층 **항목당** 토큰이 [11.8, 19.6]에 드는가 — c14 추정이 참이려면
    102항목 × 11.8~19.6 tok이어야 한다는 c88 §3(d)의 유도. J1과 독립적으로 기록한다.
J3 (교차 사이클 재현 — 결정론적 예측): raw층 42슬롯 페이로드의 중앙값은 c88 turn-raw
    k=42 중앙값 **9,960.5 tok과 정확히 일치**해야 한다. 근거: raw층 인제스트 문자열
    (observer.py:146 f"{role}: {content}")과 harness.ingest_instance granularity=turn
    (harness.py:102)이 동일 문자열이고, 질의·top_k(42)·temporal_rerank(True)·표본·몸이
    모두 같다 → 결정론적으로 같은 집합이 회수되어야 한다.
    불일치 시 → 이번 대조 전체를 의심 대상으로 강등하고 원인을 규명할 때까지 J1을
    확정하지 않는다(계기 드리프트가 있다는 뜻이므로).
정합성 자동 검사(실패 시 행 flag): n_obs == min(60, stored_obs) · n_raw == min(42, stored_raw)
 · n_total == 102 (stored 부족 문항은 flag 후 J1 중앙값 산출에서 제외하지 않고 병기).

캐비앗 (선등록 — 결과에 반드시 병기):
 (a) **몸 불일치**: №0003은 7월 몸(구척도)에서 돌았고 이 측정은 신척도(c72 아핀 제거 +
     c81 phrase 자격)다. 랭킹이 달라지면 회수 집합이 달라지므로 이것은 7월의 바이트를
     재현하는 것이 아니라 **같은 컨피그의 페이로드 자릿수**를 재는 것이다. 항목 수(102)는
     몸과 무관하게 고정이므로 자릿수 판정(J1)은 랭킹 차이에 강건하다.
 (b) **표본**: 앵커는 n=500 전수, 이번은 dev-42(stratified seed 42) — c88 turn-raw와
     같은 표본이라 J3 재현 검사가 성립한다. 500 전수와의 차이는 표본 오차로 병기.
 (c) y축(정확도) 미측정 — 아카이브 y와 (x,y) 쌍으로 결합 금지(c88 선등록 캐비앗 승계).

── 몸 (원칙 3 — 스택 선언) ──────────────────────────────────────────────────────
격리: 전용 신규 DB tmp/c89_bench_dual.sqlite3 · :8000(도그푸드)·8600·8601 무접촉.
수송층: 인프로세스 셤 — c88 선등록 이탈 선언 ①을 **승계**한다(서버 기동은 여전히
  승인 게이트, 원인 축 = **하네스 강제**이지 과학적 개정 아님 — 관측 41 수용 기준 후보 적용).
검증: provider_health_payload().effective != fastembed:BAAI/bge-small-en-v1.5 → 즉시 중단.
  + 스토어 벡터 실측(MEB1:384 기대)을 인스턴스 1의 DELETE **이전**에(c88 이탈 ②(b) 승계).
LLM 호출: **0** — observations/ 캐시 전용. 캐시 미스 문항은 LLM을 부르지 않고 **중단**한다
  (OpenAI 클라이언트를 아예 만들지 않는다 — 비용 게이트의 구조적 보장).

── 계기 견고성 (F1 처치 보강 — 채점 규칙 아님) ──────────────────────────────────
c88은 같은 사이클에서 두 번 중간 사망했고 두 번 다 산출물 0이었다(백그라운드 런은
세션과 함께 소멸). 이 계기는 **재개 가능**하다: 문항 1건이 끝날 때마다 partial JSONL에
append하고, 시작 시 이미 끝난 question_id를 건너뛴다. 사망해도 진행분이 보존된다.
실행: .venv/bin/python research/devloop/scripts/c89_dual_payload.py
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

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = str(ROOT / "tmp" / "c89_bench_dual.sqlite3")
os.environ["MEM1_DB_PATH"] = DB_PATH  # forget import 전에 — 격리 DB 바인딩

import tiktoken  # noqa: E402

sys.path.insert(0, str(ROOT / "research" / "longmemeval"))
sys.path.insert(0, str(ROOT))
import harness  # noqa: E402
from forget.db import init_db  # noqa: E402
from forget.provider_runtime import provider_health_payload  # noqa: E402
from forget.store import add_memories, delete_memories, search_memories  # noqa: E402

OBSERVER = "qwen2.5:14b-instruct-q4_K_M"
CACHE = ROOT / "research" / "longmemeval" / "observations"
OUT = ROOT / "research" / "devloop" / "notes" / "c89_dual_payload.json"
PARTIAL = ROOT / "research" / "devloop" / "notes" / "c89_dual_payload.partial.jsonl"

TOP_K, OBS_K = 84, 60
OBS_SLOTS = OBS_K                 # observer.py:150
RAW_SLOTS = TOP_K - TOP_K // 2    # observer.py:151 → 42
N, SEED = 42, 42
EXPECTED_EFFECTIVE = "fastembed:BAAI/bge-small-en-v1.5"
C88_RAW_K42_MEDIAN = 9960.5       # J3 대조값 (c88_payload_sweep.json aggregate_by_k["42"])
C14_LO, C14_HI = 1200, 2000       # J1 대조 구간 (공표 문면)

enc = tiktoken.get_encoding("o200k_base")


class _Resp:
    def __init__(self, data: dict):
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._data


class InProcClient:
    """c88과 동일한 인프로세스 셤 — server.py 핸들러의 래퍼 로직만 복제."""

    def post(self, path: str, json: dict) -> _Resp:  # noqa: A002
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
        "transport": "in-process (c88 이탈 선언 ① 승계 · 원인 축=하네스 강제)",
        "db": DB_PATH,
        "observer_cache": f"{OBSERVER} (LLM 호출 0)",
    }
    if effective != EXPECTED_EFFECTIVE:
        raise SystemExit(f"몸 검증 실패 — effective={effective!r} != {EXPECTED_EFFECTIVE!r}. 중단.")
    return fp


def store_vec_check() -> str:
    """폴백 이중 감시 — live 행이 있을 때(DELETE 이전) 호출해야 성립한다."""
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


def load_observations(qid: str) -> list[dict]:
    """캐시 전용 — 미스면 중단한다. LLM을 부르는 경로가 이 계기에는 없다."""
    f = CACHE / f"{OBSERVER}--{qid}.json"
    if not f.exists():
        raise SystemExit(f"observer 캐시 미스: {f.name} — LLM 호출 금지 규약상 중단.")
    return json.loads(f.read_text(encoding="utf-8"))


def run_instance(inst: dict, vec_check: bool = False) -> dict:
    qid = inst["question_id"]
    q, qdate = inst["question"], inst.get("question_date", "")
    scope, raw_scope = f"c89obs-{qid}", f"c89raw-{qid}"
    client = InProcClient()
    row = {"question_id": qid, "question_type": inst["question_type"], "flags": []}

    # --- 관측층 인제스트 (observer.py:122-131 그대로) ---
    client.request("DELETE", "/v1/memories/", json={"user_id": scope, "app_id": "lme"})
    stored_obs = 0
    for e in load_observations(qid):
        created = harness.normalize_date(e["date"] or qdate)
        for line in e["observations"].splitlines():
            line = line.strip().lstrip("-• ").strip()
            if len(line) > 8:
                client.post("/v1/memories/", json={
                    "text": line, "infer": False, "user_id": scope,
                    "app_id": "lme", "created_at": created,
                }).raise_for_status()
                stored_obs += 1

    # --- 원시 턴층 인제스트 (observer.py:139-148 그대로 = harness turn granularity) ---
    client.request("DELETE", "/v1/memories/", json={"user_id": raw_scope, "app_id": "lme"})
    stored_raw = 0
    dates = inst.get("haystack_dates") or []
    for si, session in enumerate(inst["haystack_sessions"]):
        created = harness.normalize_date(dates[si] if si < len(dates) else qdate)
        for turn in session:
            if "role" in turn and "content" in turn:
                client.post("/v1/memories/", json={
                    "text": f"{turn['role']}: {turn['content']}", "infer": False,
                    "user_id": raw_scope, "app_id": "lme", "created_at": created,
                }).raise_for_status()
                stored_raw += 1

    # --- 회수 (observer.py:149-154 그대로) ---
    obs_mem = harness.retrieve(client, scope, q, OBS_SLOTS)
    raw_mem = harness.retrieve(client, raw_scope, q, RAW_SLOTS)
    memories = obs_mem + raw_mem

    payload_obs = tok(harness._context_lines(obs_mem))
    payload_raw = tok(harness._context_lines(raw_mem))
    payload_dual = tok(harness._context_lines(memories))
    row.update({
        "stored_obs": stored_obs, "stored_raw": stored_raw,
        "n_obs": len(obs_mem), "n_raw": len(raw_mem), "n_total": len(memories),
        "payload_obs_tokens": payload_obs,
        "payload_raw_tokens": payload_raw,
        "payload_dual_tokens": payload_dual,
        "tok_per_item_obs": round(payload_obs / len(obs_mem), 2) if obs_mem else None,
        "tok_per_item_raw": round(payload_raw / len(raw_mem), 2) if raw_mem else None,
        "tok_per_item_dual": round(payload_dual / len(memories), 2) if memories else None,
        "additivity_delta": payload_dual - (payload_obs + payload_raw),
    })
    if len(obs_mem) != min(OBS_SLOTS, stored_obs):
        row["flags"].append(f"n_obs {len(obs_mem)} != min({OBS_SLOTS}, stored_obs {stored_obs})")
    if len(raw_mem) != min(RAW_SLOTS, stored_raw):
        row["flags"].append(f"n_raw {len(raw_mem)} != min({RAW_SLOTS}, stored_raw {stored_raw})")
    if len(memories) != 102:
        row["flags"].append(f"n_total {len(memories)} != 102 (앵커 항등식 이탈)")

    if vec_check:  # DELETE 전에 — live 행이 있어야 검사가 성립 (c88 이탈 ②(b) 승계)
        row["store_vec"] = store_vec_check()
    for s in (scope, raw_scope):
        client.request("DELETE", "/v1/memories/", json={"user_id": s, "app_id": "lme"})
    return row


def main() -> None:
    t0 = time.time()
    init_db()
    fp = verify_body()
    print("몸 검증 통과:", json.dumps(fp, ensure_ascii=False), flush=True)

    data = json.loads((ROOT / "research" / "longmemeval-data" / "longmemeval_s_cleaned.json")
                      .read_text(encoding="utf-8"))
    sample = harness.stratified_sample(data, N, random.Random(SEED))
    print(f"표본: dev-{N} (seed {SEED}) — {len(sample)}문항 · dual obs{OBS_SLOTS}+raw{RAW_SLOTS}=102",
          flush=True)

    done: dict[str, dict] = {}
    if PARTIAL.exists():  # 재개 (F1 처치 보강)
        for line in PARTIAL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["question_id"]] = r
        print(f"재개: partial에서 {len(done)}문항 복원", flush=True)

    rows: list[dict] = []
    ran_this_run = 0  # 관측 44 처치: 검사는 **문항 순번**이 아니라 **런 순번**에 건다.
    for i, inst in enumerate(sample, 1):
        qid = inst["question_id"]
        if qid in done:
            rows.append(done[qid])
            print(f"  [{i}/{len(sample)}] {qid} (재개 — 건너뜀)", flush=True)
            continue
        row = run_instance(inst, vec_check=(ran_this_run == 0))
        ran_this_run += 1
        if "store_vec" in row:
            fp["store_vec_first_instance"] = row.pop("store_vec")
            print("스토어 벡터 검사(1문항, DELETE 전):", fp["store_vec_first_instance"], flush=True)
        rows.append(row)
        with PARTIAL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"  [{i}/{len(sample)}] {qid} obs={row['n_obs']}/{row['stored_obs']} "
              f"raw={row['n_raw']}/{row['stored_raw']} dual={row['payload_dual_tokens']}tok "
              f"(obs {row['payload_obs_tokens']} + raw {row['payload_raw_tokens']}) "
              f"{'FLAGS:' + str(row['flags']) if row['flags'] else ''}", flush=True)

    def agg(key: str) -> dict:
        vals = [r[key] for r in rows]
        qs = statistics.quantiles(vals, n=10)
        return {"median": statistics.median(vals), "mean": round(statistics.mean(vals), 1),
                "p10": qs[0], "p90": qs[8], "min": min(vals), "max": max(vals)}

    aggregate = {k: agg(k) for k in
                 ("payload_dual_tokens", "payload_obs_tokens", "payload_raw_tokens",
                  "tok_per_item_obs", "tok_per_item_raw", "tok_per_item_dual")}

    # 관측 44 처치 ③: 공백을 공백으로 기록한다 — 키 부재와 "검사 결과 없음"이
    # 구별되지 않으면 사후 복원이 불가능하다(관측 40 계열).
    fp.setdefault("store_vec_first_instance", "not-run(resumed)")

    dual_med = aggregate["payload_dual_tokens"]["median"]
    obs_per_item_med = aggregate["tok_per_item_obs"]["median"]
    raw_med = aggregate["payload_raw_tokens"]["median"]
    verdicts = {
        "J1_dual_median_in_c14_range": {
            "measured_median": dual_med, "range": [C14_LO, C14_HI],
            "in_range": C14_LO <= dual_med <= C14_HI,
            "ratio_vs_hi": round(dual_med / C14_HI, 2),
        },
        "J2_obs_layer_tok_per_item": {
            "measured_median": obs_per_item_med, "range": [11.8, 19.6],
            "in_range": 11.8 <= obs_per_item_med <= 19.6,
        },
        "J3_raw42_replicates_c88": {
            "measured_median": raw_med, "c88_median": C88_RAW_K42_MEDIAN,
            "exact_match": raw_med == C88_RAW_K42_MEDIAN,
            "delta": round(raw_med - C88_RAW_K42_MEDIAN, 1),
        },
    }

    flagged = [r["question_id"] for r in rows if r["flags"]]
    out = {
        "meta": {
            "cycle": 89, "date": "2026-08-10", "body": fp,
            "dataset": "longmemeval_s_cleaned", "sample": f"dev-{N} seed {SEED} (stratified)",
            "mode": "dual", "top_k": TOP_K, "obs_k": OBS_K,
            "obs_slots": OBS_SLOTS, "raw_slots": RAW_SLOTS, "n_ctx_expected": 102,
            "observer": OBSERVER, "tokenizer": "o200k_base",
            "llm_calls": 0, "external_cost_usd": 0,
            "elapsed_s": round(time.time() - t0, 1),
            "anchor": "№0003 = runs/local-v3-{probe,r2,r3-merged} (0.784/0.788/0.780, n_ctx=102)",
            "caveats": [
                "몸 불일치: 앵커는 7월 구척도, 이번은 신척도 — 같은 컨피그의 자릿수 측정이지 바이트 재현 아님",
                "표본: 앵커 n=500 전수 vs 이번 dev-42",
                "y축 미측정 — 아카이브 정확도와 (x,y) 결합 금지",
            ],
        },
        "verdicts": verdicts,
        "aggregate": aggregate,
        "flagged_questions": flagged,
        "rows": rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}  ({out['meta']['elapsed_s']}s, flags={len(flagged)})")
    print(json.dumps(verdicts, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
