# forget-connect

Connect Claude Code, Codex, and Claude Desktop to [Forget](https://multi-turn.ai)
without overwriting the MCP servers or global instructions you already have.

```bash
npx forget-connect --user-id <memory-user> --app-id <project>
```

The guided flow detects installed clients, asks for a hosted Forget API key
with hidden input, and then:

- merges a `forget` entry into each selected MCP config;
- installs a marked memory rule in Claude Code's `CLAUDE.md` and Codex's
  `AGENTS.md`, so past-decision questions call memory before searching files;
- creates a one-time adjacent `.forget-backup` before changing an existing
  file; and
- writes through temporary files and renames them into place.

Other MCP servers and text outside the marked rule block are preserved. Invalid
JSON or a damaged marker block aborts before any selected client is changed.

The two scope values are part of the connection, not search-time hints. They
produce `/mcp/<app-id>/http/<user-id>` so a new client resumes the intended
project instead of the legacy default scope. For hosted continuity, always set
both. A bare hosted connection remains available for compatibility but prints a
warning, and `doctor` will not call it continuity-ready.

## Non-interactive use

Pass the key through the environment, not a command-line flag (command-line
arguments can be visible to other local processes):

```bash
FORGET_API_KEY=... npx forget-connect \
  --user-id my-user \
  --app-id my-project \
  --client claude-code,codex
```

`FORGET_USER_ID` and `FORGET_APP_ID` are equivalent to the two scope flags.

For a local, unauthenticated Forget server:

```bash
npx forget-connect \
  --url http://localhost:8000/mcp \
  --no-auth \
  --client all
```

Use `FORGET_MCP_URL` instead of `--url` if preferred.

## Inspect or remove

```bash
npx forget-connect status
npx forget-connect doctor --client codex
npx forget-connect disconnect
```

`doctor` is non-mutating. It checks that each selected client has the generated
transport shape, expected URL and authorization, plus the current full
instruction block (not only its markers). Only after those local checks pass
does it verify the scoped endpoint identity and perform MCP initialize and
tools/list against that URL. It fails when hosted scope is absent or mismatched,
or when the continuity tools for search, write, context, outcome, and task state
are missing. Add `--json` for automation or `--timeout 30` on a slow network.
No authorization value or memory content is printed.

`disconnect` removes only the `forget` MCP entry and the marked Forget rules
block. It does not restore backups or remove unrelated config.

## Options

```text
--client <ids>       claude-code,codex,claude-desktop,all
--url <url>          MCP URL (default: https://api.multi-turn.ai/mcp)
--user-id <id>       Memory user scope; pair with --app-id
--app-id <id>        Project/app scope; pair with --user-id
--no-auth            Do not install a Bearer token
--no-rules           Do not manage CLAUDE.md or AGENTS.md
--no-migrate-enacta  Keep matching legacy config and rule blocks
--dry-run            Show which files would change
--timeout <seconds>  Doctor network timeout, from 1 to 60
--json               Print doctor results as JSON
-y, --yes            Use detected clients, or all if none are detected
```

By default, a legacy `enacta` entry is removed only when it points to the same
MCP URL being installed. Its marked instruction block is upgraded to the
Forget block. Use `--no-migrate-enacta` to keep both.

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
