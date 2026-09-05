#!/usr/bin/env python3
"""c69 — P22 (b) 처치: 질의별 중심화/whitening 프로토타입 (read-only, LLM 0회, $0).

계기: c68이 절대 상수 경로를 **연역으로 닫았다**(허용 구간은 표본에 대해 단조 축소한다).
원장 ⑬ = 다음 무게이트 1순위 = "점수의 절반이 주제 무관 상수항"이라는 P22 (b)의 처치.

■ 물려받은 정의의 정정 (c68 자기규율 (라): 물려받은 대조군/정의를 **코드로** 확인하라)
  c68이 넘긴 정본 수치 메모는 "vector는 **raw cosine**이고"라고 적혀 있다. 1차 증거는
  반대다 — `memory_engine.cosine_similarity:793`과 `store._batch_cosine_scores:640`은
  둘 다 **`(cos + 1) / 2`**를 반환한다(4자리 라운딩·[0,1] 클램프). 즉 `vector` 필드는
  cosine이 아니라 **cosine의 아핀 재척도**다. c68의 숫자는 `score` 필드로 재서 유효하지만,
  P22 (b)의 **처치 설계**는 이 정정 없이는 표적을 잘못 잡는다.

  이 정정이 P22 (b)를 산술로 바꾼다. 강등이 없는 행에서:

      score = rule×0.45 + vector×0.55
            = rule×0.45 + 0.55×(cos + 1)/2
            = **0.275** + rule×0.45 + **0.275×cos**

  → `0.275`는 주제와 무관하게 **모든 행에 붙는 문자 그대로의 덧셈 상수**이고, 의미 신호의
  전체 동적 범위는 `0.275×cos`뿐이다. 따라서 P22 (b)가 말한 "주제 무관 상수항"은 실은
  **두 개의 독립된 원인의 합**이며, 그중 둘째는 아직 아무도 이름 붙이지 않았다:
    (원인 A) 임베딩 비등방성 — 무관 쌍의 cos가 0을 안 받고 0.6~0.8을 받는다.
    (원인 B) **아핀 재척도** `(cos+1)/2` — cos=0인 완전 무관 쌍조차 vector=0.5를 받는다.
  중심화는 A만 건드린다. B는 중심화로 사라지지 않는다. 그래서 이 사이클은 처치를
  **A·B·A+B로 분해해 각각 재고**, 어느 원인이 구속하는지를 대조로 가른다.

■ 수용 기준의 결함을 먼저 노출한다 (c67 자기규율 (다): 등록된 처치를 문자 그대로 이행하면
  거짓 음성/양성 기계가 되는지 먼저 보라)
  P22 (b)의 문자 그대로의 기준은 "같은 표본에서 허용 구간 폭이 **0.0246보다 넓어지는가**"다.
  그런데 폭(band)은 **점수 척도에 비례하는 양**이다: 모든 점수를 c배 하면 폭도 c배가 되고
  분리력은 하나도 안 변한다. 중심화·아핀 제거는 바로 그 척도를 바꾸는 처치이므로,
  문자 그대로의 기준은 **처치를 척도 변화로 통과시키거나(거짓 양성) 척도 축소로 탈락시킨다
  (거짓 음성).** 그래서 이 스크립트는 둘 다 낸다:
    · 문자 기준(band_raw > 0.0246) — 등록된 대로, 정직하게 병기
    · **척도 불변 기준** — `R = (min ON-real − max OFF) / spread(OFF)` · AUC · Cohen d.
      곱셈 재척도에 대해 불변이다(테스트가 이 성질을 고정한다).
  둘의 판정이 갈리면 그 사실 자체를 보고하고, **내 대체 기준을 내가 '충족'으로 채점하지
  않는다**(c67 (라)). 판정은 정훈/감사 사이클에 노출한다.

■ 계측기 자신의 결함을 같은 런에서 잡는 장치 (c67 자기규율 (나))
  두 개의 무료 대조가 내장돼 있다. 하나라도 깨지면 처치 판정을 내지 않는다:
    F1 (사슬 재현): 서버가 준 `rule`·`vector`를 제품의 합성 순서로 재조립한 점수가
       서버의 `score`와 **일치**해야 한다. 일치하면 "vector만 갈아끼운다"는 조작이 유효하다.
    F2 (임베딩 경로): 내가 만든 질의 임베딩과 저장 임베딩의 `(cos+1)/2`가 서버의
       `vector` 필드와 **일치**해야 한다. 일치하면 (ㄱ) 내 임베딩 경로가 제품과 같고
       (ㄴ) 아핀 재척도가 코드 독해가 아니라 **1차 증거**로 확인된다.

■ 최선의 경우 팔 금지 (c68 자기규율 (가), 관측 32의 수용 기준 ①)
  자기질의 팔은 이 스크립트에 **없다**. 분리·성공 주장은 ON-real과 OFF만으로 계산하며,
  판정 산술은 c68의 순수 함수 `verdict_band()`를 그대로 재사용한다(그 함수는 자기질의 팔을
  인자로 받지 않도록 이미 닫혀 있다). 같은 계기·같은 질의 집합에서 처치 전/후를 낸다.

read-only: 서버는 search_memories만, DB는 sqlite mode=ro, 제품 설정 DB는 열지 않는다
(get_project_settings 경유를 피하고 fastembed 프로바이더를 직접 호출한 뒤 F2로 검증한다).
쓰기 0 · LLM 0(recall=low) · 외부 비용 $0.

    .venv/bin/python research/devloop/scripts/c69_centering_prototype.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import statistics
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, REPO)

from forget.memory_engine import cosine_similarity  # noqa: E402
from forget.utils import decode_embedding  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


c68 = _load("c68_gate_recalibration")
c59 = c68.c59

GATE_NOW = c68.GATE_NOW
RULE_W, VECTOR_W = 0.45, 0.55          # store._search_score_weights (정본 메모)
SUPERSEDED_MULT = 0.45
CAPTURE_MULT = 0.5
FALLBACK_MULT = 0.88
DB = c68.DB
POOL_TOP_K = 200                       # 처치 후 top-1이 원 순위 밖에서 오는지 볼 수 있는 깊이
C68_BAND = 0.0246                      # P22 (b)의 문자 기준값 (c68 실측)
ABTT_KS = (1, 2, 3)                    # all-but-the-top: 제거할 주성분 수

# 신선 OFF 대조군 — c68의 OFF 어휘는 **재사용할 수 없다.** c68의 보고문
# "무관 질의 8건(김치찌개·lattice QCD·자동차보험·몬스테라) 전원 5/5 통과."가 기억으로
# 저장되면서(b5cb4695, 2026-08-06T20:12:49) 그 질의들은 더 이상 무관 질의가 아니다 —
# c69_universal_attractor.py의 임계 시각 스윕이 확정했다(as_of ≤ 20:12:49에서 OFF 최고
# 0.6037 = c68 재현 / 이후 0.6925). 대조군 라벨은 만료되고, 만료를 일으키는 것은 루프
# 자신의 기록 행위다. 그래서 어휘를 새로 뽑고, **주제어가 스토어 전문에 미등장인지 SQL로
# 확인한 것만** 쓴다(c69_off_arm_contamination.py의 적격 검사를 통과한 7건).
FRESH_OFF = [
    ("nf-1 어업", "명태 자망 어구 그물코 규격과 금어기 조정"),
    ("nf-2 지질", "화강암 절리 발달과 풍화 토르 지형 형성"),
    ("nf-3 제빵", "사워도우 르방 수분율과 오븐 스프링 실패"),
    ("nf-4 안과", "각막 난시 축 측정과 토릭 렌즈 회전 안정성"),
    ("nf-5 항해", "조석표 저조시 여유수심과 계류 색줄 장력"),
    ("nf-7 곤충", "말벌 영소 습성과 페로몬 경보 전파 거리"),
    ("nf-8 회계", "감가상각 정률법 잔존가액과 세무조정 차이"),
]


# ---------------------------------------------------------------- 순수 함수
def compose_score(
    rule: float,
    vector: float,
    *,
    entity_boost: float = 0.0,
    keyword: float = 0.0,
    feedback_adjust: float = 0.0,
    superseded: bool = False,
    session_capture: bool = False,
    scope_fallback: bool = False,
) -> float:
    """제품의 합성 순서를 그대로 재현한다 (store.py:4796-4838).

    F1 대조가 이 함수를 검증한다: 서버가 준 vector를 넣으면 서버의 score가 나와야 한다.
    나오면 `vector`만 갈아끼우는 처치가 유효한 조작이 된다.

    `feedback_adjust`는 **score_breakdown에 나타나지 않는 보정**이다
    (store.py:5362-5378, POSITIVE +0.05 / NEGATIVE −0.15 / VERY_NEGATIVE −0.35).
    c69 1차 런이 F1 3065/3200(4.22% 불일치)으로 걸린 원인이 정확히 이것이었고, 불일치 표본의
    관측−재조립 차이는 **전부 +0.0500**이었다. breakdown만 보고 점수를 재조립하는 감사자는
    이 행들에서 조용히 틀린다 — 관측 31(제품이 진실 아닌 것을 보고한다)과 같은 계열이다.
    """
    score = round(rule * RULE_W + vector * VECTOR_W, 4)
    if entity_boost:
        score = min(1.0, round(score + entity_boost, 4))
    if keyword:
        score = min(1.0, round(score + 0.3 * keyword, 4))
    if feedback_adjust:
        score = max(0.0, min(1.0, round(score + feedback_adjust, 4)))
    if superseded:
        score = round(score * SUPERSEDED_MULT, 4)
    if session_capture:
        score = round(score * CAPTURE_MULT, 4)
    if scope_fallback:
        score = round(score * FALLBACK_MULT, 4)
    return score


def affine_floor_cosine(gate: float = GATE_NOW) -> float:
    """rule=0·무강등 행이 게이트를 넘기 시작하는 raw cosine — 아핀 상수의 연역적 귀결.

    score = 0.275 + rule×0.45 + 0.275×cos 이므로 rule=0에서 score ≥ gate ⟺
    cos ≥ (gate − 0.275)/0.275. 이 값보다 등방성이 나쁜 공간에서는 **어휘 관련성이 0인
    기억도 전부 게이트를 넘는다** — c68이 실측한 FPR=1.00의 산술적 원인.
    """
    const = VECTOR_W / 2.0
    return (gate - const) / const


def separation_stats(on: list[float], off: list[float]) -> dict:
    """척도 불변 분리 통계 — 처치가 점수 척도를 바꿔도 비교 가능한 양.

    ratio·auc·cohen_d는 모든 점수에 대한 **양수 곱셈 재척도에 불변**이다(테스트가 고정).
    gap은 불변이 아니며, 그 사실을 드러내기 위해 함께 낸다.
    """
    if not on or not off or len(on) < 2 or len(off) < 2:
        return {"gap": None, "off_scale": None, "ratio": None, "auc": None, "cohen_d": None}
    gap = min(on) - max(off)
    off_scale = max(off) - min(off)
    ratio = (gap / off_scale) if off_scale > 0 else None
    wins = sum(1 for a in on for b in off if a > b)
    ties = sum(1 for a in on for b in off if a == b)
    auc = (wins + 0.5 * ties) / (len(on) * len(off))
    sd_on, sd_off = statistics.stdev(on), statistics.stdev(off)
    pooled = (((len(on) - 1) * sd_on ** 2 + (len(off) - 1) * sd_off ** 2)
              / (len(on) + len(off) - 2)) ** 0.5
    cohen_d = ((statistics.mean(on) - statistics.mean(off)) / pooled) if pooled > 0 else None
    return {"gap": gap, "off_scale": off_scale, "ratio": ratio, "auc": auc, "cohen_d": cohen_d}


def literal_vs_invariant(baseline: dict, treated: dict) -> dict:
    """P22 (b)의 문자 기준과 척도 불변 기준을 각각 판정하고 **불일치를 드러낸다**.

    문자 기준: treated band_raw > C68_BAND.  불변 기준: treated ratio > baseline ratio.
    둘이 갈리면 agree=False이며, 이 함수는 어느 쪽이 옳은지 결정하지 않는다 —
    내 대체 기준을 내가 '충족'으로 채점하지 않기 위해서다(c67 (라)).
    """
    band = treated.get("band")
    literal = None if band is None else band > C68_BAND
    b_ratio, t_ratio = baseline.get("ratio"), treated.get("ratio")
    invariant = None if (b_ratio is None or t_ratio is None) else t_ratio > b_ratio
    agree = None if (literal is None or invariant is None) else literal == invariant
    return {"literal_pass": literal, "invariant_pass": invariant, "agree": agree}


# ---------------------------------------------------------------- 채취
def probe_pool(query: str, top_k: int) -> list[dict]:
    """훅과 같은 스코프로 검색하고 게이트가 보는 값 + 강등 플래그를 전부 보존한다."""
    from forget_project import layered_filter, project_key_for_path, scope_disabled
    args = {"query": query, "top_k": top_k, "recall": "low", "score_breakdown": True}
    if not scope_disabled():
        project = project_key_for_path(c59.CWD)
        if project:
            args["filters"] = layered_filter(project)
    rows = c59.hook._rpc("search_memories", args).get("results") or []
    out = []
    for r in rows:
        bd = r.get("score_breakdown") or {}
        out.append({
            "id": r.get("id") or "",
            "score": float(r.get("score") or 0.0),
            "rule": float(bd.get("rule") or 0.0),
            "vector": float(bd.get("vector") or 0.0),
            "entity_boost": float(bd.get("entity_boost") or 0.0),
            "keyword": float(bd.get("keyword") or 0.0),
            "superseded": bool(bd.get("superseded")),
            "session_capture": bool(bd.get("session_capture")),
            "text": " ".join((r.get("memory") or "").split()),
        })
    return out


def load_feedback_adjust() -> dict[str, float]:
    """memory_id → 점수 보정값. store.feedback_adjusted_score의 산술을 그대로 따른다.

    이 값은 `score_breakdown`에 **없다**. F1 대조가 100%가 되려면 이것이 필요하다.
    """
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("select memory_id, feedback, metadata from feedback")
    out: dict[str, float] = {}
    for mid, value, md_raw in cur.fetchall():
        try:
            md = json.loads(md_raw) if md_raw else {}
        except (ValueError, TypeError):
            md = {}
        a1 = md.get("a1") if isinstance(md, dict) else None
        if isinstance(a1, dict) and "adjust" in a1:
            try:
                out[str(mid)] = float(a1["adjust"])
            except (TypeError, ValueError):
                out[str(mid)] = 0.0
            continue
        label = str(value or "").upper()
        out[str(mid)] = {"POSITIVE": 0.05, "NEGATIVE": -0.15,
                         "VERY_NEGATIVE": -0.35}.get(label, 0.0)
    con.close()
    return out


def load_embeddings() -> dict[str, list[float]]:
    """id → 저장 임베딩 (제품의 decode_embedding 사용, mode=ro)."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.text_factory = bytes
    cur = con.cursor()
    cur.execute("select id, embedding from memories where deleted=0")
    out: dict[str, list[float]] = {}
    for mem_id, raw in cur:
        mem_id = mem_id.decode() if isinstance(mem_id, bytes) else mem_id
        value: bytes | str = raw
        if isinstance(raw, bytes) and raw[:4] != b"MEB1":
            try:
                value = raw.decode()
            except UnicodeDecodeError:
                value = raw
        vec = decode_embedding(value)
        if vec:
            out[mem_id] = vec
    con.close()
    return out


