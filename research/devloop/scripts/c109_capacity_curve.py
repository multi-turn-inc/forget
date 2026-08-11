"""c109 계기 — 측정 ③ 용량 곡선: 합성 스토어 10²→10⁵에서 회상 정밀도·지연·페이로드.

[선등록 헤더 — 이 파일은 **실행 전에 커밋**된다 (관측 39 수용 기준 ① · c88 선례:
 판정 규칙·중단 규칙·캐비앗을 실행 전에 저장소 파일 + git 타임스탬프로 고정한다.
 add_memory 결정 기록은 런 **후**에만 쓴다. 이 사이클 능동 검색 프로브 없음).]

── 목적 ─────────────────────────────────────────────────────────────────────────
LOOP.md 백로그 #6-③ "용량 곡선: 합성 스토어 10²→10⁵건에서 회상 정밀도·지연·
페이로드 (격리 인스턴스에서)". 스토어가 1,000배 커질 때 (a) 심어 둔 니들의 회수가
유지되는가(crowding), (b) 검색 지연이 어떻게 자라는가(O(N) 스캔의 실측 기울기),
(c) 표면화 페이로드가 k 고정 시 상수로 머무는가 — 를 첫 실측한다.

── 몸 (원칙 3 — 스택 선언) ──────────────────────────────────────────────────────
격리 인스턴스: 인프로세스 엔진(c88 이탈 선언 ①의 확립 관행 — 서버 기동은 승인
게이트에 걸리므로 처음부터 인프로세스로 등록한다), MEM1_DB_PATH=tmp/c109_capacity.sqlite3
(신규 생성, 시작 시 기존 파일 제거 — c88 이탈 선언 ② (a)의 오염 교훈을 규칙화).
코드 = 이 저장소 워킹트리(editable install) = 신척도 몸. 임베딩 effective가
fastembed:BAAI/bge-small-en-v1.5 아니면 즉시 중단(deterministic-128 폴백 위 측정
금지). 스토어 벡터 MEB1:384 검사(첫 배치 후, live 행 대상 — c88 (b) 교훈).
:8000 도그푸드 · 8600/8601 트랙 영토 무접촉. MEM1_RECALL_V2 해제 — 검색은 기본
로컬 기어(rule+vector 합성, LLM 게이트 미사용). LLM 호출 0 · 외부 API $0.

── 부하 설계 (SEED=109, 전 구간 결정적) ─────────────────────────────────────────
스코프: user_id=c109cap · app_id=capbench (격리 DB 안의 단일 풀).
니들 20건: 고유 사실 문장, 첫 100건 안에 셔플 삽입 후 전 팔에서 불변.
방해물: 12주제 템플릿 합성 문장(니들과 같은 도메인 포함 — 의미 경쟁 보장),
  content_hash 중복 회피는 생성기가 고유 조합으로 보장, 정크 게이트 탈락분은
  추가 생성으로 보충(체크포인트는 SQL live 계수로 판정 — 명목 N 아님).
인제스트: add_memories 배치(200 메시지/호출, infer=False) — 팔 목표 live 계수
  {100, 1_000, 10_000, 100_000} 누적 도달.

── 측정 정의 (팔마다 동일 25질의) ───────────────────────────────────────────────
니들 질의 20건(패러프레이즈 — 원문 재인용 아님) + 부재 질의 5건(스토어에 없는
사실 — 위양성 대조팔). search_memories top_k=10, 기본 로컬 기어.
질의별: wall_ms(perf_counter, 인프로세스 종단 — 질의 임베딩 포함·HTTP 제외) ·
  니들 rank(1~10, 밖이면 None) · top1_score · payload_tokens_top5/top10(o200k_base,
  표면화 memory 텍스트 연결).
팔별 집계: hit@1 · hit@5 · MRR@10(rank 밖 0) · wall_ms 중앙값/p90 ·
  payload_top5 중앙값 · 부재팔 top1_score 중앙값(니들팔 top1과의 마진 병기).
분위수 규약(관측 45 수용 기준 ②): p90 = nearest-rank(ceil(0.9·n)번째, 1-기반),
  중앙값 = statistics.median(짝수 n은 중앙 두 값 평균). JSON에 quantile_method로
  직렬화한다.

── 대조 구조 (원칙 1) ───────────────────────────────────────────────────────────
내부 대조 = 같은 니들 20 + 같은 질의 25가 N만 4단 변하는 시리즈(곡선의 기울기가
주장의 대상) + 부재 질의 대조팔(니들 점수와 부재 점수의 마진이 N에 따라 어떻게
좁아지는가 — 게이트 척도 트랙 ⑭·A-65 계열의 입력). 외부 앵커 없음 — 이 측정이
기준선 수립이다(후속 재측정의 직전 측정이 된다).

── 중단 규칙 (선등록 — 침묵 상한 금지) ──────────────────────────────────────────
10⁴ 팔 완료 후 10⁵ 팔 비용을 투영한다: proj = 90,000/인제스트율(10⁴팔 실측) +
25 × 질의중앙값(10⁴팔) × 10(선형 외삽). proj > 2,400s면 10⁵ 팔을 생략하고
skipped_arm에 투영치를 기록한다 — 생략은 침묵하지 않는다.

── 캐비앗 (선등록) ──────────────────────────────────────────────────────────────
(i) 합성 코퍼스 — 절대 정밀도는 LME 계열 수와 비교 불가. 주장 축은 N에 따른
    변화(같은 질의의 시리즈)뿐이다.
(ii) 지연은 인프로세스 종단 — HTTP·직렬화 미포함. 서버 배치와 절대값 비교 금지.
(iii) 전 행이 같은 시간대에 생성되므로 recency 축은 평탄 — 이 곡선은 crowding을
    격리하고 aging은 측정하지 않는다.
(iv) 신척도 몸(워킹트리) — :8000 구척도·7월 몸 수와 혼용 금지.

실행: .venv/bin/python research/devloop/scripts/c109_capacity_curve.py
산출물: research/devloop/notes/c109_capacity_curve.json
"""
from __future__ import annotations

