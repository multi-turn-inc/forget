#!/usr/bin/env python3
"""c72 — ⑮ 아핀 재척도 제거 처치의 수용 측정 + P23 판정 재료 (read-only, LLM 0회, $0).

처치(이 사이클, 제품 코드): `memory_engine.cosine_similarity:793`과
`store._batch_cosine_scores:640`의 `(cos+1)/2`를 **`max(0, cos)`**로 교체했다 —
c69 스윕에서 유일하게 두 기준(문자·척도 불변)을 모두 통과한 T2의 성문화(P22 판정 §승계).
자[尺] 단독 사이클: 게이트 상수(0.45/0.30/0.03)·평탄도 margin(⑭ 소유)은 건드리지 않는다.

이 계기가 재는 것 (등록된 기준만 판정하고, 나머지는 관찰로 병기한다):

  [P23 (a) 지속성 — 등록 기준] T2의 척도 불변 R이 **표본을 늘려도 1.0 이상**인가.
    기준선 R=1.221 (c69, 신선 OFF 7 / ON-real 8). 이번 표본: 신선 OFF를 새로 뽑아
    확대한다(관측 34 규약 ① 매 사이클 신규 추출 · ② SQL 미등장 확인 · ③ 보고 열거 금지).
    표본 확대는 OFF 팔에서 일어난다 — R을 죽일 수 있는 팔이 OFF 팔이다(max OFF ↑).

  [P23 (b) 상수 재교정과의 결합 — 등록 기준] 아핀 제거 후의 허용 구간 [t_min, t_max]가
    P22 (a)의 단조 축소를 여전히 겪는가. 판정 재료 = OFF 표본 누적 접두열에 대한
    band 곡선(늘어나며 좁아지기만 하는가) + verdict_band의 t_min/t_max 단조성은
    점수 척도와 무관한 집합 산술이라는 사실(스케일을 바꿔도 연역은 그대로다).

  [계측기 유효 전제 — 하나라도 깨지면 처치 판정을 내지 않는다]
    F1 (사슬 재현): 서버 rule·vector → 서버 score 재조립 (c69 승계, 피드백 보정 포함).
    F2 (몸 미처치 확인 + 임베딩 경로): 서버 `vector` 필드 == 내가 계산한 **(cos+1)/2**.
       일치하면 (ㄱ) 살아 있는 몸(:8000)이 아직 구척도임이 1차 증거로 확정되고
       (ㄴ) 내 임베딩 경로가 제품과 같다. — 처치는 저장소에만 있고 배포는 게이트 ⑩이다.
    F3 (처치 구현 증명): 저장소의 새 `cosine_similarity`와 `_batch_cosine_scores`가
       같은 (질의, 기억) 쌍에서 **max(0, round(cos,4))와 비트 단위 일치**하는가.
       일치하면 T2가 프로토타입이 아니라 제품 코드로 정확히 이식됐다는 뜻이다.

  [관찰 — 등록 기준 아님, 성공 주장에 쓰지 않는다] 게이트 상수 0.45 미변경 상태에서
    T0/T2 각각의 ON-real TPR과 OFF FPR. c68이 실측한 FPR=1.00의 산술 원인(상수 0.275)이
    제거된 뒤의 모사값이며, **실주입이 아니라 harvested pool 위의 상한 모사**다.

read-only: 서버는 search_memories만(recall=low), DB는 sqlite mode=ro, 쓰기 0 · $0.

    .venv/bin/python research/devloop/scripts/c72_affine_verdict.py
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, REPO)

from forget.memory_engine import cosine_similarity  # noqa: E402  (처치 후 = max(0,cos))
from forget.store import _batch_cosine_scores  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


c69 = _load("c69_centering_prototype")
c68 = c69.c68

GATE_NOW = c69.GATE_NOW
POOL_TOP_K = 200
R_FLOOR = 1.0                 # P23 (a) 등록 기준
R_BASELINE = 1.221            # c69 T2 (신선 OFF 7 / ON-real 8) — 다른 어휘, 참고 병기용
BAND_BASELINE = 0.0296        # c69 T2 문자 기준값 — 다른 어휘, 참고 병기용
DB = c68.DB

# 신선 OFF 후보 — c68·c69 어휘와 겹치지 않는 새 주제 14건. 적격 판정(어절 미등장 SQL)을
# 통과한 것만 쓴다. **이 목록은 이 파일에만 산다** — 사이클 보고·원장·기억에 열거하면
# 그 순간 소모된다(관측 34 ③).
FRESH_OFF_CANDIDATES = [
    ("c72-1 승마", "마장마술 구보 반박자 전환과 고삐 장력 유지"),
    ("c72-2 염색", "쪽빛 천연염색 발효 염액 산도와 매염제 배합"),
    ("c72-3 천문", "행성상 성운 산소 방출선 협대역 필터 관측"),
    ("c72-4 치즈", "경성 치즈 숙성고 습도와 외피 세척 주기"),
    ("c72-5 철도", "궤도 캔트 부족량과 곡선 통과 속도 제한"),
    ("c72-6 잠수", "감압 정지 수심 배분과 잔류 질소 계산"),
    ("c72-7 서예", "전서체 필획 장봉 운필과 먹의 농담 조절"),
    ("c72-8 원단", "데님 셀비지 직기 폭과 인디고 로프 염색"),
    ("c72-9 족부", "족저근막염 체외충격파 시술 강도와 간격"),
    ("c72-10 조경", "잔디 배수층 마사토 두께와 관수 빈도"),
    ("c72-11 음향", "리본 마이크 근접 효과와 저역 롤오프"),
    ("c72-12 제지", "닥나무 한지 초지 발틀 흘림뜨기 두께 편차"),
    ("c72-13 등반", "빙벽 스크루 설치 각도와 아이스 낙하 하중"),
    ("c72-14 양조", "청주 입국 당화 온도와 술덧 단계 담금"),
]


def eligible_fresh_off() -> list[tuple[str, str]]:
    """관측 34 ②: 어절(≥3자)이 스토어 전문에 미등장인 것이 2개 이상인 질의만 채택."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    keep = []
    for label, q in FRESH_OFF_CANDIDATES:
        tokens = [t for t in q.split() if len(t) >= 3]
        clean = 0
        for t in tokens:
            cur.execute("select count(*) from memories where deleted=0 and memory like ?",
                        (f"%{t}%",))
            clean += int(cur.fetchone()[0] == 0)
        print(f"  {label:<12} 어절 {len(tokens)}개 중 미등장 {clean}개  "
              f"{'적격' if clean >= 2 else '★ 부적격'}")
        if clean >= 2:
            keep.append((label, q))
    con.close()
    return keep


