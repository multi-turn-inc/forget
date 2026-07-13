# ~~forget~~

**Memory for your AI. It forgets the junk, keeps what matters.**

Every LLM session starts from zero. Forget gives your AI a long-term memory
that it actually maintains: an observation gate decides what is worth keeping
at all, stale facts get retired non-destructively when new ones supersede
them, and a consolidation loop keeps the store honest while you sleep.

The secret is in the name. Good memory is not storing everything — it is
forgetting well.

- **Forget re-explaining.** Your AI remembers your decisions, preferences,
  and context across sessions and across tools.
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
- **Supersede** — when a fact changes ("we switched payment providers"),
  the old memory is demoted, not deleted. History stays auditable.
- **Temporal rerank** — recent facts outrank stale ones at recall time.
- **Consolidation** — a background pass merges, dedupes, and retires.
- **Single file** — everything lives in one SQLite database. No vector DB,
  no external services. Dependencies: FastAPI and httpx. That's it.

## Quickstart

```bash
pip install forget-ai[server]
uvicorn forget.server:app --port 8000
```

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

Forget speaks MCP over streamable HTTP at `/mcp` — 41 tools including
`search_memories`, `add_memory`, `supersede_memory`, and `assemble_context`.

Connect the local server started above without hand-editing config files:

```bash
npx forget-connect
```

The CLI preserves other MCP servers, backs up existing files once, and installs
the marked Claude Code/Codex instruction layer described below. The legacy
hosted service is still reachable with
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

> **Tip — make agents actually use it.** Clients with a shell (Claude Code,
> Codex) tend to grep the repo instead of calling memory tools. Add a rule to
> your global instruction file (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`):
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
