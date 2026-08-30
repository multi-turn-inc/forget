"""접근 그랜트 + 출구 검문 + 접근 영수증 — 기억 경제 내부 단계.

정본: botbotbot docs/spec/MEMORY_ECONOMY.md (2026-08-27 스파이크로 실증,
여기서 기관으로 승격 — 모든 클라이언트가 같은 집행을 받는다).

원칙:
- **영수증 없으면 서빙 없음** — 영수증을 원장에 먼저 기록한 뒤에만 결과를
  돌려준다. 거부도 영수증이다(안 나간 것까지 감사 대상).
- **검문은 로컬 결정론** — 답이 기기를 떠나기 전 PII를 가린다. 검문기·영수증·
  스코프 집행은 오픈 경계 코드다(닫힌 집행기는 신뢰가 아니라 믿어달라).
- **self층은 비매품** — 소유 user_id 행은 scope_fallback을 켜도 구조적으로
  격리된다(store._scope_fallback_eligible). 그랜트는 공유 원장만 연다.
- 서명은 receipts.py의 키·정준형을 공유 — verify_receipt가 접근 영수증도
  그대로 검증한다.
"""
from __future__ import annotations

import fnmatch
import hashlib
import hmac
import json
import re
from typing import Any

from .receipts import _receipt_key
from .utils import new_id, utc_now

# 출구 검문 탐지기 — 결정론·로컬. 스파이크 4종에서 출발, 확장은 여기로.
PII_DETECTORS: dict[str, re.Pattern[str]] = {
    "phone": re.compile(r"(?:\+?82[-\s]?|0)1[0-9][-\s]?[0-9]{3,4}[-\s]?[0-9]{4}"),
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "rrn": re.compile(r"\b[0-9]{6}[-\s]?[1-4][0-9]{6}\b"),
    "card": re.compile(r"\b(?:[0-9]{4}[-\s]?){3}[0-9]{4}\b"),
}
REQUEST_ID_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9_.:-]{0,126}[A-Za-z0-9])?")
PRINCIPAL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}")
PRINCIPAL_PATTERN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:*?\[\]!-]{0,159}")


def _grant_row_to_dict(row: Any) -> dict[str, Any]:
    grant = dict(row)
    grant["deny_pii"] = json.loads(grant.get("deny_pii") or "[]")
    return grant


def create_grant(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    from .db import get_db
    from .store import current_project_id

    project_id = project_id or current_project_id()
    grantee_pattern = str(payload.get("grantee_pattern") or "").strip()
    scope_app = str(payload.get("scope_app") or "").strip()
    if not grantee_pattern or not scope_app:
        raise ValueError("grantee_pattern and scope_app are required")
    allow_pattern_value = payload.get("allow_pattern", False)
    if not isinstance(allow_pattern_value, bool):
        raise ValueError("allow_pattern must be boolean")
    has_pattern = any(marker in grantee_pattern for marker in ("*", "?", "["))
    if has_pattern and not allow_pattern_value:
        raise ValueError("wildcard grantee_pattern requires allow_pattern=true")
    principal_mode = "pattern" if has_pattern else "exact"
    if principal_mode == "exact":
        if PRINCIPAL_RE.fullmatch(grantee_pattern) is None:
            raise ValueError("exact grantee_pattern must be a bounded principal identifier")
    elif PRINCIPAL_PATTERN_RE.fullmatch(grantee_pattern) is None:
        raise ValueError("grantee_pattern contains invalid pattern characters")
    if PRINCIPAL_RE.fullmatch(scope_app) is None:
        raise ValueError("scope_app must be a bounded identifier")
    deny_pii = payload.get("deny_pii")
    if deny_pii is None:
        deny_pii = list(PII_DETECTORS)  # 안전 기본값: 전 탐지기 켬
    unknown = [name for name in deny_pii if name not in PII_DETECTORS]
    if unknown:
        raise ValueError(f"unknown deny_pii detectors: {unknown}")
    quota = int(payload.get("quota") or 100)
    if quota <= 0:
        raise ValueError("quota must be positive")
    answer_mode = str(payload.get("answer_mode") or "passage").strip()
    if answer_mode not in ("passage", "pointer"):
        raise ValueError("answer_mode must be 'passage' or 'pointer'")
    grant = {
        "id": new_id("grant"),
        "project_id": project_id,
        "owner_user_id": payload.get("owner_user_id"),
        "grantee_pattern": grantee_pattern,
        "principal_mode": principal_mode,
        "scope_app": scope_app,
        "deny_pii": json.dumps(list(deny_pii)),
        "quota": quota,
        "used": 0,
        "answer_mode": answer_mode,
        "expires_at": payload.get("expires_at"),
        "revoked_at": None,
        "created_at": utc_now(),
    }
    with get_db() as conn:
        conn.execute(
            "INSERT INTO access_grants (id, project_id, owner_user_id, grantee_pattern,"
            " principal_mode, scope_app, deny_pii, quota, used, answer_mode, expires_at, revoked_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(grant.values()),
        )
    return _grant_row_to_dict(grant)


def list_grants(project_id: str | None = None, include_revoked: bool = False) -> list[dict[str, Any]]:
    from .db import get_db
    from .store import current_project_id

    project_id = project_id or current_project_id()
    sql = "SELECT * FROM access_grants WHERE project_id = ?"
    if not include_revoked:
        sql += " AND revoked_at IS NULL"
    with get_db() as conn:
        rows = conn.execute(sql + " ORDER BY created_at DESC", (project_id,)).fetchall()
    return [_grant_row_to_dict(row) for row in rows]


def revoke_grant(grant_id: str, project_id: str | None = None) -> dict[str, Any]:
    from .db import get_db
    from .store import current_project_id

    project_id = project_id or current_project_id()
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE access_grants SET revoked_at = ? WHERE id = ? AND project_id = ?"
            " AND revoked_at IS NULL",
            (utc_now(), grant_id, project_id),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"grant not found or already revoked: {grant_id}")
    return {"id": grant_id, "revoked": True}


