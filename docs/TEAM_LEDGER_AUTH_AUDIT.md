# Team ledger authenticated-principal audit

Date: 2026-08-28 KST

## Verdict

- Server/runtime contract: **PASS**
- Python regression: **PASS** (`752 passed, 2 skipped`)
- Live restart/idempotency proof: **PASS**
- Restarted Codex desktop client: **PASS**

## Security boundary

`author` is no longer caller input. An active `api_keys` row binds one Bearer
credential to `agent_principal`; FastAPI auth places that principal in the
request auth context and the MCP route copies it into the tool context.
Unbound connections and roster-unknown principals cannot call `team_read` or
`team_note`. `?principal=` is only a matching assertion; `?ptoken=` is rejected
because secrets do not belong in URLs.

Ownerless `forget-dev` rows are created only inside the `team_note` authorized
call-chain. Generic MCP memory tools and raw REST writes cannot bypass the PII,
link, lifecycle, or idempotency checks. Team items are append-only; update,
generic supersede, confirm, feedback, single delete, and bulk delete reject them.

## Structured ledger contract

- Full UUIDs are returned in structured `items[]`.
- Derived statuses: `open`, `answered`, `superseded`, `recorded`.
- Addressed items can be closed only by the addressed principal; duplicate
  closure is rejected.
- Only an item's author can create its `supersedes` link.
- Idempotency reservation key:
  `(project_id, ledger_app, authenticated principal, idempotency_key)`.
- The payload fingerprint covers `kind`, sanitized text, `reply_to`,
  `addressed_to`, and `supersedes`; same payload replays, changed payload
  conflicts.
- Consensus writes disable Hebbian merge and episodic rewriting. Even identical
  text with different keys remains two immutable protocol records.
- Text is checked after sanitization at 2,000 characters and 8,000 UTF-8 bytes.

## Test receipts

Commands:

```text
uv run pytest -q tests/test_team_ledger_tools.py tests/test_team_credential_binding.py
# 24 passed

uv run pytest -q
# 752 passed, 2 skipped

bun build .pi/extensions/forget.ts --target=node --outfile=/tmp/forget-extension-check.js
# bundle succeeded
```

The contract suite covers credential attribution, missing credentials, query
spoofing, removal of `author` from `tools/list`, raw/generic bypasses, full IDs,
validated close/supersede authority, legacy unverified links, append-only
mutation guards, PII/control/size bounds, principal-scoped full-payload
idempotency, failure cleanup, and concurrent reservation.

## Live cross-agent and restart receipt

`scripts/verify_team_ledger_live.py create` produced:

```json
{
  "question_id": "79546151-e983-40a0-8f0b-01d8601a1df9",
  "answer_id": "783c53de-660a-45df-b120-c378b246ebd2",
  "status": "answered",
  "spoof_query_http": 403,
  "query_secret_http": 400,
  "raw_bypass_http": 403,
  "secrets_printed": false
}
```

After `launchctl kickstart -k gui/501/ai.forget.server`, running the verifier in
`verify` mode returned the same two UUIDs, both as idempotent replays, and the
question remained `answered`. All three credentials (`claude-exec`, `gpt-live`,
`selfharness`) returned their own principal in `team_read.viewer`.
An operator-form nested app filter was rejected in both MCP and anonymous REST,
and a generic event lookup could not expose the team-note ADD payload.

The final authenticated handoff was written without an `author` argument as
`gpt-live`, item `79307a10-706c-4e81-b401-1d08b6aac1ad`, addressed to
`claude-exec`.

## Client credential handling

- API keys exist once per principal and key files are mode `0600`.
- The current values are also stored in macOS Keychain service
  `ai.forget.team-ledger`.
- Codex uses `bearer_token_env_var = "FORGET_TEAM_GPT_LIVE_TOKEN"`.
- Claude `.mcp.json` uses `Authorization: Bearer
  ${FORGET_TEAM_CLAUDE_EXEC_TOKEN}`; no secret is committed.
- `ai.forget.team-client-env` loads those environment variables from Keychain
  at login and when `~/.forget/keys` changes. Its last run exited `0`.
- The self-harness reads its separate mode-`0600` key and calls authenticated
  `team_read`/`team_note`; its TypeScript bundle succeeds.
- A fresh `codex mcp list` process reported Forget enabled with `Auth: Bearer
  token` and the expected environment-variable name. `claude mcp get forget`
  reported the project MCP connected with the environment-expanded Authorization
  header.
- `bun run scripts/verify_selfharness_extension.ts` executed the real extension,
  stored a note whose server-bound author was `selfharness`, and observed that
  authenticated `team_read` content entered the wake system prompt.

During validation, one diagnostic command printed two client token values into
the local execution transcript. Both credentials were immediately revoked and
replaced; the revoked values now return HTTP `401`. The self-harness credential
was also rotated because the first database backup briefly had mode `0644`.
No credential value appears in the repository or client configuration.

## Backups

- Pre-final-deploy: `~/.forget/backups/forget-before-ledger-deploy-20260828-0135.sqlite3`
  — quick-check `ok`, mode `0600`, and all team credentials forced inactive so
  restoring it cannot reactivate the exposed keys.
- Post-rotation: `~/.forget/backups/forget-after-ledger-auth-20260828.sqlite3`
  — quick-check `ok`, mode `0600`, three active principal bindings.

One empty test-only idempotency reservation left when the pre-fix live path
Hebbian-merged duplicate protocol text was removed by exact
principal/key/null-event/null-memory match; it is recoverable from the
pre-final-deploy backup.

## BotBotBot authority boundary

The public BotBotBot tree remained at commit `892f808`; this pass did not edit
its runtime or authority policy. Its existing dirty documentation work was
preserved. A fresh `npm run verify` completed with all 16 test files and
368/368 tests passing, followed by TypeScript checking and a production Vite
build. The prior boundary remains intact: Forget is the policy/receipt source of
truth and BotBotBot's DurableJournal is an audit mirror, not a second policy
engine.

## Final Codex client acceptance

**PASS after full Codex restart.** The real desktop task observed all startup
snapshot requirements:

1. `team_read` succeeded and returned `viewer="gpt-live"`.
2. The loaded `team_note` schema omitted `author` and exposed the structured
   link/idempotency fields.
3. A note submitted without `author` was stored as `gpt-live`, item
   `b8d02e2e-122f-4844-95b4-7dd94e7e609b`, event
   `6cc55bdf-abde-4428-a8c6-edc1a9bea76f`.
4. Repeating the exact payload with `gpt-live-codex-restart-final-v1` returned
   the same item/event with `idempotent_replay=true` and created no duplicate.
