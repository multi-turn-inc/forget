from __future__ import annotations

import json
from typing import Any


SYSTEM_PROMPT = (
    "You are the Mem1 memory policy adapter. Return compact JSON with label, "
    "confidence, and reason. Use only the provided trace fields."
)
SFT_SCHEMA_VERSION = "mem1-policy-sft-v1"
SUPPORTED_TRACE_DATASET_VERSION = "training-trace-v1"
ALLOWED_SOURCES = {"feedback", "proposals", "evaluation_misses", "shadow_disagreements"}
ALLOWED_LABELS = {"positive", "negative", "very_negative", "applied", "rejected", "pending", "miss", "disagreement"}


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def trace_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("results") or payload.get("items") or payload.get("data") or []
    if not isinstance(raw, list):
        raise ValueError("trace payload results must be a list")
    return [item for item in raw if isinstance(item, dict)]


def approval_metadata(payload: dict[str, Any], require_approved: bool) -> dict[str, Any]:
    dataset_version = str(payload.get("dataset_version") or SUPPORTED_TRACE_DATASET_VERSION)
    if dataset_version != SUPPORTED_TRACE_DATASET_VERSION:
        raise ValueError(f"unsupported dataset_version: {dataset_version}")
    approval = {
        "approval_id": payload.get("approval_id"),
        "approved_by": payload.get("approved_by"),
        "approved_at": payload.get("approved_at"),
        "trace_audit_id": payload.get("trace_audit_id"),
        "dataset_version": dataset_version,
    }
    if require_approved:
        missing = [key for key in ("approval_id", "approved_by", "approved_at") if not approval.get(key)]
        if missing:
            raise ValueError(f"input must be an approved trace export; missing {', '.join(missing)}")
    return approval


def normalized_source(item: dict[str, Any]) -> str:
    source = str(item.get("source") or "unknown")
    if source not in ALLOWED_SOURCES:
        raise ValueError(f"unsupported trace source: {source}")
    return source


def normalized_label(item: dict[str, Any]) -> str:
    label = str(item.get("label") or item.get("decision") or item.get("feedback") or "unknown").lower()
    if label not in ALLOWED_LABELS:
        raise ValueError(f"unsupported trace label: {label}")
    return label


def target_for_trace(item: dict[str, Any]) -> dict[str, Any]:
    source = normalized_source(item)
    label = normalized_label(item)
    reason = str(item.get("reason") or source)
    target = {
        "label": label,
        "confidence": 1.0,
        "reason": reason,
        "source": source,
    }
    if item.get("memory_id") or (isinstance(item.get("metadata"), dict) and item["metadata"].get("memory_id")):
        target["memory_id"] = item.get("memory_id") or item["metadata"].get("memory_id")
    return target


def trace_to_sft_record(item: dict[str, Any], approval: dict[str, Any] | None = None) -> dict[str, Any]:
    approval = approval or {"dataset_version": SUPPORTED_TRACE_DATASET_VERSION}
    source = normalized_source(item)
    prompt = {
        "trace_id": item.get("id"),
        "source": source,
        "input": item.get("input"),
        "output": item.get("output"),
        "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
    }
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json_dumps(prompt)},
            {"role": "assistant", "content": json_dumps(target_for_trace(item))},
        ],
        "metadata": {
            "schema_version": SFT_SCHEMA_VERSION,
            "trace_id": item.get("id"),
            "source": source,
            "dataset_version": item.get("dataset_version") or approval.get("dataset_version") or SUPPORTED_TRACE_DATASET_VERSION,
            "approval_id": approval.get("approval_id"),
            "approved_by": approval.get("approved_by"),
            "approved_at": approval.get("approved_at"),
            "trace_audit_id": approval.get("trace_audit_id"),
        },
    }


def build_sft_records(
    payload: dict[str, Any],
    deny_terms: list[str] | None = None,
    require_approved: bool = True,
) -> list[dict[str, Any]]:
    deny_terms = [term for term in (deny_terms or []) if term]
    approval = approval_metadata(payload, require_approved=require_approved)
    records = [trace_to_sft_record(item, approval=approval) for item in trace_items(payload)]
    blob = "\n".join(json_dumps(record) for record in records)
    leaked = [term for term in deny_terms if term in blob]
    if leaked:
        raise ValueError(f"deny term leaked into dataset: {', '.join(sorted(set(leaked)))}")
    return records


def build_sft_dataset(
    payload: dict[str, Any],
    deny_terms: list[str] | None = None,
    require_approved: bool = True,
) -> dict[str, Any]:
    approval = approval_metadata(payload, require_approved=require_approved)
    records = build_sft_records(payload, deny_terms=deny_terms, require_approved=require_approved)
    return {
        "schema_version": SFT_SCHEMA_VERSION,
        "dataset_version": approval["dataset_version"],
        "approval_id": approval.get("approval_id"),
        "approved_by": approval.get("approved_by"),
        "approved_at": approval.get("approved_at"),
        "trace_audit_id": approval.get("trace_audit_id"),
        "record_count": len(records),
        "records": records,
    }


def records_to_jsonl(records: list[dict[str, Any]]) -> str:
    output = "\n".join(json_dumps(record) for record in records)
    return f"{output}\n" if output else ""
