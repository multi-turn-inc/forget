import pytest

pytest.importorskip("nacl")

from nacl.pwhash import argon2id

from forget import crypto


def test_record_seal_open_roundtrip():
    key = crypto.generate_scope_key()
    blob = crypto.seal_record(
        b"we settled on Paddle", key,
        record_id="rec-1", scope_id="work", schema_ver=1, seq=7,
    )
    assert crypto.open_record(
        blob, key, record_id="rec-1", scope_id="work", schema_ver=1, seq=7,
    ) == b"we settled on Paddle"


def test_record_open_fails_on_tampered_ciphertext():
    key = crypto.generate_scope_key()
    blob = crypto.seal_record(
        b"secret", key, record_id="rec-1", scope_id="work", schema_ver=1, seq=1,
    )
    tampered = blob[:-1] + bytes([blob[-1] ^ 0x01])
    with pytest.raises(crypto.VaultCryptoError):
        crypto.open_record(
            tampered, key, record_id="rec-1", scope_id="work", schema_ver=1, seq=1,
        )


def test_record_open_fails_when_envelope_differs():
    """A server that swaps scope or replays at another seq must fail AAD."""
    key = crypto.generate_scope_key()
    blob = crypto.seal_record(
        b"secret", key, record_id="rec-1", scope_id="work", schema_ver=1, seq=1,
    )
    for changed in (
        dict(record_id="rec-2", scope_id="work", schema_ver=1, seq=1),
        dict(record_id="rec-1", scope_id="personal", schema_ver=1, seq=1),
        dict(record_id="rec-1", scope_id="work", schema_ver=2, seq=1),
        dict(record_id="rec-1", scope_id="work", schema_ver=1, seq=2),
    ):
        with pytest.raises(crypto.VaultCryptoError):
            crypto.open_record(blob, key, **changed)


def test_record_aad_rejects_delimiter_injection():
    with pytest.raises(ValueError):
        crypto.record_aad("rec|1", "work", 1, 1)
    with pytest.raises(ValueError):
        crypto.record_aad("rec-1", "work|personal", 1, 1)


def test_wrap_unwrap_key_roundtrip_and_context_binding():
    master = crypto.generate_master_key()
    scope_key = crypto.generate_scope_key()
    wrapped = crypto.wrap_key(scope_key, master, context="scope:work")
    assert crypto.unwrap_key(wrapped, master, context="scope:work") == scope_key
    with pytest.raises(crypto.VaultCryptoError):
        crypto.unwrap_key(wrapped, master, context="scope:personal")
    with pytest.raises(crypto.VaultCryptoError):
        crypto.unwrap_key(wrapped, crypto.generate_master_key(), context="scope:work")


def test_master_key_seals_to_device_and_back():
    master = crypto.generate_master_key()
    device = crypto.generate_device_keys()
    other = crypto.generate_device_keys()
    sealed = crypto.seal_to_device(master, device.exchange_public)
    assert crypto.open_from_device(sealed, device.exchange_private) == master
    with pytest.raises(crypto.VaultCryptoError):
        crypto.open_from_device(sealed, other.exchange_private)


def test_recovery_code_format_and_checksum():
    code = crypto.generate_recovery_code()
    assert code.startswith("F1-") or code.startswith("F1")
    assert crypto.validate_recovery_code(code)
    assert crypto.validate_recovery_code(code.lower().replace("-", " "))

    # The 10-bit checksum cannot catch every single-char flip (~0.11%
    # collide), so flipping a freshly drawn random code makes this test
    # fail one run in ~900. Pin a vector whose position-5 flips are all
    # collision-free, and which also freezes the checksum algorithm —
    # deployed recovery codes must keep validating across versions.
    raw = "F1QMEBFORGETRECOVERYTESTVECT5X"
    assert crypto.validate_recovery_code(raw)
    position = 5
    for replacement in crypto._RECOVERY_ALPHABET:
        if replacement == raw[position]:
            continue
        corrupted = raw[:position] + replacement + raw[position + 1:]
        assert not crypto.validate_recovery_code(corrupted)
    assert not crypto.validate_recovery_code("XX" + raw[2:])
    assert not crypto.validate_recovery_code("F1-SHORT")


def test_recovery_codes_are_unique():
    codes = {crypto.generate_recovery_code() for _ in range(64)}
    assert len(codes) == 64


def test_derive_recovery_key_deterministic_per_salt():
    code = crypto.generate_recovery_code()
    salt = crypto.generate_recovery_salt()
    fast = dict(
        opslimit=argon2id.OPSLIMIT_INTERACTIVE,
        memlimit=argon2id.MEMLIMIT_INTERACTIVE,
    )
    first = crypto.derive_recovery_key(code, salt, **fast)
    again = crypto.derive_recovery_key(f" {code.lower()} ".strip(), salt, **fast)
    assert first == again
    assert len(first) == crypto.KEY_BYTES
    assert crypto.derive_recovery_key(code, crypto.generate_recovery_salt(), **fast) != first
    with pytest.raises(ValueError):
        crypto.derive_recovery_key("not-a-code", salt, **fast)
    with pytest.raises(ValueError):
        crypto.derive_recovery_key(code, b"short", **fast)


def test_challenge_signature_roundtrip():
    device = crypto.generate_device_keys()
    challenge = b"server-nonce-123"
    signature = crypto.sign_challenge(challenge, device.signing_seed)
    assert crypto.verify_challenge(challenge, signature, device.verify_key)
    assert not crypto.verify_challenge(b"other-nonce", signature, device.verify_key)
    other = crypto.generate_device_keys()
    assert not crypto.verify_challenge(challenge, signature, other.verify_key)
