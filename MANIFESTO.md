# I don't want to share my prompts

You tell your AI things you don't tell your colleagues. Half-formed ideas.
Salary numbers. The real reason the project slipped. What you're afraid of.
That was always true of prompts — and prompts, at least, were transient.

Memory changed the deal. Every AI product now ships a memory feature, and a
memory is not a prompt: it is a curated, compounding profile of you —
your decisions, your preferences, your patterns — stored durably on
someone else's server, readable by whoever operates it.

Three facts about that arrangement:

**1. It is not privileged.** In February 2026, a US federal court ruled that
a defendant's conversations with an AI assistant were not protected by
attorney-client privilege or work product — because the provider's terms of
service said user data could be used for training and disclosed to third
parties. What you tell an AI is, legally, what you told a company.

**2. Your memory vendor will change hands.** Rewind promised local-first
privacy, pivoted to the cloud, and was acquired — its remaining users were
migrated onto the acquirer's terms of service overnight. Every startup
holding your memories is one term sheet away from being someone else's
database.

**3. The platforms will not fix this.** A model provider cannot end-to-end
encrypt memory its own servers must read, and it will never port your
memory to a competitor's tool. Native memory features are silos by design.

Your model provider already reads your prompts. There is no reason your
memory layer should be a second reader.

## What we're building

Forget is an open-source memory engine that runs on your machine. The
extraction, the search, the consolidation — all of it happens locally, in a
single SQLite file you own. That part exists today.

What's coming next is sync that cannot betray you:

- **End-to-end encrypted.** Memories are encrypted on your device before
  they touch our servers. We store ciphertext and nothing else. We cannot
  read your memories. Neither can whoever acquires us. Neither can a
  subpoena.
- **Encrypted all the way down.** Embeddings are encrypted too. A vector is
  a paraphrase of your text — services that encrypt the words and upload
  the vectors in plaintext are selling you a lock with no door.
- **Layered by design.** Memories live in scopes — personal, work, per
  project — each under its own key. A coding session can be granted your
  work layer and nothing else. Access control enforced by mathematics, not
  by a policy table.
- **Portable.** Forget speaks MCP, so the same memory follows you across
  Claude Code, Cursor, and whatever you adopt next. Your memory belongs to
  you, not to the tool that happened to collect it.
- **No passwords.** Devices hold keys; new devices are approved by ones you
  already trust; a recovery code is your fallback. Nothing a server breach
  can spend.

## What we won't pretend

Honesty is the product, so here are the boundaries:

- The model you use still sees plaintext — it has to, to use your memories.
  Encryption protects you from storage providers (including us), not from
  the AI you deliberately hand a memory to. You choose who reads; that's
  the whole point.
- If extraction runs through a cloud LLM you configure, that provider sees
  what it processes. We default to local, and we label the trade-off
  instead of hiding it.
- If you lose your devices and your recovery code, your memories are gone.
  We can't reset what we can't read. That is the price of the guarantee,
  and we won't blur it.

## The name

Good memory is not storing everything — it is forgetting well. We built an
engine that forgets junk and keeps what matters. Now we're extending the
same principle to trust: **the safest secret-keeper is one with nothing to
tell.** We can't remember what you tell us. That's the feature.

---

**Today:** run the engine locally — it's open source, and it works now.
**Next:** end-to-end encrypted sync. Join the waitlist.
**Building AI for therapy, law, or health?** Your users' memories are your
liability. We'd like to talk — we're taking design partners.