import json
import math
import os
import random
import sqlite3
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = str(ROOT / "tmp" / "c109_capacity.sqlite3")
os.environ["MEM1_DB_PATH"] = DB_PATH  # forget import 전에 — 격리 DB 바인딩
os.environ.pop("MEM1_RECALL_V2", None)  # 기본 로컬 기어 강제 (LLM 게이트 배제)

import tiktoken  # noqa: E402

sys.path.insert(0, str(ROOT))
from forget.db import init_db  # noqa: E402
from forget.provider_runtime import provider_health_payload  # noqa: E402
from forget.store import add_memories, search_memories  # noqa: E402

OUT = ROOT / "research" / "devloop" / "notes" / "c109_capacity_curve.json"
SEED = 109
SCOPE = "c109cap"
APP = "capbench"
ARMS = [100, 1_000, 10_000, 100_000]
BATCH = 200
TOP_K = 10
BUDGET_S = 2_400  # 10⁵ 팔 투영 상한 (선등록 중단 규칙)
EXPECTED_EFFECTIVE = "fastembed:BAAI/bge-small-en-v1.5"

enc = tiktoken.get_encoding("o200k_base")

# ── 니들 20 + 질의 (패러프레이즈) ────────────────────────────────────────────────
NEEDLES: list[tuple[str, str]] = [
    ("The staging Redis failover password rotates every 45 days and Priya owns the rotation calendar.",
     "who owns the staging redis failover password rotation and how often does it rotate"),
    ("The billing reconciliation job must run before 03:10 UTC or the Stripe ledger export goes stale.",
     "what is the deadline for the billing reconciliation job relative to the stripe export"),
    ("Marta prefers the aisle seat on flights longer than four hours because of her knee surgery.",
     "why does marta want an aisle seat on long flights"),
    ("The ML training cluster uses spot GPUs except for the final epoch, which pins on-demand A100s.",
     "which part of model training runs on on-demand a100 gpus instead of spot"),
    ("Grandma's kimchi stew recipe doubles the anchovy broth when using aged kimchi over six months old.",
     "what changes in the kimchi stew recipe when the kimchi is aged more than six months"),
    ("The API gateway rate limit for the free tier is 240 requests per minute, burst 60.",
     "what is the free tier rate limit and burst on the api gateway"),
    ("Dr. Yoon moved the quarterly checkup to the second Tuesday of March because of the lab renovation.",
     "when was the quarterly checkup with dr. yoon rescheduled to and why"),
    ("The design system deprecates the teal accent in v9; migration guides live under docs/migrations/teal.",
     "where are the migration docs for the deprecated teal accent color"),
    ("Backup verification restores a random 5 percent sample to the scratch cluster every Sunday night.",
     "how does the weekly backup verification sampling work"),
    ("Jun's espresso dial-in is 18.2 grams in, 39 grams out, at 27 seconds on the Niche grinder setting 14.",
     "what is jun's espresso recipe and grinder setting"),
    ("The Kubernetes ingress timeout was raised to 95 seconds for the report-export path only.",
     "which path got the 95 second ingress timeout in kubernetes"),
    ("Legal requires SOC 2 evidence screenshots archived within 24 hours of each quarterly access review.",
     "how quickly must access review screenshots be archived for soc 2"),
    ("The hiking group meets at the Suraksan north trailhead at 06:40 on first Saturdays.",
     "where and when does the hiking group meet on first saturdays"),
    ("Payments retries use exponential backoff capped at 32 minutes with jitter of plus or minus 20 percent.",
     "what is the retry backoff cap and jitter for payments"),
    ("The book club picked 'The Overstory' for September and meets at the Hapjeong branch cafe.",
     "what book did the book club choose for september and where does it meet"),
    ("Vendor invoices over 8 million KRW need dual approval from finance and the requesting team lead.",
     "when do vendor invoices need dual approval and from whom"),
    ("The office plant watering rota assigns the monstera to whoever ran the Monday standup.",
     "who waters the monstera under the office rota"),
    ("Search index rebuilds are throttled to one shard per node whenever p99 query latency exceeds 180 ms.",
     "when are search index rebuilds throttled and to what rate"),
    ("The family reunion photo archive lives on the Synology under /volume2/reunion-2019, not Google Photos.",
     "where is the family reunion photo archive actually stored"),
    ("Incident postmortems are blameless but require a timeline with UTC timestamps within five business days.",
     "what are the two hard requirements for incident postmortems"),
]

