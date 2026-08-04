"""get_provider_health must declare the running embedding stack.

Cycle 43 found the live dogfood serving fastembed/bge-small while
get_provider_health declared local/deterministic-128 — the declaration
channel read stored settings only, while semantic-by-default upgrades an
unconfigured "local" without touching them. P11 treatment 1: mirror the
catalog and carry effective_embedding_stack() in the payload, so the
health channel says what actually runs (LOOP.md principle 3).
"""
from __future__ import annotations

import forget.providers as providers
import forget.provider_runtime as provider_runtime


def _pin_settings(monkeypatch, settings: dict) -> None:
    pinned = lambda project_id="proj_local": dict(settings)  # noqa: E731
    monkeypatch.setattr(providers, "get_project_settings", pinned)
    monkeypatch.setattr(provider_runtime, "get_project_settings", pinned)


def test_health_reports_effective_stack_under_semantic_by_default(monkeypatch):
    # The cycle-43 divergence: stored settings say local, embed_text runs
    # fastembed. Health must disclose the running stack, not the stored one.
    monkeypatch.delenv("MEM1_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setattr(providers, "_fastembed_available", lambda: True)
    _pin_settings(monkeypatch, {"embedding_provider": "local"})
    payload = provider_runtime.provider_health_payload()
    assert payload["checks"]["embeddings"]["provider"] == "local"
    assert payload["effective"]["embedding_provider"] == "fastembed"
    assert payload["effective"]["resolution"] == "auto-default (unconfigured + fastembed importable)"


def test_health_effective_matches_catalog_effective(monkeypatch):
    # Both observer channels must answer from the same resolution — a split
    # between them is exactly the failure cycle 43 caught.
    monkeypatch.delenv("MEM1_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setattr(providers, "_fastembed_available", lambda: True)
    _pin_settings(monkeypatch, {"embedding_provider": "local"})
    health = provider_runtime.provider_health_payload()
    catalog = provider_runtime.provider_catalog_payload()
    assert health["effective"] == catalog["effective"]


def test_health_effective_respects_explicit_local_pin(monkeypatch):
    # An explicit pin is a real choice: effective must report the hash
    # fallback, and say so as a pin rather than an auto-upgrade.
    monkeypatch.setenv("MEM1_EMBEDDING_PROVIDER", "local")
    monkeypatch.setattr(providers, "_fastembed_available", lambda: True)
    _pin_settings(monkeypatch, {"embedding_provider": "local"})
    payload = provider_runtime.provider_health_payload()
    assert payload["effective"]["embedding_model"] == "deterministic-128"
    assert payload["effective"]["resolution"] == "explicit pin"
