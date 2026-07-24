from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import quote

import httpx

from .db import get_db, json_dumps, json_loads
from .memory_engine import deterministic_embedding, extract_memories
from .utils import new_id, utc_now


DEFAULT_PROJECT_SETTINGS = {
    "llm_provider": "local",
    "llm_model": "rule-extractor",
    "llm_fast_model": "gpt-5-mini",
    "llm_decision_model": "gpt-5.5",
    "llm_critic_model": "gpt-5.5",
    "llm_action_hint_enabled": True,
    "llm_action_hint_provider": "openai",
    "llm_action_hint_model": "gpt-5.5",
    "llm_action_hint_fallback_models": ["gpt-5.1"],
    "llm_action_hint_base_url": "",
    "llm_action_hint_api_key_env": "MEM1_ACTION_HINT_API_KEY",
    "llm_action_hint_timeout": 20,
    "llm_model_policy": {
        "observation_classification": "fast",
        "candidate_extraction": "fast",
        "boundary_decision": "decision",
        "durable_write_decision": "decision",
        "contradiction_review": "critic",
        "context_access_decision": "decision",
        "action_hint_generation": "action_hint",
    },
    "llm_base_url": "",
    "llm_api_key_env": "MEM1_LLM_API_KEY",
    "llm_api_key_required": True,
    "llm_default_api_key": "",
    "embedding_provider": "local",
    "embedding_model": "deterministic-128",
    "embedding_base_url": "",
    "embedding_api_key_env": "MEM1_EMBEDDING_API_KEY",
    "embedding_api_key_required": True,
    "embedding_default_api_key": "",
    "vector_store": "sqlite",
    "vector_store_url": "",
    "vector_store_api_key_env": "MEM1_QDRANT_API_KEY",
    "vector_store_collection": "mem1_memories",
    "vector_store_timeout": 5,
    "vector_store_strict": False,
    "vector_store_auto_create": False,
    "vector_store_distance": "Cosine",
    "vector_store_dimensions": 128,
    "graph_enabled": False,
    "reranker_provider": "local",
    "reranker_model": "lexical-v1",
    "reranker_base_url": "https://api.cohere.com/v2",
    "reranker_api_key_env": "COHERE_API_KEY",
    "reranker_api_key_required": True,
    "shadow_mode_enabled": False,
    "shadow_provider": "local",
    "shadow_model": "deterministic-shadow-v1",
    "shadow_adapter_url": "",
    "shadow_timeout": 5,
    "shadow_promotion_enabled": False,
    "shadow_promotion_gate_passed": False,
    "shadow_promotion_min_confidence": 0.8,
    "shadow_canary_enabled": False,
    "shadow_canary_min_reviews": 5,
    "shadow_canary_min_precision": 0.9,
    "shadow_canary_min_confidence": 0.95,
    "trace_redaction_terms": [],
    "trace_redaction_deny_terms": [],
    "trace_redaction_allow_terms": [],
    "trace_redaction_policy": "basic_pii_v1",
    "entity_link_prune_enabled": True,
    "entity_link_prune_min_negative_feedback": 2,
    "entity_link_prune_negative_ratio": 0.67,
    "proposal_required_reviews": 1,
    "policy_preset": "balanced",
    "policy_risk_tolerance": "balanced",
    "promotion_audit_retention_enabled": False,
    "promotion_audit_retention_older_than_days": 30,
    "promotion_audit_retention_limit": 500,
    "promotion_audit_retention_interval_seconds": 86400,
    "retrieval_criteria": {},
    "categories": [],
}

OPENAI_COMPATIBLE_LLM_PROVIDERS = {
    "openai",
    "openai_compatible",
    "openai_structured",
    "deepseek",
    "groq",
    "litellm",
    "lmstudio",
    "minimax",
    "ollama",
    "sarvam",
    "together",
    "vllm",
    "xai",
}

OPENAI_COMPATIBLE_EMBEDDING_PROVIDERS = {
    "openai",
    "openai_compatible",
    "lmstudio",
    "ollama",
    "together",
    "vllm",
}

GEMINI_LLM_PROVIDERS = {"gemini"}
GEMINI_EMBEDDING_PROVIDERS = {"gemini"}
COHERE_RERANKER_PROVIDERS = {"cohere_reranker"}
ANTHROPIC_LLM_PROVIDERS = {"anthropic"}
AZURE_OPENAI_LLM_PROVIDERS = {"azure_openai", "azure_openai_structured"}
AZURE_OPENAI_EMBEDDING_PROVIDERS = {"azure_openai"}
AWS_BEDROCK_LLM_PROVIDERS = {"aws_bedrock"}
AWS_BEDROCK_EMBEDDING_PROVIDERS = {"aws_bedrock"}
FASTEMBED_EMBEDDING_PROVIDERS = {"fastembed"}
HUGGINGFACE_EMBEDDING_PROVIDERS = {"huggingface"}
VERTEXAI_EMBEDDING_PROVIDERS = {"vertexai"}
LLM_RERANKER_PROVIDERS = {"llm_reranker"}
SENTENCE_TRANSFORMER_RERANKER_PROVIDERS = {"sentence_transformer_reranker"}
HUGGINGFACE_RERANKER_PROVIDERS = {"huggingface_reranker"}
ZERO_ENTROPY_RERANKER_PROVIDERS = {"zero_entropy_reranker"}