ABSENT_QUERIES: list[str] = [
    "who owns the vault unseal ceremony for the osaka region",
    "what is the wifi password of the busan satellite office",
    "which vendor supplies the underwater drone batteries",
    "when does the llama herd vaccination schedule start",
    "what did the auditor say about the helsinki data center generator",
]

TOPICS: dict[str, tuple[list[str], dict[str, list[str]]]] = {
    "infra": (
        ["The {svc} service {act} after the {evt} window on {day}.",
         "{name} bumped the {svc} {knob} to {num} during the {evt} review.",
         "Rollbacks of {svc} require a {knob} freeze approved by {name}."],
        {"svc": ["redis", "postgres", "ingress", "queue", "scheduler", "cache", "search", "metrics"],
         "act": ["restarts", "drains connections", "re-elects a leader", "compacts segments", "resyncs replicas"],
         "evt": ["maintenance", "failover", "deploy", "audit", "capacity"],
         "knob": ["timeout", "pool size", "retry budget", "heap limit", "shard count"]},
    ),
    "billing": (
        ["Invoices from {name} settle in {num} days under the {plan} plan.",
         "The {plan} plan grants {num} seats and bills on the {day}.",
         "{name} disputed a {plan} charge of {num} thousand won last {day}."],
        {"plan": ["starter", "growth", "enterprise", "legacy", "partner"]},
    ),
    "food": (
        ["{name}'s {dish} needs {num} minutes of resting before serving.",
         "The {dish} at the {place} branch tastes better with extra {ing}.",
         "{name} swaps {ing} for perilla oil in the {dish} on weekdays."],
        {"dish": ["bibimbap", "pasta", "curry", "stew", "salad", "ramen"],
         "place": ["hapjeong", "gangnam", "mapo", "pangyo", "seongsu"],
         "ing": ["sesame", "garlic", "scallions", "butter", "gochujang"]},
    ),
    "travel": (
        ["{name} books the {num}:{num2} train to {place} for the {evt} trip.",
         "The {place} hotel upgrade requires {num} nights on the {plan} tier.",
         "{name} keeps a packing list of {num} items for {place} winters."],
        {"place": ["osaka", "taipei", "jeju", "sapporo", "danang", "helsinki"],
         "evt": ["family", "offsite", "conference", "holiday"],
         "plan": ["silver", "gold", "diamond"]},
    ),
    "health": (
        ["{name} logs {num} minutes of zone-two cardio on {day}s.",
         "The physio told {name} to cap deadlifts at {num} kilograms until {day}.",
         "{name}'s allergy shots moved to every {num} weeks after the {evt} test."],
        {"evt": ["skin", "blood", "stress", "sleep"]},
    ),
    "ml": (
        ["The {model} fine-tune converges after {num} epochs with cosine decay.",
         "{name} pins the {model} eval to seed {num} for the {evt} report.",
         "Gradient checkpointing cut the {model} run's memory by {num} percent."],
        {"model": ["reranker", "encoder", "distilled", "adapter", "baseline"],
         "evt": ["weekly", "board", "ablation", "release"]},
    ),
    "office": (
        ["The {room} room projector needs the {num}-pin adapter kept by {name}.",
         "Standup moves to {num}:{num2} on {day}s during the {evt} season.",
         "{name} restocks the {room} snack shelf every {num} days."],
        {"room": ["mango", "tigris", "aurora", "baekdu", "han"],
         "evt": ["planning", "budget", "hiring", "review"]},
    ),
    "reading": (
        ["{name} shelves {num} unread issues of the {topic} journal.",
         "The {topic} reading group summarizes {num} papers per {day}.",
         "{name} annotates {topic} books with {num} colored tabs."],
        {"topic": ["systems", "biology", "economics", "typography", "history"]},
    ),
    "home": (
        ["The {room} humidifier runs {num} hours after {num2} pm in winter.",
         "{name} descaled the kettle {num} days ago with citric acid.",
         "The {room} blinds jam unless opened past {num} degrees."],
        {"room": ["study", "bedroom", "kitchen", "balcony", "hall"]},
    ),
    "security": (
        ["Access tokens for the {svc} console expire after {num} hours since {evt}.",
         "{name} rotates the {svc} signing key every {num} weeks.",
         "The {svc} audit trail keeps {num} days of hot logs before cold storage."],
        {"svc": ["admin", "vault", "ci", "vpn", "sso"],
         "evt": ["login", "issuance", "escalation"]},
    ),
    "meetings": (
        ["The {evt} sync recurs every {num} weeks with {name} as scribe.",
         "{name} caps the {evt} agenda at {num} items with a parking lot.",
         "Decisions from the {evt} review post to the wiki within {num} hours."],
        {"evt": ["roadmap", "capacity", "design", "growth", "postmortem"]},
    ),
    "hardware": (
        ["The lab's {dev} firmware {num} fixes the {evt} drift bug.",
         "{name} labels {dev} cables with {num}-digit asset tags.",
         "Spare {dev} units live in bin {num} of the {room} closet."],
        {"dev": ["router", "printer", "sensor", "dock", "monitor"],
         "evt": ["clock", "thermal", "sync", "power"],
         "room": ["storage", "server", "supply"]},
    ),
}

