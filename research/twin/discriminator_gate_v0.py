#!/usr/bin/env python3
"""적대 판별기 게이트 v0 — 되기 P1 (becoming-junghun.md §2).

질문: 판별자가 실발화와 쌍둥이 발화를 구별할 수 있는가?
방법: 강제 이지선다 — 같은 컨텍스트에서 (실발화, twin_v1 발화) 쌍을 만들고
      판별자(Spark 27B — 쌍둥이와 다른 모델)가 진짜를 고른다. A/B 위치는
      고정 시드로 무작위화. 구별률 50% = 구별 불가 = 목소리 완성.

판정 대역 (선등록 — 결과 산출 전 문면 고정, 2026-08-13):
  구별률 ≤ 0.65  → 게이트 통과 (승격 후보 — 사람 검수로)
  0.65 < x < 0.80 → 중간 (목소리 근접, 승격 보류)
  구별률 ≥ 0.80  → 낙제 (구별 쉬움 — 각인 부족)
  ± Wilson 95% CI 병기. n < 40이면 판정 유보(표본 미달)로만 보고.

정직 캐비앗 (선언): 길이·절단은 그 자체가 문체 신호이지만 인공 단서이기도
하다 — 양쪽을 300자로 통일 절단해 완화하되, 절단 흔적이 남는 쌍은 그대로
둔다(실발화도 자주 짧다). 판별자 위치 편향은 A/B 무작위화로 상쇄.
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import urllib.request
from pathlib import Path

SCORES = Path.home() / ".forget/twin/shadow_scores.jsonl"
STREAM_DIR = Path.home() / ".forget/proxy/stream"
# 홀드아웃 규율: twin_v1 훈련 컷오프(2026-08-12 밤) 이후의 발화만 쌍 재료로
# 쓴다 — 훈련이 본 발화로 판별하면 축자 재현이 가능해 게이트가 관대해진다.
STREAM_DAY = "2026-08-13"
OUT = Path.home() / f".forget/twin/discriminator_{os.environ.get('TWIN_MODEL', 'twin_v1')}.jsonl"

TWIN_URL = os.environ.get("TWIN_URL", "http://127.0.0.1:8024/v1/chat/completions")
TWIN_MODEL = os.environ.get("TWIN_MODEL", "twin_v1")
JUDGE_URL = "http://127.0.0.1:11435/api/chat"  # Spark 27B — 쌍둥이와 다른 모델
JUDGE_MODEL = "qwen3.6:27b"
N_PAIRS = int(sys.argv[1]) if len(sys.argv) > 1 else 60
CAP = 300  # 양쪽 발화 통일 절단(자)

CONTAM = re.compile(
    r"\[SUGGESTION MODE|Suggest what the user might naturally type"
    r"|\[forget 회상|\[forget 캡슐|<command-|<local-command|<bash-input"
    r"|<system-reminder|Caveat:|\[SYSTEM NOTIFICATION|<task-notification"
    r"|The user (stepped away|sent a new message)|Recap in under"
    r"|This is how Claude Code surfaces",
    re.I,
)

SYSTEM_PROMPT = ("너는 정훈이다. 1인 창업자, forget(로컬 AI 기억 제품)을 만든다. "
                 "아래는 네 에이전트의 최신 보고다. 정훈으로서 다음 메시지를 써라 — "
                 "짧고 직설적으로, 실제 채팅처럼.")


def _post(url: str, payload: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def twin_say(ctx: str) -> str:
    # 기본 = 훈련과 동일한 시스템 프롬프트(분포 일치가 쌍둥이에게 공정).
    # TWIN_SYSTEM 환경변수는 널 대조용 — 각인 없는 베이스에 길이 지시만 주고
    # 게이트가 목소리를 재는지(베이스 낙제) 길이만 재는지(베이스도 통과) 가른다.
    system = os.environ.get("TWIN_SYSTEM", TRAIN_SYSTEM_PROMPT)
    body = _post(TWIN_URL, {
        "model": TWIN_MODEL, "temperature": 0.7, "max_tokens": 150,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": ctx[-1600:]}],
    })
    return str((body.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()


def judge(ctx: str, a: str, b: str) -> str:
    prompt = (
        "다음은 AI 에이전트의 보고(컨텍스트)와, 그에 대한 답장 후보 A/B다.\n"
        "하나는 실제 사람(정훈, 1인 창업자)이 쓴 것이고 하나는 그를 흉내낸 AI다.\n"
        "실제 사람이 쓴 쪽을 골라라. 반드시 'A' 또는 'B' 한 글자로만 답하라.\n\n"
        f"[컨텍스트]\n{ctx[-1200:]}\n\n[A]\n{a}\n\n[B]\n{b}\n\n답:"
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


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content
                         if isinstance(p, dict) and p.get("type") == "text")
    return ""


HOLDOUT = Path.home() / ".forget/twin/twin_holdout.json"
# twin_v1 훈련 스크립트(train_twin_v0.py)가 훈련에서 제외한 시간 꼬리 60쌍 —
# 격리가 구성적으로 보장된다(rows[-60:], 훈련 미접촉). 4090 원본의 사본.
TRAIN_SYSTEM_PROMPT = "너는 정훈이다. 아래는 어시스턴트의 보고다. 정훈으로서 반응하라."


def load_holdout_pairs() -> list[dict]:
    # CONTAM을 실배선 (2026-08-14 감사 결함 ①): 스트림 경로용으로 짜였다가
    # 홀드아웃 경로 전환 때 호출이 누락돼 죽은 코드였다 — 홀드아웃 60쌍 중
    # 4건(중단 마커·영어 브리프·SSH 설정)이 그대로 통과한 원인.
    items = json.loads(HOLDOUT.read_text())
    return [{"ctx": it["context"], "actual": it["response"], "cls": it.get("cls", "")}
            for it in items
            if it.get("context") and it.get("response")
            and not CONTAM.search(str(it["response"])[:300])]


def main() -> None:
    rng = random.Random(42)
    pool = load_holdout_pairs()
    rng.shuffle(pool)
    pool = pool[:N_PAIRS]
    print(f"쌍 재료 {len(pool)}개 (twin_holdout.json — 훈련 미접촉 시간 꼬리)", file=sys.stderr)

    correct = 0
    judged = 0
    OUT.write_text("")
    with OUT.open("a") as fh:
        for i, item in enumerate(pool):
            try:
                fake = twin_say(item["ctx"])
            except Exception as exc:
                print(f"[skip] twin 생성 실패: {exc}", file=sys.stderr)
                continue
            if not fake:
                continue
            real, fake = item["actual"][:CAP], fake[:CAP]
            real_is_a = rng.random() < 0.5
            a, b = (real, fake) if real_is_a else (fake, real)
            try:
                pick = judge(item["ctx"], a, b)
            except Exception as exc:
                print(f"[skip] 판별 실패: {exc}", file=sys.stderr)
                continue
            if pick == "?":
                continue
            hit = (pick == "A") == real_is_a
            correct += 1 if hit else 0
            judged += 1
            fh.write(json.dumps({
                "i": i, "real_is_a": real_is_a, "pick": pick, "judge_correct": hit,
                "real": real, "twin": fake, "ctx_tail": item["ctx"][-300:],
            }, ensure_ascii=False) + "\n")
            if judged % 10 == 0:
                print(f"  {judged}쌍: 구별률 {correct/judged:.3f}", file=sys.stderr)

    if judged == 0:
        sys.exit("판정 쌍 0 — 엔진 상태 확인")
    rate = correct / judged
    lo, hi = wilson(correct, judged)
    if judged < 40:
        verdict = "표본 미달 — 판정 유보"
    elif rate <= 0.65:
        verdict = "게이트 통과 (승격 후보 — 사람 검수로)"
    elif rate < 0.80:
        verdict = "중간 (목소리 근접, 승격 보류)"
    else:
        verdict = "낙제 (구별 쉬움 — 각인 부족)"
    print(json.dumps({
        "n": judged, "discrimination_rate": round(rate, 4),
        "wilson_95": [lo, hi], "verdict": verdict,
        "twin": f"{TWIN_MODEL} (vllm LoRA)", "judge": JUDGE_MODEL,
        "cap_chars": CAP, "out": str(OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
