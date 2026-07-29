"""Scope migration: merge a legacy app pool into its canonical successor.

The first field report (feedback round 2) set the contract: a verified legacy
alias (e.g. the pre-0.3.3 connector's ``Mem1`` app_id) may be normalized into
the canonical pool, but the original scope must survive as provenance and the
operation must leave a receipt. Records with no owner are never claimed
implicitly — ``claim_null_user`` is an explicit, separate decision.

Dry-run is the default; nothing is written unless ``apply=True``.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _resolve_db_path(db_path: str | None) -> Path:
    if db_path:
        return Path(db_path).expanduser()
    from .db import current_db_path

    return Path(current_db_path())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def migrate_scope(
    *,
    from_app: str,
    to_app: str,
    user: str | None = None,
    claim_null_user: str | None = None,
    db_path: str | None = None,
    apply: bool = False,
    reason: str = "verified_legacy_alias",
) -> dict[str, Any]:
    """Move memories/claims/gate-log rows from one app pool to another.

    Returns the receipt. With ``apply=True`` the receipt is also written to
    ``<db dir>/migrations/`` and every migrated memory carries its original
    scope in ``metadata.scope_migration``.
    """
    if not from_app or not to_app:
        raise ValueError("from_app and to_app are required")
    if from_app == to_app:
        raise ValueError("from_app and to_app must differ")

    path = _resolve_db_path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"database not found: {path}")

    migrated_at = _now()
    provenance = {"original_app_id": from_app, "migrated_at": migrated_at, "reason": reason}
    receipt: dict[str, Any] = {
        "migration_id": str(uuid.uuid4()),
        "migrated_at": migrated_at,
        "db_path": str(path),
        "from_app": from_app,
        "to_app": to_app,
        "user": user,
        "claim_null_user": claim_null_user,
        "reason": reason,
        "applied": bool(apply),
        "counts": {},
        "ids": {},
    }

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        user_clause = " AND user_id = :user" if user else ""
        params: dict[str, Any] = {"from_app": from_app, "to_app": to_app, "user": user}

        rows = conn.execute(
            f"SELECT id FROM memories WHERE app_id = :from_app{user_clause}", params
        ).fetchall()
        memory_ids = [r["id"] for r in rows]

        claim_rows = conn.execute(
            "SELECT id, scope FROM claims WHERE json_extract(scope, '$.app_id') = :from_app"
            + (" AND json_extract(scope, '$.user_id') = :user" if user else ""),
            params,
        ).fetchall()
        claim_ids = [r["id"] for r in claim_rows]

        gate_rows = conn.execute(
            f"SELECT id FROM gate_log WHERE app_id = :from_app{user_clause}", params
        ).fetchall()
        gate_ids = [r["id"] for r in gate_rows]

        null_ids: list[str] = []
        null_claim_ids: list[str] = []
        if claim_null_user:
            null_rows = conn.execute(
                "SELECT id FROM memories WHERE user_id IS NULL AND app_id IN (:from_app, :to_app)",
                {"from_app": from_app, "to_app": to_app},
            ).fetchall()
            null_ids = [r["id"] for r in null_rows]
            null_claim_rows = conn.execute(
                "SELECT id FROM claims WHERE json_extract(scope, '$.user_id') IS NULL "
                "AND json_extract(scope, '$.app_id') IN (:from_app, :to_app)",
                {"from_app": from_app, "to_app": to_app},
            ).fetchall()
            null_claim_ids = [r["id"] for r in null_claim_rows]

        receipt["counts"] = {
            "memories": len(memory_ids),
            "claims": len(claim_ids),
            "gate_log": len(gate_ids),
            "null_user_claimed": len(null_ids),
            "null_user_claims_claimed": len(null_claim_ids),
        }
        receipt["ids"] = {
            "memories": memory_ids,
            "claims": claim_ids,
            "gate_log": gate_ids,
            "null_user_claimed": null_ids,
            "null_user_claims_claimed": null_claim_ids,
        }

        if apply:
            conn.execute(
                f"""
                UPDATE memories
                SET app_id = :to_app,
                    metadata = json_set(COALESCE(metadata, '{{}}'), '$.scope_migration', json(:prov))
                WHERE app_id = :from_app{user_clause}
                """,
                {**params, "prov": json.dumps(provenance, ensure_ascii=False)},
            )
            conn.execute(
                "UPDATE claims SET scope = json_set(scope, '$.app_id', :to_app) "
                "WHERE json_extract(scope, '$.app_id') = :from_app"
                + (" AND json_extract(scope, '$.user_id') = :user" if user else ""),
                params,
            )
            conn.execute(
                f"UPDATE gate_log SET app_id = :to_app WHERE app_id = :from_app{user_clause}",
                params,
            )
            if claim_null_user and null_ids:
                claim_prov = {
                    "original_user_id": None,
                    "claimed_by": claim_null_user,
                    "migrated_at": migrated_at,
                    "reason": "explicit_null_user_claim",
                }
                placeholders = ",".join("?" * len(null_ids))
                conn.execute(
                    "UPDATE memories SET user_id = ?, "
                    "metadata = json_set(COALESCE(metadata, '{}'), '$.owner_claim', json(?)) "
                    f"WHERE id IN ({placeholders})",
                    [claim_null_user, json.dumps(claim_prov, ensure_ascii=False), *null_ids],
                )
            if claim_null_user and null_claim_ids:
                # Claims keep provenance in the receipt only: extra keys inside
                # the scope JSON would perturb scope matching.
                placeholders = ",".join("?" * len(null_claim_ids))
                conn.execute(
                    "UPDATE claims SET scope = json_set(scope, '$.user_id', ?) "
                    f"WHERE id IN ({placeholders})",
                    [claim_null_user, *null_claim_ids],
                )
            conn.commit()

            migrations_dir = path.parent / "migrations"
            migrations_dir.mkdir(mode=0o700, exist_ok=True)
            receipt_path = migrations_dir / f"scope-{migrated_at.replace(':', '')}-{receipt['migration_id'][:8]}.json"
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=1))
            receipt_path.chmod(0o600)
            receipt["receipt_path"] = str(receipt_path)
    finally:
        conn.close()

    return receipt