def affine_vector(cos: float) -> float:
    """구척도 (cos+1)/2 — 몸(:8000)이 아직 쓰는 척도. F2와 T0 재계산용."""
    return max(0.0, min(1.0, round((cos + 1.0) / 2.0, 4)))


def t2_vector(cos: float) -> float:
    """신척도 max(0,cos) — F3가 이 값과 저장소 코드의 비트 단위 일치를 검사한다."""
    return max(0.0, min(1.0, round(cos, 4)))


def main() -> None:
    print("c72 — 아핀 재척도 제거(⑮/P23) 수용 측정")
    print(f"게이트(미변경)={GATE_NOW}  가중치=rule×{c69.RULE_W}+vector×{c69.VECTOR_W}  "
          f"pool_top_k={POOL_TOP_K}")
    print(f"등록 기준: R ≥ {R_FLOOR} (P23 (a)) — 기준선 R={R_BASELINE} (c69 T2, 다른 어휘)")

    print("\n[신선 OFF 적격 검사 — 관측 34 ①②, 어휘는 이 파일에만 산다]")
    fresh_off = eligible_fresh_off()
    print(f"  적격 {len(fresh_off)}/{len(FRESH_OFF_CANDIDATES)}건 — "
          f"표본 확대: OFF {len(fresh_off)} vs c69의 7 (ON-real은 c68 정본 8 유지)")

    emb = c69.load_embeddings()
    dims = {}
    for v in emb.values():
        dims[len(v)] = dims.get(len(v), 0) + 1
    main_dim = max(dims, key=lambda d: dims[d])
    fb_adj = c69.load_feedback_adjust()
    print(f"\n임베딩 로드: {len(emb)}행 (주 차원 {main_dim})  피드백 보정 {len(fb_adj)}행")

    queries = [("ON-real", label, q) for label, q in c68.ON_REAL] + \
              [("OFF", label, q) for label, q in fresh_off]
    pools: dict[str, list[dict]] = {}
    qvecs: dict[str, np.ndarray] = {}
    print(f"채취: ON-real {len(c68.ON_REAL)} + OFF {len(fresh_off)} = {len(queries)}질의 "
          f"× top_k={POOL_TOP_K}")
    for _arm, label, q in queries:
        pools[label] = c69.probe_pool(q, POOL_TOP_K)
        qvecs[label] = np.asarray(c69.embed_query(q), dtype=np.float64)

    # ---------------- F1: 사슬 재현 ----------------
    print("\n" + "=" * 78)
    print("[F1 — 사슬 재현] 서버 rule·vector → 서버 score (피드백 보정 포함, c69 승계)")
    f1_ok = 0
    f1_known_bypass = 0     # 관측 33: rule=0·vector=0인데 score>0 — 사슬을 우회하는
    f1_unexplained = 0      # task_state 클레임. c69 정직 병기 ④의 기지 서명이며,
    #                         제외는 침묵이 아니라 **선언된 범위 한정**이다.
    for label, rows in pools.items():
        for r in rows:
            hit = None
            for fb in (False, True):
                if abs(c69.compose_score(
                        r["rule"], r["vector"], entity_boost=r["entity_boost"],
                        keyword=r["keyword"], feedback_adjust=fb_adj.get(r["id"], 0.0),
                        superseded=r["superseded"],
                        session_capture=r["session_capture"], scope_fallback=fb)
                        - r["score"]) <= 0.0002:
                    hit = fb
                    break
            if hit is None:
                if r["rule"] == 0.0 and r["vector"] == 0.0 and r["score"] > 0.0:
                    f1_known_bypass += 1
                else:
                    f1_unexplained += 1
                    print(f"  ★ 미지 불일치: {label} id={r['id'][:8]} rule={r['rule']} "
                          f"vector={r['vector']} score={r['score']}")
            else:
                f1_ok += 1
                r["scope_fallback"] = hit
    f1_total = f1_ok + f1_known_bypass + f1_unexplained
    print(f"  재현 {f1_ok}/{f1_total} ({100.0 * f1_ok / max(1, f1_total):.2f}%)  "
          f"기지 우회 {f1_known_bypass}행(관측 33 서명, 선언된 제외)  "
          f"미지 불일치 {f1_unexplained}행")

    # ---------------- F2: 몸 미처치 확인 + 임베딩 경로 ----------------
    print("\n" + "=" * 78)
    print("[F2 — 몸 미처치 확인] 서버 vector 필드 == 내 (cos+1)/2 인가")
    print("  (일치 = :8000은 아직 구척도로 돈다. 처치는 저장소에만 있고 배포는 게이트 ⑩)")
    f2_ok = f2_bad = f2_skip = 0
    f3_scalar_ok = f3_scalar_bad = 0
    worst2 = worst3 = 0.0
    pairs_by_label: dict[str, list[tuple[dict, float]]] = {}
    for label, rows in pools.items():
        q = qvecs[label]
        if len(q) != main_dim:
            continue
        pairs_by_label[label] = []
        qf = [float(x) for x in q]
        for r in rows:
            m = emb.get(r["id"])
            if not m or len(m) != len(q):
                f2_skip += 1
                continue
            cos = c69.raw_cos(q, np.asarray(m, dtype=np.float64))
            pairs_by_label[label].append((r, cos))
            d2 = abs(affine_vector(cos) - r["vector"])
            worst2 = max(worst2, d2)
            if d2 <= 0.0002:
                f2_ok += 1
            else:
                f2_bad += 1
            # F3 스칼라 팔: 저장소의 새 cosine_similarity == max(0, round(cos,4))
            mine = cosine_similarity(qf, m)
            d3 = abs(mine - t2_vector(cos))
            worst3 = max(worst3, d3)
            if d3 == 0.0:
                f3_scalar_ok += 1
            else:
                f3_scalar_bad += 1
    print(f"  일치 {f2_ok}  불일치 {f2_bad}  대조 불가 {f2_skip}  최대 편차 {worst2:.6f}")

    print("\n[F3 — 처치 구현 증명] 저장소 코드 == max(0, round(cos,4)) 비트 단위인가")
    print(f"  스칼라(cosine_similarity):    일치 {f3_scalar_ok}  불일치 {f3_scalar_bad}  "
          f"최대 편차 {worst3:.6f}")
    f3_batch_ok = f3_batch_bad = 0
    for label, pairs in pairs_by_label.items():
        if len(pairs) < 64:            # _batch_cosine_scores는 64행 미만이면 스칼라 폴백
            continue
        cands = [{"id": r["id"], "_embedding": emb[r["id"]]} for r, _ in pairs]
        batch = _batch_cosine_scores([float(x) for x in qvecs[label]], cands)
        for r, cos in pairs:
            got = batch.get(r["id"])
            if got is None:
                continue
            if abs(got - t2_vector(cos)) == 0.0:
                f3_batch_ok += 1
            else:
                f3_batch_bad += 1
    print(f"  배치(_batch_cosine_scores):   일치 {f3_batch_ok}  불일치 {f3_batch_bad}")

    gate = (f1_unexplained == 0) and (f2_bad == 0) and f2_ok > 0 \
        and (f3_scalar_bad == 0) and (f3_batch_bad == 0) and f3_batch_ok > 0
    print(f"\n  계측기 유효 전제: "
          f"{'충족 — 처치 판정으로 진행' if gate else '미충족 — 아래는 참고값, 판정 근거 아님'}")

    # ---------------- T0/T2 스윕 ----------------
    print("\n" + "=" * 78)
    print("[스윕] 같은 질의·같은 사슬, vector 성분만 T0(구척도 재계산) / T2(저장소 새 코드)")
    arm_top1: dict[str, dict[str, list[tuple[str, float]]]] = {
        "T0": {"ON-real": [], "OFF": []}, "T2": {"ON-real": [], "OFF": []}}
    gate_counts = {"T0": {"ON-real": 0, "OFF": 0}, "T2": {"ON-real": 0, "OFF": 0}}
    arm_n = {"ON-real": 0, "OFF": 0}
    for arm, qlabel, _q in queries:
        pairs = pairs_by_label.get(qlabel) or []
        scored = {"T0": [], "T2": []}
        for r, cos in pairs:
            if "scope_fallback" not in r:
                continue
            for t_label, vec in (("T0", affine_vector(cos)), ("T2", t2_vector(cos))):
                scored[t_label].append(c69.compose_score(
                    r["rule"], vec, entity_boost=r["entity_boost"], keyword=r["keyword"],
                    feedback_adjust=fb_adj.get(r["id"], 0.0), superseded=r["superseded"],
                    session_capture=r["session_capture"], scope_fallback=r["scope_fallback"]))
        if not scored["T0"] or not scored["T2"]:
            continue
        arm_n[arm] += 1
        for t_label in ("T0", "T2"):
            top1 = max(scored[t_label])
            arm_top1[t_label][arm].append((qlabel, top1))
            gate_counts[t_label][arm] += int(top1 >= GATE_NOW)

    for t_label in ("T0", "T2"):
        on = [s for _, s in arm_top1[t_label]["ON-real"]]
        off = [s for _, s in arm_top1[t_label]["OFF"]]
        band = c68.verdict_band(on, off)
        stats = c69.separation_stats(on, off)
        fmt = lambda x, n=4: "n/a" if x is None else f"{x:.{n}f}"
        print(f"\n  {t_label}: ON최저={fmt(min(on))} OFF최고={fmt(max(off))} "
              f"band={fmt(band['band'])} ({band['verdict']})  "
              f"R={fmt(stats['ratio'], 3)} AUC={fmt(stats['auc'], 3)} d={fmt(stats['cohen_d'], 2)}")
        if t_label == "T2":
            t2_stats, t2_band, t2_on, t2_off = stats, band, on, off

    # ---------------- 판정 재료 ----------------
    print("\n" + "=" * 78)
    print("=== 판정 재료 ===")
    r_val = t2_stats["ratio"]
    if not gate or r_val is None:
        print("  계측기 전제 미충족 또는 R 계산 불가 — 판정을 내지 않는다.")
        return

    print(f"\n[P23 (a) 지속성 — 등록 기준 R ≥ {R_FLOOR}]")
    print(f"  T2 R = {r_val:.3f}  (표본: 신선 OFF {arm_n['OFF']} / ON-real {arm_n['ON-real']} "
          f"— c69의 OFF 7 대비 확대)")
    print(f"  → {'**성립** — 분리 상수가 계속 존재한다' if r_val >= R_FLOOR else '**반증** — 아핀 제거도 닫혔다. 남는 것은 리랭커·어휘 성분 재설계다'}")
    print(f"  참고 병기: c69 T2와의 비교는 어휘가 다르므로(관측 34 ①) 동일 표본 추세가 아니다 "
          f"— R {R_BASELINE} → {r_val:.3f}, band {BAND_BASELINE} → {t2_band['band']}")

    print(f"\n[P23 (b) 상수 재교정과의 결합 — 단조 축소가 신척도에서도 성립하는가]")
    print("  OFF 누적 접두열에 대한 T2 허용 구간 폭(집합 산술상 좁아지기만 해야 한다):")
    off_series = arm_top1["T2"]["OFF"]
    prev = None
    widened = 0
    for n in range(3, len(off_series) + 1):
        band_n = c68.verdict_band(t2_on, [s for _, s in off_series[:n]])
        width = band_n["band"]
        mark = ""
        if prev is not None and width is not None and prev is not None and width > prev + 1e-12:
            widened += 1
            mark = "  ★ 넓어짐(반증 표본)"
        print(f"    OFF n={n:>2}  band={'n/a' if width is None else f'{width:.4f}'} "
              f"({band_n['verdict']}){mark}")
        prev = width
    print(f"  → 넓어진 전이 {widened}회: "
          f"{'**성립 방향** — 아핀 제거는 상수 경로를 다시 열지 않는다(t_min↑·t_max↓ 산술은 척도 무관)' if widened == 0 else '**반증** — c68 폐쇄 판정 재검토 필요'}")

    print(f"\n[관찰 — 등록 기준 아님: 게이트 {GATE_NOW} 미변경 시 top-1 통과율 (pool 모사, 실주입 아님)]")
    for t_label in ("T0", "T2"):
        print(f"  {t_label}: ON-real {gate_counts[t_label]['ON-real']}/{arm_n['ON-real']} 통과 · "
              f"OFF {gate_counts[t_label]['OFF']}/{arm_n['OFF']} 통과")
    print("  (T0의 OFF 통과가 c68의 FPR=1.00 계열이고, T2의 차이는 상수 0.275 제거의 산술 "
          "귀결이다. 단 이 값은 배포 전 모사이며 살아 있는 몸의 행동이 아니다 — 게이트 ⑩.)")

    print("\n" + "=" * 78)
    print("CAVEAT: ① OFF의 무관함·ON-real의 관련성은 이 손의 어휘 판단 + SQL 어절 검사다. "
          "② 후보 풀은 서버 **구척도** 원 점수 상위 200행이다 — T2 top-1이 풀 밖에서 올 "
          "가능성은 배제되지 않았다(c69와 동일 한계). ③ 단일 시점·현 스택(:8000 구척도 몸). "
          "④ ON-real 8은 c68 정본 재사용이다 — ON 라벨은 OFF와 달리 기록으로 만료되지 "
          "않는다(스토어에 관련 기억이 '있다'는 명제는 기록이 강화한다). 단 ON 표본 미확대는 "
          "t_max 하강 압력을 재지 않았다는 뜻이므로 (a) 성립은 OFF 확대 축에 한정해 읽어라. "
          "⑤ R 비교(1.221 →)는 어휘 교체를 낀 비동일 표본 비교다 — 등록 기준은 절대값 "
          "R ≥ 1.0이지 추세가 아니다. ⑥ 이 계기는 게이트 상수를 바꾸지 않으며, 재교정 "
          "권고도 내지 않는다(P22 (a) 폐쇄 유지 — 재개봉 조건은 P23 (b) 반증뿐). "
          "⑦ F1의 기지 우회 행(관측 33 서명: rule=0·vector=0·score>0인 task_state "
          "클레임)은 처치 계산에서 제외했다 — 스윕은 그 행을 제외한 집합의 성질이다"
          "(c69 정직 병기 ④ 승계, 선언된 범위 한정).")


if __name__ == "__main__":
    main()
