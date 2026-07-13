"""E2EE vault primitives: keys, wrapping, record sealing, recovery codes.

Pure functions over libsodium (PyNaCl); no I/O and no key custody here —
see docs/vault-design.md for the key hierarchy this implements and
forget/keyring.py (future) for storage. Nothing in this module invents a
cryptographic construction: every operation maps 1:1 onto a libsodium
primitive.

Requires the optional dependency: pip install forget-ai[vault]
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

try:
    from nacl.bindings import (
        crypto_aead_xchacha20poly1305_ietf_decrypt,
        crypto_aead_xchacha20poly1305_ietf_encrypt,
    )
    from nacl.exceptions import CryptoError
    from nacl.public import PrivateKey, PublicKey, SealedBox
    from nacl.pwhash import argon2id
    from nacl.signing import SigningKey, VerifyKey
except ImportError as error:  # pragma: no cover
    raise ImportError(
        "forget.crypto needs PyNaCl. Install it with: pip install forget-ai[vault]"
    ) from error

KEY_BYTES = 32
NONCE_BYTES = 24

_RECOVERY_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"  # RFC 4648 base32
_RECOVERY_VERSION = "F1"
_RECOVERY_DATA_CHARS = 26  # 130 bits of entropy
_RECOVERY_CHECK_CHARS = 2


class VaultCryptoError(Exception):
    """Decryption or verification failed: wrong key, tampered data, or
    mismatched envelope (AAD)."""


@dataclass(frozen=True)
class DeviceKeys:
    """One device's key material. Private halves belong in the OS keychain."""

    signing_seed: bytes  # Ed25519 seed (server-auth signing)
    verify_key: bytes  # Ed25519 public
    exchange_private: bytes  # X25519 private (master-key sealing)
    exchange_public: bytes  # X25519 public


# --- key generation -------------------------------------------------------

def generate_master_key() -> bytes:
    return secrets.token_bytes(KEY_BYTES)


def generate_scope_key() -> bytes:
    return secrets.token_bytes(KEY_BYTES)


def generate_device_keys() -> DeviceKeys:
    signing = SigningKey.generate()
    exchange = PrivateKey.generate()
    return DeviceKeys(
        signing_seed=bytes(signing),
        verify_key=bytes(signing.verify_key),
        exchange_private=bytes(exchange),
        exchange_public=bytes(exchange.public_key),
    )


# --- master key <-> device (sealed box) -----------------------------------

def seal_to_device(secret: bytes, exchange_public: bytes) -> bytes:
    """Encrypt a secret so only the holder of the device private key can
    read it. Anyone (including the server relaying enrollment) can produce
    this; only the device can open it."""
    return SealedBox(PublicKey(exchange_public)).encrypt(secret)


def open_from_device(sealed: bytes, exchange_private: bytes) -> bytes:
    try:
        return SealedBox(PrivateKey(exchange_private)).decrypt(sealed)
    except CryptoError as error:
        raise VaultCryptoError("sealed key does not open with this device key") from error


# --- scope keys <-> master key (AEAD wrap) --------------------------------

def _aead_encrypt(plaintext: bytes, key: bytes, aad: bytes) -> bytes:
    nonce = secrets.token_bytes(NONCE_BYTES)
    ciphertext = crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, aad, nonce, key)
    return nonce + ciphertext


def _aead_decrypt(blob: bytes, key: bytes, aad: bytes, what: str) -> bytes:
    if len(blob) <= NONCE_BYTES:
        raise VaultCryptoError(f"{what}: blob too short")
    try:
        return crypto_aead_xchacha20poly1305_ietf_decrypt(
            blob[NONCE_BYTES:], aad, blob[:NONCE_BYTES], key
        )
    except CryptoError as error:
        raise VaultCryptoError(f"{what}: wrong key, tampered data, or mismatched context") from error


def wrap_key(key_to_wrap: bytes, master_key: bytes, *, context: str) -> bytes:
    """Wrap a scope key under the master key. `context` (e.g. "scope:<uuid>")
    binds the wrap to its purpose so a wrapped key cannot be replayed as a
    different scope's key."""
    return _aead_encrypt(key_to_wrap, master_key, context.encode())


def unwrap_key(wrapped: bytes, master_key: bytes, *, context: str) -> bytes:
    return _aead_decrypt(wrapped, master_key, context.encode(), "unwrap_key")


