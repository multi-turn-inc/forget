#!/usr/bin/env python3
"""섀도 데몬 v0 — 라이브 "되기" 계기 (becoming-junghun.md §1).

원리: 프록시 스트림의 모든 요청에는 정훈의 최신 메시지가 들어 있다. 각 새
정훈-발화에 대해 — 그 직전 컨텍스트(어시스턴트 마지막 보고)만으로 쌍둥이가
"정훈은 뭐라 할 것인가"를 사후 예측하고, 실발화와 채점해 곡선에 쌓는다.

v0 설계 결정:
- 사후(retro) 채점 — 실시간 선예측은 서빙 상주가 필요해 v1로. 사후라도
  시간축 홀드아웃은 동일하게 성립한다 (예측 시점에 실발화를 컨텍스트에서 숨김).
- 채점 2계기: ①임베딩 유사도 (로컬 e5) ②방향 일치 — 교정/승인/지시 3분류
  (거친 판단 축 — Park식 정규화의 v0 대용).
- 엔진 라우터 자리: TWIN_URL (기본 = Spark 27B ollama; 어댑터 서빙 붙으면 교체).
- 상태: ~/.forget/twin/shadow_scores.jsonl (append-only 곡선),
        ~/.forget/twin/shadow_state.json (마지막 처리 위치).
실행: launchd 주기(예: 17분) 또는 수동. GPU 불요 (원격 생성 + 로컬 임베딩).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

STREAM_DIR = Path.home() / ".forget/proxy/stream"
TWIN_DIR = Path.home() / ".forget/twin"
SCORES = TWIN_DIR / "shadow_scores.jsonl"
TWIN_URL = os.environ.get("TWIN_URL", "http://127.0.0.1:11435/api/chat")  # Spark 터널 기본
TWIN_MODEL = os.environ.get("TWIN_MODEL", "qwen3.6:27b")
TWIN_VARIANT = os.environ.get("TWIN_VARIANT", f"prompt-only/{TWIN_MODEL}")
# 변형별 상태 분리 — 같은 턴을 서로 다른 변형이 각각 채점해야 통일 곡선에서
# 변형 간 대조가 성립한다. 기본 변형은 기존 파일명을 유지(하위호환).
_VARIANT_SLUG = "".join(c if c.isalnum() else "-" for c in TWIN_VARIANT)
STATE = TWIN_DIR / ("shadow_state.json" if "TWIN_VARIANT" not in os.environ
                    else f"shadow_state.{_VARIANT_SLUG}.json")
EMB_URL = os.environ.get("EMB_URL", "http://127.0.0.1:11434/api/embed")   # 로컬 ollama
EMB_MODEL = os.environ.get("EMB_MODEL", "nomic-embed-text")
MAX_PER_RUN = int(os.environ.get("SHADOW_MAX", "12"))

NOISE = re.compile(r"\[forget 회상|\[forget 캡슐|<command-|<local-command|<bash-input|<system-reminder|Caveat:|\[SYSTEM NOTIFICATION|<task-notification|The user (stepped away|sent a new message)|Recap in under|This is how Claude Code surfaces|\[SUGGESTION MODE|Suggest what the user might naturally type", re.I)
CORRECT = re.compile(r"^(아니|아냐|안 ?돼|틀렸|잘못|하지 ?마|왜 |그게 아니|말고|어휴|아씨)", re.U)
APPROVE = re.compile(r"^(응|넵|네[\s.!]|좋아|좋다|오케이|ok|ㄱㄱ|가자|진행|그래|맞아|고마워)", re.I)


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content
                         if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _clean_user(t: str) -> str:
    t = re.split(r"\n\[forget|\n<system-reminder|\nSessionStart:", t)[0]
    return t.strip()


def direction(t: str) -> str:
    head = t.strip()[:40]
    if CORRECT.match(head):
        return "correct"
    if APPROVE.match(head):
        return "approve"
    return "direct"


def _post(url: str, payload: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


SYSTEM_PROMPT = "너는 정훈이다. 1인 창업자, forget(로컬 AI 기억 제품)을 만든다. 아래는 네 에이전트의 최신 보고다. 정훈으로서 다음 메시지를 써라 — 짧고 직설적으로, 실제 채팅처럼."


def twin_predict(context: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context[-1600:]},
    ]
    if "/v1/chat/completions" in TWIN_URL:
        # OpenAI-호환 서빙 (vllm LoRA 모듈 등) — 어댑터 변형은 이 경로로 곡선에 오른다.
        body = _post(TWIN_URL, {
            "model": TWIN_MODEL, "messages": messages,
            "temperature": 0.7, "max_tokens": 150,
            # Qwen3.5 하이브리드 thinking 차단 — ollama 경로의 think:false와 동치
            "chat_template_kwargs": {"enable_thinking": False},
        })
        choices = body.get("choices") or [{}]
        return str((choices[0].get("message") or {}).get("content") or "").strip()
    body = _post(TWIN_URL, {
        "model": TWIN_MODEL, "stream": False, "think": False, "keep_alive": "3h",
        "messages": messages,
        "options": {"temperature": 0.7, "num_predict": 150},
    })
    return str((body.get("message") or {}).get("content") or "").strip()


def embed_sim(a: str, b: str) -> float:
    try:
        r = _post(EMB_URL, {"model": EMB_MODEL, "input": [a[:800], b[:800]]}, timeout=30)
        va, vb = r["embeddings"][0], r["embeddings"][1]
        dot = sum(x * y for x, y in zip(va, vb))
        na = sum(x * x for x in va) ** 0.5
        nb = sum(x * x for x in vb) ** 0.5
        return dot / max(1e-9, na * nb)
    except Exception:
        return -1.0


def iter_turns():
    """스트림에서 (직전 어시스턴트 텍스트, 정훈 실발화, ts)를 시간순으로."""
    files = sorted(STREAM_DIR.glob("*.jsonl"))
    for f in files:
        for line in f.open():
            try:
                row = json.loads(line)
            except Exception:
                continue
            msgs = row.get("request_messages") or []
            # 마지막 user 메시지 = 이 요청을 촉발한 정훈 발화(또는 도구 결과)
            last_user_i = max((i for i, m in enumerate(msgs) if m.get("role") == "user"), default=-1)
            if last_user_i < 0:
                continue
            user_t = _clean_user(_text(msgs[last_user_i].get("content")))
            if not user_t or len(user_t) < 4 or NOISE.search(user_t[:200]):
                continue
            # 직전 assistant 텍스트 (예측 컨텍스트)
            ctx = ""
            for m in reversed(msgs[:last_user_i]):
                if m.get("role") == "assistant":
                    ctx = _text(m.get("content"))
                    if ctx.strip():
                        break
            if not ctx.strip():
                continue
            yield {"key": f"{f.name}:{row.get('ts','')}:{hash(user_t[:80]) & 0xffffffff:08x}",
                   "ctx": ctx, "actual": user_t[:800], "ts": row.get("ts", "")}


def main() -> None:
    TWIN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        done = set(json.loads(STATE.read_text()).get("done", []))
    except Exception:
        done = set()

    scored = 0
    for turn in iter_turns():
        if turn["key"] in done:
            continue
        if scored >= MAX_PER_RUN:
            break
        try:
            pred = twin_predict(turn["ctx"])
        except Exception as exc:
            print(f"[skip] twin 생성 실패: {exc}", file=sys.stderr)
            break  # 엔진 다운 — 다음 주기에
        if not pred:
            done.add(turn["key"])
            continue
        sim = embed_sim(pred, turn["actual"])
        d_pred, d_act = direction(pred), direction(turn["actual"])
        row = {"ts": turn["ts"], "scored_at": time.strftime("%F %T"),
               "sim": round(sim, 4), "dir_pred": d_pred, "dir_actual": d_act,
               "dir_match": d_pred == d_act,
               "pred_head": pred[:160], "actual_head": turn["actual"][:160],
               "ctx": turn["ctx"][-1600:], "actual": turn["actual"],
               "engine": TWIN_MODEL,
               # 통일 계기(정훈-예측기 v0): 모든 쌍둥이 버전이 같은 곡선 위에서
               # 비교되도록 변형 식별자를 행마다 남긴다. 어댑터/기억 결합이
               # 붙으면 TWIN_VARIANT로 구별한다 (예: adapter_v2+mem).
               "variant": TWIN_VARIANT}
        with SCORES.open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        done.add(turn["key"])
        scored += 1

    STATE.write_text(json.dumps({"done": sorted(done)[-5000:], "updated": time.strftime("%F %T")}))
    # 요약 한 줄 (원장 겸 사람용)
    if SCORES.exists():
        rows = [json.loads(l) for l in SCORES.open()]
        sims = [r["sim"] for r in rows if r.get("sim", -1) >= 0]
        dirm = [r["dir_match"] for r in rows if "dir_match" in r]
        print(f"섀도 곡선: 누적 {len(rows)}점 | 이번 {scored}점 | "
              f"유사도 평균 {sum(sims)/max(1,len(sims)):.3f} | 방향 일치 {sum(dirm)}/{len(dirm)}")


if __name__ == "__main__":
    main()