NAMES = ["Priya", "Marta", "Jun", "Sena", "Ravi", "Hana", "Teo", "Mina", "Owen", "Dana"]
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def distractor_stream(rng: random.Random):
    """고유 합성 문장의 무한 생성기 — 결정적(SEED), content_hash 충돌 회피."""
    seen: set[str] = set()
    topics = list(TOPICS)
    serial = 0
    while True:
        topic = rng.choice(topics)
        templates, slots = TOPICS[topic]
        template = rng.choice(templates)
        text = template.format(
            name=rng.choice(NAMES), day=rng.choice(DAYS),
            num=rng.randint(2, 97), num2=rng.randint(10, 59),
            **{key: rng.choice(vals) for key, vals in slots.items()},
        )
        if text in seen:
            serial += 1
            text = text[:-1] + f" per ticket FGT-{serial + 1000}."
            if text in seen:
                continue
        seen.add(text)
        yield text


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
        "arithmetic": "신척도 (워킹트리 editable — c72 affine 제거 + c81 phrase 자격)",
        "transport": "in-process (c88 관행 — 선등록 헤더 참조)",
        "db": DB_PATH,
    }
    if effective != EXPECTED_EFFECTIVE:
        raise SystemExit(f"몸 검증 실패 — effective={effective!r} != {EXPECTED_EFFECTIVE!r}: "
                         "폴백 위 측정 금지 (선등록 스펙). 중단.")
    return fp


