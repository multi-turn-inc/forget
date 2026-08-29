"""사다리 컴파일러 v0 — 반복 감지·형태 분류·드라이런 (헌장: memory-intelligence-design.md).

임무: 원장의 반복 군집을 감지해 알맞은 장기 형태(rule/fact/procedure)로
분류하고, 강등 대상을 산출한다. v0는 **드라이런 전용** — 실DB 변형 없음.
집행 모드는 P-C-1 판정(오분류 ≤15%) 후 별도 구현·정훈 게이트.

설계 계보: 감지=임베딩 군집(헤비안 카운터 공백 실측 — 반복은 패러프레이즈로
온다) · 분류=결정론 1차 + 로컬 27B 게이트(P-PF-2 교훈: 형태 판별은 의미 판단).
"""
from __future__ import annotations

import json
import re
import sqlite3
import urllib.request
from collections import Counter
from typing import Any

from .utils import decode_embedding

SIM_THRESHOLD = 0.80
MIN_REPEATS = 4          # 자신 포함
MIN_DAYS = 3             # 다일 조건 — 한 세션 내 재진술 제외
LLM_URL = "http://127.0.0.1:18812/v1/chat/completions"
LLM_TIMEOUT = 90

# 결정론 1차 분류 — 확실한 것만. 나머지는 LLM 게이트로.
_CAPTURE_RE = re.compile(r"^세션 캡처 \(|session capture", re.I)
_JOURNAL_RE = re.compile(r"^\[devloop\]|사이클 \d+|^\[일일 응고")

_GATE_PROMPT = """You classify a cluster of near-duplicate memory rows into ONE long-term form.

Forms:
- rule: a standing behavioral discipline/constraint the agent should always follow (e.g. "always compare full dates")
- fact: a stable statement about the world/project that should exist once with an evidence count (e.g. "issue #22 is verified")
- procedure: a repeated multi-step how-to that belongs in a script/checklist
- journal: episodic work log entries that merely share structure; contents differ per day — must be preserved as-is
- other: none of the above

Cluster samples (repeated {n} times across {days} days):
{samples}

Reply with EXACTLY one word: rule, fact, procedure, journal, or other."""


def load_vectors(db_path: str, user_id: str) -> tuple[list[dict], Any]:
    import numpy as np

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, memory, embedding, created_at, app_id, agent_id FROM memories"
        " WHERE user_id = ? AND deleted = 0 AND LENGTH(embedding) > 10"
        " AND LENGTH(memory) > 30",
        (user_id,),
    ).fetchall()
    conn.close()
    items, embs = [], []
    for r in rows:
        try:
            e = decode_embedding(r["embedding"])
        except Exception:
            continue
        if e and len(e) > 100:
            items.append({"id": r["id"], "text": r["memory"],
                          "day": str(r["created_at"])[:10],
                          "app_id": r["app_id"], "agent_id": r["agent_id"]})
            embs.append(e)
    dims = Counter(len(e) for e in embs)
    main_dim = dims.most_common(1)[0][0]
    keep = [i for i in range(len(embs)) if len(embs[i]) == main_dim]
    X = np.array([embs[i] for i in keep], dtype=np.float32)
    X = X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
    return [items[i] for i in keep], X


def detect_clusters(items: list[dict], X: Any) -> list[list[int]]:
    """탐욕 군집 — 이웃 많은 씨앗부터, 다일 조건."""
    import numpy as np

    S = (X @ X.T).astype(np.float32)
    np.fill_diagonal(S, 0)
    visited: set[int] = set()
    clusters: list[list[int]] = []
    order = np.argsort(-(S > SIM_THRESHOLD).sum(axis=1))
    for i in order:
        if int(i) in visited:
            continue
        nb = {int(j) for j in np.where(S[i] > SIM_THRESHOLD)[0]} - visited
        if len(nb) >= MIN_REPEATS - 1:
            cluster = sorted({int(i)} | nb)
            days = {items[j]["day"] for j in cluster}
            if len(days) >= MIN_DAYS:
                visited |= set(cluster)
                clusters.append(cluster)
    return clusters


