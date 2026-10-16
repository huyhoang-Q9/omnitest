"""Che secret trong file trace Playwright trước khi lưu.

Trace ghi lại giá trị nhập vào form, request/response và snapshot DOM, nên có thể chứa secret.
Mọi entry trong zip được thay chuỗi secret (dạng thô, dạng escape JSON, dạng URL-encode) bằng ***.
Nếu sau khi thay vẫn còn dấu vết secret thì không trả trace (an toàn hơn là lộ secret).
"""

import io
import json
import zipfile
from urllib.parse import quote, quote_plus

MASK = b"***"


def _variants(secret: str) -> list[bytes]:
    forms = {
        secret,
        json.dumps(secret)[1:-1],
        json.dumps(secret, ensure_ascii=False)[1:-1],
        quote(secret, safe=""),
        quote_plus(secret, safe=""),
    }
    return sorted({f.encode() for f in forms if f}, key=len, reverse=True)


def redact_trace(data: bytes, secrets: list[str]) -> bytes | None:
    """Trả trace đã che secret, hoặc None nếu không chắc đã che hết."""
    variants = [v for s in secrets if len(s) >= 3 for v in _variants(s)]
    if not variants:
        return data
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(data)) as src,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for info in src.infolist():
            content = src.read(info)
            for v in variants:
                content = content.replace(v, MASK)
            if any(v in content for v in variants):
                return None
            dst.writestr(info.filename, content)
    return out.getvalue()