def _admit(grantee: str, scope_app: str, project_id: str) -> tuple[dict[str, Any] | None, str]:
    """원자 입장 — (입장된 그랜트, 사유). gpt-live 인계 ③: 읽고-올리기의
    레이스를 없앤다. 입장의 정본은 단일 UPDATE의 rowcount다: `used < quota`
    조건부 증가가 성공한 요청만 입장하고, 동시 요청이 몰려도 quota를 넘는
    입장은 구조적으로 불가능하다."""
    from .db import get_db

    now = utc_now()
    candidates = [
        grant for grant in list_grants(project_id)
        if grant["scope_app"] == scope_app
        and (
            fnmatch.fnmatchcase(grantee, grant["grantee_pattern"])
            if grant.get("principal_mode") == "pattern"
            else grantee == grant["grantee_pattern"]
        )
    ]
    if not candidates:
        return None, "no-matching-grant"
    live = [g for g in candidates if not (g["expires_at"] and str(g["expires_at"]) < now)]
    if not live:
        return None, "grant-expired"
    for grant in live:
        with get_db() as conn:
            cursor = conn.execute(
                "UPDATE access_grants SET used = used + 1"
                " WHERE id = ? AND revoked_at IS NULL AND used < quota",
                (grant["id"],),
            )
            if cursor.rowcount == 1:
                return grant, "granted"
    return None, "quota-exhausted"


def _apply_gate(text: str, deny_pii: list[str]) -> tuple[str, int]:
    redactions = 0
    for name in deny_pii:
        detector = PII_DETECTORS.get(name)
        if detector is None:
            continue
        text, count = detector.subn(f"[redacted-{name}]", text)
        redactions += count
    return text, redactions


def _sign(payload: dict[str, Any]) -> dict[str, Any]:
    # 공용 서명기(receipts.sign_receipt) — 삭제·접근 영수증이 같은 정준형·
    # 같은 키(HMAC + Ed25519 v1)를 쓴다. 제3자는 공개키만으로 검증 가능.
    from .receipts import sign_receipt
    return sign_receipt(payload)


def _query_commitment(query: str) -> str:
    return hmac.new(
        _receipt_key(), f"query:{query}".encode(), hashlib.sha256,
    ).hexdigest()


def _write_receipt(receipt: dict[str, Any], project_id: str) -> None:
    from .db import get_db

    with get_db() as conn:
        conn.execute(
            "INSERT INTO access_receipts (id, project_id, grant_id, grantee, scope_app,"
            " allowed, reason, query_hash, query_commitment, request_id, items_served, redactions,"
            " receipt_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (receipt["receipt_id"], project_id, receipt.get("grant_id"),
             receipt["grantee"], receipt["scope_app"], int(receipt["allowed"]),
             receipt["reason"], "", receipt["query_commitment"], receipt.get("request_id"),
             receipt["items_served"], receipt["redactions"],
             json.dumps(receipt, ensure_ascii=False), receipt["at"]),
        )


