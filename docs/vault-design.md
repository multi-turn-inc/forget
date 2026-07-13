# Vault: key hierarchy, encrypted records, and device auth

Status: DRAFT v0.1 (2026-07-13) — design for the E2EE sync layer.
The local engine is unchanged: extraction, search, and consolidation keep
running against the local SQLite database. This document specifies what
leaves the device, and under which keys.

## Goals

- The sync server stores **only ciphertext**. It can never read memory
  text, embeddings, entities, categories, or metadata — not by policy, by
  construction.
- **Scoped access**: memories belong to scopes (personal, work, per
  project). Each scope has its own key, so a session, device, or partner
  can be granted one layer without unlocking the vault.
- **Multi-device** without passwords: devices hold keys; new devices are
  approved by existing ones; a recovery code is the fallback of last
  resort.
- **No hand-rolled cryptography.** libsodium (PyNaCl) primitives only.

## Non-goals

- Protecting memories from the model the user deliberately grants access
  to. The model must read plaintext to use a memory; encryption protects
  against storage operators (including us), not against the user's own AI
  session.
- Server-side semantic search over ciphertext. Search is local; the server
  is a blind replication log.
- Protecting a device the attacker controls while it is unlocked.

## Key hierarchy

```
Recovery Code (printed once, mandatory)          Device A          Device B
        │ Argon2id                                  │ keychain        │ keychain
        ▼                                           ▼                 ▼
  Recovery Key ──wraps──▶  Master Key  ◀──wrapped to── X25519_A, X25519_B
                               │
                 ┌─────────────┼─────────────┐
                 ▼             ▼             ▼
             DEK(personal) DEK(work)   DEK(project-X)     ── random, MK-wrapped
                 │             │             │
                 ▼             ▼             ▼
          records: XChaCha20-Poly1305(plaintext, DEK, nonce, AAD)
```

- **Device keys.** On first run each device generates an Ed25519 signing
  keypair (server auth) and an X25519 keypair (key exchange). Private keys
  live in the OS keychain (macOS Keychain, libsecret, DPAPI); file-based
  fallback is 0600 with a loud warning.
- **Master Key (MK).** 32 random bytes, created once per vault. Never
  stored or transmitted in the clear. Server holds one copy per enrolled
  device, sealed to that device's X25519 public key (`crypto_box_seal`),
  plus one copy wrapped under the Recovery Key.
- **Recovery Code.** Generated at vault creation, base32, ~29 chars with
  checksum (1Password Secret Key style). Argon2id (`crypto_pwhash`,
  MODERATE limits) derives the Recovery Key. The setup flow does not
  proceed until the user confirms the code — losing all devices plus the
  code means the vault is unrecoverable, by design.
- **Scope keys (DEKs).** 32 random bytes per scope, wrapped by MK
  (`crypto_aead_xchacha20poly1305_ietf` with a derived subkey). Random
  rather than HKDF-derived so a scope can be rotated or shared without
  touching MK. Sharing a scope = wrapping its DEK to a recipient's X25519
  key; revocation = rotate DEK, lazily re-encrypt.

## Record encryption

Everything semantic is encrypted: `memory` text, `embedding` (a vector is
a paraphrase of the text — shipping it in plaintext would void the whole
guarantee), `categories`, `metadata`, entity links, and history events.
The server sees only routing envelope fields.

```
plaintext   = msgpack({memory, embedding, categories, metadata, entities, hash, ...})
nonce       = random 24 bytes
aad         = record_id || scope_id || schema_ver || seq
ciphertext  = XChaCha20-Poly1305(plaintext, DEK[scope], nonce, aad)
```

AAD binds the ciphertext to its envelope so the server cannot replay a
record under a different scope or position. Optional length padding to
size buckets (256 B steps) blunts size-correlation analysis.

v1 packs text and embedding into one ciphertext per record. The
alternative — separate ciphertexts under distinct HKDF info strings, so
embeddings can re-sync alone on a model change — is deferred: model
changes get a dedicated re-embed op instead.

