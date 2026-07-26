# ~~forget~~

**Memory for your AI. It forgets the junk, keeps what matters.**

[![PyPI](https://img.shields.io/pypi/v/forget-ai?style=flat-square&color=d31126&label=forget-ai)](https://pypi.org/project/forget-ai/)
[![npm](https://img.shields.io/npm/v/forget-connect?style=flat-square&color=d31126&label=forget-connect)](https://www.npmjs.com/package/forget-connect)
[![LongMemEval](https://img.shields.io/badge/LongMemEval-81.8%25_·_local_pipeline_76.2%25-1a1c20?style=flat-square)](https://forget.sh/#benchmark)
[![License](https://img.shields.io/badge/license-Apache--2.0-71767d?style=flat-square)](LICENSE)

<a href="https://forget.sh"><img src="https://forget.sh/og.png" alt="forget — tell Claude Code once, Cursor remembers. Local-first memory for AI agents, 81.8% on LongMemEval." width="100%"></a>

On [LongMemEval](https://github.com/xiaowu0162/LongMemEval), the standard
long-term-memory benchmark (full 500-question set, GPT-4o reader and judge):

| configuration | accuracy |
|---|---|
| GPT-4o full-context, no memory system ([paper baseline](https://arxiv.org/abs/2410.10813)) | 60.6% |
| **Forget, fully local memory pipeline** (Qwen 14B observer) | **76.2%** |
| **Forget, best configuration** (GPT-4o observer) | **81.8%** |
| GPT-4o oracle — evidence sessions handed to the reader ([paper ceiling](https://arxiv.org/abs/2410.10813)) | 87.0% |

Knowledge-update questions, where memory products usually fail: **92.3%**
(best config). Our weakest category, so you don't have to dig for it:
single-session-preference, 43.3%. Per-question outputs and run configs are
in [`research/longmemeval/runs/`](research/longmemeval/runs/).

Every LLM session starts from zero. Forget gives your AI a long-term memory
that it actually maintains: an observation gate decides what is worth keeping
at all, stale facts get retired non-destructively when new ones supersede
them, and a consolidation loop keeps the store honest while you sleep.

The secret is in the name. Good memory is not storing everything — it is
forgetting well.

- **Forget re-explaining.** Your AI remembers your decisions, preferences,
  and context across sessions and across tools.
- **Forget asking.** Memory arrives on its own: a context capsule opens each
  session, relevant memories are pushed mid-conversation, and a conflict
  alert fires if you're about to act on a fact that was later corrected.
- **Forget context limits.** Durable facts live outside the window and come
  back only when relevant.
- **Forget trusting us.** Everything runs on your machine, in one SQLite
  file you own. End-to-end encrypted sync is next — built so that we
  cannot read what we carry. ([Why this matters →](MANIFESTO.md))
- **Forget nothing** — that matters.

## How it works

```
conversation ──▶ observation gate ──▶ durable facts (SQLite)
                     │                     │
                     ▼                     ▼
               "junk, skip it"      search ◀── temporal rerank
                                           │
              consolidation loop ◀── supersede (non-destructive)
```

- **Observation gate** — extraction keeps only durable, useful facts.
  Questions, chit-chat, and assistant filler never become "memories".
- **Supersede / confirm** — when a fact changes, the old memory is demoted
  and linked to its replacement, not deleted; when an unverified claim gets
  its receipt, `confirm_memory` promotes it. History stays auditable.
- **Trust labels** — every memory carries provenance (who vouches for it)
  and recall returns a permission: **green** (user-stated or tool-observed)
  = safe to act on, **yellow** (agent-inferred) = verify first, **red**
  (superseded) = reference only.
- **Temporal rerank** — recent facts outrank stale ones at recall time.
- **Consolidation** — a background pass merges, dedupes, and retires.
- **Single file** — everything lives in one SQLite database. No vector DB,
  no external services. Dependencies: FastAPI and httpx. That's it.

## Quickstart

```bash
pip install 'forget-ai[server]'
forget-server install-service   # login service (launchd/systemd) — survives reboots
# or, to try it in the foreground first:
forget-server run
```

`forget-server status` tells you what's true; `forget-server uninstall-service`
removes it. The server binds to localhost only.

Store and recall:

```bash
curl -X POST localhost:8000/v1/memories/ \
  -H 'Content-Type: application/json' \
  -d '{"text": "We settled on Paddle for payments.", "user_id": "me"}'

curl -X POST localhost:8000/v1/memories/search/ \
  -H 'Content-Type: application/json' \
  -d '{"query": "what did we pick for payments?", "user_id": "me"}'
```

## Connect your AI (MCP)

Forget speaks MCP over streamable HTTP at `/mcp` — 42 tools including
`search_memories`, `add_memory`, `supersede_memory`, `confirm_memory`, and
`prepare_context_autopilot`.

Connect the local server started above without hand-editing config files:

```bash
npx forget-connect
```

The CLI preserves other MCP servers, backs up existing files once, installs
the marked instruction layer (Claude Code / Codex / Claude Desktop), and —
for Claude Code — installs the **hooks layer**: a session-start context
capsule, per-turn push recall with conflict-zone alerts, and session capture
feeding a usage-outcome flywheel. Hooks are fail-open (a stopped server
never blocks a session), preserve any foreign hooks byte-for-byte, and are
skippable with `--no-hooks`. `npx forget-connect doctor` diagnoses config,
rules, hooks, and the MCP connection; `disconnect` reverses everything.

The legacy hosted service remains reachable with
`npx forget-connect --hosted --user-id <memory-user> --app-id <project>`
while it is phased out in favor of local-first.

Manual configuration:

**Claude Code**

```json
{ "mcpServers": { "forget": { "type": "http", "url": "http://localhost:8000/mcp" } } }
```

**Codex** (`~/.codex/config.toml`)

```toml
[mcp_servers.forget]
url = "http://localhost:8000/mcp"
```

**Claude Desktop** (bridge via mcp-remote, `claude_desktop_config.json`)

```json
{ "mcpServers": { "forget": { "command": "npx",
  "args": ["-y", "mcp-remote@latest", "http://localhost:8000/mcp"] } } }
```

> **Tip — make agents actually use it.** `npx forget-connect` handles this:
> it installs both the instruction rules *and* the hooks that push memory
> into sessions unasked. If you configure manually instead, at minimum add
> to your global instruction file (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`):
> *"ALWAYS call `search_memories` on `forget` FIRST — before any shell
> command — whenever the user refers to their own past decisions."*

## Security

Forget is local-first: with no configuration it binds to localhost and
accepts unauthenticated requests. Before exposing it to a network, set:

```bash
FORGET_REQUIRE_AUTH=true
FORGET_API_KEY=<your key>        # sent as "Authorization: Bearer <key>"
```

## Compatibility

The REST surface and MCP tool names are API-compatible with mem0 and
OpenMemory clients — point an existing client at Forget and it works.

## Sync — end-to-end encrypted (in design)

The engine is local today. What's next is multi-device sync that cannot
betray you: memories — and their embeddings — are encrypted on your device
before they touch a server. The server stores ciphertext and nothing else.
Not us, not an acquirer, not a subpoena.

The reasoning is in [MANIFESTO.md](MANIFESTO.md); the key hierarchy, record
format, and device-auth design are in
[docs/vault-design.md](docs/vault-design.md).

**Building AI for therapy, law, or health?** Your users' memories are your
liability. We're taking design partners — founder@multi-turn.ai.

## License

Apache-2.0.
