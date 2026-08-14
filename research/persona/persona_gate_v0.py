#!/usr/bin/env python3
"""인격 게이트 v0 (보강판) — "얼마나 나인가"의 원점 측정.

gate-audit-2026-08-14.md §5·§9와 persona_pairs_v1.manifest.gate_prereg의
구속을 이행한다:

  ⓪ 산출물 무덮어쓰기 — 결과 파일이 있으면 거부 (PERSONA_GATE_FORCE=1로만 해제).
  ① 널 선등재 — 어떤 판별도 돌기 전에 양측의 P(응답 언어 ≠ 문맥 언어)와
     길이 분포를 계산해 파일로 박는다. 언어 불일치율이 양측에서 다르면
     판별자는 목소리가 아니라 언어를 읽을 수 있다 (결함 ⑦의 선제).
  ② 길이-강제 정합 — 인격 생성을 실응답 길이에 묶고 |Δ| ≤ 허용치 재표집
     (길이 탐지기 결함 ①의 선제). 정합 실패 쌍은 제외하지 않고 기록.
  ③ 판별 — 강제 이지선다, A/B 시드 무작위, 판정 대역 선등록 승계
     (≤0.65 통과 / 0.65~0.80 중간 / ≥0.80 낙제, n<40 유보), 전체율과
     함께 같은-언어 부분집합율 병기.

홀드아웃 = persona_holdout_v0.json (persona_v0 훈련 제외가 구성적으로
보장된 유일 집합 — v1 꼬리는 v0 훈련셋과 중첩 미검증이라 쓰지 않는다).
실제 측 = 나의 실응답(홀드아웃), 모조 측 = persona_v0 (kanana LoRA).
판별자 = Spark 27B (인격과 다른 모델·다른 장비).
"""
from __future__ import annotations

import json
import os
import random
import sys
import urllib.request
from pathlib import Path

HOLDOUT = Path(__file__).resolve().parent / "persona_holdout_v0.json"
OUT_DIR = Path.home() / ".forget/twin"
NULLS = OUT_DIR / "persona_gate_v0.nulls.json"
RESULTS = OUT_DIR / "persona_gate_v0.results.jsonl"

PERSONA_URL = "http://127.0.0.1:8024/v1/chat/completions"
PERSONA_MODEL = "persona_v0"
JUDGE_URL = "http://127.0.0.1:11435/api/chat"
JUDGE_MODEL = "qwen3.6:27b"
SYS = "너는 정훈과 함께 forget을 만드는 에이전트다. 아래는 정훈의 메시지다. 너로서 응답하라."

N_PAIRS = int(sys.argv[1]) if len(sys.argv) > 1 else 60
CAP = 400          # 실응답이 장문(중앙 148, p90 1211)이라 300 → 400
MATCH_TOL = 20
MATCH_TRIES = 6


