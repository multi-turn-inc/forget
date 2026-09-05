# Memory Agent cross-client prototype — E2E evidence

Date: 2026-08-30 (Asia/Seoul)  
Status: **PASS for the local, zero-price prototype boundary**

## Proven boundary

Codex and Claude Code can use one personal Forget vault while retaining
different authenticated principals, client identities, tool profiles, grants,
and receipts. A reviewed Memory Agent snapshot can be discovered, quoted,
explicitly approved, consulted, verified, and revoked through the same six MCP
tools:

```text
catalog_search
  → product_quote
  → grant_create (approve=true only after exact user approval)
  → agent_consult (unique request_id)
  → receipt_verify
  → grant_revoke
```

This pass does not include billing, paid model calls, a public deployment,
grant expansion, commit, or push.

## Identity model

| Concern | Binding |
|---|---|
| Personal continuity | one scoped vault route: `/mcp/forget/http/<vault>` |
| Provider surface | `profile=codex` or `profile=claude` |
| Acting principal | `agent_principal` from the authenticated API key |
| Vault authority | `owner_user_id` from the same API key; must match the route |
| Project | authenticated project context plus the canonical `forget` app scope |
| Consultation | exact product, purpose, quota, client, principal, vault, expiry |

The route path is a selector, not proof of identity. Supplying a different
vault in a URL or omitting the credential-bound vault fails closed.

## Publication and disclosure gates

- Draft creation records publisher principal and publisher vault provenance.
- Publication requires an explicit reviewed item; draft rows are absent from
  catalog results.
- Only ownerless source rows are eligible. `self`/owner-sourced memories are
  non-sale even if they also carry an app tag.
- Review copies an immutable curated snapshot instead of serving the live
  personal memory table.
- PII gates run at review and again at serving.
- Consultation discloses at most three minimal passages or pointers.
- A signed receipt is persisted before an allowed result is returned. If
  persistence fails, the result is not served.
- Idempotent request IDs cannot be rebound; quota and revocation are enforced.
- Every quote and receipt in this prototype has `price_units`/`charged_units`
  equal to zero.

Publisher creation/review/publish is intentionally a server-side module API in
this prototype. It is not yet a public publisher endpoint or marketplace UI.

## Client packaging

`forget-connect` installs:

- the same canonical vault with provider-specific query profiles;
- the same `memory-agent` skill for Codex and Claude Code;
- Codex `.codex-plugin/plugin.json` and Claude `.claude-plugin/plugin.json`
  payloads with no baked-in vault URL, key, or hook path;
- client-specific lifecycle registrations over shared fail-open Python scripts;
- only files it owns, preserving foreign hook groups and user-owned skills.

Removing one client leaves shared hook scripts in place while the other still
references them. Removing the last client removes the shared scripts. Local
Bearer auth is opt-in and loopback-only (`--local-auth`); a leftover
`FORGET_API_KEY` is otherwise ignored for HTTP loopback.

## E2E construction

The combined E2E test creates separate credential-bound keys for
`claude.connector` and `codex.connector`, runs the real `forget-connect` binary
twice in an isolated HOME, then reads the exact generated `.claude.json` and
`config.toml` URLs and Authorization values. Those artifacts drive the real
FastAPI MCP routes through the complete six-tool flow.

Both clients receive the same curated result. Their receipts remain distinct:

- Claude: `client_id=claude-code`, principal `claude.connector`
- Codex: `client_id=codex`, principal `codex.connector`

This proves the connector-to-server contract without invoking a paid provider
model. It does not claim a live hosted Codex or Claude inference run.

## Verification commands and observed results

From the Forget repository root:

```bash
.venv/bin/pytest -q tests/test_memory_agent_mcp_e2e.py
# 3 passed, 1 Starlette TestClient deprecation warning

.venv/bin/pytest -q
# 854 passed, 1 skipped, 1 warning in 34.11s

cd packages/forget-connect
npm run lint
# PASS

npm test
# 79 passed, 0 failed

npm pack --dry-run --json
# PASS; 27 files, 70,975-byte archive; plugin/skill assets present; no pyc
```

Manifest and skill validators:

```bash
uv run --with pyyaml python \
  /Users/junghunkim/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py \
  packages/forget-connect/assets/plugins/memory-agent
# Plugin validation passed

uv run --with pyyaml python \
  /Users/junghunkim/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  packages/forget-connect/assets/skills/memory-agent
# Skill is valid
```

## Safe local exercise

Use a purpose-created, vault-bound local API key. Never put the key in the
command line:

```bash
export FORGET_API_KEY='…'

npx forget-connect \
  --client claude-code,codex --yes \
  --user-id '<vault-id>' --app-id forget \
  --local-auth --no-proxy

npx forget-connect doctor --client claude-code,codex --local-auth

npx forget-connect disconnect --client claude-code,codex --no-proxy
```

## Known remaining production work

1. Publisher-facing authenticated APIs and review UI.
2. Public catalog moderation, abuse handling, and key rotation policy.
3. Billing/settlement only after the zero-price safety model remains stable.
4. Hosted end-to-end runs against real Codex and Claude clients.
5. Replace the deprecated Starlette/httpx TestClient compatibility layer.

The local signing key and SQLite persistence are appropriate for this test
boundary, not a production trust root.
