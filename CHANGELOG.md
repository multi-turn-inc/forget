# Changelog

## Unreleased

### Scope integrity
- Write-time scope guard: every memory write (MCP and REST converge in
  `store.add_memories`) is now checked against the canonical pool
  (`<owner> × forget`) and the `MEM1_ALLOWED_SCOPES` allowlist
  (`"user:app,user2:*"`). Modes via `MEM1_SCOPE_GUARD`: `warn` (default —
  the write proceeds but is stamped `metadata.scope_guard="foreign"` and
  the response carries an in-band warning), `enforce` (foreign writes are
  rejected with the remedy: allowlist the scope or point demos at a
  dedicated instance via `FORGET_HOME`), `off`. Until now any stray
  request could silently create a new pool in the store — that is exactly
  how 339 demo/experiment memories contaminated the dogfood DB (the F4
  cleanup, 2026-07-31); doctor could only detect it after the fact.
  `doctor`'s foreign-pool check now shares the guard's verdict, so an
  allowlisted pool is never flagged and the two can't drift apart.

## 0.3.6 — 2026-07-31

The confidence release: everything a new user (or their inviter) needs to
know whether the install can be relied on. Precondition for inviting the
first external cohort.

### Diagnosability
- `forget-server doctor` — one-shot verdict over the whole wiring: server
  up, MCP endpoint answering, store integrity, scope contamination (the
  F4 class), Claude Code hooks. Every red line ships its own remedy.
  `--probe` does a write/read round-trip in a dedicated scope; `--report`
  builds a shareable diagnostic bundle containing zero memory content.
- `forget-server weekly` — the quiet first week becomes countable: this
  week's accruals, corrections (history preserved), and gate refusals by
  reason. Numbers only, no content.
- Update notice inside doctor only, notification only — applying is always
  the user's hand; development installs stay silent.

### Onboarding
- `install.sh` now ends with the doctor verdict. A red verdict exits 1 and
  says "send this output to whoever invited you" — a failed install
  becomes a diagnosable field report instead of a shrug.
- `docs/first-week.md` — cold-start expectations: the silence is designed,
  the reboot ritual, the token Q&A.

## 0.3.5 — 2026-07-31

The first releases authored substantially by the self-development loop:
both fixes came from field notes the loop filed about its own sessions,
each with a falsifiable prediction registered before the change.

### Context quality
- The session capsule's state lines now carry their recording age
  ("3시간 전 기록"), and past `MEM1_CAPSULE_STALE_HOURS` (default 24) a
  warning is inserted early enough to survive budget trimming: fast-layer
  state must be re-validated, not obeyed (loop cycle 2, friction F1).
- Task-state search results no longer receive a flat activeness boost on
  top of the recency bonus — off-topic active tasks used to ride ~0.16 of
  free score over recall gates and shadow relevant memories. Activeness
  is the capsule's job; search ranks by topic (loop cycle 3, friction F2).


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