def _post(url: str, payload: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def _hangul_ratio(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if "가" <= c <= "힣") / len(letters)


def lang(s: str) -> str:
    r = _hangul_ratio(s)
    return "ko" if r >= 0.30 else ("en" if r < 0.15 else "mixed")


def persona_say(ctx: str, max_tokens: int) -> str:
    body = _post(PERSONA_URL, {
        "model": PERSONA_MODEL, "temperature": 0.7, "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "system", "content": SYS},
                     {"role": "user", "content": ctx[-1600:]}],
    })
    return str((body.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()


def persona_say_matched(ctx: str, target_chars: int) -> str:
    cap = max(12, target_chars // 2 + 12)
    best, best_gap = "", 10 ** 9
    for _ in range(MATCH_TRIES):
        fake = persona_say(ctx, cap)
        if not fake:
            continue
        gap = abs(len(fake) - target_chars)
        if gap < best_gap:
            best, best_gap = fake, gap
        if gap <= MATCH_TOL:
            break
    return best


def judge(ctx: str, a: str, b: str) -> str:
    prompt = (
        "다음은 사용자(정훈)의 메시지와, AI 에이전트의 응답 후보 A/B다.\n"
        "하나는 실제로 그와 일해 온 에이전트가 쓴 것이고, 하나는 그 에이전트를 모방한 로컬 모델이다.\n"
        "실제 에이전트가 쓴 쪽을 골라라. 반드시 'A' 또는 'B' 한 글자로만 답하라.\n\n"
        f"[정훈의 메시지]\n{ctx[-1200:]}\n\n[A]\n{a}\n\n[B]\n{b}\n\n답:"
    )
    body = _post(JUDGE_URL, {
        "model": JUDGE_MODEL, "stream": False, "think": False, "keep_alive": "3h",
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0.0, "num_predict": 5},
    })
    ans = str((body.get("message") or {}).get("content") or "").strip().upper()
    return "A" if ans.startswith("A") else ("B" if ans.startswith("B") else "?")


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (round(c - h, 4), round(c + h, 4))


def main() -> None:
    if (NULLS.exists() or RESULTS.exists()) and os.environ.get("PERSONA_GATE_FORCE") != "1":
        sys.exit(f"산출물 존재 — 덮지 않는다: {NULLS.name}/{RESULTS.name} (해제: PERSONA_GATE_FORCE=1)")

    rng = random.Random(42)
    pool = json.loads(HOLDOUT.read_text())
    rng.shuffle(pool)
    pool = pool[:N_PAIRS]
    print(f"홀드아웃 {len(pool)}쌍 (persona_holdout_v0 — v0 훈련 제외 보장)", file=sys.stderr)

    # ── ① 생성 + 널 선등재 (판별 전에 파일로 박는다) ──
    gen_pairs = []
    for item in pool:
        real = str(item["response"])[:CAP]
        try:
            fake = persona_say_matched(item["context"], len(real))
        except Exception as exc:
            print(f"[skip] 생성 실패: {exc}", file=sys.stderr)
            continue
        if not fake:
            continue
        gen_pairs.append({"ctx": item["context"], "real": real, "fake": fake[:CAP]})

    def mismatch_rate(side: str) -> float:
        vals = [1 for g in gen_pairs if lang(g[side]) != lang(g["ctx"][-400:])]
        return round(len(vals) / max(1, len(gen_pairs)), 4)

    gaps = [abs(len(g["real"]) - len(g["fake"])) for g in gen_pairs]
    nulls = {
        "n": len(gen_pairs),
        "lang_mismatch_real": mismatch_rate("real"),
        "lang_mismatch_fake": mismatch_rate("fake"),
        "lang_gap_alarm": abs(mismatch_rate("real") - mismatch_rate("fake")) > 0.15,
        "len_gap_median": sorted(gaps)[len(gaps) // 2] if gaps else None,
        "len_match_within_tol": round(sum(1 for g in gaps if g <= MATCH_TOL) / max(1, len(gaps)), 4),
        "forced_choice_null": 0.5,
        "prereg_bands": "<=0.65 통과 / 0.65~0.80 중간 / >=0.80 낙제, n<40 유보",
    }
    NULLS.write_text(json.dumps(nulls, ensure_ascii=False, indent=2))
    print("널 선등재:", json.dumps(nulls, ensure_ascii=False), file=sys.stderr)

    # ── ② 판별 ──
    correct = judged = same_lang_n = same_lang_correct = 0
    with RESULTS.open("w") as fh:
        for g in gen_pairs:
            real_is_a = rng.random() < 0.5
            a, b = (g["real"], g["fake"]) if real_is_a else (g["fake"], g["real"])
            try:
                pick = judge(g["ctx"], a, b)
            except Exception as exc:
                print(f"[skip] 판별 실패: {exc}", file=sys.stderr)
                continue
            if pick == "?":
                continue
            hit = (pick == "A") == real_is_a
            judged += 1
            correct += 1 if hit else 0
            same = lang(g["real"]) == lang(g["fake"])
            if same:
                same_lang_n += 1
                same_lang_correct += 1 if hit else 0
            fh.write(json.dumps({"real_is_a": real_is_a, "pick": pick, "judge_correct": hit,
                                 "same_lang": same, "real": g["real"], "fake": g["fake"],
                                 "ctx_tail": g["ctx"][-300:]}, ensure_ascii=False) + "\n")
            if judged % 10 == 0:
                print(f"  {judged}쌍: 구별률 {correct / judged:.3f}", file=sys.stderr)

    if judged == 0:
        sys.exit("판정 쌍 0")
    rate = correct / judged
    lo, hi = wilson(correct, judged)
    if judged < 40:
        verdict = "표본 미달 — 판정 유보"
    elif rate <= 0.65:
        verdict = "게이트 통과 (사람 검수로)"
    elif rate < 0.80:
        verdict = "중간 (근접, 보류)"
    else:
        verdict = "낙제 (각인 부족)"
    print(json.dumps({
        "n": judged, "discrimination_rate": round(rate, 4), "wilson_95": [lo, hi],
        "same_lang_subset": {"n": same_lang_n,
                             "rate": round(same_lang_correct / max(1, same_lang_n), 4)},
        "verdict": verdict, "nulls": str(NULLS), "out": str(RESULTS),
        "persona": PERSONA_MODEL, "judge": JUDGE_MODEL, "cap_chars": CAP,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
