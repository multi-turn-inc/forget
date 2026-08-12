# forget-connect

Connect Claude Code, Codex, and Claude Desktop to a local
[Forget](https://github.com/multi-turn-inc/forget) memory server without
overwriting the MCP servers or global instructions you already have.

```bash
npx forget-connect
```

By default this targets the local server at `http://localhost:8000` and
scopes each client to its own memory pool at
`/mcp/<client>/http/<os-username>` (for example
`/mcp/claude-code/http/junghun`) — your memories stay on your machine and
stay isolated per user and per client. Pass `--no-scope` for the shared
unscoped `/mcp` endpoint. The guided flow detects installed clients and
then:

- merges a `forget` entry into each selected MCP config;
- installs a marked memory rule in Claude Code's `CLAUDE.md` and Codex's
  `AGENTS.md`, so past-decision questions call memory before searching files;
- creates a one-time adjacent `.forget-backup` before changing an existing
  file; and
- writes through temporary files and renames them into place.

Other MCP servers and text outside the marked rule block are preserved. Invalid
JSON or a damaged marker block aborts before any selected client is changed.

## Non-interactive use

```bash
npx forget-connect --client claude-code,codex --yes
```

Use `FORGET_MCP_URL` or `--url` for a server on another port or host. A Bearer
token (`FORGET_API_KEY`) is only sent over HTTPS; over loopback HTTP the CLI
connects without a token and says so.

## Hosted service (legacy)

The managed service remains available behind an explicit flag while it is
phased out in favor of local-first:

```bash
FORGET_API_KEY=... npx forget-connect --hosted \
  --user-id <memory-user> --app-id <project>
```

Pass the key through the environment, not a command-line flag (command-line
arguments can be visible to other local processes). `FORGET_USER_ID` and
`FORGET_APP_ID` are equivalent to the two scope flags. The scope values are
part of the connection, not search-time hints: they produce
`/mcp/<app-id>/http/<user-id>` so a new client resumes the intended project.
A bare hosted connection prints a warning, and `doctor` will not call it
continuity-ready.

## Inspect or remove

```bash
npx forget-connect status
npx forget-connect doctor --client codex
npx forget-connect disconnect
```

`doctor` is non-mutating. It checks that each selected client has the generated
transport shape, expected URL and authorization, plus the current full
instruction block (not only its markers). Only after those local checks pass
does it perform MCP initialize and tools/list against that URL. For hosted
connections it also verifies the scoped endpoint identity. Add `--json` for
automation or `--timeout 30` on a slow network. No authorization value or
memory content is printed.

`disconnect` removes only the `forget` MCP entry and the marked Forget rules
block. It does not restore backups or remove unrelated config.

## Options

```text
--client <ids>       claude-code,codex,claude-desktop,all
--url <url>          Exact MCP URL to install (default base: http://localhost:8000/mcp)
--hosted             Use the managed Forget service (legacy)
--user-id <id>       Memory user scope; pair with --app-id
--app-id <id>        Project/app scope; pair with --user-id
--no-scope           Install the shared unscoped /mcp endpoint (legacy behavior)
--no-auth            Do not install a Bearer token
--no-rules           Do not manage CLAUDE.md or AGENTS.md
--no-hooks           Do not install Claude Code memory hooks
--no-proxy           Do not wire the local capture proxy (macOS only)
--no-migrate-enacta  Keep matching legacy config and rule blocks
--dry-run            Show which files would change
--timeout <seconds>  Doctor network timeout, from 1 to 60
--json               Print doctor results as JSON
-y, --yes            Use detected clients, or all if none are detected
```

By default, a legacy `enacta` entry is removed when it points to the URL being
installed or to the hosted service. Its marked instruction block is upgraded
to the Forget block. Use `--no-migrate-enacta` to keep both.

## Files managed

| Client | MCP config | Instruction file |
|---|---|---|
| Claude Code | `~/.claude.json` | `~/.claude/CLAUDE.md` |
| Codex | `$CODEX_HOME/config.toml` or `~/.codex/config.toml` | `$CODEX_HOME/AGENTS.md` or `~/.codex/AGENTS.md` |
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` | — |
| Claude Desktop (Windows) | `%APPDATA%/Claude/claude_desktop_config.json` | — |
| Claude Desktop (Linux) | `~/.config/Claude/claude_desktop_config.json` | — |

## Development

```bash
npm test
npm run lint
npm pack --dry-run
```

## Hooks (Claude Code)

`forget-connect` installs four harness hooks so memory arrives without being asked:

- **SessionStart** — injects a context capsule (open tasks, next actions, constraints)
- **UserPromptSubmit** — pushes memories relevant to the current turn, with trust lights
  (green = act on it, yellow = confirm first, red = superseded), and raises a
  conflict-zone alert when the conversation enters territory with a correction history
- **PreCompact / SessionEnd** — captures the session into the ledger and records
  whether offered memories were actually used (the outcome flywheel)

Hooks are judgment-free and fail-open: if the Forget server is down they exit
silently and never block your session. They need `python3` on PATH.
Skip them with `--no-hooks`; `disconnect` always removes them. Foreign hooks
registered by other tools are preserved byte-for-byte.

## Capture proxy (macOS)

On macOS, connect also wires the zero-config capture proxy when `forget-proxy`
(from `pip install 'forget-ai[server]'`) is on PATH:

- registers launchd services `ai.forget.proxy` (KeepAlive, port 8377) and
  `ai.forget.proxy.watchdog` (60s health checks)
- sets `env.ANTHROPIC_BASE_URL = http://127.0.0.1:8377` in
  `~/.claude/settings.json`. An existing custom base URL is chained as the
  proxy's `--upstream`, never discarded; a settings file we cannot parse
  skips the wiring entirely with a warning.

If the proxy stops answering for three consecutive checks, the watchdog
removes the override (only the value we wrote) and restores your original
base URL — losing capture is cheaper than losing Claude. When the proxy
recovers, the override returns unless you changed the value yourself.
Skip with `--no-proxy`; `disconnect` always unwires and removes the services.
