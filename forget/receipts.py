"""삭제 영수증 v0 — 증명 가능한 소거 (망각 헌장 L1-③, P-F-3).

## P-F-3 v0 등록 (2026-08-26 새벽, 숫자 보기 전 고정 — 데모 수준)

주장: "지웠다"를 말이 아니라 문서로 — 삭제 시 ①원장 소프트 삭제 ②파생
계층 전파(세계모델 재파생) ③각 계층 부재 검증 ④영수증 발급.
영수증 원칙: **내용은 남지 않는다** — 원문 대신 해시(무엇이었는지의
지문)만. 서명은 v0 HMAC(로컬 키) — 진짜 공개키 서명·제3자 검증은 v1.
판정 (계약 테스트 4): 삭제 후 검색 미노출 · 세계모델 재파생 후 사건/고리
부재 · 영수증의 계층 주장이 실제 상태와 일치 · 영수증에 원문 부재(해시만).
4/4 통과 = v0 채택.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from . import worldmodel

RECEIPT_KEY_PATH = Path.home() / ".forget" / "receipt_key"


def _receipt_key() -> bytes:
    if RECEIPT_KEY_PATH.exists():
        return RECEIPT_KEY_PATH.read_bytes()
    key = os.urandom(32)
    RECEIPT_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT_KEY_PATH.write_bytes(key)
    RECEIPT_KEY_PATH.chmod(0o600)
    return key


def delete_with_receipt(memory_id: str, *, ledger_db: str | None = None,
                        world_db: str | None = None,
                        reason: str = "user_request") -> dict[str, Any]:
    """소거 + 전파 + 검증 + 영수증. 존재하지 않으면 KeyError."""
    from .db import current_db_path
    ledger = ledger_db or str(current_db_path())
    world = world_db or worldmodel.DEFAULT_WORLD_DB

    conn = sqlite3.connect(ledger)
    try:
        row = conn.execute("SELECT memory FROM memories WHERE id = ? AND deleted = 0",
                           (memory_id,)).fetchone()
        if row is None:
            raise KeyError(f"기억 없음(또는 이미 삭제): {memory_id}")
        content_hash = hashlib.sha256(str(row[0]).encode()).hexdigest()
        conn.execute("UPDATE memories SET deleted = 1 WHERE id = ?", (memory_id,))
        conn.commit()
    finally:
        conn.close()

    # 파생 전파 — 재파생이 곧 삭제 전파 (대장 #19)
    if os.path.exists(world):
        worldmodel.rebuild(world, ledger, strict_events=True)

    # 계층별 부재 검증 (영수증의 주장은 전부 실측)
    layers: dict[str, str] = {}
    conn = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    try:
        alive = conn.execute("SELECT 1 FROM memories WHERE id = ? AND deleted = 0",
                             (memory_id,)).fetchone()
        layers["ledger"] = "soft_deleted" if alive is None else "STILL_ALIVE"
    finally:
        conn.close()
    if os.path.exists(world):
        wconn = sqlite3.connect(f"file:{world}?mode=ro", uri=True)
        try:
            ev = wconn.execute("SELECT 1 FROM events WHERE id = ?",
                               (f"ev-{memory_id}",)).fetchone()
            lp = wconn.execute("SELECT 1 FROM loops WHERE id = ?",
                               (f"loop-{memory_id}",)).fetchone()
            layers["worldmodel_events"] = "absent" if ev is None else "STILL_PRESENT"
            layers["worldmodel_loops"] = "absent" if lp is None else "STILL_PRESENT"
        finally:
            wconn.close()
    else:
        layers["worldmodel_events"] = layers["worldmodel_loops"] = "no_world_db"
    # 기질은 읽기 시점 원장 대조로 소거됨 (계약 테스트 고정) — 상태 선언
    layers["substrate_mentions"] = "read_time_filtered"

    receipt = {
        "version": "receipt-v0",
        "memory_id": memory_id,
        "content_sha256": content_hash,       # 지문만 — 내용은 없다
        "deleted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reason": reason,
        "layers": layers,
        "verified": all(v in {"soft_deleted", "absent", "read_time_filtered", "no_world_db"}
                        for v in layers.values()),
    }
    payload = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
    receipt["signature_hmac_sha256"] = hmac.new(
        _receipt_key(), payload.encode(), hashlib.sha256).hexdigest()
    return receipt


def verify_receipt(receipt: dict[str, Any]) -> bool:
    """영수증 무결성 검증 — 서명 필드를 뺀 본문의 HMAC 재계산 대조."""
    sig = receipt.get("signature_hmac_sha256")
    body = {k: v for k, v in receipt.items() if k != "signature_hmac_sha256"}
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True)
    expect = hmac.new(_receipt_key(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(str(sig), expect)
