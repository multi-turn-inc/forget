# Changelog

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
