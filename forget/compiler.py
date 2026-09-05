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
# P-C-3 (야전 정독 «두 번 교정되면 규칙화»): 교정-마커 군집은 저문턱 —
# 교정의 비용이 반복의 비용보다 크다. 검출만(제안 큐행), 집행 없음.
CORRECTION_MIN_REPEATS = 2
CORRECTION_MIN_DAYS = 2
_CORRECTION_RE = None  # 지연 초기화 (아래 detect_clusters에서)
LLM_URL = "http://127.0.0.1:18812/v1/chat/completions"
LLM_TIMEOUT = 90

# 결정론 1차 분류 — 확실한 것만. 나머지는 LLM 게이트로.
_CAPTURE_RE = re.compile(r"^세션 캡처 \(|session capture", re.I)
_JOURNAL_RE = re.compile(r"^\[devloop\]|사이클 \d+|^\[일일 응고")

_GATE_PROMPT = """You classify a cluster of near-duplicate memory rows into ONE long-term form.

Forms:
- rule: a standing behavioral discipline/constraint the agent should always follow (e.g. "always compare full dates")
- fact: a stable statement about the world/project that should exist once with an evidence count (e.g. "issue #22 is verified")
- stale-state: repeated snapshots of a TIME-VARYING status — counts, sizes, "X is empty", "currently N rows", "server running (pid N)". Only the newest snapshot matters; older ones are stale. If the samples state the same kind of measurement with drifting numbers/dates, it is stale-state, not fact.
- procedure: a repeated multi-step how-to that belongs in a script/checklist
- journal: episodic work log entries that merely share structure; contents differ per day — must be preserved as-is
- other: none of the above

Cluster samples (repeated {n} times across {days} days, ordered by centrality — the first is the most representative):
{samples}

Reply with EXACTLY one word: rule, fact, stale-state, procedure, journal, or other."""


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


def _is_correction(text: str) -> bool:
    global _CORRECTION_RE
    if _CORRECTION_RE is None:
        _CORRECTION_RE = re.compile(r"정정|자기\s*교정|사고\b|자백|틀렸|오진|잘못\s*(?:알|읽|판단)")
    return bool(_CORRECTION_RE.search(text or ""))


def detect_clusters(items: list[dict], X: Any) -> list[list[int]]:
    """탐욕 군집 — 2-패스 (P-C-3 수정판: 1차 시도가 탐욕 순서를 흔들어
    기존 군집을 변형시킴 — stale 3→2 실측. 교정 패스는 본 패스의 잔여에서만
    돌아 기존 결과를 비트 단위로 보존한다)."""
    import numpy as np

    S = (X @ X.T).astype(np.float32)
    np.fill_diagonal(S, 0)
    visited: set[int] = set()
    clusters: list[list[int]] = []
    order = np.argsort(-(S > SIM_THRESHOLD).sum(axis=1))
    # 1패스: 종전과 동일 (4회·3일)
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
    # 2패스 (P-C-3): 잔여 중 교정-마커 과반 군집만 저문턱(2회·2일)
    for i in order:
        if int(i) in visited or not _is_correction(items[int(i)]["text"]):
            continue
        nb = {int(j) for j in np.where(S[i] > SIM_THRESHOLD)[0]} - visited
        cluster = sorted({int(i)} | nb)
        if len(cluster) < CORRECTION_MIN_REPEATS:
            continue
        if sum(_is_correction(items[j]["text"]) for j in cluster) * 2 <= len(cluster):
            continue
        days = {items[j]["day"] for j in cluster}
        if len(days) >= CORRECTION_MIN_DAYS:
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
        # "stale"을 먼저 본다 — "stale-state"/"stale_state"/"stale" 변주 흡수.
        if "stale" in text:
            return "stale-state"
        for form in ("rule", "fact", "procedure", "journal", "other"):
            if form in text:
                return form
    except Exception:
        pass
    return "other"  # 게이트 불가 시 보수적 — 컴파일 안 함