def token_estimate(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return max(1, len(value.split()) or len(value) // 4)
    if isinstance(value, list):
        return sum(token_estimate(item) for item in value)
    if isinstance(value, dict):
        return sum(token_estimate(item) for item in value.values())
    return token_estimate(str(value))


def get_project_settings(project_id: str = "proj_local") -> dict[str, Any]:
    with get_db() as conn:
        row = conn.execute("SELECT custom_instructions, settings FROM projects WHERE project_id = ?", (project_id,)).fetchone()
    settings = dict(DEFAULT_PROJECT_SETTINGS)
    if row:
        settings.update(json_loads(row["settings"], {}))
        if row["custom_instructions"]:
            settings["custom_instructions"] = row["custom_instructions"]
    return settings


def update_project_settings(project_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    settings.update({k: v for k, v in updates.items() if v is not None})
    with get_db() as conn:
        row = conn.execute("SELECT 1 FROM projects WHERE project_id = ?", (project_id,)).fetchone()
        if not row:
            return settings
        conn.execute(
            "UPDATE projects SET settings = ?, updated_at = ? WHERE project_id = ?",
            (json_dumps(settings), utc_now(), project_id),
        )
    return settings


def apply_custom_instructions(facts: list[str], instructions: str | None) -> list[str]:
    if not instructions:
        return facts
    lowered = instructions.lower()
    if "only" not in lowered:
        return facts
    allow_terms = {
        "preference": ("prefer", "likes", "loves", "favorite", "avoid"),
        "preferences": ("prefer", "likes", "loves", "favorite", "avoid"),
        "work": ("work", "job", "company", "project", "team"),
        "travel": ("travel", "trip", "hotel", "flight"),
        "health": ("allergy", "allergies", "medication", "dietary"),
        "schedule": ("meeting", "calendar", "schedule", "morning", "afternoon"),
    }
    selected_terms: list[str] = []
    for name, terms in allow_terms.items():
        if name in lowered:
            selected_terms.extend(terms)
    if not selected_terms:
        return facts
    return [fact for fact in facts if any(term in fact.lower() for term in selected_terms)]


def extract_facts(
    messages: list[dict[str, Any]],
    infer: bool,
    project_id: str,
    custom_instructions: str | None = None,
    extraction_policy: str | None = None,
    assistant_is_subject: bool = False,
    gate_log: list[dict[str, Any]] | None = None,
) -> list[str]:
    settings = get_project_settings(project_id)
    instructions = custom_instructions or settings.get("custom_instructions")
    provider = str(settings.get("llm_provider", "local")).lower()
    if provider in OPENAI_COMPATIBLE_LLM_PROVIDERS and infer and _provider_credentials_available(settings, "llm"):
        try:
            facts = _extract_with_chat_provider(messages, settings, instructions)
            if facts:
                # the model already honored the instructions; the keyword
                # allowlist below is a heuristic for the local extractor only
                return facts
        except Exception:
            pass
    if provider in GEMINI_LLM_PROVIDERS and infer and _provider_credentials_available(settings, "llm"):
        try:
            facts = _extract_with_gemini_provider(messages, settings, instructions)
            if facts:
                # the model already honored the instructions; the keyword
                # allowlist below is a heuristic for the local extractor only
                return facts
        except Exception:
            pass
    if provider in ANTHROPIC_LLM_PROVIDERS and infer and _provider_credentials_available(settings, "llm"):
        try:
            facts = _extract_with_anthropic_provider(messages, settings, instructions)
            if facts:
                # the model already honored the instructions; the keyword
                # allowlist below is a heuristic for the local extractor only
                return facts
        except Exception:
            pass
    if provider in AZURE_OPENAI_LLM_PROVIDERS and infer and _provider_credentials_available(settings, "llm"):
        try:
            facts = _extract_with_azure_openai_provider(messages, settings, instructions)
            if facts:
                # the model already honored the instructions; the keyword
                # allowlist below is a heuristic for the local extractor only
                return facts
        except Exception:
            pass
    if provider in AWS_BEDROCK_LLM_PROVIDERS and infer:
        try:
            facts = _extract_with_aws_bedrock_provider(messages, settings, instructions)
            if facts:
                # the model already honored the instructions; the keyword
                # allowlist below is a heuristic for the local extractor only
                return facts
        except Exception:
            pass
    return apply_custom_instructions(
        extract_memories(
            messages,
            infer=infer,
            extraction_policy=extraction_policy,
            assistant_is_subject=assistant_is_subject,
            gate_log=gate_log,
        ),
        instructions,
    )


def _provider_credentials_available(settings: dict[str, Any], prefix: str) -> bool:
    required = bool(settings.get(f"{prefix}_api_key_required", True))
    default_key = str(settings.get(f"{prefix}_default_api_key") or "")
    env_available = any(os.getenv(env_name) for env_name in _provider_api_key_env_candidates(settings, prefix))
    return bool(default_key or env_available or not required)


def _provider_api_key(settings: dict[str, Any], prefix: str) -> str | None:
    default_key = str(settings.get(f"{prefix}_default_api_key") or "")
    for env_name in _provider_api_key_env_candidates(settings, prefix):
        value = os.getenv(env_name)
        if value:
            return value
    return default_key or None


def _provider_api_key_env_candidates(settings: dict[str, Any], prefix: str) -> list[str]:
    env_name = str(settings.get(f"{prefix}_api_key_env") or f"MEM1_{prefix.upper()}_API_KEY")
    candidates = [env_name] if env_name else []
    provider_key = "llm_provider" if prefix == "llm" else "embedding_provider" if prefix == "embedding" else ""
    provider = str(settings.get(provider_key) or "").lower()
    if prefix in {"llm", "embedding"} and provider == "openai" and "OPENAI_API_KEY" not in candidates:
        candidates.append("OPENAI_API_KEY")
    return candidates


def _json_headers(api_key: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _facts_from_json_text(content: str) -> list[str]:
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    data = json_loads(text, None)
    if isinstance(data, dict):
        data = data.get("facts") or data.get("memories") or data.get("items") or []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]


def _json_object_from_text(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    data = json_loads(text, None)
    if isinstance(data, dict):
        return data
    match = re.search(r"\{.*\}", text, flags=re.S)
    if match:
        data = json_loads(match.group(0), None)
        if isinstance(data, dict):
            return data
    return {}


def _bool_setting(value: Any, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _redacted_key_is_placeholder(api_key: str | None) -> bool:
    normalized = str(api_key or "").strip().lower()
    if not normalized:
        return True
    return normalized in {
        "placeholder",
        "dummy",
        "test",
        "test-key",
        "your-api-key",
        "changeme",
        "none",
        "null",
    }


def _bounded_action_hint_targets(candidate_targets: list[dict[str, Any]] | list[Any]) -> list[dict[str, Any]]:
    allowed_fields = {
        "target",
        "source",
        "target_role",
        "target_utility",
        "action_plan_match",
        "action_plan_rank",
        "recommended_use",
        "selection_guard",
    }
    bounded: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidate_targets[:12]:
        if isinstance(candidate, dict):
            target = str(candidate.get("target") or "").strip()
            item: dict[str, Any] = {
                key: candidate.get(key)
                for key in allowed_fields
                if candidate.get(key) not in (None, "")
            }
            item["source"] = str(item.get("source") or "").strip()
        else:
            target = str(candidate or "").strip()
            item = {"source": ""}
        if not target or target in seen:
            continue
        seen.add(target)
        item["target"] = target
        bounded.append(item)
    return bounded


def _action_hint_model_chain(settings: dict[str, Any], primary_model: str) -> list[str]:
    raw_fallbacks: Any = os.getenv("MEM1_ACTION_HINT_FALLBACK_MODELS")
    if raw_fallbacks is None:
        raw_fallbacks = settings.get("llm_action_hint_fallback_models") or []
    if isinstance(raw_fallbacks, str):
        fallback_models = [item.strip() for item in raw_fallbacks.split(",") if item.strip()]
    elif isinstance(raw_fallbacks, list):
        fallback_models = [str(item).strip() for item in raw_fallbacks if str(item).strip()]
    else:
        fallback_models = []
    models: list[str] = []
    for model in [primary_model, *fallback_models]:
        if model and model not in models:
            models.append(model)
    return models or ["gpt-5.5"]


def generate_action_hint_targets(
    *,
    query: str,
    next_action_text: str,
    candidate_targets: list[dict[str, Any]] | list[Any],
    source_route: dict[str, Any] | None = None,
    action_plan: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    settings = get_project_settings(project_id)
    enabled = _bool_setting(
        os.getenv("MEM1_ACTION_HINT_ENABLED"),
        _bool_setting(settings.get("llm_action_hint_enabled"), True),
    )
    if not enabled:
        return {"used": False, "reason": "disabled"}
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("MEM1_ACTION_HINT_ENABLED") is None:
        return {"used": False, "reason": "disabled_in_pytest"}
    allowed_targets = _bounded_action_hint_targets(candidate_targets)
    if len(allowed_targets) < 2:
        return {"used": False, "reason": "insufficient_candidates", "candidate_count": len(allowed_targets)}
    provider = str(
        os.getenv("MEM1_ACTION_HINT_PROVIDER")
        or settings.get("llm_action_hint_provider")
        or settings.get("llm_provider")
        or "openai"
    ).lower()
    if provider not in OPENAI_COMPATIBLE_LLM_PROVIDERS:
        return {"used": False, "reason": "unsupported_provider", "provider": provider}
    model = str(
        os.getenv("MEM1_ACTION_HINT_MODEL")
        or settings.get("llm_action_hint_model")
        or settings.get("llm_decision_model")
        or "gpt-5.5"
    )
    provider_settings = dict(settings)
    provider_settings["llm_provider"] = provider
    provider_settings["llm_model"] = model
    if settings.get("llm_action_hint_api_key_env"):
        provider_settings["llm_api_key_env"] = settings.get("llm_action_hint_api_key_env")
    api_key = os.getenv("MEM1_ACTION_HINT_API_KEY") or _provider_api_key(provider_settings, "llm")
    if _redacted_key_is_placeholder(api_key):
        return {"used": False, "reason": "missing_api_key", "provider": provider, "model": model}
    base_url = (
        os.getenv("MEM1_ACTION_HINT_BASE_URL")
        or settings.get("llm_action_hint_base_url")
        or settings.get("llm_base_url")
        or os.getenv("MEM1_LLM_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    try:
        timeout = float(os.getenv("MEM1_ACTION_HINT_TIMEOUT") or settings.get("llm_action_hint_timeout") or 20)
    except (TypeError, ValueError):
        timeout = 20.0
    system = (
        "You select the first useful code-inspection targets for a coding agent. "
        "Choose only from the allowed target strings. Do not invent paths, tools, or commands. "
        "Prefer targets with higher target_utility when they match the current user request. "
        "Prefer implementation and test files for engine/product behavior changes. "
        "When implementation and test targets are both relevant, choose implementation first unless the task is explicitly verification, regression, or test-only. "
        "Choose hook, plugin, proxy, or setup scripts only when the task explicitly asks for those surfaces. "
        "Use source_route as the typed routing contract; prefer targets that match source_route.source_class and its availability. "
        "Use action_plan as the typed first-action contract; prefer targets whose target_role appears earlier in action_plan.preferred_target_roles unless the request says otherwise. "
        "Use selection_guard and recommended_use to avoid nearby but wrong files. "
        "Return only a JSON object like "
        '{"targets":[{"target":"allowed target","purpose":"short reason","confidence":0.0}]}. '
        "Pick at most three targets in the order the agent should inspect them."
    )
    user = {
        "query": str(query or "")[:2000],
        "next_action": str(next_action_text or "")[:1200],
        "source_route": source_route if isinstance(source_route, dict) else {},
        "action_plan": action_plan if isinstance(action_plan, dict) else {},
        "allowed_targets": allowed_targets,
    }
    action_hint_temperature = os.getenv("MEM1_ACTION_HINT_TEMPERATURE")
    attempted_models: list[str] = []
    last_http_error: dict[str, Any] | None = None
    last_provider_error: dict[str, Any] | None = None
    content = ""
    selected_model = model
    model_chain = _action_hint_model_chain(settings, model)
    with httpx.Client(timeout=timeout) as client:
        for index, candidate_model in enumerate(model_chain):
            attempted_models.append(candidate_model)
            request_body: dict[str, Any] = {
                "model": candidate_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json_dumps(user)},
                ],
                "response_format": {"type": "json_object"},
            }
            if action_hint_temperature not in (None, ""):
                try:
                    request_body["temperature"] = float(action_hint_temperature)
                except ValueError:
                    pass
            try:
                response = client.post(
                    f"{base_url}/chat/completions",
                    headers=_json_headers(api_key),
                    json=request_body,
                )
                if response.status_code in {400, 404} and index < len(model_chain) - 1:
                    last_http_error = {
                        "status_code": response.status_code,
                        "model": candidate_model,
                    }
                    continue
                response.raise_for_status()
                selected_model = candidate_model
                content = response.json()["choices"][0]["message"]["content"]
                break
            except httpx.HTTPStatusError as exc:
                last_http_error = {
                    "status_code": exc.response.status_code,
                    "model": candidate_model,
                }
                if index < len(model_chain) - 1:
                    continue
                return {
                    "used": False,
                    "reason": "provider_http_error",
                    "provider": provider,
                    "model": model,
                    "status_code": exc.response.status_code,
                    "attempted_models": attempted_models,
                }
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                last_provider_error = {
                    "reason": "provider_timeout" if isinstance(exc, httpx.TimeoutException) else "provider_error",
                    "failed_model": candidate_model,
                    "error_type": exc.__class__.__name__,
                }
                if index < len(model_chain) - 1:
                    continue
                return {
                    "used": False,
                    "reason": last_provider_error["reason"],
                    "provider": provider,
                    "model": model,
                    "error_type": exc.__class__.__name__,
                    "attempted_models": attempted_models,
                }
            except Exception as exc:
                last_provider_error = {
                    "reason": "provider_error",
                    "failed_model": candidate_model,
                    "error_type": exc.__class__.__name__,
                }
                if index < len(model_chain) - 1:
                    continue
                return {
                    "used": False,
                    "reason": "provider_error",
                    "provider": provider,
                    "model": model,
                    "error_type": exc.__class__.__name__,
                    "attempted_models": attempted_models,
                }
    if not content:
        return {
            "used": False,
            "reason": (
                str(last_provider_error.get("reason"))
                if last_provider_error
                else "provider_http_error"
                if last_http_error
                else "empty_provider_response"
            ),
            "provider": provider,
            "model": model,
            "attempted_models": attempted_models,
            **(last_provider_error or {}),
            **(last_http_error or {}),
        }

    allowed_by_target = {item["target"]: item for item in allowed_targets}
    parsed = _json_object_from_text(str(content))
    items = parsed.get("targets") if isinstance(parsed.get("targets"), list) else []
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str):
            target_text = item.strip()
            purpose = "LLM selected this allowed target as useful for the next action."
            confidence_value = 0.7
        elif isinstance(item, dict):
            target_text = str(item.get("target") or "").strip()
            purpose = str(item.get("purpose") or "LLM selected this allowed target as useful for the next action.")
            try:
                confidence_value = float(item.get("confidence", 0.7))
            except (TypeError, ValueError):
                confidence_value = 0.7
        else:
            continue
        if target_text not in allowed_by_target or target_text in seen:
            continue
        seen.add(target_text)
        selected.append(
            {
                "target": target_text,
                "purpose": purpose[:180],
                "confidence": round(min(max(confidence_value, 0.0), 1.0), 4),
                "original_source": allowed_by_target[target_text].get("source") or "",
            }
        )
        if len(selected) >= 3:
            break
    if not selected:
        return {
            "used": False,
            "reason": "no_valid_targets",
            "provider": provider,
            "model": selected_model,
            "primary_model": model,
            "attempted_models": attempted_models,
            "candidate_count": len(allowed_targets),
        }
    return {
        "used": True,
        "provider": provider,
        "model": selected_model,
        "primary_model": model,
        "attempted_models": attempted_models,
        "targets": selected,
        "candidate_count": len(allowed_targets),
    }


def _model_resource_name(model: str) -> str:
    normalized = str(model or "").strip()
    if not normalized:
        return "models/gemini-2.0-flash"
    return normalized if normalized.startswith("models/") else f"models/{normalized}"


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if value:
                    parts.append(str(value))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(parts)
    return "" if content is None else str(content)


def _gemini_contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for message in messages:
        text = _message_content_text(message.get("content")).strip()
        if not text:
            continue
        role = "model" if str(message.get("role") or "").lower() == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": text}]})
    return contents or [{"role": "user", "parts": [{"text": ""}]}]


def _anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for message in messages:
        text = _message_content_text(message.get("content")).strip()
        if not text:
            continue
        role = "assistant" if str(message.get("role") or "").lower() == "assistant" else "user"
        items.append({"role": role, "content": text})
    return items or [{"role": "user", "content": ""}]


def _extraction_prompt(instructions: str | None, response_contract: str) -> str:
    # extraction models default to English facts for non-English input, and
    # translating invites homonym errors (군무 "group dance" -> "military
    # dance"), so the source-language rule ships in every provider prompt
    return (
        "Extract concise long-term memory facts from the conversation. "
        f"{response_contract} "
        "Write each fact in the same language as the message it came from "
        "(Korean input gives Korean facts); never translate. Keep proper "
        "nouns, titles, and technical terms exactly as the user wrote them. "
        f"Instructions: {instructions or 'store stable user facts and preferences'}"
    )


def _extract_with_chat_provider(
    messages: list[dict[str, Any]],
    settings: dict[str, Any],
    instructions: str | None,
) -> list[str]:
    api_key = _provider_api_key(settings, "llm") or os.getenv("MEM1_LLM_API_KEY")
    base_url = (
        settings.get("llm_base_url")
        or os.getenv("MEM1_LLM_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = settings.get("llm_model") or os.getenv("MEM1_LLM_MODEL") or "gpt-5.5"
    prompt = _extraction_prompt(
        instructions,
        'Respond with a JSON object of the form {"facts": ["..."]} and nothing else.',
    )
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": prompt}, *messages],
        "temperature": 0,
    }
    if str(settings.get("llm_provider", "")).lower() in {"openai", "openai_structured"}:
        # conversational framing makes the model answer in prose otherwise
        # (an assistant turn mid-transcript is enough to break array output)
        body["response_format"] = {"type": "json_object"}
    with httpx.Client(timeout=15) as client:
        response = client.post(
            f"{base_url}/chat/completions",
            headers=_json_headers(api_key),
            json=body,
        )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return _facts_from_json_text(content)


def _extract_with_gemini_provider(
    messages: list[dict[str, Any]],
    settings: dict[str, Any],
    instructions: str | None,
) -> list[str]:
    api_key = _provider_api_key(settings, "llm") or os.getenv("GEMINI_API_KEY")
    base_url = (
        settings.get("llm_base_url")
        or os.getenv("GEMINI_BASE_URL")
        or "https://generativelanguage.googleapis.com/v1beta"
    ).rstrip("/")
    model = settings.get("llm_model") or os.getenv("GEMINI_MODEL") or "gemini-2.0-flash"
    prompt = _extraction_prompt(instructions, "Return only a JSON array of strings.")
    with httpx.Client(timeout=15) as client:
        response = client.post(
            f"{base_url}/{_model_resource_name(str(model))}:generateContent",
            headers={"Content-Type": "application/json"},
            params={"key": api_key},
            json={
                "contents": _gemini_contents(messages),
                "systemInstruction": {"parts": [{"text": prompt}]},
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
            },
        )
    response.raise_for_status()
    payload = response.json()
    candidates = payload.get("candidates") if isinstance(payload, dict) else []
    content = ((candidates or [{}])[0].get("content") or {}) if isinstance(candidates, list) else {}
    parts = content.get("parts") if isinstance(content, dict) else []
    text = "\n".join(str(part.get("text") or "") for part in (parts or []) if isinstance(part, dict))
    return _facts_from_json_text(text)


def _extract_with_anthropic_provider(
    messages: list[dict[str, Any]],
    settings: dict[str, Any],
    instructions: str | None,
) -> list[str]:
    api_key = _provider_api_key(settings, "llm") or os.getenv("ANTHROPIC_API_KEY")
    base_url = (
        settings.get("llm_base_url")
        or os.getenv("ANTHROPIC_BASE_URL")
        or "https://api.anthropic.com/v1"
    ).rstrip("/")
    model = settings.get("llm_model") or os.getenv("ANTHROPIC_MODEL") or "claude-haiku-4-5"
    version = os.getenv("ANTHROPIC_VERSION") or "2023-06-01"
    prompt = _extraction_prompt(instructions, "Return only a JSON array of strings.")
    with httpx.Client(timeout=15) as client:
        response = client.post(
            f"{base_url}/messages",
            headers={
                "Content-Type": "application/json",
                "anthropic-version": version,
                "X-Api-Key": str(api_key or ""),
            },
            json={
                "model": model,
                "max_tokens": 512,
                "system": prompt,
                "messages": _anthropic_messages(messages),
                "temperature": 0,
            },
        )
    response.raise_for_status()
    payload = response.json()
    blocks = payload.get("content") if isinstance(payload, dict) else []
    text = "\n".join(str(block.get("text") or "") for block in (blocks or []) if isinstance(block, dict))
    return _facts_from_json_text(text)


def _azure_openai_endpoint(base_url: str, model: str, operation: str, api_version: str) -> str:
    base = str(base_url or "").rstrip("/")
    if not base:
        raise ValueError("Azure OpenAI base URL is required")
    if base.endswith(f"/{operation}") or f"/{operation}?" in base:
        return base
    if base.endswith("/openai/v1") or "/openai/v1/" in base:
        return f"{base}/{operation}"
    separator = "&" if "?" in base else "?"
    if "/openai/deployments/" in base:
        return f"{base}/{operation}{separator}api-version={api_version}"
    deployment = quote(str(model or "").strip(), safe="")
    return f"{base}/openai/deployments/{deployment}/{operation}?api-version={api_version}"


def _azure_openai_headers(api_key: str | None) -> dict[str, str]:
    headers = _json_headers(api_key)
    if api_key:
        headers["api-key"] = api_key
    return headers


def _extract_with_azure_openai_provider(
    messages: list[dict[str, Any]],
    settings: dict[str, Any],
    instructions: str | None,
) -> list[str]:
    api_key = _provider_api_key(settings, "llm") or os.getenv("LLM_AZURE_OPENAI_API_KEY")
    base_url = settings.get("llm_base_url") or os.getenv("LLM_AZURE_ENDPOINT") or os.getenv("AZURE_OPENAI_ENDPOINT")
    model = settings.get("llm_model") or os.getenv("LLM_AZURE_DEPLOYMENT") or "gpt-5-mini"
    api_version = os.getenv("LLM_AZURE_API_VERSION") or os.getenv("AZURE_OPENAI_API_VERSION") or "2024-10-21"
    prompt = _extraction_prompt(instructions, "Return only a JSON array of strings.")
    with httpx.Client(timeout=15) as client:
        response = client.post(
            _azure_openai_endpoint(str(base_url or ""), str(model), "chat/completions", api_version),
            headers=_azure_openai_headers(api_key),
            json={
                "model": model,
                "messages": [{"role": "system", "content": prompt}, *messages],
                "temperature": 0,
            },
        )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return _facts_from_json_text(content)


def _aws_bedrock_client():
    import boto3

    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-west-2"
    return boto3.client("bedrock-runtime", region_name=region)


def _bedrock_messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    system: list[dict[str, str]] = []
    items: list[dict[str, Any]] = []
    for message in messages:
        text = _message_content_text(message.get("content")).strip()
        if not text:
            continue
        role = str(message.get("role") or "user").lower()
        if role == "system":
            system.append({"text": text})
        else:
            items.append({"role": "assistant" if role == "assistant" else "user", "content": [{"text": text}]})
    return items or [{"role": "user", "content": [{"text": ""}]}], system


def _extract_with_aws_bedrock_provider(
    messages: list[dict[str, Any]],
    settings: dict[str, Any],
    instructions: str | None,
) -> list[str]:
    model = settings.get("llm_model") or os.getenv("AWS_BEDROCK_LLM_MODEL") or "anthropic.claude-3-5-sonnet-20240620-v1:0"
    prompt = _extraction_prompt(instructions, "Return only a JSON array of strings.")
    bedrock_messages, system = _bedrock_messages(messages)
    response = _aws_bedrock_client().converse(
        modelId=str(model),
        messages=bedrock_messages,
        system=[{"text": prompt}, *system],
        inferenceConfig={"maxTokens": 512, "temperature": 0},
    )
    content = ((response.get("output") or {}).get("message") or {}).get("content") or []
    text = "\n".join(str(block.get("text") or "") for block in content if isinstance(block, dict))
    return _facts_from_json_text(text)


def e5_prefixed(text: str, model: str, role: str) -> str:
    """Apply the asymmetric instruction prefix e5-family models were trained on.

    The 2026-07 contrast-set validation showed the e5 switch only delivers
    (paraphrase rank 92→2) WITH "query:"/"passage:" prefixes — flipping the
    model config without them silently forfeits the gain. Token-match so
    "gte-large" or a hypothetical "base5" never false-positives.
    """
    tokens = re.split(r"[/\-_.]", str(model).lower())
    if "e5" not in tokens:
        return text
    return f"{'query' if role == 'query' else 'passage'}: {text}"


def embed_text(text: str, project_id: str = "proj_local", role: str = "passage") -> list[float]:
    settings = get_project_settings(project_id)
    provider = (os.getenv("MEM1_EMBEDDING_PROVIDER") or str(settings.get("embedding_provider", "local"))).lower()
    if provider in OPENAI_COMPATIBLE_EMBEDDING_PROVIDERS and _provider_credentials_available(settings, "embedding"):
        try:
            return _embed_with_provider(text, settings)
        except Exception:
            pass
    if provider in GEMINI_EMBEDDING_PROVIDERS and _provider_credentials_available(settings, "embedding"):
        try:
            return _embed_with_gemini_provider(text, settings)
        except Exception:
            pass
    if provider in AZURE_OPENAI_EMBEDDING_PROVIDERS and _provider_credentials_available(settings, "embedding"):
        try:
            return _embed_with_azure_openai_provider(text, settings)
        except Exception:
            pass
    if provider in AWS_BEDROCK_EMBEDDING_PROVIDERS:
        try:
            return _embed_with_aws_bedrock_provider(text, settings)
        except Exception:
            pass
    if provider in FASTEMBED_EMBEDDING_PROVIDERS:
        try:
            return _embed_with_fastembed_provider(text, settings, role=role)
        except Exception:
            pass
    if provider in HUGGINGFACE_EMBEDDING_PROVIDERS:
        try:
            return _embed_with_huggingface_provider(text, settings, role=role)
        except Exception:
            pass
    if provider in VERTEXAI_EMBEDDING_PROVIDERS:
        try:
            return _embed_with_vertexai_provider(text, settings)
        except Exception:
            pass
    return deterministic_embedding(text)


def _embed_with_provider(text: str, settings: dict[str, Any]) -> list[float]:
    api_key = _provider_api_key(settings, "embedding") or os.getenv("MEM1_EMBEDDING_API_KEY")
    base_url = (
        settings.get("embedding_base_url")
        or os.getenv("MEM1_EMBEDDING_BASE_URL")
        or os.getenv("MEM1_LLM_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = settings.get("embedding_model") or os.getenv("MEM1_EMBEDDING_MODEL") or "text-embedding-3-small"
    with httpx.Client(timeout=15) as client:
        response = client.post(
            f"{base_url}/embeddings",
            headers=_json_headers(api_key),
            json={"model": model, "input": text},
        )
    response.raise_for_status()
    embedding = response.json()["data"][0]["embedding"]
    return [float(value) for value in embedding]


def _embed_with_gemini_provider(text: str, settings: dict[str, Any]) -> list[float]:
    api_key = _provider_api_key(settings, "embedding") or os.getenv("GEMINI_API_KEY")
    base_url = (
        settings.get("embedding_base_url")
        or os.getenv("GEMINI_EMBEDDING_BASE_URL")
        or os.getenv("GEMINI_BASE_URL")
        or "https://generativelanguage.googleapis.com/v1beta"
    ).rstrip("/")
    model = settings.get("embedding_model") or os.getenv("GEMINI_EMBEDDING_MODEL") or "gemini-embedding-001"
    with httpx.Client(timeout=15) as client:
        response = client.post(
            f"{base_url}/{_model_resource_name(str(model))}:embedContent",
            headers={"Content-Type": "application/json", "x-goog-api-key": str(api_key or "")},
            json={"model": _model_resource_name(str(model)), "content": {"parts": [{"text": text}]}},
        )
    response.raise_for_status()
    payload = response.json()
    embedding = payload.get("embedding") if isinstance(payload, dict) else {}
    values = embedding.get("values") if isinstance(embedding, dict) else []
    return [float(value) for value in values]


def _embed_with_azure_openai_provider(text: str, settings: dict[str, Any]) -> list[float]:
    api_key = _provider_api_key(settings, "embedding") or os.getenv("EMBEDDING_AZURE_OPENAI_API_KEY")
    base_url = (
        settings.get("embedding_base_url")
        or os.getenv("EMBEDDING_AZURE_ENDPOINT")
        or os.getenv("AZURE_OPENAI_ENDPOINT")
    )
    model = settings.get("embedding_model") or os.getenv("EMBEDDING_AZURE_DEPLOYMENT") or "text-embedding-3-small"
    api_version = os.getenv("EMBEDDING_AZURE_API_VERSION") or os.getenv("AZURE_OPENAI_API_VERSION") or "2024-10-21"
    with httpx.Client(timeout=15) as client:
        response = client.post(
            _azure_openai_endpoint(str(base_url or ""), str(model), "embeddings", api_version),
            headers=_azure_openai_headers(api_key),
            json={"model": model, "input": text.replace("\n", " ")},
        )
    response.raise_for_status()
    embedding = response.json()["data"][0]["embedding"]
    return [float(value) for value in embedding]


def _embed_with_aws_bedrock_provider(text: str, settings: dict[str, Any]) -> list[float]:
    model = settings.get("embedding_model") or os.getenv("AWS_BEDROCK_EMBEDDING_MODEL") or "amazon.titan-embed-text-v1"
    provider = str(model).split(".", 1)[0]
    body = {"texts": [text], "input_type": "search_document"} if provider == "cohere" else {"inputText": text}
    response = _aws_bedrock_client().invoke_model(
        body=json.dumps(body),
        modelId=str(model),
        accept="application/json",
        contentType="application/json",
    )
    payload = json.loads(response.get("body").read())
    embedding = (payload.get("embeddings") or [[]])[0] if provider == "cohere" else payload.get("embedding")
    return [float(value) for value in (embedding or [])]


def _embed_with_fastembed_provider(text: str, settings: dict[str, Any], role: str = "passage") -> list[float]:
    from fastembed import TextEmbedding

    model = settings.get("embedding_model") or os.getenv("FASTEMBED_MODEL") or "thenlper/gte-large"
    text = e5_prefixed(text, str(model), role)
    embeddings = list(TextEmbedding(model_name=str(model)).embed(text.replace("\n", " ")))
    return [float(value) for value in embeddings[0]]


def _embed_with_huggingface_provider(text: str, settings: dict[str, Any], role: str = "passage") -> list[float]:
    base_url = str(settings.get("embedding_base_url") or os.getenv("HUGGINGFACE_EMBEDDING_BASE_URL") or "").rstrip("/")
    if base_url:
        return _embed_with_provider(text, settings)
    from sentence_transformers import SentenceTransformer

    model = settings.get("embedding_model") or os.getenv("HUGGINGFACE_EMBEDDING_MODEL") or "multi-qa-MiniLM-L6-cos-v1"
    text = e5_prefixed(text, str(model), role)
    embedding = SentenceTransformer(str(model)).encode(text, convert_to_numpy=True).tolist()
    return [float(value) for value in embedding]


def _embed_with_vertexai_provider(text: str, settings: dict[str, Any]) -> list[float]:
    from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel

    model = settings.get("embedding_model") or os.getenv("VERTEXAI_EMBEDDING_MODEL") or "gemini-embedding-001"
    dimensions = int(settings.get("vector_store_dimensions") or os.getenv("VERTEXAI_EMBEDDING_DIMS") or 256)
    embedding_model = TextEmbeddingModel.from_pretrained(str(model))
    text_input = TextEmbeddingInput(text=text, task_type="RETRIEVAL_DOCUMENT")
    embeddings = embedding_model.get_embeddings(texts=[text_input], output_dimensionality=dimensions)
    return [float(value) for value in embeddings[0].values]


def rerank_memory_results(
    query: str,
    memories: list[dict[str, Any]],
    project_id: str = "proj_local",
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    settings = get_project_settings(project_id)
    provider = str(settings.get("reranker_provider", "local")).lower()
    if provider in COHERE_RERANKER_PROVIDERS and memories and _provider_credentials_available(settings, "reranker"):
        try:
            return _rerank_with_cohere(query, memories, settings, top_n=top_n)
        except Exception:
            pass
    if provider in LLM_RERANKER_PROVIDERS and memories and _provider_credentials_available(settings, "reranker"):
        try:
            return _rerank_with_llm(query, memories, settings, top_n=top_n)
        except Exception:
            pass
    if provider in SENTENCE_TRANSFORMER_RERANKER_PROVIDERS and memories:
        try:
            return _rerank_with_sentence_transformer(query, memories, settings, top_n=top_n)
        except Exception:
            pass
    if provider in HUGGINGFACE_RERANKER_PROVIDERS and memories:
        try:
            return _rerank_with_huggingface(query, memories, settings, top_n=top_n)
        except Exception:
            pass
    if provider in ZERO_ENTROPY_RERANKER_PROVIDERS and memories and _provider_credentials_available(settings, "reranker"):
        try:
            return _rerank_with_zero_entropy(query, memories, settings, top_n=top_n)
        except Exception:
            pass
    return memories


def _memory_text(memory: dict[str, Any]) -> str:
    return str(memory.get("memory") or memory.get("text") or memory.get("content") or "")


def _score_from_text(text: str) -> float:
    match = re.search(r"\b([01](?:\.\d+)?)\b", str(text or ""))
    if not match:
        return 0.5
    return max(0.0, min(1.0, float(match.group(1))))


def _merge_external_reranker_scores(memories: list[dict[str, Any]], scores: dict[int, float]) -> list[dict[str, Any]]:
    reranked: list[dict[str, Any]] = []
    for index, memory in enumerate(memories):
        item = dict(memory)
        if index in scores:
            external = max(0.0, min(1.0, float(scores[index])))
            base = float(item.get("score") or 0.0)
            item["reranker_score"] = round(external, 4)
            item["score"] = round((base * 0.45) + (external * 0.55), 4)
        reranked.append(item)
    return reranked


def _rerank_with_cohere(
    query: str,
    memories: list[dict[str, Any]],
    settings: dict[str, Any],
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    api_key = _provider_api_key(settings, "reranker") or os.getenv("COHERE_API_KEY")
    base_url = (
        settings.get("reranker_base_url")
        or os.getenv("COHERE_BASE_URL")
        or "https://api.cohere.com/v2"
    ).rstrip("/")
    model = settings.get("reranker_model") or os.getenv("COHERE_RERANK_MODEL") or "rerank-v4.0-pro"
    limit = min(max(int(top_n or len(memories)), 1), len(memories))
    documents = [str(memory.get("memory") or "") for memory in memories]
    with httpx.Client(timeout=15) as client:
        response = client.post(
            f"{base_url}/rerank",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            json={"model": model, "query": query, "documents": documents, "top_n": limit},
        )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results") if isinstance(payload, dict) else []
    external_scores: dict[int, float] = {}
    for item in results or []:
        if not isinstance(item, dict):
            continue
        try:
            external_scores[int(item["index"])] = float(item.get("relevance_score") or 0.0)
        except (KeyError, TypeError, ValueError):
            continue
    reranked: list[dict[str, Any]] = []
    for index, memory in enumerate(memories):
        item = dict(memory)
        if index in external_scores:
            external = max(0.0, min(1.0, external_scores[index]))
            base = float(item.get("score") or 0.0)
            item["reranker_score"] = round(external, 4)
            item["score"] = round((base * 0.45) + (external * 0.55), 4)
        reranked.append(item)
    return reranked


def _rerank_with_llm(
    query: str,
    memories: list[dict[str, Any]],
    settings: dict[str, Any],
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    api_key = _provider_api_key(settings, "reranker") or os.getenv("MEM1_RERANKER_API_KEY")
    base_url = (settings.get("reranker_base_url") or os.getenv("MEM1_RERANKER_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    model = settings.get("reranker_model") or os.getenv("MEM1_RERANKER_MODEL") or "gpt-4o-mini"
    limit = min(max(int(top_n or len(memories)), 1), len(memories))
    system = (
        "You are a relevance scoring assistant. Given a query and one memory document, "
        "respond only with one number from 0.0 to 1.0."
    )
    scores: dict[int, float] = {}
    with httpx.Client(timeout=15) as client:
        for index, memory in enumerate(memories[:limit]):
            response = client.post(
                f"{base_url}/chat/completions",
                headers=_json_headers(api_key),
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": f"Query: {query[:4000]}\n\nDocument: {_memory_text(memory)[:4000]}",
                        },
                    ],
                    "temperature": 0,
                    "max_tokens": 16,
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            scores[index] = _score_from_text(str(content))
    return _merge_external_reranker_scores(memories, scores)


def _normalize_scores(values: list[float]) -> list[float]:
    if not values:
        return values
    low = min(values)
    high = max(values)
    if high == low:
        return [0.5 for _ in values]
    return [(value - low) / (high - low) for value in values]


def _rerank_with_sentence_transformer(
    query: str,
    memories: list[dict[str, Any]],
    settings: dict[str, Any],
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    from sentence_transformers import CrossEncoder

    model = settings.get("reranker_model") or os.getenv("SENTENCE_TRANSFORMER_RERANKER_MODEL")
    model = model or "cross-encoder/ms-marco-MiniLM-L-6-v2"
    limit = min(max(int(top_n or len(memories)), 1), len(memories))
    pairs = [[query, _memory_text(memory)] for memory in memories[:limit]]
    raw_scores = CrossEncoder(str(model)).predict(pairs, show_progress_bar=False)
    if hasattr(raw_scores, "tolist"):
        raw_scores = raw_scores.tolist()
    scores = {index: score for index, score in enumerate(_normalize_scores([float(score) for score in raw_scores]))}
    return _merge_external_reranker_scores(memories, scores)


def _rerank_with_huggingface(
    query: str,
    memories: list[dict[str, Any]],
    settings: dict[str, Any],
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    model_name = settings.get("reranker_model") or os.getenv("HUGGINGFACE_RERANKER_MODEL") or "BAAI/bge-reranker-base"
    limit = min(max(int(top_n or len(memories)), 1), len(memories))
    tokenizer = AutoTokenizer.from_pretrained(str(model_name))
    model = AutoModelForSequenceClassification.from_pretrained(str(model_name))
    model.eval()
    pairs = [[query, _memory_text(memory)] for memory in memories[:limit]]
    inputs = tokenizer(pairs, padding=True, truncation=True, max_length=512, return_tensors="pt")
    with torch.no_grad():
        raw_scores = model(**inputs).logits.squeeze(-1).detach().cpu()
    values = raw_scores.tolist()
    if not isinstance(values, list):
        values = [float(values)]
    scores = {index: score for index, score in enumerate(_normalize_scores([float(score) for score in values]))}
    return _merge_external_reranker_scores(memories, scores)


def _rerank_with_zero_entropy(
    query: str,
    memories: list[dict[str, Any]],
    settings: dict[str, Any],
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    from zeroentropy import ZeroEntropy

    api_key = _provider_api_key(settings, "reranker") or os.getenv("ZERO_ENTROPY_API_KEY")
    model = settings.get("reranker_model") or os.getenv("ZERO_ENTROPY_RERANKER_MODEL") or "zerank-1"
    documents = [_memory_text(memory) for memory in memories]
    response = ZeroEntropy(api_key=api_key).models.rerank(model=str(model), query=query, documents=documents)
    scores: dict[int, float] = {}
    for result in getattr(response, "results", []):
        scores[int(result.index)] = float(result.relevance_score)
    reranked = _merge_external_reranker_scores(memories, scores)
    limit = min(max(int(top_n or len(reranked)), 1), len(reranked))
    return reranked[:limit]


def record_usage(
    project_id: str,
    operation: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency: float = 0,
    status: str = "SUCCEEDED",
    event_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    total_tokens = input_tokens + output_tokens
    per_1k = float(os.getenv("MEM1_USAGE_COST_PER_1K", "0.0001"))
    cost = round((total_tokens / 1000) * per_1k, 8)
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO usage_events (
                id, project_id, operation, input_tokens, output_tokens,
                total_tokens, cost, latency, status, event_id, metadata, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(new_id()),
                project_id,
                operation,
                input_tokens,
                output_tokens,
                total_tokens,
                cost,
                latency,
                status,
                event_id,
                json_dumps(metadata or {}),
                utc_now(),
            ),
        )


def usage_summary(project_id: str = "proj_local", limit: int = 100) -> dict[str, Any]:
    limit = min(max(limit, 1), 500)
    with get_db() as conn:
        totals = conn.execute(
            """
            SELECT COUNT(*) AS operation_count,
                   COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens,
                   COALESCE(SUM(cost), 0) AS total_cost,
                   COALESCE(AVG(latency), 0) AS avg_latency
              FROM usage_events
             WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()
        rows = conn.execute(
            """
            SELECT * FROM usage_events
             WHERE project_id = ?
             ORDER BY created_at DESC
             LIMIT ?
            """,
            (project_id, limit),
        ).fetchall()
    return {
        "project_id": project_id,
        "operation_count": totals["operation_count"],
        "input_tokens": totals["input_tokens"],
        "output_tokens": totals["output_tokens"],
        "total_tokens": totals["total_tokens"],
        "total_cost": round(float(totals["total_cost"]), 8),
        "avg_latency": round(float(totals["avg_latency"]), 3),
        "results": [
            {
                "id": row["id"],
                "project_id": row["project_id"],
                "operation": row["operation"],
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "total_tokens": row["total_tokens"],
                "cost": row["cost"],
                "latency": row["latency"],
                "status": row["status"],
                "event_id": row["event_id"],
                "metadata": json_loads(row["metadata"], {}),
                "created_at": row["created_at"],
            }
            for row in rows
        ],
    }
