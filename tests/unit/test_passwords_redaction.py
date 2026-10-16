import logging

from omnitest_api.security.passwords import hash_password, password_problems, verify_password
from omnitest_api.security.redaction import RedactingFilter, redact_mapping, redact_text


def test_password_hash_verify() -> None:
    h = hash_password("Abcdefgh12")
    assert h.startswith("$argon2")
    assert verify_password(h, "Abcdefgh12")
    assert not verify_password(h, "abcdefgh12")
    assert not verify_password(None, "Abcdefgh12")
    assert not verify_password("garbage", "x")


def test_password_policy() -> None:
    assert password_problems("Abcdefgh12") == []
    assert len(password_problems("short")) >= 2
    assert password_problems("alllowercase1")
    assert password_problems("NoDigitsHereAtAll")


def test_redact_text_headers_and_known_secrets() -> None:
    s = "Authorization: Bearer abc.def token=xyz password hunter2-secret"
    out = redact_text(s, known_secrets=["hunter2-secret"])
    assert "abc.def" not in out
    assert "hunter2-secret" not in out


def test_redact_mapping_nested() -> None:
    out = redact_mapping({"name": "a", "api_key": "k", "nested": {"Password": "p", "ok": 1}})
    assert out == {"name": "a", "api_key": "***", "nested": {"Password": "***", "ok": 1}}


def test_logging_filter() -> None:
    rec = logging.LogRecord(
        "t", logging.INFO, __file__, 1, "Cookie: omnitest_session=abc123", None, None
    )
    RedactingFilter().filter(rec)
    assert "abc123" not in rec.getMessage()
