#!/usr/bin/env python3
"""verdict 재료 확장 v1 — P36(R̂ 크럭스, 마감 2026-09-10)의 선행 재료.

v0(42건, 커밋 4c0fe9a) 위에 누적한다. 표적 = "판단의 순간" — 명제와
그 명제에 대한 정훈/원장의 평결 쌍.

소스 4종:
  A. devloop 원장 — predictions.md의 예측 블록별 판정 문면 (성립/반증/유보)
  B. frictions/observations — 관측 처분 문면 (종결/존속/회부)
  C. 기억 장부 — trust.kind=action_report 중 verified/superseded 전이
     (= 주장이 사후 참/거짓으로 판명된 쌍)
  D. 프록시 스트림 — 정훈의 교정/승인/기각 발화와 그 직전 어시스턴트 명제

규율 (러닝북 승계):
- 중복 제거: hashlib 결정론 해시 (내장 hash() 금지)
- 시간 컷오프: 각 항목에 ts 기록 — 홀드아웃은 시간 분할로만
- 무덮어쓰기: 산출물 존재 시 거부 (VERDICT_FORCE=1로만 해제)
- 라벨 분포를 매니페스트에 등재 (다수 클래스 널 — 격언 이행)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent
VERSION = os.environ.get("VERDICT_VERSION", "v1")
OUT = OUT_DIR / f"verdict_dataset_{VERSION}.jsonl"
MANIFEST = OUT_DIR / f"verdict_dataset_{VERSION}.manifest.json"
SEED = OUT_DIR / "verdict_dataset_v0.jsonl"
PRED = ROOT / "research/devloop/predictions.md"
FRIC = ROOT / "research/devloop/frictions.md"
STREAM_DIR = Path.home() / ".forget/proxy/stream"
# 최대 광맥: 로컬 트랜스크립트 — 프록시 개통(8/12) 이전의 전 이력.
TRANSCRIPT_DIR = Path.home() / ".claude/projects"

VERDICT_WORDS = re.compile(r"(반증|성립|지지|기각|유보|무판정|종결|존속)")
# 정훈의 판단 발화 — 교정/승인/기각의 표층 신호
JUDGE_HEAD = re.compile(
    r"^(아니|아냐|안 ?돼|틀렸|잘못|하지 ?마|그게 아니|말고|어휴|아씨|음\.\.|흠"
    r"|응|넵|좋아|좋다|오케이|ok|ㄱㄱ|가자|진행|그래|맞아|고마워|받았|확인)",
    re.I,
)


def _key(*parts: str) -> str:
    return hashlib.md5("|".join(parts).encode("utf-8", "ignore")).hexdigest()


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content
                         if isinstance(p, dict) and p.get("type") == "text")
    return ""


def mine_predictions() -> list[dict]:
    """A. 예측 원장 — '## P<N> — <명제>' 블록에서 판정 문면 추출."""
    if not PRED.exists():
        return []
    out = []
    blocks = re.split(r"\n## ", PRED.read_text())
    for b in blocks:
        head = b.split("\n", 1)[0].strip()
        if not head.startswith("P"):
            continue
        body = b
        for m in re.finditer(r"^\s*[-*]?\s*\*\*?\(?([a-e])\)?[^*\n]{0,60}\*\*?(.{0,400})", body, re.M | re.S):
            frag = m.group(2)
            v = VERDICT_WORDS.search(frag)
            if not v:
                continue
            out.append({"src": f"devloop:{head.split()[0]}", "kind": "outcome",
                        "proposition": f"{head} — 항목 ({m.group(1)})",
                        "verdict": v.group(1),
                        "verdict_text": re.sub(r"\s+", " ", frag).strip()[:400],
                        "ts": ""})
    return out


def mine_frictions() -> list[dict]:
    """B. 마찰 원장 — 관측 처분 문단."""
    if not FRIC.exists():
        return []
    out = []
    text = FRIC.read_text()
    for m in re.finditer(r"관측 (\d+)([^\n]{0,120})\n(.{0,600})", text, re.S):
        frag = m.group(3)
        v = VERDICT_WORDS.search(frag)
        if not v:
            continue
        out.append({"src": f"devloop:관측{m.group(1)}", "kind": "disposition",
                    "proposition": f"관측 {m.group(1)}{m.group(2)}".strip()[:300],
                    "verdict": v.group(1),
                    "verdict_text": re.sub(r"\s+", " ", frag).strip()[:400],
                    "ts": ""})
    return out


def mine_ledger() -> list[dict]:
    """C. 기억 장부 — action_report의 사후 검증 전이."""
    os.environ.setdefault("MEM1_DB_PATH", str(Path.home() / ".forget/forget.sqlite3"))
    try:
        import sqlite3
        db = sqlite3.connect(os.environ["MEM1_DB_PATH"])
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT memory, metadata, created_at FROM memories WHERE deleted=0 "
            "AND (metadata LIKE '%verified_at%' OR metadata LIKE '%superseded_by%') LIMIT 400"
        ).fetchall()
    except Exception as exc:
        print(f"[warn] 장부 채굴 실패: {exc}", file=sys.stderr)
        return []
    out = []
    for r in rows:
        try:
            md = json.loads(r["metadata"] or "{}")
        except json.JSONDecodeError:
            md = {}
        verdict = "성립" if md.get("verified_at") else "반증"
        ev = md.get("verified_evidence") or md.get("supersede_reason") or ""
        out.append({"src": "ledger", "kind": "verdict",
                    "proposition": str(r["memory"])[:300],
                    "verdict": verdict, "verdict_text": str(ev)[:400],
                    "ts": str(r["created_at"] or "")})
    return out


def mine_stream() -> list[dict]:
    """D. 프록시 스트림 — 정훈의 판단 발화 + 직전 어시스턴트 명제."""
    out = []
    for f in sorted(STREAM_DIR.glob("*.jsonl")):
        for line in f.open():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            msgs = row.get("request_messages") or []
            li = max((i for i, m in enumerate(msgs) if m.get("role") == "user"), default=-1)
            if li < 0:
                continue
            u = _text(msgs[li].get("content")).strip()
            u = re.split(r"\n\[forget|\n<system-reminder|\nSessionStart:|<local-command", u)[0].strip()
            if not u or len(u) < 4 or len(u) > 400 or not JUDGE_HEAD.match(u):
                continue
            prop = ""
            for m in reversed(msgs[:li]):
                if m.get("role") == "assistant":
                    t = _text(m.get("content")).strip()
                    if t:
                        prop = t[-600:]
                        break
            if not prop:
                continue
            out.append({"src": "stream", "kind": "judgment",
                        "proposition": prop, "verdict": "판단",
                        "verdict_text": u, "ts": str(row.get("ts") or "")})
    return out


def mine_transcripts() -> list[dict]:
    """D2. 로컬 트랜스크립트 — 프록시 이전 전 이력의 판단 순간."""
    out = []
    for f in TRANSCRIPT_DIR.glob("*/*.jsonl"):
        last_asst = ""
        try:
            for line in f.open():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                typ = row.get("type")
                msg = row.get("message") or {}
                if typ == "assistant":
                    t = _text(msg.get("content")).strip()
                    if t:
                        last_asst = t[-600:]
                    continue
                if typ != "user":
                    continue
                u = _text(msg.get("content")).strip()
                u = re.split(r"\n\[forget|\n<system-reminder|\nSessionStart:|<local-command", u)[0].strip()
                if not u or len(u) < 4 or len(u) > 400 or u.startswith("[{"):
                    continue
                if not JUDGE_HEAD.match(u) or not last_asst:
                    continue
                out.append({"src": "transcript", "kind": "judgment",
                            "proposition": last_asst, "verdict": "판단",
                            "verdict_text": u, "ts": str(row.get("timestamp") or "")})
        except OSError:
            continue
    return out


def main() -> None:
    if OUT.exists() and os.environ.get("VERDICT_FORCE") != "1":
        sys.exit(f"산출물 존재 — 덮지 않는다: {OUT.name} (해제: VERDICT_FORCE=1)")
    items: list[dict] = []
    if SEED.exists():
        items += [json.loads(l) for l in SEED.open()]
    seed_n = len(items)
    src_counts = Counter()
    for name, fn in (("predictions", mine_predictions), ("frictions", mine_frictions),
                     ("ledger", mine_ledger), ("stream", mine_stream), ("transcripts", mine_transcripts)):
        got = fn()
        src_counts[name] = len(got)
        items += got
    seen, uniq = set(), []
    for it in items:
        k = _key(str(it.get("proposition", ""))[:200], str(it.get("verdict_text", ""))[:120])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)
    with OUT.open("w") as fh:
        for it in uniq:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    labels = Counter(it.get("verdict") for it in uniq)
    manifest = {
        "version": VERSION, "total": len(uniq), "seed_v0": seed_n,
        "mined_by_source": dict(src_counts),
        "label_dist": dict(labels),
        "majority_null": round(max(labels.values()) / max(1, len(uniq)), 4),
        "note": "홀드아웃은 시간 분할로만 (ts 기준). 무작위 분할 금지.",
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