def store_vec_check() -> str:
    """폴백 이중 감시 — live 행의 벡터 형식 실측 (기대 MEB1:384). SQL은 c48 정본."""
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


def live_count() -> int:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "select count(*) from memories where deleted=0 and user_id=?", (SCOPE,)).fetchone()
        return int(row[0])
    finally:
        conn.close()


def add_batch(texts: list[str]) -> None:
    add_memories({
        "user_id": SCOPE, "app_id": APP, "infer": False,
        "messages": [{"role": "user", "content": text} for text in texts],
    })


def needle_ids() -> dict[str, str]:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        mapping: dict[str, str] = {}
        for text, _query in NEEDLES:
            rows = conn.execute(
                "select id from memories where deleted=0 and user_id=? and memory=?",
                (SCOPE, text)).fetchall()
            if len(rows) != 1:
                raise SystemExit(f"니들 유일성 위반: {len(rows)}행 — {text[:60]!r}")
            mapping[text] = rows[0][0]
        return mapping
    finally:
        conn.close()


def tok(s: str) -> int:
    return len(enc.encode(s))


def q_p90(vals: list[float]) -> float:
    """nearest-rank: 정렬 후 ceil(0.9·n)번째(1-기반) — 관례를 JSON meta에 직렬화."""
    ordered = sorted(vals)
    return ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)]


def run_queries(arm: int, ids: dict[str, str]) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    for kind, pairs in (("needle", NEEDLES), ("absent", [(None, q) for q in ABSENT_QUERIES])):
        for needle_text, query in pairs:
            t0 = time.perf_counter()
            results = search_memories({
                "query": query, "filters": {"user_id": SCOPE}, "top_k": TOP_K,
            }).get("results", [])
            wall_ms = (time.perf_counter() - t0) * 1000
            rank = None
            if needle_text is not None:
                target = ids[needle_text]
                for pos, result in enumerate(results, 1):
                    if result.get("id") == target:
                        rank = pos
                        break
            texts = [str(r.get("memory") or "") for r in results]
            rows.append({
                "arm": arm, "kind": kind, "query": query,
                "wall_ms": round(wall_ms, 1), "rank": rank,
                "top1_score": float(results[0].get("score") or 0.0) if results else None,
                "needle_score": next((float(r.get("score") or 0.0) for r in results
                                      if needle_text is not None and r.get("id") == ids[needle_text]), None),
                "payload_tokens_top5": tok("\n".join(texts[:5])),
                "payload_tokens_top10": tok("\n".join(texts[:10])),
            })
    needle_rows = [r for r in rows if r["kind"] == "needle"]
    absent_rows = [r for r in rows if r["kind"] == "absent"]
    ranks = [r["rank"] for r in needle_rows]
    wall = [r["wall_ms"] for r in rows]
    agg = {
        "hit@1": sum(1 for r in ranks if r == 1) / len(ranks),
        "hit@5": sum(1 for r in ranks if r is not None and r <= 5) / len(ranks),
        "mrr@10": round(sum((1 / r) for r in ranks if r is not None) / len(ranks), 4),
        "wall_ms_median": round(statistics.median(wall), 1),
        "wall_ms_p90": round(q_p90(wall), 1),
        "payload_top5_median": statistics.median(r["payload_tokens_top5"] for r in needle_rows),
        "needle_top1_score_median": round(statistics.median(
            r["top1_score"] for r in needle_rows), 4),
        "absent_top1_score_median": round(statistics.median(
            r["top1_score"] for r in absent_rows), 4),
    }
    agg["needle_absent_margin"] = round(
        agg["needle_top1_score_median"] - agg["absent_top1_score_median"], 4)
    return rows, agg