def _replay_receipt(request_id: str, grantee: str, project_id: str) -> dict[str, Any] | None:
    from .db import get_db

    with get_db() as conn:
        row = conn.execute(
            "SELECT receipt_json FROM access_receipts WHERE project_id = ?"
            " AND grantee = ? AND request_id = ? ORDER BY created_at LIMIT 1",
            (project_id, grantee, request_id),
        ).fetchone()
    return json.loads(row["receipt_json"]) if row else None


def serve(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    """원자 입장 → 검색 → 출구 검문 → 영수증 선기록 → 결과 반환.

    request_id 멱등(gpt-live 인계 ①): 같은 (grantee, request_id) 재요청은
    쿼터를 다시 소모하지 않고 원 영수증을 그대로 돌려준다(results는 비움 —
    멱등의 목적은 영수증·쿼터의 유일성이지 결과 재배달이 아니다)."""
    from .store import current_project_id, search_memories

    project_id = project_id or current_project_id()
    grantee = str(payload.get("grantee") or "").strip()
    scope_app = str(payload.get("scope_app") or payload.get("app_id") or "").strip()
    query = str(payload.get("query") or "").strip()
    request_id = str(payload.get("request_id") or "").strip() or None
    if not grantee or not scope_app or not query:
        raise ValueError("grantee, scope_app and query are required")
    if request_id and REQUEST_ID_RE.fullmatch(request_id) is None:
        raise ValueError("request_id must be a 1-128 character identifier")

    if request_id:
        prior = _replay_receipt(request_id, grantee, project_id)
        if prior is not None:
            return {"allowed": bool(prior.get("allowed")), "reason": "idempotent-replay",
                    "results": [], "receipt": prior}

    grant, reason = _admit(grantee, scope_app, project_id)

    results: list[dict[str, Any]] = []
    redactions = 0
    if grant is not None:
        # scope_fallback 금지 (2026-08-29 데모 리허설 실측 누수): 폴백은
        # 소유자 개인 회상의 편의지, 그랜트 서빙에선 타 앱 공유 행이
        # 허락 범위 밖으로 새는 구멍이었다 — demo 스코프 1행 그랜트가
        # forget-dev proposal을 서빙했다. 그랜트의 계약은 "scope_app
        # 원장만"이며, 아래 app_id 재확인은 검색 내부가 어떤 이유로든
        # 범위 밖 행을 돌려줘도 출구에서 막는 이중벽이다.
        raw = search_memories({
            "query": query,
            "filters": {"app_id": scope_app},
            "scope_fallback": False,
            "top_k": int(payload.get("top_k") or 8),
        }, project_id)
        pointer_mode = grant.get("answer_mode") == "pointer"
        for row in (raw.get("results") or []):
            if str(row.get("app_id") or "") != scope_app:
                continue
            # 그랜트가 여는 것은 공유 원장(무소유 행)뿐. 소유 user_id가 붙은
            # 행은 app 태그가 있어도 개인 기억이다 — 1차 매칭으로 새는 것을
            # 여기서 구조적으로 막는다 (계약 테스트 ⑥이 이 줄의 근거).
            if row.get("user_id"):
                continue
            if pointer_mode:
                # 외부 판매 최소형(gpt-live 인계 ⑤): 원문 passage는 나가지
                # 않는다 — 참조와 좌표만.
                results.append({"ref": row.get("id"), "agent_id": row.get("agent_id"),
                                "created_at": row.get("created_at"), "score": row.get("score")})
                continue
            text = str(row.get("memory") or "")
            gated, count = _apply_gate(text, grant["deny_pii"])
            redactions += count
            results.append({"memory": gated, "agent_id": row.get("agent_id"),
                            "created_at": row.get("created_at"), "score": row.get("score")})

    receipt = _sign({
        "kind": "access_receipt",
        "receipt_id": new_id("areceipt"),
        "grant_id": grant["id"] if grant else None,
        "grantee": grantee,
        "scope_app": scope_app,
        "allowed": grant is not None,
        "reason": reason,
        # 평문 SHA-256은 저엔트로피 query 사전 공격에 열려 있어 제거한다.
        # 소비자는 query를 인증된 검증 엔드포인트의 기대값으로 보내고,
        # 서버가 이 키드 커밋먼트와 대조한다.
        "query_commitment": _query_commitment(query),
        "request_id": request_id,
        "answer_mode": grant.get("answer_mode") if grant else None,
        "items_served": len(results),
        "redactions": redactions,
        "at": utc_now(),
    })
    # 영수증 선기록 — 실패 시 예외가 전파되어 서빙 자체가 없던 일이 된다.
    _write_receipt(receipt, project_id)

    return {"allowed": grant is not None, "reason": reason,
            "results": results, "receipt": receipt}


def verify_access_receipt(
    receipt: dict[str, Any],
    *,
    expected_query: str,
    expected_grantee: str,
    expected_scope_app: str,
    project_id: str | None = None,
) -> dict[str, bool]:
    """Verify signature, local persistence, and exact request bindings."""
    from .db import get_db
    from .receipts import verify_receipt
    from .store import current_project_id

    project_id = project_id or current_project_id()
    signature_valid = bool(verify_receipt(receipt))
    with get_db() as conn:
        row = conn.execute(
            "SELECT receipt_json FROM access_receipts WHERE project_id = ? AND id = ?",
            (project_id, str(receipt.get("receipt_id") or "")),
        ).fetchone()
    persisted = json.loads(row["receipt_json"]) if row else None
    persistence_valid = persisted == receipt
    binding_valid = (
        receipt.get("kind") == "access_receipt"
        and hmac.compare_digest(
            str(receipt.get("query_commitment") or ""),
            _query_commitment(expected_query),
        )
        and receipt.get("grantee") == expected_grantee
        and receipt.get("scope_app") == expected_scope_app
    )
    return {
        "valid": signature_valid and persistence_valid and binding_valid,
        "signature_valid": signature_valid,
        "persistence_valid": persistence_valid,
        "binding_valid": binding_valid,
    }


def list_access_receipts(project_id: str | None = None, grantee: str | None = None,
                         limit: int = 50) -> list[dict[str, Any]]:
    from .db import get_db
    from .store import current_project_id

    project_id = project_id or current_project_id()
    sql = "SELECT receipt_json FROM access_receipts WHERE project_id = ?"
    params: list[Any] = [project_id]
    if grantee:
        sql += " AND grantee = ?"
        params.append(grantee)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(int(limit))
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [json.loads(row["receipt_json"]) for row in rows]


def usage_statement(project_id: str | None = None, grantee: str | None = None,
                    scope_app: str | None = None, days: int = 30) -> dict[str, Any]:
    """사용 명세서 (마켓 제도, 2026-08-30) — 영수증 원장의 기간 집계.

    «허락한 만큼인지 확인할 수 있게»의 조회면: 서빙/거절 건수·서빙 항목·
    검문 건수·일별 추이. 원천은 영수증뿐(별도 계수기 없음 — 명세와 원장이
    어긋날 수 없다). B3O 감사 UX가 이 한 콜로 화면을 그린다.
    """
    from .db import get_db
    from .store import current_project_id

    project_id = project_id or current_project_id()
    days = max(1, min(int(days or 30), 365))
    sql = ("SELECT receipt_json, created_at FROM access_receipts"
           " WHERE project_id = ? AND created_at > datetime('now', ?)")
    params: list[Any] = [project_id, f"-{days} days"]
    if grantee:
        sql += " AND grantee = ?"
        params.append(grantee)
    if scope_app:
        sql += " AND scope_app = ?"
        params.append(scope_app)
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
    serves = denials = items = redactions = 0
    by_day: dict[str, dict[str, int]] = {}
    for row in rows:
        receipt = json.loads(row["receipt_json"])
        day = str(row["created_at"])[:10]
        bucket = by_day.setdefault(day, {"serves": 0, "denials": 0, "items": 0})
        if receipt.get("allowed"):
            serves += 1
            bucket["serves"] += 1
            items += int(receipt.get("items_served") or 0)
            bucket["items"] += int(receipt.get("items_served") or 0)
            redactions += int(receipt.get("redactions") or 0)
        else:
            denials += 1
            bucket["denials"] += 1
    return {
        "schema_version": "forget-usage-statement-v1",
        "period_days": days,
        "grantee": grantee, "scope_app": scope_app,
        "serves": serves, "denials": denials,
        "items_served_total": items, "redactions_total": redactions,
        "by_day": dict(sorted(by_day.items())),
        "receipt_count": len(rows),
    }
