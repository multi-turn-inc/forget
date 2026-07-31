# Changelog

## 0.3.5 — Unreleased (gate: 정훈)

Dogfooding round 1: the devloop — an agent using forget as its own working
memory while developing forget — filed its first two field notes, and both
fixes ship here. The fast layer (task state) was leaking into places it
doesn't belong: presented as current when stale, and surfacing in recall
when off-topic.

### Recall quality
- Capsule task state now carries its age (`_state_age_hours`,
  `_state_age_label`) and a stale warning once it exceeds
  `MEM1_CAPSULE_STALE_HOURS` (default 24h), placed ahead of the state so
  budget pressure can't silently drop it. A two-day-old beat had been
  presented as the "current goal" with nothing marking it old
  (field note #1, cycle 2).
- `search_memories` no longer gives task-state claims an unconditional
  activeness boost (+0.08) that let unrelated in-progress tasks outrank
  topical results. Activeness is now reflected through recency only;
  search ranks by topic — surfacing active state is the capsule's job,
  not search's (field note #2, cycle 3).

## 0.3.4 — 2026-07-30

Field-report round 3 (the same first user, re-testing 0.3.3 in real work)
drove all three fixes: no more per-client memory pools, no more silently
ignored search arguments, and a receipted way to merge legacy scopes.

### Scope integrity
- `forget-connect` now scopes every client to one canonical pool
  (`/mcp/forget/http/<os-user>`) instead of inventing a per-client app pool —
  a `codex` pool made Codex writes invisible to Claude and vice versa (#27).
  Which tool wrote a memory is provenance, not an isolation boundary.
- New `forget-server migrate-scope --from-app X --to-app Y [--user U]
  [--claim-null-user U] [--apply]`: merges a verified legacy alias into its
  canonical pool across memories, task-state claims, and the gate log.
  Dry-run by default; every migrated memory keeps its original scope in
  `metadata.scope_migration`; a receipt lands in `<db dir>/migrations/`.
  Ownerless records are never claimed implicitly (#22).

### Correctness
- Search tools (`search_memories`, `search_memory`) reject unknown top-level
  arguments with a 400 naming the argument (with a did-you-mean hint) instead
  of appending a warning nobody reads (#29). Non-read tools keep the warning.


## 0.3.3 — 2026-07-30

First external user report (an agent, running multi-day work) plus a
cold-install audit drove this release: scope integrity on the default
path, honest process exits, and a stricter search argument contract.

### Security & privacy
- The unscoped `/mcp` endpoint no longer stores memories under a hardcoded
  `user_id='codex' × app_id='codex'` ghost scope (cold-install audit
  2026-07-29, defect 1). The fallback owner is now the OS username
  (`MEM1_MCP_DEFAULT_USER_ID` still overrides), no app_id is invented, and
  a fallback-scoped `add_memory` response carries an explicit warning
  pointing to the scoped endpoint. OpenMemory-compat tools
  (`add_memories`, `search_memory`, `list_memories`) now require a client
  identity instead of silently adopting one.
- `forget-connect` installs a scoped endpoint per client by default
  (`/mcp/<client>/http/<os-username>`), so user × app isolation holds on
  the golden path. `--no-scope` restores the shared unscoped endpoint;
  an explicit `--url` is installed verbatim; hosted still requires an
  explicit `--user-id`/`--app-id` pair.

### Correctness
- MCP search tools reject unknown parameters instead of silently ignoring
  them, and `limit` is accepted as an alias for `top_k` — a live probe
  passing `limit=3` used to get 10 results back with no warning.

### CLI
- `forget-server run` exits nonzero when the port is already taken, prints
  the success banner only after a successful bind, and prescribes the fix
  (`forget-server status`, `--port`). It used to exit 0 with a
  success-looking banner over a dead server.

## 0.3.2 — 2026-07-28

Dogfood sprint: every open issue closed, all fixes shipped with regression tests.

### Security & privacy
- `GET /v1/memories/` no longer leaks internal storage fields — `_embedding`
  (128 floats), `hash`, `project_id` are stripped at the public boundary,
  matching the single-read path (#7).
- The default database is created `0600`, its directory `0700` — regardless
  of umask, and even when the data directory was pre-created by the CLI (#4).

### Correctness
- A combined-scope add (`user_id` + `agent_id`) stores one record carrying
  both IDs; the same payload used as search filters now finds it (#6).
- Recurring monitor/watch/poll next-actions stay open until the observation
  reports a state change or the caller marks completion explicitly —
  a successful check is not a finished watch (#14).
- Sentence splitting treats quote pairs as atomic; fragments no longer begin
  mid-quotation with a dangling mark (#2).
- Entity typing on Korean/English mixed text: technical nouns and acronyms
  (Redis, CI, E2EE, …) are no longer typed as `person`; person confidence
  comes from the classifier, not the pattern matcher (#1).

### CLI
- `forget-connect doctor --json` keeps stdout parseable — human notices go
  to stderr; EPIPE exits cleanly (#10).
- Context routing: GitHub-bound follow-ups no longer receive local search
  hints; claim-backed task-state results honor recorded feedback.

## 0.3.1 and earlier
Pre-changelog releases. See git history.
