"""Che thông tin nhạy cảm trước khi ghi log."""

import logging
import re

SENSITIVE_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|cookie|session|credential)",
    re.IGNORECASE,
)
_HEADER_PATTERN = re.compile(
    r"(?i)\b(authorization|cookie|set-cookie|x-api-key)\s*[:=]\s*([^\s,;]+(?:\s+[^\s,;]+)?)"
)
MASK = "***"


def redact_text(text: str, known_secrets: list[str] | None = None) -> str:
    for value in known_secrets or []:
        if value and len(value) >= 4:
            text = text.replace(value, MASK)
    return _HEADER_PATTERN.sub(lambda m: f"{m.group(1)}: {MASK}", text)


def redact_mapping(data: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in data.items():
        if SENSITIVE_KEY_PATTERN.search(k):
            out[k] = MASK
        elif isinstance(v, dict):
            out[k] = redact_mapping(v)
        else:
            out[k] = v
    return out


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(str(record.msg))
        if record.args:
            record.args = tuple(redact_text(a) if isinstance(a, str) else a for a in record.args)
        return True