def main() -> None:
    t_start = time.time()
    for suffix in ("", "-wal", "-shm"):
        stale = Path(DB_PATH + suffix)
        if stale.exists():
            stale.unlink()  # 신규 파일 불변식 (c88 이탈 ② (a)의 규칙화)
    Path(DB_PATH).parent.mkdir(exist_ok=True)
    init_db()
    fp = verify_body()
    print("몸 검증 통과:", json.dumps(fp, ensure_ascii=False), flush=True)

    rng = random.Random(SEED)
    stream = distractor_stream(rng)

    first_arm = [next(stream) for _ in range(ARMS[0] - len(NEEDLES))]
    first_arm += [text for text, _query in NEEDLES]
    rng.shuffle(first_arm)  # 니들을 첫 100건 안에 셔플 삽입 (선등록 부하 설계)

    arms_out: list[dict] = []
    all_rows: list[dict] = []
    skipped_arm: dict | None = None
    ids: dict[str, str] = {}
    ingest_rate_10k = None
    query_median_10k = None

    for arm in ARMS:
        if arm == ARMS[-1] and ingest_rate_10k:
            proj = (ARMS[-1] - ARMS[-2]) / ingest_rate_10k + 25 * (query_median_10k / 1000) * 10
            if proj > BUDGET_S:
                skipped_arm = {"arm": arm, "projected_s": round(proj, 1), "budget_s": BUDGET_S,
                               "rule": "선등록 중단 규칙 — proj > budget이면 생략, 침묵하지 않는다"}
                print(f"10⁵ 팔 생략: 투영 {proj:.0f}s > 예산 {BUDGET_S}s", flush=True)
                break
        t_arm = time.time()
        inserted_before = live_count()
        pending: list[str] = list(first_arm) if arm == ARMS[0] else []
        first_batch_done = False
        while live_count() < arm:
            if not pending:
                pending = [next(stream) for _ in range(min(BATCH, arm - live_count()))]
            add_batch(pending[:BATCH])
            pending = pending[BATCH:]
            if not first_batch_done:
                vec = store_vec_check()
                if arm == ARMS[0]:
                    fp["store_vec_first_batch"] = vec
                    if not vec.startswith("MEB1:"):
                        raise SystemExit(f"스토어 벡터 검증 실패: {vec} — 중단.")
                first_batch_done = True
        ingest_s = time.time() - t_arm
        inserted = live_count() - inserted_before
        rate = inserted / ingest_s if ingest_s > 0 else float("inf")
        if arm == ARMS[0]:
            ids = needle_ids()
        rows, agg = run_queries(arm, ids)
        all_rows.extend(rows)
        arm_summary = {
            "arm_target": arm, "live_count": live_count(),
            "ingest_new_items": inserted, "ingest_s": round(ingest_s, 1),
            "items_per_s": round(rate, 1), **agg,
        }
        arms_out.append(arm_summary)
        print(json.dumps(arm_summary, ensure_ascii=False), flush=True)
        if arm == 10_000:
            ingest_rate_10k = rate
            query_median_10k = agg["wall_ms_median"]

    out = {
        "meta": {
            "cycle": 109, "date": "2026-08-12", "seed": SEED, "body": fp,
            "scope": {"user_id": SCOPE, "app_id": APP},
            "arms": ARMS, "top_k": TOP_K, "batch": BATCH,
            "n_needles": len(NEEDLES), "n_absent": len(ABSENT_QUERIES),
            "tokenizer": "o200k_base",
            "quantile_method": "p90=nearest-rank ceil(0.9n) 1-based; median=statistics.median (짝수 n 중앙 두 값 평균)",
            "llm_calls": 0, "external_cost_usd": 0,
            "elapsed_s": round(time.time() - t_start, 1),
            "caveats": [
                "합성 코퍼스 — 절대 정밀도는 LME 계열과 비교 불가, 주장 축은 N 시리즈 내 변화뿐",
                "지연은 인프로세스 종단(질의 임베딩 포함, HTTP 제외)",
                "동일 시간대 생성 — recency 평탄, crowding 격리·aging 미측정",
                "신척도 몸(워킹트리) — 타 몸 수와 혼용 금지",
            ],
        },
        "arms": arms_out,
        "skipped_arm": skipped_arm,
        "rows": all_rows,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}  ({out['meta']['elapsed_s']}s)", flush=True)
    header = (f"{'N':>7} {'hit@1':>6} {'hit@5':>6} {'mrr':>6} {'lat_med':>8} "
              f"{'lat_p90':>8} {'payload5':>9} {'margin':>7}")
    print(header)
    for a in arms_out:
        print(f"{a['live_count']:>7} {a['hit@1']:>6.2f} {a['hit@5']:>6.2f} {a['mrr@10']:>6.3f} "
              f"{a['wall_ms_median']:>8} {a['wall_ms_p90']:>8} "
              f"{a['payload_top5_median']:>9} {a['needle_absent_margin']:>7}")


if __name__ == "__main__":
    main()
