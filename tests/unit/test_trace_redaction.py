import io
import zipfile

from omnitest_adapters.web_playwright.trace_redaction import redact_trace


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def _read(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist()}


def test_masks_raw_json_escaped_and_url_encoded_forms() -> None:
    secret = 'Mật"khẩu@1 2'
    trace = _zip(
        {
            "trace.trace": b'{"value":"' + 'Mật\\"khẩu@1 2'.encode() + b'"}',
            "trace.network": b"password=M%E1%BA%ADt%22kh%E1%BA%A9u%401+2",
            "resources/a.html": f"<input value='{secret}'>".encode(),
        }
    )
    out = redact_trace(trace, [secret])
    assert out is not None
    entries = _read(out)
    assert set(entries) == {"trace.trace", "trace.network", "resources/a.html"}
    joined = b"".join(entries.values())
    assert secret.encode() not in joined
    assert b"%E1%BA%ADt" not in joined
    assert joined.count(b"***") == 3


def test_no_secrets_returns_original() -> None:
    trace = _zip({"trace.trace": b"abc"})
    assert redact_trace(trace, []) == trace
    assert redact_trace(trace, ["ab"]) == trace  # quá ngắn, không che (giống quy tắc che log)