def classify_cluster(items: list[dict], cluster: list[int], X: Any = None) -> dict[str, Any]:
    days = sorted({items[j]["day"] for j in cluster})
    # P-C-1b(①): 대표 표본 = 군집 중심성 순 — 혼합 군집의 변두리 표본이
    # 게이트를 other로 도피시키던 과보수(P-C-1 감사: fact 놓침 전건)의 교정.
    order = list(cluster)
    if X is not None and len(cluster) >= 2:
        sub = X[cluster] @ X[cluster].T
        centrality = sub.mean(axis=1)
        order = [cluster[k] for k in centrality.argsort()[::-1]]
    texts = [items[j]["text"] for j in order]
    head = texts[0]
    # P-C-1c 트랙 라우팅 (§4.8): 군집 과반이 개인 층 밖(app_id 보유)이면
    # 타 트랙 저널 — 불가침. 의미 판단이 필요 없는 자리에 27B를 세워두고
    # 오답을 세던 것이 P-C-1b 엄격 75%의 몸통(13/15)이었다.
    personal = sum(1 for j in cluster if not items[j].get("app_id"))
    if _CAPTURE_RE.search(head) or sum(bool(_CAPTURE_RE.search(t)) for t in texts[:5]) >= 3:
        form, via = "capture-pointer", "deterministic"
    elif personal * 2 < len(cluster):
        form, via = "journal", "deterministic-track"
    elif _JOURNAL_RE.search(head) or sum(bool(_JOURNAL_RE.search(t)) for t in texts[:5]) >= 3:
        form, via = "journal", "deterministic"
    else:
        form, via = _llm_gate(texts, len(cluster), len(days)), "llm-gate"
    compilable = form in ("rule", "fact", "procedure", "stale-state")
    return {
        "size": len(cluster),
        "days": len(days),
        "span": f"{days[0]}~{days[-1]}",
        "form": form,
        "via": via,
        "compilable": compilable,
        # 강등 대상 = 정본 1행(최신)을 뺀 나머지 — rule/fact/stale-state
        # (stale-state는 정의상 최신만 정본 — §4.4 발견의 성문화)
        "demote_count": (len(cluster) - 1) if form in ("rule", "fact", "stale-state") else 0,
        "canonical": max(cluster, key=lambda j: items[j]["day"]),
        "representative": head[:150],
        "member_ids": [items[j]["id"] for j in cluster],
    }


def dry_run(db_path: str, user_id: str) -> dict[str, Any]:
    items, X = load_vectors(db_path, user_id)
    clusters = detect_clusters(items, X)
    report = [classify_cluster(items, c, X) for c in clusters]
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


# ── 집행 모드 v0 (P-C-1d 판정 §4.11 — 가역 supersede 강등) ────────────────
# 실DB 적용은 정훈 게이트 뒤. 가역성이 계약: 전 처치를 원장(jsonl)에 기록하고
# revert_compile이 역재생으로 전량 복원한다. 삭제·텍스트 변형 없음 — 기존
# supersede 침강 경로(metadata.superseded_by/at)와 동일해 회상 경쟁의 억제
# 간선이 그대로 작동한다.

COMPILE_FORMS = ("rule", "fact", "stale-state")


def execute_compile(db_path: str, report: list[dict[str, Any]],
                    ledger_path: str, batch_id: str) -> dict[str, Any]:
    """드라이런 리포트의 컴파일 가능 군집을 강등 집행. 멱등(재실행 무해)."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    demoted, skipped = 0, 0
    entries = []
    try:
        for cluster in report:
            if cluster.get("form") not in COMPILE_FORMS:
                continue
            member_ids = cluster["member_ids"]
            rows = conn.execute(
                "SELECT id, created_at, metadata FROM memories WHERE id IN ({})"
                " AND deleted = 0".format(",".join("?" for _ in member_ids)),
                member_ids).fetchall()
            if len(rows) < 2:
                continue
            canonical_id = max(rows, key=lambda r: str(r["created_at"]))["id"]
            for row in rows:
                if row["id"] == canonical_id:
                    continue
                meta = json.loads(row["metadata"] or "{}")
                if meta.get("superseded_by"):
                    skipped += 1          # 이미 침강 — 재집행 무해(멱등)
                    continue
                prev = {k: meta.get(k) for k in ("superseded_by", "superseded_at", "sank_by")}
                meta.update(superseded_by=canonical_id, superseded_at=now,
                            sank_by=f"compiler:{batch_id}",
                            compiled_form=cluster["form"])
                conn.execute("UPDATE memories SET metadata = ? WHERE id = ?",
                             (json.dumps(meta, ensure_ascii=False), row["id"]))
                entries.append({"batch": batch_id, "demoted": row["id"],
                                "canonical": canonical_id,
                                "form": cluster["form"], "prev": prev, "at": now})
                demoted += 1
        conn.commit()
    finally:
        conn.close()
    with open(ledger_path, "a", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"batch": batch_id, "demoted": demoted, "skipped": skipped,
            "clusters": sum(1 for c in report if c.get("form") in COMPILE_FORMS)}


def revert_compile(db_path: str, ledger_path: str, batch_id: str) -> dict[str, Any]:
    """원장 역재생 — 해당 배치의 강등을 전량 복원 (가역성 계약)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    restored = 0
    try:
        for line in open(ledger_path, encoding="utf-8"):
            entry = json.loads(line)
            if entry.get("batch") != batch_id:
                continue
            row = conn.execute("SELECT metadata FROM memories WHERE id = ?",
                               (entry["demoted"],)).fetchone()
            if row is None:
                continue
            meta = json.loads(row["metadata"] or "{}")
            if meta.get("sank_by") != f"compiler:{batch_id}":
                continue                  # 다른 경로가 손댄 행은 건드리지 않는다
            meta.pop("compiled_form", None)
            for key, value in entry["prev"].items():
                if value is None:
                    meta.pop(key, None)
                else:
                    meta[key] = value
            conn.execute("UPDATE memories SET metadata = ? WHERE id = ?",
                         (json.dumps(meta, ensure_ascii=False), entry["demoted"]))
            restored += 1
        conn.commit()
    finally:
        conn.close()
    return {"batch": batch_id, "restored": restored}