**Scope names are data, not routing.** The server sees random scope
UUIDs only. Human-readable names ("work", "project-X") live in a small
encrypted *scope manifest*, sealed under an MK-derived manifest key —
even the shape of a user's life (how they label their layers) stays
unreadable. The sync scope unit defaults to the engine's `project_id`
in v1.

## Sync data model (server)

The server-side `memories` table is replaced, for synced vaults, by an
append-only oplog. No text column, no embedding column — those exist only
inside `ciphertext`.

```sql
CREATE TABLE encrypted_records (
    account_id  TEXT NOT NULL,
    seq         INTEGER NOT NULL,          -- per-account monotonic
    record_id   TEXT NOT NULL,             -- opaque UUID
    scope_id    TEXT NOT NULL,             -- opaque scope UUID
    schema_ver  INTEGER NOT NULL,
    nonce       BLOB NOT NULL,
    ciphertext  BLOB NOT NULL,
    deleted     INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (account_id, seq)
);

CREATE TABLE wrapped_keys (                -- MK sealed per device / recovery
    account_id  TEXT NOT NULL,
    holder_id   TEXT NOT NULL,             -- device id or 'recovery'
    wrapped_mk  BLOB NOT NULL,
    PRIMARY KEY (account_id, holder_id)
);

CREATE TABLE devices (
    account_id  TEXT NOT NULL,
    device_id   TEXT NOT NULL,
    ed25519_pk  BLOB NOT NULL,             -- server-auth verify key
    x25519_pk   BLOB NOT NULL,             -- MK sealing key
    enrolled_by TEXT,                      -- device that approved this one
    created_at  TEXT NOT NULL,
    revoked     INTEGER DEFAULT 0,
    PRIMARY KEY (account_id, device_id)
);
```

Clients pull `seq > last_seen`, decrypt locally, and apply to the local
SQLite store; local changes push as new oplog entries. An op is one of
`add`, `supersede(old→new)`, or `tombstone` — mirroring the engine's
non-destructive semantics. Merge is client-side and order-tolerant: ops
union; supersede edges apply on top; concurrent adds of identical content
dedupe on the engine's existing content `hash`; concurrent supersedes of
the same record resolve last-writer-wins by (logical clock, device id).
Because supersede is non-destructive, a "lost" writer stays auditable —
the engine's philosophy survives sync intact. (Merge cost at scale is an
open crux — see below.)

## Authentication

Two separate problems, deliberately kept separate:

1. **Server auth (who may push/pull ciphertext).** Ed25519
   challenge–response: the server issues a nonce, the device signs it,
   the server verifies against the enrolled public key. No passwords
   exist anywhere in the system. Account identity is an email verified at
   signup, used only for coordination and abuse control — it grants no
   decryption capability.
2. **Key custody (who may decrypt).** Possession of an enrolled device
   key or the recovery code. The server cannot escalate one into the
   other.

**Device enrollment.** A new device generates its keypairs and displays a
short authentication string (emoji/word SAS derived from both devices'
public keys). An existing device verifies the SAS out-of-band, then seals
MK to the new device's X25519 key and uploads the wrapped copy. The server
relays blobs it cannot open. First-device setup instead runs the recovery
code ceremony.

**Revocation.** Mark the device revoked (server stops accepting its
signature), delete its wrapped MK, and rotate scope DEKs lazily. A revoked
device that already held keys is assumed to have read everything up to
revocation — rotation protects the future, not the past.

## Consent-scoped third-party access (design partners)

Deployments in mental-health and similar domains may require humans to
review flagged conversations (crisis escalation). The scope model supports
this without breaking the core guarantee: a deployment may define a
`safety` scope whose DEK is wrapped both to the user and to the
operator's safety key — **with the user's explicit, recorded consent at
enrollment**. Memories route to that scope only by explicit policy. The
operator can read exactly that scope, provably nothing else, and the
consent artifact is auditable. Zero-knowledge stays the default; readable
scopes are an opt-in exception, cryptographically bounded.