# --- record sealing --------------------------------------------------------

def record_aad(record_id: str, scope_id: str, schema_ver: int, seq: int) -> bytes:
    """Canonical associated data binding a ciphertext to its envelope row.
    A server that swaps scope_id or replays a record at a different seq
    produces a blob that fails authentication."""
    for name, value in (("record_id", record_id), ("scope_id", scope_id)):
        if "|" in value:
            raise ValueError(f"{name} must not contain '|'")
    return f"{record_id}|{scope_id}|{schema_ver}|{seq}".encode()


def seal_record(
    plaintext: bytes,
    scope_key: bytes,
    *,
    record_id: str,
    scope_id: str,
    schema_ver: int,
    seq: int,
) -> bytes:
    """Encrypt one memory record (text, embedding, metadata — already
    serialized) under its scope key. Returns nonce-prefixed ciphertext."""
    return _aead_encrypt(
        plaintext, scope_key, record_aad(record_id, scope_id, schema_ver, seq)
    )


def open_record(
    blob: bytes,
    scope_key: bytes,
    *,
    record_id: str,
    scope_id: str,
    schema_ver: int,
    seq: int,
) -> bytes:
    return _aead_decrypt(
        blob,
        scope_key,
        record_aad(record_id, scope_id, schema_ver, seq),
        "open_record",
    )


# --- recovery code ---------------------------------------------------------

def _recovery_checksum(data: str) -> str:
    digest = hashlib.blake2b(data.encode(), digest_size=4).digest()
    value = int.from_bytes(digest, "big")
    first = _RECOVERY_ALPHABET[value % 32]
    second = _RECOVERY_ALPHABET[(value // 32) % 32]
    return first + second


def normalize_recovery_code(code: str) -> str:
    return code.replace("-", "").replace(" ", "").upper()


def generate_recovery_code() -> str:
    """One-time recovery code (130 bits + checksum), shown once at vault
    creation. Format: F1-XXXXX-XXXXX-XXXXX-XXXXX-XXXXX-XXX."""
    data = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(_RECOVERY_DATA_CHARS))
    raw = _RECOVERY_VERSION + data + _recovery_checksum(_RECOVERY_VERSION + data)
    groups = [raw[i : i + 5] for i in range(0, len(raw), 5)]
    return "-".join(groups)


def validate_recovery_code(code: str) -> bool:
    raw = normalize_recovery_code(code)
    expected_len = len(_RECOVERY_VERSION) + _RECOVERY_DATA_CHARS + _RECOVERY_CHECK_CHARS
    if len(raw) != expected_len or not raw.startswith(_RECOVERY_VERSION):
        return False
    body, check = raw[:-_RECOVERY_CHECK_CHARS], raw[-_RECOVERY_CHECK_CHARS:]
    if any(char not in _RECOVERY_ALPHABET for char in body[len(_RECOVERY_VERSION):]):
        return False
    return _recovery_checksum(body) == check


def derive_recovery_key(
    code: str,
    salt: bytes,
    *,
    opslimit: int = argon2id.OPSLIMIT_MODERATE,
    memlimit: int = argon2id.MEMLIMIT_MODERATE,
) -> bytes:
    """Argon2id-derive the recovery key that wraps the master key. The salt
    is stored server-side next to the recovery-wrapped master key; the code
    itself never leaves the user."""
    if not validate_recovery_code(code):
        raise ValueError("malformed recovery code")
    if len(salt) != argon2id.SALTBYTES:
        raise ValueError(f"salt must be {argon2id.SALTBYTES} bytes")
    return argon2id.kdf(
        KEY_BYTES,
        normalize_recovery_code(code).encode(),
        salt,
        opslimit=opslimit,
        memlimit=memlimit,
    )


def generate_recovery_salt() -> bytes:
    return secrets.token_bytes(argon2id.SALTBYTES)


# --- server auth (Ed25519 challenge-response) ------------------------------

def sign_challenge(challenge: bytes, signing_seed: bytes) -> bytes:
    return SigningKey(signing_seed).sign(challenge).signature


def verify_challenge(challenge: bytes, signature: bytes, verify_key: bytes) -> bool:
    try:
        VerifyKey(verify_key).verify(challenge, signature)
        return True
    except CryptoError:
        return False
