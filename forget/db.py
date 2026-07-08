from __future__ import annotations

import json
import os
import sqlite3
import uuid
import hashlib
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("MEM1_DB_PATH", ROOT / "mem1.sqlite3"))


def current_db_path() -> Path:
    return Path(os.getenv("MEM1_DB_PATH", DB_PATH))


def json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=True, sort_keys=True)


def json_loads(value: str | None, default: Any = None) -> Any:
    if value in (None, ""):
        return {} if default is None else default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {} if default is None else default


def connect() -> sqlite3.Connection:
    path = current_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    address TEXT DEFAULT '',
    contact_email TEXT DEFAULT '',
    phone_number TEXT DEFAULT '',
    website TEXT DEFAULT '',
    on_paid_plan INTEGER DEFAULT 0,
    owner INTEGER DEFAULT 1,
    members TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT UNIQUE NOT NULL,
    org_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    api_key TEXT NOT NULL,
    custom_instructions TEXT DEFAULT '',
    settings TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(org_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tenant_users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    email_normalized TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'user',
    email_verified INTEGER DEFAULT 0,
    email_verified_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT,
    disabled_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_tenant_users_email ON tenant_users(email_normalized);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    access_token_hash TEXT UNIQUE NOT NULL,
    refresh_token_hash TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    refresh_expires_at TEXT NOT NULL,
    revoked_at TEXT,
    user_agent TEXT DEFAULT '',
    ip_address TEXT DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES tenant_users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_access ON auth_sessions(access_token_hash);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_refresh ON auth_sessions(refresh_token_hash);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id);