## Threat model summary

| Threat | Outcome |
|---|---|
| Sync server breach | Ciphertext, opaque UUIDs, sizes/timing only |
| Acquisition, insider, subpoena on us | Nothing readable to produce |
| Stolen device (locked) | Keys sit in OS keychain behind device auth |
| One device compromised | Rotate: revoke device, re-wrap MK, rotate DEKs |
| All devices + recovery code lost | Vault unrecoverable — the honest price |
| Malicious server swaps/replays records | AAD binding fails authentication |
| Metadata analysis (counts, sizes, times) | Partially mitigated (padding); documented residual |

## Plaintext egress audit (2026-07-13)

Every path where plaintext leaves the device today, and its disposition
under vault mode:

| Path | Today | E2EE disposition |
|---|---|---|
| Remote LLM extraction (`providers.extract_facts` remote branches) | opt-in via config | allowed only with an explicit `plaintext_egress` ack per provider; default local extractor |
| Remote embeddings (`providers.embed_text` remote branches) | opt-in, falls back local | same gate; prefer on-device upgrade (fastembed/ollama) over remote |
| Consolidation adjudication (`consolidation` → cloud LLM) | no-op without API key | same gate; local-LLM adjudicator is the target |
| Remote vector stores (`vector_adapters.*`) | opt-in, default sqlite | **hard-disabled in vault mode** — encrypted vectors cannot be searched server-side, so there is nothing honest to offer |
| `forget-connect` default URL | local since 0.2.0 | done; hosted stays behind `--hosted` (legacy) |
| Scope ids in MCP URLs/filters | plaintext | local transport only, acceptable; the sync layer uses scope UUIDs |

## Spikes before any marketing claims

In order — and the landing/waitlist copy does not get to say
"end-to-end encrypted sync, in beta" until 1–2 pass:

1. **Vault core round-trip** against a mock relay: key hierarchy +
   record encrypt/decrypt + oplog encode/decode. (crypto.py done;
   keyring/vault/relay remain.)
2. **Two-device merge** through the mock relay, including concurrent
   supersede conflict and content-hash dedupe.
3. **Local embedding upgrade decision.** deterministic-128 is private but
   weak; measure fastembed ONNX (e.g. bge-small) on-device cost vs
   quality so the private default is also a good default.
4. **Enrollment + recovery walkthrough on two real machines**, one a
   headless Linux box — no OS keychain, exercising the 0600 identity-file
   fallback — driven entirely from the CLI.

## Open cruxes

1. **Merge cost at scale.** Each device rebuilds its local index from
   decrypted embeddings; measure rebuild/merge at 10k–100k memories on
   laptop hardware.
2. **Oplog compaction.** Tombstone GC without letting the server infer
   deletion patterns — likely batched per-scope rewrites.
3. **Padding policy.** Bucket sizes vs. storage overhead — pick defaults
   after measuring real memory-length distributions.
4. **Scope granularity defaults.** v1 syncs per `project_id`; whether solo
   users get `personal`/`work` auto-scopes is decided after design-partner
   interviews (see gtm/ discovery script, question 4).

## Implementation notes

- `forget/crypto.py`: primitives only — key generation, wrap/unwrap, record
  seal/open, recovery-code derivation. Pure functions over PyNaCl; no I/O.
- `forget/keyring.py`: local key custody (OS keychain, file fallback) and
  the recovery-code ceremony.
- `forget/vault.py`: high-level vault API over crypto + keyring — scopes,
  enrollment, record lifecycle.
- `forget/sync.py`: oplog client (pull/decrypt/apply, collect/encrypt/push)
  against the local SQLite store.
- Server: `encrypted_records` + `devices` + `wrapped_keys` endpoints; dumb
  by design, deployable as a tiny FastAPI app or an object-store-backed
  worker.
- The local database itself may additionally use SQLCipher for at-rest
  protection; that is orthogonal to this design.