# ── 정기 실행 (응고 주기 편입, 2026-08-29) ────────────────────────────────
# 자동/게이트의 경계가 헌법: **이미 판결된 군집의 재성장만 자동 강등**하고
# (판결 증거 = 과거 compiler 배치가 강등한 멤버의 존재 — 결정론, LLM 불요),
# 신규 군집은 제안 큐로 게이트 대기. 게이트 라벨(27B/승급 모델)은 제안서의
# 자문 정보이지 집행 근거가 아니다 — P-C-1c 교훈(의미 판단이 필요 없는
# 자리에 LLM을 세우지 마라)의 역방향 적용.


def _prior_verdicts(conn: sqlite3.Connection, member_ids: list[str]) -> dict[str, Any] | None:
    """군집 멤버 중 과거 compiler 배치가 강등한 행 → 판결(형태) 회수."""
    rows = conn.execute(
        "SELECT metadata FROM memories WHERE id IN ({})".format(
            ",".join("?" for _ in member_ids)), member_ids).fetchall()
    for row in rows:
        meta = json.loads(row["metadata"] or "{}")
        if str(meta.get("sank_by") or "").startswith("compiler:"):
            return {"form": meta.get("compiled_form") or "fact",
                    "batch": meta["sank_by"]}
    return None


def scheduled_run(db_path: str, user_id: str, ledger_path: str,
                  proposals_path: str, batch_id: str,
                  report: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """야간 정기 실행 — 재성장 자동 강등 + 신규 제안 큐."""
    if report is None:
        report = dry_run(db_path, user_id)["report"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    auto, proposals = [], []
    try:
        for cluster in report:
            verdict = _prior_verdicts(conn, cluster["member_ids"])
            if verdict:
                auto.append({**cluster, "form": verdict["form"],
                             "verdict_source": verdict["batch"]})
            elif cluster.get("form") in COMPILE_FORMS:
                proposals.append({k: cluster[k] for k in
                                  ("form", "via", "size", "days", "span",
                                   "representative", "member_ids")})
    finally:
        conn.close()
    executed = execute_compile(db_path, auto, ledger_path, batch_id) if auto \
        else {"batch": batch_id, "demoted": 0, "skipped": 0, "clusters": 0}
    if proposals:
        with open(proposals_path, "w", encoding="utf-8") as fh:
            json.dump({"batch": batch_id, "proposals": proposals}, fh,
                      ensure_ascii=False, indent=1)
    return {"batch": batch_id, "regrowth_clusters": len(auto),
            "demoted": executed["demoted"], "skipped": executed["skipped"],
            "proposals": len(proposals)}


def _scheduled_main() -> None:
    import argparse
    from datetime import datetime, timezone

    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduled", action="store_true", required=True)
    parser.add_argument("--db", default=_os.path.expanduser("~/.forget/forget.sqlite3"))
    parser.add_argument("--user", default="junghunkim")
    args = parser.parse_args()
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    batch_id = f"nightly-{day}"
    ledger_dir = _os.path.expanduser("~/.forget/compile_ledgers")
    proposals_dir = _os.path.expanduser("~/.forget/compile_proposals")
    _os.makedirs(ledger_dir, exist_ok=True)
    _os.makedirs(proposals_dir, exist_ok=True)
    out = scheduled_run(args.db, args.user,
                        f"{ledger_dir}/{batch_id}.jsonl",
                        f"{proposals_dir}/{batch_id}.json", batch_id)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    _scheduled_main()