def _llm_gate(samples: list[str], n: int, days: int) -> str:
    body = {
        "model": "local",
        "messages": [{"role": "user", "content": _GATE_PROMPT.format(
            n=n, days=days,
            samples="\n".join(f"- {s[:180]}" for s in samples[:5]))}],
        "max_tokens": 200, "temperature": 0.1,
    }
    req = urllib.request.Request(
        LLM_URL, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    try:
        out = json.loads(urllib.request.urlopen(req, timeout=LLM_TIMEOUT).read())
        text = out["choices"][0]["message"]["content"].strip().lower()
        for form in ("rule", "fact", "procedure", "journal", "other"):
            if form in text:
                return form
    except Exception:
        pass
    return "other"  # 게이트 불가 시 보수적 — 컴파일 안 함


def classify_cluster(items: list[dict], cluster: list[int]) -> dict[str, Any]:
    texts = [items[j]["text"] for j in cluster]
    days = sorted({items[j]["day"] for j in cluster})
    head = texts[0]
    if _CAPTURE_RE.search(head) or sum(bool(_CAPTURE_RE.search(t)) for t in texts[:5]) >= 3:
        form, via = "capture-pointer", "deterministic"
    elif _JOURNAL_RE.search(head) or sum(bool(_JOURNAL_RE.search(t)) for t in texts[:5]) >= 3:
        form, via = "journal", "deterministic"
    else:
        form, via = _llm_gate(texts, len(cluster), len(days)), "llm-gate"
    compilable = form in ("rule", "fact", "procedure")
    return {
        "size": len(cluster),
        "days": len(days),
        "span": f"{days[0]}~{days[-1]}",
        "form": form,
        "via": via,
        "compilable": compilable,
        # 강등 대상 = 정본 1행(최신)을 뺀 나머지 — rule/fact만
        "demote_count": (len(cluster) - 1) if form in ("rule", "fact") else 0,
        "canonical": max(cluster, key=lambda j: items[j]["day"]),
        "representative": head[:150],
        "member_ids": [items[j]["id"] for j in cluster],
    }


def dry_run(db_path: str, user_id: str) -> dict[str, Any]:
    items, X = load_vectors(db_path, user_id)
    clusters = detect_clusters(items, X)
    report = [classify_cluster(items, c) for c in clusters]
    summary = Counter(r["form"] for r in report)
    return {
        "vectors": len(items),
        "clusters": len(clusters),
        "clustered_rows": sum(r["size"] for r in report),
        "forms": dict(summary),
        "compilable_clusters": sum(1 for r in report if r["compilable"]),
        "total_demote": sum(r["demote_count"] for r in report),
        "report": report,
    }


# ── 에코 차단기 (P-C-1b 레인 ②) ───────────────────────────────────────────
# 이미 컴파일된 문면(기상 프롬프트·CLAUDE.md 규율 등)의 일화 에코가 저장
# 경로로 재유입되는 것을 차단한다. 실측 병리: 시각 규율 124행/5일 — 매 기상
# 재저장. 등록부는 ~/.forget/compiled_forms.json, 판정은 임베딩 코사인
# (지시문 0 — 계산만). 게이트는 gate_log에 남겨 관측 가능성 유지.

import os as _os
import time as _time
from pathlib import Path as _Path

COMPILED_FORMS_PATH = _Path.home() / ".forget" / "compiled_forms.json"
# 0.62: 패러프레이즈 에코 실측 0.676 vs 무관 문장 0.121 — 갭이 넓어 낮은
# 문턱이 안전. 위양성은 gate_log로 상시 관측(스킵은 로그에 남는다).
ECHO_SIM_THRESHOLD = 0.62

_forms_cache: dict[str, Any] = {"mtime": None, "forms": [], "vectors": None}


def load_compiled_forms(project_id: str = "proj_local") -> list[dict[str, Any]]:
    """등록부 로드 + 임베딩 캐시 (mtime 기반)."""
    try:
        mtime = COMPILED_FORMS_PATH.stat().st_mtime
    except FileNotFoundError:
        _forms_cache.update(mtime=None, forms=[], vectors=None)
        return []
    if _forms_cache["mtime"] == mtime and _forms_cache["vectors"] is not None:
        return _forms_cache["forms"]
    try:
        forms = json.loads(COMPILED_FORMS_PATH.read_text(encoding="utf-8"))
        assert isinstance(forms, list)
    except Exception:
        return _forms_cache["forms"]
    import numpy as np
    from .store import embed_text
    vectors = []
    for form in forms:
        vec = embed_text(str(form.get("text") or ""), project_id=project_id)
        vectors.append(vec if vec else [])
    dims = {len(v) for v in vectors if v}
    matrix = None
    if len(dims) == 1:
        matrix = np.array([v for v in vectors if v], dtype=np.float32)
        matrix = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    _forms_cache.update(mtime=mtime, forms=forms, vectors=matrix)
    return forms


def check_echo(embedding: list[float] | None, project_id: str = "proj_local") -> dict[str, Any] | None:
    """신규 기억 임베딩이 컴파일된 문면의 에코인가 — (form, sim) 또는 None."""
    if not embedding:
        return None
    forms = load_compiled_forms(project_id)
    matrix = _forms_cache.get("vectors")
    if matrix is None or not forms or matrix.shape[1] != len(embedding):
        return None
    import numpy as np
    q = np.array(embedding, dtype=np.float32)
    q = q / (np.linalg.norm(q) + 1e-9)
    sims = matrix @ q
    best = int(np.argmax(sims))
    if float(sims[best]) >= ECHO_SIM_THRESHOLD:
        return {"form": forms[best], "sim": round(float(sims[best]), 4)}
    return None