CREATE TABLE IF NOT EXISTS org_memberships (
    org_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revoked_at TEXT,
    PRIMARY KEY (org_id, user_id),
    FOREIGN KEY (org_id) REFERENCES organizations(org_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES tenant_users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_org_memberships_user ON org_memberships(user_id, revoked_at);

CREATE TABLE IF NOT EXISTS project_memberships (
    project_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    revoked_at TEXT,
    PRIMARY KEY (project_id, user_id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES tenant_users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_project_memberships_user ON project_memberships(user_id, revoked_at);

CREATE TABLE IF NOT EXISTS tenant_invites (
    invite_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    project_id TEXT,
    email TEXT NOT NULL,
    email_normalized TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    project_role TEXT DEFAULT '',
    invited_by_user_id TEXT DEFAULT '',
    token_hash TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    accepted_at TEXT,
    revoked_at TEXT,
    delivery_status TEXT DEFAULT 'pending',
    delivery_provider TEXT DEFAULT '',
    delivery_security TEXT DEFAULT '',
    delivery_message_id TEXT DEFAULT '',
    delivery_error TEXT DEFAULT '',
    resend_count INTEGER DEFAULT 0,
    last_resent_at TEXT,
    FOREIGN KEY (org_id) REFERENCES organizations(org_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tenant_invites_org ON tenant_invites(org_id, revoked_at, accepted_at);
CREATE INDEX IF NOT EXISTS idx_tenant_invites_email ON tenant_invites(email_normalized, revoked_at);
CREATE INDEX IF NOT EXISTS idx_tenant_invites_token ON tenant_invites(token_hash);

CREATE TABLE IF NOT EXISTS auth_rate_limits (
    bucket TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    identifier_hash TEXT NOT NULL,
    window_start TEXT NOT NULL,
    attempts INTEGER NOT NULL,
    last_attempt_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_rate_limits_action ON auth_rate_limits(action, last_attempt_at);

CREATE TABLE IF NOT EXISTS auth_security_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    actor_type TEXT DEFAULT '',
    user_id TEXT DEFAULT '',
    org_id TEXT DEFAULT '',
    project_id TEXT DEFAULT '',
    ip_hash TEXT DEFAULT '',
    user_agent_hash TEXT DEFAULT '',
    status_code INTEGER,
    detail TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_security_events_created ON auth_security_events(created_at);
CREATE INDEX IF NOT EXISTS idx_auth_security_events_type ON auth_security_events(event_type, created_at);

CREATE TABLE IF NOT EXISTS auth_security_alerts (
    alert_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    provider TEXT DEFAULT '',
    destination_hash TEXT DEFAULT '',
    status TEXT NOT NULL,
    status_code INTEGER,
    error TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_security_alerts_event ON auth_security_alerts(event_id);
CREATE INDEX IF NOT EXISTS idx_auth_security_alerts_created ON auth_security_alerts(created_at);

CREATE TABLE IF NOT EXISTS auth_oauth_states (
    state_hash TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    nonce TEXT NOT NULL,
    nonce_hash TEXT NOT NULL,
    code_verifier TEXT NOT NULL,
    return_to TEXT DEFAULT '/',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    user_agent TEXT DEFAULT '',
    ip_address TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_auth_oauth_states_provider ON auth_oauth_states(provider, expires_at, consumed_at);

CREATE TABLE IF NOT EXISTS tenant_identity_links (
    provider TEXT NOT NULL,
    provider_subject TEXT NOT NULL,
    user_id TEXT NOT NULL,
    email TEXT NOT NULL,
    email_normalized TEXT NOT NULL,
    email_verified INTEGER DEFAULT 0,
    profile TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (provider, provider_subject),
    FOREIGN KEY (user_id) REFERENCES tenant_users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tenant_identity_links_user ON tenant_identity_links(user_id);
CREATE INDEX IF NOT EXISTS idx_tenant_identity_links_email ON tenant_identity_links(provider, email_normalized);

CREATE TABLE IF NOT EXISTS auth_email_actions (
    token_id TEXT PRIMARY KEY,
    purpose TEXT NOT NULL,
    user_id TEXT NOT NULL,
    email TEXT NOT NULL,
    email_normalized TEXT NOT NULL,
    token_hash TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    requested_ip TEXT DEFAULT '',
    user_agent TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    FOREIGN KEY (user_id) REFERENCES tenant_users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_auth_email_actions_token ON auth_email_actions(token_hash);
CREATE INDEX IF NOT EXISTS idx_auth_email_actions_user ON auth_email_actions(user_id, purpose, consumed_at);
CREATE INDEX IF NOT EXISTS idx_auth_email_actions_email ON auth_email_actions(email_normalized, purpose, created_at);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    memory TEXT NOT NULL,
    user_id TEXT,
    agent_id TEXT,
    app_id TEXT,
    run_id TEXT,
    primary_entity_type TEXT,
    primary_entity_id TEXT,
    metadata TEXT DEFAULT '{}',
    categories TEXT DEFAULT '[]',
    embedding TEXT DEFAULT '[]',
    hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id);
CREATE INDEX IF NOT EXISTS idx_memories_app ON memories(app_id);
CREATE INDEX IF NOT EXISTS idx_memories_run ON memories(run_id);
CREATE INDEX IF NOT EXISTS idx_memories_deleted_created ON memories(deleted, created_at);
CREATE INDEX IF NOT EXISTS idx_memories_project_user ON memories(project_id, deleted, user_id);

CREATE TABLE IF NOT EXISTS memory_history (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    project_id TEXT DEFAULT 'proj_local',
    event TEXT NOT NULL,
    input TEXT DEFAULT '[]',
    old_memory TEXT,
    new_memory TEXT,
    user_id TEXT,
    agent_id TEXT,
    app_id TEXT,
    run_id TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memory_entities (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    memory_id TEXT NOT NULL,
    entity TEXT NOT NULL,
    normalized_entity TEXT NOT NULL,
    entity_type TEXT DEFAULT 'concept',
    confidence REAL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memory_entities_project_entity ON memory_entities(project_id, normalized_entity);
CREATE INDEX IF NOT EXISTS idx_memory_entities_memory ON memory_entities(memory_id);

CREATE TABLE IF NOT EXISTS entity_aliases (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    entity TEXT NOT NULL,
    normalized_entity TEXT NOT NULL,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    entity_type TEXT DEFAULT 'concept',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, normalized_alias)
);

CREATE INDEX IF NOT EXISTS idx_entity_aliases_project_entity ON entity_aliases(project_id, normalized_entity);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_project_alias ON entity_aliases(project_id, normalized_alias);

CREATE TABLE IF NOT EXISTS observation_events (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    tenant_id TEXT DEFAULT 'local',
    source_event_id TEXT,
    memory_id TEXT,
    source_role TEXT NOT NULL DEFAULT 'imported',
    actor_id TEXT DEFAULT '',
    actor_type TEXT DEFAULT '',
    scope TEXT DEFAULT '{}',
    content TEXT NOT NULL,
    payload TEXT DEFAULT '{}',
    source_hash TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE SET NULL,
    FOREIGN KEY (source_event_id) REFERENCES events(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_observation_events_project_recorded ON observation_events(project_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_observation_events_memory ON observation_events(project_id, memory_id);
CREATE INDEX IF NOT EXISTS idx_observation_events_source_event ON observation_events(project_id, source_event_id);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    tenant_id TEXT DEFAULT 'local',
    memory_id TEXT,
    claim_text TEXT NOT NULL,
    scope TEXT DEFAULT '{}',
    subject_key TEXT NOT NULL,
    predicate_key TEXT NOT NULL,
    object_value TEXT DEFAULT '{}',
    assertion_kind TEXT NOT NULL DEFAULT 'fact',
    polarity TEXT NOT NULL DEFAULT 'positive',
    modality TEXT NOT NULL DEFAULT 'asserted',
    valid_from TEXT,
    valid_to TEXT,
    observed_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    retired_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    supersedes_claim_ids TEXT DEFAULT '[]',
    contradicts_claim_ids TEXT DEFAULT '[]',
    source_event_ids TEXT DEFAULT '[]',
    source_hashes TEXT DEFAULT '[]',
    source_role TEXT NOT NULL DEFAULT 'imported',
    authority TEXT NOT NULL DEFAULT 'inferred',
    confidence REAL DEFAULT 0.7,
    sensitivity TEXT DEFAULT 'normal',
    retention_policy TEXT DEFAULT 'default',
    policy_version TEXT DEFAULT 'claim-model-v1',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_claims_project_status ON claims(project_id, status, recorded_at);
CREATE INDEX IF NOT EXISTS idx_claims_memory ON claims(project_id, memory_id);
CREATE INDEX IF NOT EXISTS idx_claims_subject_predicate ON claims(project_id, subject_key, predicate_key);
CREATE INDEX IF NOT EXISTS idx_claims_validity ON claims(project_id, valid_from, valid_to, status);

CREATE TABLE IF NOT EXISTS hybrid_observations (
    observation_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'local',
    project_id TEXT NOT NULL DEFAULT 'proj_local',
    task_id TEXT NOT NULL DEFAULT '',
    session_id TEXT NOT NULL DEFAULT '',
    actor_id TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    observed_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    authority TEXT NOT NULL DEFAULT 'inferred',
    trust_level TEXT NOT NULL DEFAULT 'normal',
    source_hash TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    UNIQUE(project_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_hybrid_observations_task_recorded ON hybrid_observations(project_id, task_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_hybrid_observations_event ON hybrid_observations(project_id, event_type, recorded_at);

CREATE TABLE IF NOT EXISTS hybrid_episodes (
    episode_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'proj_local',
    task_id TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    closed_at TEXT,
    state TEXT NOT NULL DEFAULT 'open',
    boundary_reason_codes TEXT NOT NULL DEFAULT '[]',
    observation_ids TEXT NOT NULL DEFAULT '[]',
    integrated_summary TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT '',
    evidence_refs TEXT NOT NULL DEFAULT '[]',
    integrator_version TEXT NOT NULL DEFAULT 'hybrid-workspace-v0'
);

CREATE INDEX IF NOT EXISTS idx_hybrid_episodes_task_state ON hybrid_episodes(project_id, task_id, state, started_at);

CREATE TABLE IF NOT EXISTS workspace_epochs (
    workspace_epoch_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'proj_local',
    task_id TEXT NOT NULL DEFAULT '',
    scope_json TEXT NOT NULL DEFAULT '{}',
    predecessor_epoch_id TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    current_goal TEXT NOT NULL DEFAULT '',
    current_status TEXT NOT NULL DEFAULT '',
    active_hypothesis TEXT NOT NULL DEFAULT '',
    blockers_json TEXT NOT NULL DEFAULT '[]',
    next_actions_json TEXT NOT NULL DEFAULT '[]',
    constraints_json TEXT NOT NULL DEFAULT '[]',
    verified_results_json TEXT NOT NULL DEFAULT '[]',
    unresolved_questions_json TEXT NOT NULL DEFAULT '[]',
    relevant_artifacts_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    snapshot_hash TEXT NOT NULL,
    reducer_version TEXT NOT NULL DEFAULT 'hybrid-workspace-v0',
    FOREIGN KEY (predecessor_epoch_id) REFERENCES workspace_epochs(workspace_epoch_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_workspace_epochs_task_active ON workspace_epochs(project_id, task_id, valid_to, valid_from);

CREATE TABLE IF NOT EXISTS hybrid_decisions (
    decision_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'proj_local',
    task_id TEXT NOT NULL DEFAULT '',
    decision_type TEXT NOT NULL,
    subject_id TEXT NOT NULL DEFAULT '',
    decision TEXT NOT NULL,
    reason_codes TEXT NOT NULL DEFAULT '[]',
    evidence_refs TEXT NOT NULL DEFAULT '[]',
    decided_at TEXT NOT NULL,
    decider_version TEXT NOT NULL DEFAULT 'hybrid-workspace-v0'
);

CREATE INDEX IF NOT EXISTS idx_hybrid_decisions_task_type ON hybrid_decisions(project_id, task_id, decision_type, decided_at);

CREATE TABLE IF NOT EXISTS context_traces (
    trace_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'proj_local',
    task_id TEXT NOT NULL DEFAULT '',
    task_phase TEXT NOT NULL DEFAULT '',
    policy_version TEXT NOT NULL DEFAULT '',
    query TEXT NOT NULL DEFAULT '',
    filters TEXT NOT NULL DEFAULT '{}',
    candidate_ids TEXT NOT NULL DEFAULT '[]',
    selected_ids TEXT NOT NULL DEFAULT '[]',
    rejected_ids TEXT NOT NULL DEFAULT '[]',
    scores TEXT NOT NULL DEFAULT '{}',
    roles TEXT NOT NULL DEFAULT '{}',
    decision_reasons TEXT NOT NULL DEFAULT '{}',
    token_cost INTEGER NOT NULL DEFAULT 0,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_context_traces_project_created ON context_traces(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_context_traces_task_created ON context_traces(project_id, task_id, created_at);

CREATE TABLE IF NOT EXISTS context_outcomes (
    outcome_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'proj_local',
    trace_id TEXT NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    used_memory_ids TEXT NOT NULL DEFAULT '[]',
    missing_memory_ids TEXT NOT NULL DEFAULT '[]',
    harmful_memory_ids TEXT NOT NULL DEFAULT '[]',
    first_action_productive INTEGER NOT NULL DEFAULT 0,
    user_correction_required INTEGER NOT NULL DEFAULT 0,
    failure_stage TEXT NOT NULL DEFAULT 'unknown',
    first_action TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (trace_id) REFERENCES context_traces(trace_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_context_outcomes_project_created ON context_outcomes(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_context_outcomes_trace ON context_outcomes(project_id, trace_id);

CREATE TABLE IF NOT EXISTS context_observations (
    observation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'proj_local',
    trace_id TEXT NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    observed TEXT NOT NULL DEFAULT '{}',
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (trace_id) REFERENCES context_traces(trace_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_context_observations_project_created ON context_observations(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_context_observations_trace ON context_observations(project_id, trace_id);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT DEFAULT '{}',
    metadata TEXT DEFAULT '{}',
    results TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    latency REAL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);

CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    memory_id TEXT,
    feedback TEXT NOT NULL,
    feedback_reason TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_feedback_memory ON feedback(memory_id);

CREATE TABLE IF NOT EXISTS exports (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    status TEXT NOT NULL,
    schema TEXT DEFAULT '{}',
    filters TEXT DEFAULT '{}',
    data TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS webhooks (
    webhook_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    event_types TEXT DEFAULT '[]',
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    webhook_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    url TEXT NOT NULL,
    payload TEXT DEFAULT '{}',
    status TEXT NOT NULL,
    status_code INTEGER,
    response_body TEXT DEFAULT '',
    error TEXT DEFAULT '',
    attempts INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cost REAL DEFAULT 0,
    latency REAL DEFAULT 0,
    status TEXT DEFAULT 'SUCCEEDED',
    event_id TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_project_created ON usage_events(project_id, created_at);

CREATE TABLE IF NOT EXISTS billing_plans (
    plan_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    currency TEXT NOT NULL DEFAULT 'usd',
    price_cents INTEGER NOT NULL DEFAULT 0,
    interval TEXT NOT NULL DEFAULT 'month',
    project_limit INTEGER,
    api_keys_per_project INTEGER,
    memory_write_limit INTEGER,
    memory_search_limit INTEGER,
    storage_memory_limit INTEGER,
    extra_usage_available INTEGER DEFAULT 0,
    features TEXT DEFAULT '[]',
    provider_product_id TEXT DEFAULT '',
    provider_price_id TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_billing_plans_status ON billing_plans(status, price_cents);

CREATE TABLE IF NOT EXISTS billing_subscriptions (
    subscription_id TEXT PRIMARY KEY,
    org_id TEXT UNIQUE NOT NULL,
    plan_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    provider TEXT NOT NULL DEFAULT 'manual',
    provider_customer_id TEXT DEFAULT '',
    provider_subscription_id TEXT DEFAULT '',
    current_period_start TEXT NOT NULL,
    current_period_end TEXT NOT NULL,
    cancel_at_period_end INTEGER DEFAULT 0,
    trial_ends_at TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(org_id) ON DELETE CASCADE,
    FOREIGN KEY (plan_id) REFERENCES billing_plans(plan_id)
);

CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_org_status
    ON billing_subscriptions(org_id, status);
CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_provider
    ON billing_subscriptions(provider, provider_subscription_id);

CREATE TABLE IF NOT EXISTS billing_extra_usage (
    org_id TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 0,
    budget_cents INTEGER,
    budget_options TEXT DEFAULT '[]',
    current_spend_cents INTEGER DEFAULT 0,
    max_budget_cents INTEGER,
    overage_rate REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(org_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS billing_events (
    event_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'manual',
    provider_event_id TEXT DEFAULT '',
    event_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'recorded',
    payload TEXT DEFAULT '{}',
    error TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(org_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_billing_events_org_created ON billing_events(org_id, created_at);
CREATE INDEX IF NOT EXISTS idx_billing_events_provider_event
    ON billing_events(provider, provider_event_id);

CREATE TABLE IF NOT EXISTS billing_payments (
    payment_id TEXT PRIMARY KEY,
    org_id TEXT NOT NULL,
    subscription_id TEXT,
    plan_id TEXT DEFAULT '',
    order_id TEXT DEFAULT '',
    payment_key TEXT DEFAULT '',
    provider TEXT NOT NULL DEFAULT 'manual',
    provider_payment_id TEXT DEFAULT '',
    amount_cents INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'usd',
    status TEXT NOT NULL DEFAULT 'pending',
    paid_at TEXT,
    refunded_at TEXT,
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(org_id) ON DELETE CASCADE,
    FOREIGN KEY (subscription_id) REFERENCES billing_subscriptions(subscription_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_billing_payments_org_created ON billing_payments(org_id, created_at);
CREATE INDEX IF NOT EXISTS idx_billing_payments_provider
    ON billing_payments(provider, provider_payment_id);
CREATE INDEX IF NOT EXISTS idx_billing_payments_order ON billing_payments(provider, order_id);
CREATE INDEX IF NOT EXISTS idx_billing_payments_payment_key ON billing_payments(provider, payment_key);

CREATE TABLE IF NOT EXISTS evaluations (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    dataset TEXT DEFAULT '[]',
    results TEXT DEFAULT '{}',
    metrics TEXT DEFAULT '{}',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evaluations_project_created ON evaluations(project_id, created_at);

CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    filters TEXT DEFAULT '{}',
    source_memory_ids TEXT DEFAULT '[]',
    summary TEXT NOT NULL,
    drift TEXT DEFAULT '{}',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_summaries_project_created ON summaries(project_id, created_at);

CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    proposal_type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload TEXT DEFAULT '{}',
    result TEXT DEFAULT '{}',
    review_reason TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_proposals_project_status ON proposals(project_id, status, created_at);

CREATE TABLE IF NOT EXISTS proposal_reviews (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    proposal_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, proposal_id, reviewer_id),
    FOREIGN KEY (proposal_id) REFERENCES proposals(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_proposal_reviews_proposal ON proposal_reviews(project_id, proposal_id);

CREATE TABLE IF NOT EXISTS judgment_reviews (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    event_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT DEFAULT '',
    risk_flags TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, event_id, reviewer_id),
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_judgment_reviews_event ON judgment_reviews(project_id, event_id);

CREATE TABLE IF NOT EXISTS promotion_blocker_reviews (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    blocker_code TEXT NOT NULL,
    blocker_key TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT DEFAULT '',
    blocker_snapshot TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project_id, blocker_code, blocker_key, reviewer_id)
);

CREATE INDEX IF NOT EXISTS idx_promotion_blocker_reviews_key
    ON promotion_blocker_reviews(project_id, blocker_code, blocker_key);

CREATE TABLE IF NOT EXISTS request_logs (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER DEFAULT 0,
    latency REAL DEFAULT 0,
    ip TEXT DEFAULT '',
    user_agent TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_request_logs_project_created ON request_logs(project_id, created_at);

CREATE TABLE IF NOT EXISTS trace_export_audits (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    dataset_version TEXT NOT NULL,
    sources TEXT DEFAULT '[]',
    filters TEXT DEFAULT '{}',
    redacted INTEGER DEFAULT 0,
    redaction_policy TEXT DEFAULT 'none',
    redaction TEXT DEFAULT '{}',
    result_count INTEGER DEFAULT 0,
    source_counts TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trace_export_audits_project_created ON trace_export_audits(project_id, created_at);

CREATE TABLE IF NOT EXISTS trace_export_approvals (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    status TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    sources TEXT DEFAULT '[]',
    filters TEXT DEFAULT '{}',
    redaction TEXT DEFAULT '{}',
    result_count INTEGER DEFAULT 0,
    source_counts TEXT DEFAULT '{}',
    trace_audit_id TEXT,
    requested_by TEXT DEFAULT '',
    reviewed_by TEXT DEFAULT '',
    review_reason TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    data TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_trace_export_approvals_project_status ON trace_export_approvals(project_id, status, created_at);

CREATE TABLE IF NOT EXISTS fine_tuning_jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    status TEXT NOT NULL,
    provider TEXT DEFAULT 'local',
    base_model TEXT DEFAULT '',
    adapter_model TEXT DEFAULT '',
    approval_id TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    dataset_count INTEGER DEFAULT 0,
    trainer_url TEXT DEFAULT '',
    result TEXT DEFAULT '{}',
    error TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_fine_tuning_jobs_project_status ON fine_tuning_jobs(project_id, status, created_at);

CREATE TABLE IF NOT EXISTS model_artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    fine_tuning_job_id TEXT NOT NULL,
    adapter_model TEXT NOT NULL,
    provider TEXT DEFAULT 'local',
    artifact_uri TEXT NOT NULL,
    checksum TEXT DEFAULT '',
    status TEXT DEFAULT 'READY',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_model_artifacts_project_created ON model_artifacts(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_model_artifacts_job ON model_artifacts(project_id, fine_tuning_job_id);

CREATE TABLE IF NOT EXISTS model_deployments (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    artifact_id TEXT NOT NULL,
    environment TEXT DEFAULT 'staging',
    status TEXT NOT NULL,
    adapter_model TEXT NOT NULL,
    deployer_url TEXT DEFAULT '',
    result TEXT DEFAULT '{}',
    error TEXT DEFAULT '',
    metadata TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_model_deployments_project_status ON model_deployments(project_id, status, created_at);

CREATE TABLE IF NOT EXISTS model_activation_history (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    deployment_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT DEFAULT 'ACTIVE',
    settings_before TEXT DEFAULT '{}',
    settings_after TEXT DEFAULT '{}',
    metadata TEXT DEFAULT '{}',
    activated_at TEXT NOT NULL,
    rolled_back_at TEXT,
    rollback_reason TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_model_activation_history_project_status ON model_activation_history(project_id, status, activated_at);
CREATE INDEX IF NOT EXISTS idx_model_activation_history_deployment ON model_activation_history(project_id, deployment_id);

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    project_id TEXT DEFAULT 'proj_local',
    owner_user_id TEXT DEFAULT '',
    name TEXT NOT NULL,
    api_key TEXT UNIQUE NOT NULL,
    key_prefix TEXT NOT NULL,
    scopes TEXT DEFAULT '[]',
    created_by_role TEXT DEFAULT 'operator',
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_keys_key ON api_keys(api_key);
CREATE INDEX IF NOT EXISTS idx_api_keys_project ON api_keys(project_id);

CREATE TABLE IF NOT EXISTS app_onboard_requests (
    request_id TEXT PRIMARY KEY,
    email_normalized TEXT NOT NULL,
    magic_token_hash TEXT NOT NULL,
    device_nonce_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    api_key TEXT,
    user_id TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    verified_at TEXT,
    consumed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_app_onboard_token ON app_onboard_requests(magic_token_hash);
CREATE INDEX IF NOT EXISTS idx_app_onboard_email ON app_onboard_requests(email_normalized);
"""


def _stable_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _scope_from_memory_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "user_id": row["user_id"],
        "agent_id": row["agent_id"],
        "app_id": row["app_id"],
        "run_id": row["run_id"],
    }


def _backfill_claim_ledger(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT * FROM memories m
         WHERE NOT EXISTS (
            SELECT 1 FROM claims c
             WHERE c.project_id = m.project_id
               AND c.memory_id = m.id
         )
        """
    ).fetchall()
    for row in rows:
        project_id = row["project_id"] if "project_id" in row.keys() else "proj_local"
        created_at = row["created_at"]
        scope = _scope_from_memory_row(row)
        observation_id = str(uuid.uuid4())
        source_hash = _hash_text(
            _stable_json(
                {
                    "memory_id": row["id"],
                    "memory": row["memory"],
                    "scope": scope,
                    "created_at": created_at,
                }
            )
        )
        conn.execute(
            """
            INSERT INTO observation_events (
                id, project_id, tenant_id, source_event_id, memory_id, source_role,
                actor_id, actor_type, scope, content, payload, source_hash,
                observed_at, recorded_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation_id,
                project_id,
                "local",
                None,
                row["id"],
                "imported",
                "",
                "",
                _stable_json(scope),
                row["memory"],
                _stable_json({"backfill": True, "memory_id": row["id"]}),
                source_hash,
                created_at,
                created_at,
                created_at,
            ),
        )
        subject_key = str(row["primary_entity_id"] or row["user_id"] or row["agent_id"] or row["app_id"] or row["run_id"] or "memory")
        conn.execute(
            """
            INSERT INTO claims (
                id, project_id, tenant_id, memory_id, claim_text, scope,
                subject_key, predicate_key, object_value, assertion_kind,
                polarity, modality, valid_from, valid_to, observed_at,
                recorded_at, retired_at, status, supersedes_claim_ids,
                contradicts_claim_ids, source_event_ids, source_hashes,
                source_role, authority, confidence, sensitivity,
                retention_policy, policy_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                project_id,
                "local",
                row["id"],
                row["memory"],
                _stable_json(scope),
                subject_key,
                "memory",
                _stable_json({"text": row["memory"]}),
                "fact",
                "positive",
                "asserted",
                created_at,
                None,
                created_at,
                created_at,
                created_at if int(row["deleted"] or 0) else None,
                "retracted" if int(row["deleted"] or 0) else "active",
                "[]",
                "[]",
                _stable_json([observation_id]),
                _stable_json([source_hash]),
                "imported",
                "inferred",
                0.7,
                "normal",
                "default",
                "claim-model-v1",
                created_at,
                row["updated_at"],
            ),
        )


def init_db() -> None:
    from .utils import utc_now

    with get_db() as conn:
        conn.executescript(SCHEMA)
        existing_memory_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(memories)").fetchall()
        }
        existing_project_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(projects)").fetchall()
        }
        existing_history_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_history)").fetchall()
        }
        existing_event_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(events)").fetchall()
        }
        existing_export_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(exports)").fetchall()
        }
        existing_delivery_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(webhook_deliveries)").fetchall()
        }
        existing_entity_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_entities)").fetchall()
        }
        existing_entity_alias_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(entity_aliases)").fetchall()
        }
        existing_evaluation_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(evaluations)").fetchall()
        }
        existing_feedback_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(feedback)").fetchall()
        }
        existing_request_log_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(request_logs)").fetchall()
        }
        existing_api_key_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(api_keys)").fetchall()
        }
        existing_billing_payment_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(billing_payments)").fetchall()
        }
        existing_tenant_user_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(tenant_users)").fetchall()
        }
        existing_tenant_invite_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(tenant_invites)").fetchall()
        }
        existing_workspace_epoch_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(workspace_epochs)").fetchall()
        }
        if "settings" not in existing_project_columns:
            conn.execute("ALTER TABLE projects ADD COLUMN settings TEXT DEFAULT '{}'")
        if existing_tenant_user_columns and "email_verified" not in existing_tenant_user_columns:
            conn.execute("ALTER TABLE tenant_users ADD COLUMN email_verified INTEGER DEFAULT 0")
        if existing_tenant_user_columns and "email_verified_at" not in existing_tenant_user_columns:
            conn.execute("ALTER TABLE tenant_users ADD COLUMN email_verified_at TEXT")
        if existing_tenant_invite_columns and "delivery_status" not in existing_tenant_invite_columns:
            conn.execute("ALTER TABLE tenant_invites ADD COLUMN delivery_status TEXT DEFAULT 'pending'")
        if existing_tenant_invite_columns and "delivery_provider" not in existing_tenant_invite_columns:
            conn.execute("ALTER TABLE tenant_invites ADD COLUMN delivery_provider TEXT DEFAULT ''")
        if existing_tenant_invite_columns and "delivery_security" not in existing_tenant_invite_columns:
            conn.execute("ALTER TABLE tenant_invites ADD COLUMN delivery_security TEXT DEFAULT ''")
        if existing_tenant_invite_columns and "delivery_message_id" not in existing_tenant_invite_columns:
            conn.execute("ALTER TABLE tenant_invites ADD COLUMN delivery_message_id TEXT DEFAULT ''")
        if existing_tenant_invite_columns and "delivery_error" not in existing_tenant_invite_columns:
            conn.execute("ALTER TABLE tenant_invites ADD COLUMN delivery_error TEXT DEFAULT ''")
        if existing_tenant_invite_columns and "resend_count" not in existing_tenant_invite_columns:
            conn.execute("ALTER TABLE tenant_invites ADD COLUMN resend_count INTEGER DEFAULT 0")
        if existing_tenant_invite_columns and "last_resent_at" not in existing_tenant_invite_columns:
            conn.execute("ALTER TABLE tenant_invites ADD COLUMN last_resent_at TEXT")
        if existing_workspace_epoch_columns and "scope_json" not in existing_workspace_epoch_columns:
            conn.execute("ALTER TABLE workspace_epochs ADD COLUMN scope_json TEXT DEFAULT '{}'")
        if "project_id" not in existing_memory_columns:
            conn.execute("ALTER TABLE memories ADD COLUMN project_id TEXT DEFAULT 'proj_local'")
        if "embedding" not in existing_memory_columns:
            conn.execute("ALTER TABLE memories ADD COLUMN embedding TEXT DEFAULT '[]'")
        if "project_id" not in existing_history_columns:
            conn.execute("ALTER TABLE memory_history ADD COLUMN project_id TEXT DEFAULT 'proj_local'")
        if "project_id" not in existing_event_columns:
            conn.execute("ALTER TABLE events ADD COLUMN project_id TEXT DEFAULT 'proj_local'")
        if "project_id" not in existing_export_columns:
            conn.execute("ALTER TABLE exports ADD COLUMN project_id TEXT DEFAULT 'proj_local'")
        if "project_id" not in existing_delivery_columns:
            conn.execute("ALTER TABLE webhook_deliveries ADD COLUMN project_id TEXT DEFAULT 'proj_local'")
        if "feedback_reason" not in existing_feedback_columns:
            conn.execute("ALTER TABLE feedback ADD COLUMN feedback_reason TEXT DEFAULT ''")
        if existing_evaluation_columns and "metadata" not in existing_evaluation_columns:
            conn.execute("ALTER TABLE evaluations ADD COLUMN metadata TEXT DEFAULT '{}'")
        if existing_request_log_columns and "project_id" not in existing_request_log_columns:
            conn.execute("ALTER TABLE request_logs ADD COLUMN project_id TEXT DEFAULT 'proj_local'")
        if existing_api_key_columns and "project_id" not in existing_api_key_columns:
            conn.execute("ALTER TABLE api_keys ADD COLUMN project_id TEXT DEFAULT 'proj_local'")
        if existing_api_key_columns and "owner_user_id" not in existing_api_key_columns:
            conn.execute("ALTER TABLE api_keys ADD COLUMN owner_user_id TEXT DEFAULT ''")
        if existing_api_key_columns and "scopes" not in existing_api_key_columns:
            conn.execute("ALTER TABLE api_keys ADD COLUMN scopes TEXT DEFAULT '[]'")
        if existing_api_key_columns and "created_by_role" not in existing_api_key_columns:
            conn.execute("ALTER TABLE api_keys ADD COLUMN created_by_role TEXT DEFAULT 'operator'")
        if existing_billing_payment_columns and "plan_id" not in existing_billing_payment_columns:
            conn.execute("ALTER TABLE billing_payments ADD COLUMN plan_id TEXT DEFAULT ''")
        if existing_billing_payment_columns and "order_id" not in existing_billing_payment_columns:
            conn.execute("ALTER TABLE billing_payments ADD COLUMN order_id TEXT DEFAULT ''")
        if existing_billing_payment_columns and "payment_key" not in existing_billing_payment_columns:
            conn.execute("ALTER TABLE billing_payments ADD COLUMN payment_key TEXT DEFAULT ''")
        if existing_entity_alias_columns and "project_id" not in existing_entity_alias_columns:
            conn.execute("ALTER TABLE entity_aliases ADD COLUMN project_id TEXT DEFAULT 'proj_local'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tenant_users_email ON tenant_users(email_normalized)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_access ON auth_sessions(access_token_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_refresh ON auth_sessions(refresh_token_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_org_memberships_user ON org_memberships(user_id, revoked_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_memberships_user ON project_memberships(user_id, revoked_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tenant_invites_org ON tenant_invites(org_id, revoked_at, accepted_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tenant_invites_email ON tenant_invites(email_normalized, revoked_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tenant_invites_token ON tenant_invites(token_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_rate_limits_action ON auth_rate_limits(action, last_attempt_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_security_events_created ON auth_security_events(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_security_events_type ON auth_security_events(event_type, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_security_alerts_event ON auth_security_alerts(event_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_security_alerts_created ON auth_security_alerts(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_oauth_states_provider ON auth_oauth_states(provider, expires_at, consumed_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tenant_identity_links_user ON tenant_identity_links(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tenant_identity_links_email ON tenant_identity_links(provider, email_normalized)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_email_actions_token ON auth_email_actions(token_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_email_actions_user ON auth_email_actions(user_id, purpose, consumed_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_email_actions_email ON auth_email_actions(email_normalized, purpose, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_project_created ON usage_events(project_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_billing_plans_status ON billing_plans(status, price_cents)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_org_status "
            "ON billing_subscriptions(org_id, status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_billing_subscriptions_provider "
            "ON billing_subscriptions(provider, provider_subscription_id)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_billing_events_org_created ON billing_events(org_id, created_at)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_billing_events_provider_event "
            "ON billing_events(provider, provider_event_id)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_billing_payments_org_created ON billing_payments(org_id, created_at)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_billing_payments_provider "
            "ON billing_payments(provider, provider_payment_id)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_billing_payments_order ON billing_payments(provider, order_id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_billing_payments_payment_key "
            "ON billing_payments(provider, payment_key)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_proposals_project_status ON proposals(project_id, status, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_proposal_reviews_proposal ON proposal_reviews(project_id, proposal_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_judgment_reviews_event ON judgment_reviews(project_id, event_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_promotion_blocker_reviews_key ON promotion_blocker_reviews(project_id, blocker_code, blocker_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_memory ON feedback(memory_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_request_logs_project_created ON request_logs(project_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_export_audits_project_created ON trace_export_audits(project_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trace_export_approvals_project_status ON trace_export_approvals(project_id, status, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fine_tuning_jobs_project_status ON fine_tuning_jobs(project_id, status, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_model_artifacts_project_created ON model_artifacts(project_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_model_artifacts_job ON model_artifacts(project_id, fine_tuning_job_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_model_deployments_project_status ON model_deployments(project_id, status, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_model_activation_history_project_status ON model_activation_history(project_id, status, activated_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_model_activation_history_deployment ON model_activation_history(project_id, deployment_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_key ON api_keys(api_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_project ON api_keys(project_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_entities_project_entity ON memory_entities(project_id, normalized_entity)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_entities_memory ON memory_entities(memory_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_aliases_project_entity ON entity_aliases(project_id, normalized_entity)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_aliases_project_alias ON entity_aliases(project_id, normalized_alias)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_observation_events_project_recorded ON observation_events(project_id, recorded_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_observation_events_memory ON observation_events(project_id, memory_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_observation_events_source_event ON observation_events(project_id, source_event_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_project_status ON claims(project_id, status, recorded_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_memory ON claims(project_id, memory_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_subject_predicate ON claims(project_id, subject_key, predicate_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_validity ON claims(project_id, valid_from, valid_to, status)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hybrid_observations_task_recorded "
            "ON hybrid_observations(project_id, task_id, recorded_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hybrid_observations_event "
            "ON hybrid_observations(project_id, event_type, recorded_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hybrid_episodes_task_state "
            "ON hybrid_episodes(project_id, task_id, state, started_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_workspace_epochs_task_active "
            "ON workspace_epochs(project_id, task_id, valid_to, valid_from)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hybrid_decisions_task_type "
            "ON hybrid_decisions(project_id, task_id, decision_type, decided_at)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_context_traces_project_created ON context_traces(project_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_context_traces_task_created ON context_traces(project_id, task_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_context_outcomes_project_created ON context_outcomes(project_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_context_outcomes_trace ON context_outcomes(project_id, trace_id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_context_observations_project_created "
            "ON context_observations(project_id, created_at)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_context_observations_trace ON context_observations(project_id, trace_id)")
        _backfill_claim_ledger(conn)
        if existing_evaluation_columns:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evaluations_project_created ON evaluations(project_id, created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_summaries_project_created ON summaries(project_id, created_at)")
        now = utc_now()
        if not conn.execute("SELECT 1 FROM organizations LIMIT 1").fetchone():
            conn.execute(
                """
                INSERT INTO organizations (
                    org_id, name, description, contact_email, website, on_paid_plan,
                    owner, members, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "org_local",
                    "Local Workspace",
                    "Default local organization",
                    "owner@example.local",
                    "http://127.0.0.1:8000",
                    0,
                    1,
                    json.dumps([1]),
                    now,
                    now,
                ),
            )
        if not conn.execute("SELECT 1 FROM projects LIMIT 1").fetchone():
            conn.execute(
                """
                INSERT INTO projects (
                    project_id, org_id, name, description, api_key,
                    custom_instructions, settings, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "proj_local",
                    "org_local",
                    "Default Project",
                    "Local Forget project",
                    os.getenv("MEM1_API_KEY", "m0-local-dev-key"),
                    "",
                    json.dumps(
                        {
                            "llm_provider": "local",
                            "llm_model": "rule-extractor",
                            "embedding_provider": "local",
                            "embedding_model": "deterministic-128",
                            "vector_store": "sqlite",
                            "graph_enabled": False,
                            "retrieval_criteria": {},
                            "categories": [],
                        },
                        sort_keys=True,
                    ),
                    now,
                    now,
                ),
            )
