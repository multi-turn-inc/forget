# Codex adapter v1 audit

Date: 2026-08-28 KST

## Boundary

Codex now connects to the canonical user pool with `?profile=codex` and an
agent-bound `codex` Bearer credential. The profile exposes nine tools:

- `prepare_codex_context`
- `search_memories`
- `add_memory`
- `supersede_memory`
- `confirm_memory`
- `get_event_status`
- `record_context_outcome`
- `team_read`
- `team_note`

Generic `prepare_context_autopilot` and task-state tools are deliberately not
on the profile. A field audit showed generic autopilot selecting an unrelated
devloop task, recommending files absent from the BotBotBot checkout, and still
reporting sufficient context.

`prepare_codex_context` requires the client's absolute working directory,
derives one repository project key locally, applies the same project + global +
legacy layer used by hooks, and emits only bounded memory rows plus an untrusted
reference capsule. It never emits file or tool action suggestions. An
unresolvable working directory returns an empty `project_unresolved` result.

## Live evidence

- MCP `tools/list`: 9 tools.
- Authenticated `team_read.viewer`: `codex`.
- BotBotBot workdir resolved through `~/.forget/projects.json` alias to
  project `봇봇봇`.
- Live project context returned the canonical UI decision and zero rows tagged
  to another project.
- A synthetic memory written through the Codex credential was recalled through
  the Claude credential, then deleted; no active canary remains.

## Tests

- Forget full regression: `783 passed, 1 skipped`.
- Codex/profile/project/team targeted contract: `39 passed`.
- `forget-connect` core + CLI: `32 passed`; syntax lint passed.
- The package-wide hook-asset sync test remains independently blocked by a
  pre-existing dirty `hooks/forget_sessionstart.py` vs packaged asset drift from
  another active workstream; this adapter did not overwrite either file.

## Client rollout

`~/.codex/config.toml` uses the Codex profile and `FORGET_CODEX_TOKEN`.
`~/.codex/AGENTS.md` uses the Codex-specific cwd-bound rules. Existing Codex
sessions retain their startup MCP schema; a full Codex restart is required to
replace the old 46-tool surface with the new 9-tool profile.
