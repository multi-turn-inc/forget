from __future__ import annotations

from typing import Any

from .mcp import mem1_capabilities_payload
from .provider_runtime import provider_health_payload
from .store import lora_training_readiness, model_adapter_promotion_report, self_improvement_status


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _promotion_blocker_codes(report: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    for blocker in report.get("blockers", []):
        if isinstance(blocker, dict):
            code = blocker.get("code")
            if code:
                _append_unique(codes, str(code))
    return codes


def _preflight_actions(blocker_codes: list[str], warning_codes: list[str]) -> list[str]:
    actions: list[str] = []
    if "capability_contracts_missing" in blocker_codes:
        actions.append("Check GET /v1/mem1/capabilities/ and restore the contracts registry.")
    if "missing_context_composer_eval" in blocker_codes:
        actions.append("Run POST /v1/mem1/context/evaluations/ with a context composer regression fixture.")
    if "missing_model_adapter_eval" in blocker_codes:
        actions.append("Run POST /v1/mem1/model-adapters/evaluations/ against an approved trace dataset.")
    if "missing_claim_verification_eval" in warning_codes:
        actions.append("Run POST /v1/mem1/claims/evaluations/ with a claim guardrail regression fixture.")
    if "claim_verification_accuracy_below_threshold" in warning_codes:
        actions.append("Review unsupported or drifted claim fixtures before trusting generated memory-grounded answers.")
    if "judgment_audit_needs_review" in blocker_codes:
        actions.append("Review open judgment audit risks with POST /v1/mem1/judgments/audit/{event_id}/reviews/.")
    if "promotion_not_ready" in blocker_codes:
        actions.append("Inspect GET /v1/mem1/model-adapters/promotion-report/ and resolve or review blockers.")
    if "lora_not_ready" in blocker_codes or "lora_not_ready" in warning_codes:
        actions.append("Use GET /v1/mem1/lora/readiness/ before starting a 4090 LoRA training run.")
    if "provider_health_not_ready" in blocker_codes or "provider_health_not_ready" in warning_codes:
        actions.append("Inspect GET /v1/mem1/providers/health/ and fix the active provider credentials, URLs, or optional dependencies.")
    return actions


def mem1_preflight_payload(
    *,
    project_id: str = "proj_local",
    limit: int = 100,
    min_adapter_accuracy: float = 0.9,
    min_benchmark_accuracy: float = 1.0,
    min_claim_accuracy: float = 1.0,
    min_context_accuracy: float = 1.0,
    min_shadow_precision: float = 0.9,
    min_shadow_reviews: int = 1,
    require_self_improvement_ready: bool = False,
    require_promotion_ready: bool = False,
    require_lora_ready: bool = False,
    require_provider_ready: bool = False,
    include_details: bool = False,
) -> dict[str, Any]:
    capabilities = mem1_capabilities_payload()
    contracts = capabilities.get("contracts") if isinstance(capabilities.get("contracts"), dict) else {}
    self_improvement = self_improvement_status(
        project_id=project_id,
        min_context_accuracy=min_context_accuracy,
        min_adapter_accuracy=min_adapter_accuracy,
        min_claim_accuracy=min_claim_accuracy,
    )
    provider_health = provider_health_payload(project_id=project_id)
    lora = lora_training_readiness(project_id=project_id)
    promotion_report = model_adapter_promotion_report(
        project_id=project_id,
        limit=limit,
        min_adapter_accuracy=min_adapter_accuracy,
        min_benchmark_accuracy=min_benchmark_accuracy,
        min_context_accuracy=min_context_accuracy,
        min_shadow_precision=min_shadow_precision,
        min_shadow_reviews=min_shadow_reviews,
        require_self_improvement_ready=require_self_improvement_ready,
        record=False,
    )

    blocker_codes: list[str] = []
    warning_codes: list[str] = []
    api_ready = capabilities.get("schema_version") == "mem1-capabilities-v1" and bool(contracts)
    if not api_ready:
        _append_unique(blocker_codes, "capability_contracts_missing")
    if not self_improvement.get("ready", False):
        for code in self_improvement.get("blocker_codes", []):
            _append_unique(blocker_codes, str(code))
    for code in self_improvement.get("warning_codes", []):
        _append_unique(warning_codes, str(code))

    promotion_ready = bool(promotion_report.get("can_promote", False))
    promotion_blockers = _promotion_blocker_codes(promotion_report)
    if not promotion_ready:
        target = blocker_codes if require_promotion_ready else warning_codes
        _append_unique(target, "promotion_not_ready")
        for code in promotion_blockers:
            _append_unique(target, f"promotion:{code}")

    lora_ready = lora.get("status") == "READY"
    if not lora_ready:
        _append_unique(blocker_codes if require_lora_ready else warning_codes, "lora_not_ready")
    provider_ready = bool(provider_health.get("ready", False))
    if not provider_ready:
        target = blocker_codes if require_provider_ready else warning_codes
        _append_unique(target, "provider_health_not_ready")
        provider_checks = provider_health.get("checks") if isinstance(provider_health.get("checks"), dict) else {}
        for category, check in provider_checks.items():
            if isinstance(check, dict) and not check.get("ready", False):
                _append_unique(target, f"provider:{category}:blocked")

    result = {
        "schema_version": "mem1-preflight-v1",
        "project_id": project_id,
        "ready": not blocker_codes,
        "api_ready": api_ready,
        "self_improvement_ready": bool(self_improvement.get("ready", False)),
        "promotion_ready": promotion_ready,
        "lora_ready": lora_ready,
        "provider_ready": provider_ready,
        "blocker_codes": blocker_codes,
        "warning_codes": warning_codes,
        "recommended_actions": _preflight_actions(blocker_codes, warning_codes),
        "thresholds": {
            "limit": limit,
            "min_adapter_accuracy": min_adapter_accuracy,
            "min_benchmark_accuracy": min_benchmark_accuracy,
            "min_claim_accuracy": min_claim_accuracy,
            "min_context_accuracy": min_context_accuracy,
            "min_shadow_precision": min_shadow_precision,
            "min_shadow_reviews": min_shadow_reviews,
            "require_self_improvement_ready": require_self_improvement_ready,
            "require_promotion_ready": require_promotion_ready,
            "require_lora_ready": require_lora_ready,
            "require_provider_ready": require_provider_ready,
            "include_details": include_details,
        },
        "capabilities": {
            "schema_version": capabilities.get("schema_version"),
            "preferred_namespace": capabilities.get("preferred_namespace"),
            "control_plane": capabilities.get("control_plane", {}),
            "governance": capabilities.get("governance", {}),
        },
        "contracts": contracts,
        "components": {
            "self_improvement": {
                "ready": bool(self_improvement.get("ready", False)),
                "blocker_codes": self_improvement.get("blocker_codes", []),
                "warning_codes": self_improvement.get("warning_codes", []),
                "schema_version": self_improvement.get("schema_version"),
            },
            "lora": {
                "ready": lora_ready,
                "status": lora.get("status"),
                "missing_dependencies": lora.get("missing_dependencies", []),
                "schema_version": lora.get("schema_version"),
            },
            "promotion": {
                "ready": promotion_ready,
                "recommendation": promotion_report.get("recommendation"),
                "blocker_codes": promotion_blockers,
                "reviewed_blocker_count": promotion_report.get("reviewed_blocker_count", 0),
            },
            "providers": {
                "ready": provider_ready,
                "status": provider_health.get("status"),
                "schema_version": provider_health.get("schema_version"),
                "blocked_categories": [
                    category
                    for category, check in (provider_health.get("checks") or {}).items()
                    if isinstance(check, dict) and not check.get("ready", False)
                ],
            },
        },
    }
    if include_details:
        result.update(
            {
                "self_improvement": self_improvement,
                "lora_readiness": lora,
                "promotion_report": promotion_report,
                "provider_health": provider_health,
            }
        )
    return result


def mem1_readiness_payload(
    *,
    project_id: str = "proj_local",
    limit: int = 100,
    min_adapter_accuracy: float = 0.9,
    min_benchmark_accuracy: float = 1.0,
    min_claim_accuracy: float = 1.0,
    min_context_accuracy: float = 1.0,
    min_shadow_precision: float = 0.9,
    min_shadow_reviews: int = 1,
    require_self_improvement_ready: bool = False,
    require_promotion_ready: bool = False,
    require_lora_ready: bool = False,
    require_provider_ready: bool = False,
) -> dict[str, Any]:
    preflight = mem1_preflight_payload(
        project_id=project_id,
        limit=limit,
        min_adapter_accuracy=min_adapter_accuracy,
        min_benchmark_accuracy=min_benchmark_accuracy,
        min_claim_accuracy=min_claim_accuracy,
        min_context_accuracy=min_context_accuracy,
        min_shadow_precision=min_shadow_precision,
        min_shadow_reviews=min_shadow_reviews,
        require_self_improvement_ready=require_self_improvement_ready,
        require_promotion_ready=require_promotion_ready,
        require_lora_ready=require_lora_ready,
        require_provider_ready=require_provider_ready,
        include_details=False,
    )
    return {
        "schema_version": "mem1-readiness-v1",
        "status": "ready" if preflight.get("ready") else "hold",
        "ready": bool(preflight.get("ready")),
        "preflight_schema_version": preflight.get("schema_version"),
        "blocker_codes": preflight.get("blocker_codes", []),
        "warning_codes": preflight.get("warning_codes", []),
        "recommended_actions": preflight.get("recommended_actions", []),
    }
