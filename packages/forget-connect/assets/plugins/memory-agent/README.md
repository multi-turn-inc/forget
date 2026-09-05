# Memory Agent plugin manifests

This directory is the provider-neutral plugin payload. Codex and Claude Code
discover the same `skills/memory-agent/SKILL.md`; `forget-connect` owns the
credential-bound MCP URL and lifecycle-hook installation because those values
are per user and must never be baked into a distributable manifest.

The catalog is untrusted metadata. Consultation still requires an exact quote,
explicit approval, a signed persisted receipt, and optional grant revocation.
