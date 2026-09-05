"""앵커 소급 + 다국어 임베딩 전환 — 게이트 집행 (2026-08-23, 정훈 승인).

승인 문면: "임베딩 전환을 해야겠군. 다국어 임베딩 전환을 승인할게."
집행 범위: 게이트 큐에 묶여 있던 그대로 — 앵커 없이 임베딩만 갈면 헐벗은 조각을
새 모델로 다시 박제하는 것이고(단독 효과 미미 실측: 정답 순위 270→245/291),
나중에 앵커를 붙이면 전체 재임베딩을 또 해야 한다. 한 번에 간다.

무엇을 하나 (대상 DB의 생존 기억 전부):
  1. 앵커 소급 — memory_history ADD 행의 input(원문, 생존 기억 100% 커버 실측)에서
     episode_anchor()로 주제문을 유도해 metadata.episode에 기록 (backfilled: true).
     이미 episode가 있는 행(신규 쓰기 경로 산)은 보존한다.
  2. 재임베딩 — sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (768차원,
     fastembed 0.8.0 지원 목록 확인)로, 입력은 결합 규칙 그대로:
     anchor_applies(fact, anchor)면 "앵커 — 사실", 아니면 bare fact.
     런타임 embed_text의 전처리(개행→공백)와 동일하게 맞춘다.
  3. 설정 전환 — projects.settings.embedding_model을 대상 DB에 기록. 이후 그 DB를
     읽는 서버는 질의도 같은 모델로 임베딩한다 (혼합 공간 없음).

## 사전 등록 판정 (사본에서, 실DB 적용 전 — 숫자를 보기 전에 고정)

같은 사본으로 마이그레이션 전/후 평가셋 v1을 돌린다 (스냅샷 차이 오염 없음).
  P-Mig-A (천장): machine_resume 층 천장이 오르면 지지. 전체 천장도 병기.
      전제 확인용 — 이 게이트는 "쓰기 경로+임베딩이 검색 천장의 병목"이라는
      진단 위에 승인됐다.
  P-Mig-B (문면 가드): 생존 기억 100건 표본 — 자기 문면으로 검색 시 rank-1이
      99% 이상 유지. 다국어 전환이 문면 검색을 깎으면 실패 (일화 결합의
      후퇴 금지 가드와 같은 원칙).
  P-Mig-C (θ 재보정): eval_semantic_echo를 새 스택으로 재실행 — 새 θ에서
      v2 재현율이 0.38(영어 인코더 하한)을 넘으면 전환의 실질 이득 확인.
      넘지 못해도 A·B가 통과면 적용은 하되(앵커 이득은 별개) 결과를 병기.
  적용 규칙: A 지지 & B 통과 → 실DB 적용(백업 선행). A 반증이면 중단하고 보고.

읽기: 대상 DB는 MEM1_DB_PATH. 실DB에 직접 걸지 말 것 — 사본 검증 후 별도 실행.
사용: MEM1_DB_PATH=<대상> .venv/bin/python scripts/migrate_embeddings_v2.py [--verify-only]
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
BATCH = 128
DB = os.environ.get("MEM1_DB_PATH", "")


def main() -> None:
    if not DB:
        sys.exit("MEM1_DB_PATH가 필요하다 — 실DB 실수 방지를 위해 기본값을 두지 않는다")
    verify_only = "--verify-only" in sys.argv

    from forget.memory_engine import anchor_applies, episode_anchor, message_content_text
    from forget.utils import decode_embedding, encode_embedding

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # ── 1. 원문 지도: memory_id → ADD input ────────────────────────────────
    source: dict[str, str] = {}
    for row in con.execute(
        "SELECT memory_id, input FROM memory_history WHERE event='ADD' AND input IS NOT NULL"
    ):
        raw = str(row["input"] or "")
        try:
            parsed = json.loads(raw)
        except Exception:
            source[str(row["memory_id"])] = raw
            continue
        if isinstance(parsed, list):
            texts = []
            for msg in parsed:
                content = msg.get("content") if isinstance(msg, dict) else msg
                text = message_content_text(content) if not isinstance(content, str) else content
                if isinstance(text, str) and text.strip():
                    texts.append(text)
            source[str(row["memory_id"])] = "\n".join(texts)
        else:
            source[str(row["memory_id"])] = raw

    rows = con.execute(
        "SELECT id, memory, metadata FROM memories WHERE deleted = 0"
    ).fetchall()
    print(f"생존 기억 {len(rows)} · 원문 커버 {sum(1 for r in rows if str(r['id']) in source)}")

    # ── 2. 앵커 유도 + 임베딩 입력 구성 ────────────────────────────────────
    plans = []      # (id, new_metadata_json | None, embed_input)
    stats = {"anchored": 0, "bound": 0, "kept_existing": 0, "no_source": 0}
    for row in rows:
        mid, fact = str(row["id"]), str(row["memory"] or "")
        meta = json.loads(row["metadata"] or "{}") or {}
        episode = meta.get("episode") or {}
        if episode.get("anchor"):
            stats["kept_existing"] += 1        # 신규 쓰기 경로가 이미 결합함
            anchor = str(episode["anchor"])
        else:
            src = source.get(mid, "")
            anchor = episode_anchor(src) if src else ""
            if not src:
                stats["no_source"] += 1
            if anchor:
                stats["anchored"] += 1
                meta["episode"] = {**episode, "anchor": anchor, "backfilled": True,
                                   "bound": anchor_applies(fact, anchor)}
        bind = anchor if (anchor and anchor_applies(fact, anchor)) else ""
        if bind:
            stats["bound"] += 1
        embed_input = (f"{bind} — {fact}" if bind else fact).replace("\n", " ")
        new_meta = json.dumps(meta, ensure_ascii=False) if meta.get("episode") else None
        plans.append((mid, new_meta, embed_input))
    print(f"앵커: 소급 {stats['anchored']} · 기존 보존 {stats['kept_existing']} "
          f"· 결합 {stats['bound']} · 원문 없음 {stats['no_source']}")
    if verify_only:
        return

    # ── 3. 배치 재임베딩 (fastembed 직결 — 6천 건을 embed_text 단건으로 돌리지 않는다) ──
    from fastembed import TextEmbedding
    t0 = time.time()
    engine = TextEmbedding(model_name=MODEL)
    print(f"모델 적재 {time.time()-t0:.0f}s: {MODEL}")
    t0 = time.time()
    dim = None
    for i in range(0, len(plans), BATCH):
        chunk = plans[i:i + BATCH]
        vectors = list(engine.embed([p[2] for p in chunk], batch_size=BATCH))
        with con:
            for (mid, new_meta, _), vec in zip(chunk, vectors):
                emb = encode_embedding([float(v) for v in vec])
                dim = dim or len(vec)
                if new_meta is not None:
                    con.execute("UPDATE memories SET embedding=?, metadata=? WHERE id=?",
                                (emb, new_meta, mid))
                else:
                    con.execute("UPDATE memories SET embedding=? WHERE id=?", (emb, mid))
        if (i // BATCH) % 8 == 0:
            done = min(i + BATCH, len(plans))
            print(f"  … {done}/{len(plans)} ({time.time()-t0:.0f}s)")
    print(f"재임베딩 완료 {len(plans)}건 · {dim}차원 · {time.time()-t0:.0f}s")

    # ── 4. 설정 전환 — 이 DB를 읽는 서버는 질의도 같은 모델을 쓴다 ─────────
    row = con.execute("SELECT settings FROM projects WHERE project_id='proj_local'").fetchone()
    settings = json.loads(row["settings"] or "{}") if row else {}
    settings["embedding_model"] = MODEL
    if row:
        with con:
            con.execute("UPDATE projects SET settings=? WHERE project_id='proj_local'",
                        (json.dumps(settings),))
    else:
        with con:
            con.execute("INSERT INTO projects (project_id, settings) VALUES ('proj_local', ?)",
                        (json.dumps(settings),))
    print(f"설정 전환: embedding_model = {MODEL}")

    # ── 5. 정합 검사 — 절반만 갈린 공간은 조용한 쓰레기다 ──────────────────
    sample = con.execute(
        "SELECT embedding FROM memories WHERE deleted=0 ORDER BY random() LIMIT 200"
    ).fetchall()
    dims = {len(decode_embedding(r["embedding"])) for r in sample}
    print(f"차원 표본 200: {dims}")
    assert dims == {dim}, f"혼합 차원 발견 — 마이그레이션 불완전: {dims}"
    con.close()
    print("정합 OK")


if __name__ == "__main__":
    main()
