# Access receipt verification v1

Date: 2026-08-28
Status: implemented and joint-loopback verified

## Contract

New access receipts contain `query_commitment` and never `query_hash`. The
commitment is `HMAC(receipt_key, "query:" + query)` and remains covered by the
receipt signature. The authenticated verifier accepts exactly:

```json
{
  "receipt": {"kind":"access_receipt", "...":"..."},
  "expected": {
    "query":"client meeting",
    "grantee":"agent_1",
    "scope_app":"team_ledger"
  }
}
```

It returns:

```json
{
  "schema_version":"forget-receipt-verification-v1",
  "valid":true,
  "signature_valid":true,
  "persistence_valid":true,
  "binding_valid":true
}
```

`valid` is true only when all three independent checks pass:

1. the signed receipt body is intact;
2. the exact receipt is already durable in this authenticated project; and
3. its keyed query commitment, grantee, and app scope match the caller's exact
   expectations.

The HMAC key never crosses the server boundary. A valid receipt from another
project, a receipt not yet in the access ledger, a guessed low-entropy query, or
a caller-selected grantee/scope mismatch fails closed.

First-use Ed25519 key publication writes and fsyncs a mode-`0600` temporary
file, then atomically links the complete seed into place. Concurrent processes
never observe a partial 32-byte seed; the public-key file is replaced atomically
from the winning key.

## Compatibility

The SQL `query_hash` column remains as an empty legacy slot so existing SQLite
files migrate without a destructive table rebuild. New `receipt_json` payloads
and consumer mirrors do not carry it. Existing receipts that already contain a
keyed commitment can still be verified; a legacy receipt without one cannot
satisfy an expected-query check.

BotBotBot writes commitment-only `memory.access.mirrored` payload schema v2.
DurableJournal continues to replay schema-v1 `queryHash` events and recognizes
the same receipt during migration by receipt ID, signature, and all common
fields.

## Principal mode

New grants default to `principal_mode="exact"`; the stored principal must match
the serving grantee byte-for-byte. Patterns containing `*`, `?`, or `[` are
rejected unless the owner explicitly sends `allow_pattern=true`, in which case
the durable grant records `principal_mode="pattern"`. Existing wildcard grants
are migrated to pattern mode so the security-relevant expansion remains visible
instead of silently changing behavior.

Grant creation/list/revocation and raw access-receipt audit require operator,
owner/admin role, or an explicit `grants:admin` credential scope. Agent
credentials cannot mint their own permission. Serve and access-receipt
verification derive the grantee from `agent_principal`; a caller-selected or
mismatched grantee is rejected.

## Evidence

- Forget focused grant/signature/verification tests: 25 passed.
- Forget full regression: 776 passed, 1 skipped.
- BotBotBot focused adapter/mirror/journal tests: 28 passed.
- BotBotBot full verification: 372 passed, TypeScript and production build
  succeeded.
- Live joint receipt:
  `areceipt_425b5ab6-a6ff-4e28-b0ca-81ae4169f66d`.
- Live result: redaction 1, commitment-only receipt, one durable mirror event,
  same-receipt replay, zero replay capsule lines, exact-principal default,
  wildcard rejection without explicit opt-in, owner/agent authority separation,
  zero active smoke grants, and zero live smoke memories after cleanup.