def embed_query(text: str) -> list[float]:
    """제품의 fastembed 프로바이더를 직접 호출한다 (설정 DB를 열지 않는다).

    settings={} → _fastembed_default_model이 BAAI/bge-small-en-v1.5로 해석한다(:8000의
    effective 스택과 같은 몸). 이 가정은 신뢰가 아니라 **F2 대조**로 검증된다.
    """
    from forget.providers import _embed_with_fastembed_provider
    return _embed_with_fastembed_provider(text, {}, role="query")


# ---------------------------------------------------------------- 처치
def unit(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=-1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return mat / norms


class Space:
    """저장 임베딩 전체가 정하는 공간 — 중심(μ)과 주성분을 한 번만 계산해 재사용한다."""

    def __init__(self, vectors: list[list[float]]):
        self.matrix = unit(np.asarray(vectors, dtype=np.float64))
        self.mu = self.matrix.mean(axis=0)
        centered = self.matrix - self.mu
        # 주성분: 중심화된 스토어 행렬의 우특이벡터. n≫d이므로 SVD로 충분하다.
        _, sing, vt = np.linalg.svd(centered, full_matrices=False)
        self.components = vt
        self.singular = sing

    def transform(self, vec: np.ndarray, *, center: bool, abtt: int = 0,
                  mu: np.ndarray | None = None) -> np.ndarray:
        """center=True면 mu를 차감한다. mu=None이면 스토어 전역 μ, 아니면 주어진 중심
        (질의별 후보 집합 평균 — P22 (b)가 문자 그대로 지정한 변형)."""
        out = vec / (np.linalg.norm(vec) or 1.0)
        if center:
            out = out - (self.mu if mu is None else mu)
        for i in range(abtt):
            comp = self.components[i]
            out = out - float(out @ comp) * comp
        return out


def raw_cos(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(a @ b / (na * nb))


TREATMENTS = [
    # (label, 설명, center, abtt, affine, local_mu)
    ("T0 baseline", "제품 현행 — (cos+1)/2, 중심화 없음", False, 0, True, False),
    ("T1 center", "원인 A만: 전역 μ 차감 후 (cos+1)/2 (아핀 유지)", True, 0, True, False),
    ("T2 affine", "원인 B만: max(0,cos) — 아핀 상수 제거 (중심화 없음)", False, 0, False, False),
    ("T3 center+affine", "A+B: 전역 μ 차감 + max(0,cos)", True, 0, False, False),
    ("T4 abtt1+affine", "A+B, 주성분 1개 추가 제거", True, 1, False, False),
    ("T5 abtt2+affine", "A+B, 주성분 2개 추가 제거", True, 2, False, False),
    ("T6 abtt3+affine", "A+B, 주성분 3개 추가 제거", True, 3, False, False),
    # P22 (b)가 문자 그대로 지정한 변형: "후보 집합의 평균 임베딩을 차감" = 질의별 중심.
    # 평탄도 축(FLATNESS_MARGIN)은 건드리지 않으므로 ⑬⑭ 동시 금지에 걸리지 않는다.
    ("T7 local-center", "P22 문면: 질의별 후보 평균 차감 + (cos+1)/2", True, 0, True, True),
    ("T8 local+affine", "P22 문면 + 아핀 제거", True, 0, False, True),
]


def treated_vector(space: Space, q: np.ndarray, m: np.ndarray,
                   *, center: bool, abtt: int, affine: bool,
                   mu: np.ndarray | None = None) -> float:
    qt = space.transform(q, center=center, abtt=abtt, mu=mu)
    mt = space.transform(m, center=center, abtt=abtt, mu=mu)
    cos = raw_cos(qt, mt)
    v = (cos + 1.0) / 2.0 if affine else max(0.0, cos)
    return round(min(1.0, max(0.0, v)), 4)


# ---------------------------------------------------------------- 본체
def main() -> None:
    print("c69 — P22 (b) 처치: 질의별 중심화/whitening 프로토타입")
    print(f"현행 게이트={GATE_NOW}  가중치=rule×{RULE_W}+vector×{VECTOR_W}  "
          f"pool_top_k={POOL_TOP_K}  문자 기준값 C68_BAND={C68_BAND}")
    print("몸 선언: step 0 [Body] 지문이 정본 (effective 스택 — checks 아님)")

    print("\n[정정 — 물려받은 정의] `vector`는 raw cosine이 아니라 **(cos+1)/2**다 "
          "(memory_engine.py:793 · store.py:640).")
    print(f"  ⇒ score = {VECTOR_W / 2:.3f} + rule×{RULE_W} + {VECTOR_W / 2:.3f}×cos "
          f"— {VECTOR_W / 2:.3f}은 주제 무관 **덧셈 상수**이고 의미 신호 범위는 "
          f"{VECTOR_W / 2:.3f}×cos뿐이다.")
    print(f"  ⇒ 연역: rule=0·무강등 행은 raw cos ≥ {affine_floor_cosine():.4f}이면 "
          f"게이트 {GATE_NOW}를 넘는다. (F2 대조가 이 산술의 전제를 1차 증거로 확인한다)")

    fact_n, hook_n = c68.store_composition()
    print(f"\n스토어 구성: 사실 기억 {fact_n} / 세션 캡처 {hook_n} "
          f"(캡처 {100.0 * hook_n / (fact_n + hook_n):.1f}% — c68 (몸 지문) 승계)")

    emb = load_embeddings()
    dims = {}
    for v in emb.values():
        dims[len(v)] = dims.get(len(v), 0) + 1
    print(f"임베딩 로드: {len(emb)}행, 차원 분포 {dims}")
    main_dim = max(dims, key=lambda d: dims[d])

    fb_adj = load_feedback_adjust()
    print(f"피드백 보정 로드: {len(fb_adj)}행 "
          f"(breakdown에 없는 보정 — 0이 아닌 행 {sum(1 for v in fb_adj.values() if v)})")

    # ---------------- 채취: 같은 계기·같은 질의 집합 ----------------
    # OFF 팔은 **신선 어휘**가 1급이고, c68 어휘 팔은 오염량을 재기 위한 부팔이다.
    queries = [("ON-real", label, q) for label, q in c68.ON_REAL] + \
              [("OFF", label, q) for label, q in FRESH_OFF] + \
              [("OFF-c68", label, q) for label, q in c68.OFF]
    pools: dict[str, list[dict]] = {}
    qvecs: dict[str, np.ndarray] = {}
    print(f"\n채취: ON-real {len(c68.ON_REAL)} + OFF {len(c68.OFF)} = {len(queries)}질의 "
          f"× top_k={POOL_TOP_K} (서버 search_memories, recall=low)")
    for arm, label, q in queries:
        pools[label] = probe_pool(q, POOL_TOP_K)
        qv = embed_query(q)
        qvecs[label] = np.asarray(qv, dtype=np.float64)
        print(f"  {arm:<8} {label:<12} 결과 {len(pools[label]):>3}건  "
              f"질의 임베딩 dim={len(qv)}")

    # ---------------- F1: 사슬 재현 대조 ----------------
    print("\n" + "=" * 78)
    print("[F1 대조 — 합성 사슬 재현] 서버의 rule·vector로 서버의 score가 재조립되는가")
    f1_ok = f1_bad = 0
    fallback_rows = 0
    for label, rows in pools.items():
        for r in rows:
            hit = None
            for fb in (False, True):
                if abs(compose_score(
                        r["rule"], r["vector"], entity_boost=r["entity_boost"],
                        keyword=r["keyword"], feedback_adjust=fb_adj.get(r["id"], 0.0),
                        superseded=r["superseded"],
                        session_capture=r["session_capture"], scope_fallback=fb)
                        - r["score"]) <= 0.0002:
                    hit = fb
                    break
            if hit is None:
                f1_bad += 1
            else:
                f1_ok += 1
                r["scope_fallback"] = hit
                fallback_rows += int(hit)
    total_rows = f1_ok + f1_bad
    print(f"  재현 {f1_ok}/{total_rows} ({100.0 * f1_ok / total_rows:.2f}%)  "
          f"불일치 {f1_bad}  스코프 폴백 추정 {fallback_rows}행")
    if f1_bad:
        print("  ★ 불일치 행이 있다 — 그 행은 처치 계산에서 제외한다(미채취를 '이상 없음'으로 "
              "접지 않는다). 사슬에 내가 모르는 보정이 하나 더 있다는 뜻이다.")

    # ---------------- F2: 임베딩 경로 대조 ----------------
    print("\n" + "=" * 78)
    print("[F2 대조 — 임베딩 경로] 내 (cos+1)/2가 서버의 vector 필드와 일치하는가")
    f2_ok = f2_bad = f2_skip = 0
    worst = 0.0
    for label, rows in pools.items():
        q = qvecs[label]
        if len(q) != main_dim:
            continue
        for r in rows:
            m = emb.get(r["id"])
            if not m or len(m) != len(q):
                f2_skip += 1
                continue
            mine = cosine_similarity([float(x) for x in q], m)
            diff = abs(mine - r["vector"])
            worst = max(worst, diff)
            if diff <= 0.0002:
                f2_ok += 1
            else:
                f2_bad += 1
    print(f"  일치 {f2_ok}  불일치 {f2_bad}  대조 불가 {f2_skip}  최대 편차 {worst:.6f}")
    if f2_bad == 0 and f2_ok > 0:
        print("  → 내 임베딩 경로 == 제품 경로. 그리고 **아핀 재척도 (cos+1)/2가 코드 독해가 "
              "아니라 1차 증거로 확인됐다** (제품의 cosine_similarity로 재현했다).")
    else:
        print("  ★ 경로가 다르다 — 중심화 처치의 cos 계산은 제품과 다른 공간에서 일어난다. "
              "처치 판정을 내지 않고 원인을 먼저 규명해야 한다.")

    gate = (f1_bad == 0) and (f2_bad == 0) and f2_ok > 0
    print(f"\n  계측기 유효 전제: {'충족 — 처치 판정으로 진행' if gate else '미충족 — 아래는 참고값이며 판정 근거로 쓰지 않는다'}")

    # ---------------- 처치 스윕 ----------------
    space = Space([v for v in emb.values() if len(v) == main_dim])
    print(f"\n공간: n={space.matrix.shape[0]} d={space.matrix.shape[1]}  "
          f"‖μ‖={float(np.linalg.norm(space.mu)):.4f}  "
          f"(‖μ‖가 크면 그만큼 모든 쌍이 공통 방향을 공유한다 = 비등방성의 크기)")
    top_sv = space.singular[:3] / space.singular.sum()
    print(f"  주성분 설명 비중 상위3 = {', '.join(f'{x:.4f}' for x in top_sv)}")

    print("\n" + "=" * 78)
    print("[처치 스윕] 같은 질의 집합·같은 사슬, vector 성분만 교체")
    # 질의별 중심(T7·T8용): 그 질의의 후보 집합 임베딩 평균 — 질의 벡터는 넣지 않는다.
    local_mu: dict[str, np.ndarray] = {}
    for _arm, qlabel, _q in queries:
        vecs = [emb[r["id"]] for r in pools[qlabel]
                if r["id"] in emb and len(emb[r["id"]]) == main_dim]
        if vecs:
            local_mu[qlabel] = unit(np.asarray(vecs, dtype=np.float64)).mean(axis=0)

    results = []
    for label, desc, center, abtt, affine, use_local in TREATMENTS:
        on_top1: list[float] = []
        off_top1: list[float] = []
        off_c68_top1: list[float] = []
        max_src_rank = 0
        for arm, qlabel, _q in queries:
            rows = pools[qlabel]
            q = qvecs[qlabel]
            mu = local_mu.get(qlabel) if use_local else None
            if use_local and mu is None:
                continue
            scored = []
            for rank, r in enumerate(rows, start=1):
                if "scope_fallback" not in r:
                    continue                      # F1 불일치 행 — 제외
                m = emb.get(r["id"])
                if not m or len(m) != len(q):
                    continue
                v = treated_vector(space, q, np.asarray(m, dtype=np.float64),
                                   center=center, abtt=abtt, affine=affine, mu=mu)
                s = compose_score(
                    r["rule"], v, entity_boost=r["entity_boost"], keyword=r["keyword"],
                    feedback_adjust=fb_adj.get(r["id"], 0.0),
                    superseded=r["superseded"], session_capture=r["session_capture"],
                    scope_fallback=r["scope_fallback"])
                scored.append((s, rank))
            if not scored:
                continue
            best_s, best_rank = max(scored)
            max_src_rank = max(max_src_rank, best_rank)
            {"ON-real": on_top1, "OFF": off_top1, "OFF-c68": off_c68_top1}[arm].append(best_s)
        band = c68.verdict_band(on_top1, off_top1)
        stats = separation_stats(on_top1, off_top1)
        # 부팔: 오염된 c68 어휘로 같은 처치를 재면 얼마나 달라지는가 (오염량의 실측)
        band_c68 = c68.verdict_band(on_top1, off_c68_top1)
        results.append((label, desc, band, stats, max_src_rank, on_top1, off_top1,
                        band_c68, off_c68_top1))

    baseline_stats = results[0][3]
    fmt = lambda x, n=4: "n/a" if x is None else f"{x:.{n}f}"
    print(f"  (OFF 팔 = 신선 어휘 {len(FRESH_OFF)}건. c68 어휘 팔은 오염 대조로 오른쪽에 병기)")
    print(f"\n  {'처치':<18} {'ON최저':>8} {'OFF최고':>8} {'band':>8} {'OFFσ폭':>8} "
          f"{'R':>7} {'AUC':>6} {'d':>7}  {'판정':<10} {'c68팔OFF최고':>11} {'c68팔판정':<9}")
    for label, desc, band, stats, _rank, on, off, band_c68, off_c68 in results:
        print(f"  {label:<18} {fmt(min(on) if on else None):>8} "
              f"{fmt(max(off) if off else None):>8} {fmt(band['band']):>8} "
              f"{fmt(stats['off_scale']):>8} {fmt(stats['ratio'], 3):>7} "
              f"{fmt(stats['auc'], 3):>6} {fmt(stats['cohen_d'], 2):>7}  {band['verdict']:<10} "
              f"{fmt(max(off_c68) if off_c68 else None):>11} {band_c68['verdict']:<9}")

    print("\n  (band = 허용 상수 구간 폭[t_min,t_max] · OFFσ폭 = OFF top-1 산포 · "
          "R = (ON최저−OFF최고)/OFFσ폭 · AUC = ON>OFF 확률 · d = Cohen's d)")
    print(f"  처치 후 top-1이 온 최대 원 순위: "
          f"{max(r[4] for r in results)}/{POOL_TOP_K} "
          f"— 이 값이 pool 깊이에 가까우면 pool이 얕아 결과가 절단됐다는 뜻이다.")

    # ---------------- 판정 ----------------
    print("\n" + "=" * 78)
    print("=== 판정 재료 (P22 (b)) ===")
    print(f"  baseline R={baseline_stats['ratio']:.3f} "
          f"AUC={baseline_stats['auc']:.3f} d={baseline_stats['cohen_d']:.2f}")
    for label, desc, band, stats, _rank, _on, _off, _bc, _oc in results[1:]:
        v = literal_vs_invariant(baseline_stats, {**stats, "band": band["band"]})
        mark = {True: "통과", False: "탈락", None: "판정불가"}
        print(f"\n  {label} — {desc}")
        print(f"    문자 기준(band {band['band'] if band['band'] is not None else 'n/a'} > {C68_BAND}): "
              f"{mark[v['literal_pass']]}"
              f"   |   척도 불변(R {stats['ratio'] if stats['ratio'] is None else round(stats['ratio'], 3)} > "
              f"{round(baseline_stats['ratio'], 3)}): {mark[v['invariant_pass']]}")
        if v["agree"] is False:
            print("    ★ 두 기준이 **갈렸다** — 등록된 문자 기준이 척도 의존이라는 예고가 "
                  "실측으로 발생했다. 어느 쪽으로 판정할지는 이 손이 정하지 않는다(노출).")

    print("\n" + "=" * 78)
    print("CAVEAT: ① OFF 8건의 무관함·ON-real 8건의 관련성은 이 손의 어휘 판단이다 "
          "(c66 caveat ① → c68 승계). ② 후보 풀은 서버의 **원 점수** 상위 "
          f"{POOL_TOP_K}행이다 — 처치 후 top-1이 풀 밖에서 올 가능성은 배제되지 않았고, "
          "위의 '최대 원 순위'가 그 절단 위험의 대리 지표다. ③ 단일 시점·현 스택 측정. "
          "④ 훅의 세션 ledger·중복 억제·평탄도 게이트는 재현하지 않았다 — 여기서 '통과'는 "
          "절대 상수 단독 통과이며 실주입의 상한이다. ⑤ 중심화는 두 형태를 모두 쟀다 — "
          "전역 μ(T1·T3~T6)와 **질의별 후보 집합 평균**(T7·T8, P22 (b)의 문면). "
          "P22 (b)가 함께 적은 '**평균 점수** 차감' 변형은 하지 않았다: 그것은 질의 내 점수 "
          "낙폭을 자[尺]로 쓰는 처치여서 평탄도 축(⑭·관측 24 소유)과 같은 것을 건드리고, "
          "⑬⑭ 동시 변경 금지 규율에 걸린다(P22 (c)). 미이행으로 남긴다. "
          "⑥ 이 스크립트는 **제품 상수를 하나도 바꾸지 않는다** — 프로토타입 측정이다.")


if __name__ == "__main__":
    main()
