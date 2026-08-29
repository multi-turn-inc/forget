"""상황 좌석 (P-M-8, §19) — 질의가 가리키는 활성 트랙을 인식해 상태 1줄을 회상.

실전 사고(2026-08-30)의 처방: «벤치마크로 증명할 수 있으려나»가 LME-V2
제출-대기 사실을 못 데려왔다. 부검이 정한 구조:
- 후보화 = 결정론 하이브리드 (코사인 + 외래어/자구 다리) — 임베딩 단독은
  실측 오답(전용 풀에서도 top-1이 엉뚱한 트랙).
- 판독 = 로컬 LLM 1콜 — 25줄 목록에서 «가리키는 트랙»을 고르는 것은
  의미 판단의 일 (P-PF-2 교훈). 판독기가 none이라면 침묵.
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

LLM_URL = "http://127.0.0.1:18812/v1/chat/completions"
LLM_TIMEOUT = 12
MAX_TRACKS = 40
SHORTLIST = 12
# 발화 문턱: 부검 실측 — 표본의 bench-loop 코사인 0.411, 다리 적중.
# 코사인 단독이면 0.40, 자구 다리 적중이면 0.32까지 완화.
COS_GATE = 0.40
COS_GATE_BRIDGED = 0.32

# 외래어 다리: 한글 외래어 ↔ 라틴 어간 (결정론 — 표본 사고의 직접 원인 어휘부터.
# 항목 추가는 사고가 정한다: 미스 표본 없이 사전을 불리지 않는다 — 법칙 B.)
_LOANWORDS = {
    # 표본 사고(2026-08-30)가 정한 항목만. "메모리"는 넣지 않는다 — 이
    # 프로젝트에선 전 트랙이 memory를 품어 다리가 전역에 걸리는 것을 실측
    # (다리의 자격 = 판별력이지 번역이 아니다).
    "벤치마크": ("bench", "benchmark"),
    "벤치": ("bench",),
    "리더보드": ("leaderboard", "lme"),
}

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.\-]+|[가-힣]{2,}")

_PROMPT = """The user is working on a project with these active tracks (id: state):

{tracks}

User's question: "{query}"

If the question is asking about — or would need the state of — exactly one of these tracks, reply with ONLY that track id. If none clearly applies, reply ONLY: none."""


def _bridge_tokens(query: str) -> set[str]:
    out: set[str] = set()
    for token in _TOKEN_RE.findall(query):
        if token in _LOANWORDS:
            out.update(_LOANWORDS[token])
        elif re.fullmatch(r"[A-Za-z][A-Za-z0-9_.\-]+", token):
            out.add(token.lower())
    return out


def _lexical_bridge(query: str, task_id: str, summary: str) -> bool:
    tokens = _bridge_tokens(query)
    if not tokens:
        return False
    haystack = f"{task_id} {summary}".lower()
    return any(t in haystack for t in tokens)


def _llm_pick(query: str, shortlist: list[dict[str, Any]]) -> str | None:
    tracks = "\n".join(f"- {t['task_id']}: {t['line'][:110]}" for t in shortlist)
    body = {
        "model": "local",
        "messages": [{"role": "user", "content": _PROMPT.format(tracks=tracks, query=query[:250])}],
        # thinking 억제 필수 (2026-08-30 실측): 켜두면 27B가 상한을 사유로
        # 태우고 빈 발화로 종료 — 훅 지연 예산도 초과. 억제 시 ~1s.
        "max_tokens": 300, "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        LLM_URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    try:
        out = json.loads(urllib.request.urlopen(req, timeout=LLM_TIMEOUT).read())
        text = out["choices"][0]["message"]["content"].strip().lower()
    except Exception:
        return None
    if "none" in text[:12]:
        return None
    for t in shortlist:
        if t["task_id"].lower() in text:
            return t["task_id"]
    return None


def situation_recall(query: str, project_id: str) -> dict[str, Any] | None:
    """질의가 가리키는 활성 트랙 1건 — {task_id, line, via} 또는 None."""
    from .memory_engine import cosine_similarity
    from .store import embed_text, get_task_state

    query = (query or "").strip()
    if len(query) < 8:
        return None
    try:
        tasks = (get_task_state({"limit": MAX_TRACKS}, project_id) or {}).get("results") or []
    except Exception:
        return None
    if not tasks:
        return None
    qv = embed_text(query, project_id=project_id, role="query")
    cands = []
    for t in tasks:
        task_id = str(t.get("task_id") or "").strip()
        line = str(t.get("current_goal") or t.get("summary") or "").strip()
        if not task_id or not line:
            continue
        try:
            cos = cosine_similarity(qv, embed_text(f"{task_id}: {line}", project_id=project_id))
        except Exception:
            cos = 0.0
        bridged = _lexical_bridge(query, task_id, line)
        gate = COS_GATE_BRIDGED if bridged else COS_GATE
        cands.append({"task_id": task_id, "line": line, "cos": cos,
                      "bridged": bridged, "fires": cos >= gate})
    if not any(c["fires"] for c in cands):
        return None
    # 후보 서열: 다리 적중 우선, 코사인 차순 — 판독기엔 상위 SHORTLIST만.
    cands.sort(key=lambda c: (not c["bridged"], -c["cos"]))
    shortlist = cands[:SHORTLIST]
    picked = _llm_pick(query, shortlist)
    if picked is None:
        return None
    hit = next((c for c in shortlist if c["task_id"] == picked), None)
    if hit is None:
        return None
    return {"task_id": hit["task_id"], "line": hit["line"][:200],
            "via": "bridge+reader" if hit["bridged"] else "cos+reader",
            "cos": round(hit["cos"], 3)}
