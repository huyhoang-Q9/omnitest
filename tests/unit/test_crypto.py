import pytest

from omnitest_api.security.crypto import SecretCipher, SecretCipherError, generate_master_key


def test_roundtrip_and_random_nonce() -> None:
    c = SecretCipher(generate_master_key())
    a = c.encrypt("s3cr3t-value", "envvar:1")
    b = c.encrypt("s3cr3t-value", "envvar:1")
    assert a != b
    assert b"s3cr3t-value" not in a
    assert c.decrypt(a, "envvar:1") == "s3cr3t-value"


def test_context_binding_prevents_copying_ciphertext() -> None:
    c = SecretCipher(generate_master_key())
    blob = c.encrypt("x", "envvar:1")
    with pytest.raises(SecretCipherError):
        c.decrypt(blob, "envvar:2")


def test_wrong_key_fails() -> None:
    blob = SecretCipher(generate_master_key()).encrypt("x", "ctx")
    with pytest.raises(SecretCipherError):
        SecretCipher(generate_master_key()).decrypt(blob, "ctx")


def test_tampered_ciphertext_fails() -> None:
    c = SecretCipher(generate_master_key())
    blob = bytearray(c.encrypt("x", "ctx"))
    blob[-1] ^= 1
    with pytest.raises(SecretCipherError):
        c.decrypt(bytes(blob), "ctx")


@pytest.mark.parametrize("bad", ["", "abc", "!!!notbase64!!!"])
def test_invalid_master_key_rejected(bad: str) -> None:
    with pytest.raises(SecretCipherError):
        SecretCipher(bad)
