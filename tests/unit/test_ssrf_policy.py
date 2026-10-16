"""Kiểm thử chính sách chống SSRF: các dạng viết địa chỉ nội bộ, metadata cloud, DNS rebinding."""

import asyncio
from urllib.parse import urlsplit

import pytest
from omnitest_adapters.core import network
from omnitest_adapters.core.network import (
    BlockedTargetError,
    GuardedNetworkBackend,
    NetworkPolicy,
    check_ip,
    check_url,
    check_url_static,
)
from omnitest_adapters.web_playwright import egress_proxy
from omnitest_adapters.web_playwright.egress_proxy import BLOCKED_HEADER, EgressProxy

OPEN = NetworkPolicy((), allow_private_network=False)
PRIVATE_OK = NetworkPolicy((), allow_private_network=True)


def allow(url: str) -> NetworkPolicy:
    """Chính sách cho phép đúng host của URL, để chứng minh lớp chặn khác (IP, scheme...) mới là lớp chặn."""
    host = (urlsplit(url).hostname or "").lower()
    return NetworkPolicy((host,), allow_private_network=False)


@pytest.mark.parametrize(
    "ip",
    [
        "169.254.169.254",  # metadata AWS/GCP/Azure
        "::ffff:169.254.169.254",  # metadata viết dạng IPv6 ánh xạ IPv4
        "fe80::1",  # link-local IPv6
        "fd00:ec2::254",  # metadata AWS IPv6 (ULA) thuộc mạng nội bộ
        "0.0.0.0",  # noqa: S104 - đây là dữ liệu kiểm thử, không bind
        "::",
        "224.0.0.1",
        "240.0.0.1",
    ],
)
def test_always_blocked_or_private_ranges(ip: str) -> None:
    with pytest.raises(BlockedTargetError):
        check_ip(ip, OPEN)


@pytest.mark.parametrize("ip", ["169.254.169.254", "::ffff:169.254.169.254", "fe80::1", "0.0.0.0"])  # noqa: S104
def test_metadata_and_link_local_blocked_even_when_private_allowed(ip: str) -> None:
    with pytest.raises(BlockedTargetError):
        check_ip(ip, PRIVATE_OK)


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "::1",
        "::ffff:127.0.0.1",
        "10.0.0.5",
        "192.168.1.1",
        "172.16.0.1",
        "100.64.0.1",
        "fd00::1",
    ],
)
def test_private_needs_admin_opt_in(ip: str) -> None:
    with pytest.raises(BlockedTargetError):
        check_ip(ip, OPEN)
    check_ip(ip, PRIVATE_OK)


def test_public_ip_allowed() -> None:
    check_ip("93.184.215.14", OPEN)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://127.0.0.1/",
        "ftp://example.org/",
        "http://user:pass@example.org/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http:///nohost",
    ],
)
def test_bad_urls_rejected(url: str) -> None:
    with pytest.raises(BlockedTargetError):
        check_url_static(url, allow(url))


@pytest.mark.parametrize(
    "url",
    [
        "http://2130706433/",  # 127.0.0.1 dạng số thập phân
        "http://0x7f000001/",  # dạng hex
        "http://0177.0.0.1/",  # dạng bát phân
        "http://127.1/",  # dạng rút gọn
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://localhost/",
    ],
)
async def test_obfuscated_loopback_resolves_and_is_blocked(url: str) -> None:
    with pytest.raises(BlockedTargetError):
        check_url_static(url, allow(url))  # host hợp lệ trong allowlist
        await check_url(url, allow(url))  # nhưng phân giải ra loopback nên bị chặn


def test_host_allowlist_and_port() -> None:
    p = NetworkPolicy.from_environment("https://app.example.com:8443", ["*.cdn.example.com"], False)
    check_url_static("https://app.example.com:8443/x", p)
    check_url_static("https://img.cdn.example.com/x.png", p)
    for bad in (
        "https://cdn.example.com/",
        "https://evil.com/",
        "https://app.example.com.evil.com/",
    ):
        with pytest.raises(BlockedTargetError):
            check_url_static(bad, p)


async def test_dns_rebinding_blocked_at_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tên miền được phép nhưng lúc kết nối lại phân giải ra metadata cloud: phải chặn."""

    async def evil_resolve(host: str, port: int) -> list[str]:
        return ["169.254.169.254"]

    monkeypatch.setattr(network, "resolve", evil_resolve)
    backend = GuardedNetworkBackend(NetworkPolicy(("app.example.com",), True))
    with pytest.raises(BlockedTargetError):
        await backend.connect_tcp("app.example.com", 80)


async def _raw(proxy_url: str, request: bytes) -> bytes:
    host, port = proxy_url.removeprefix("http://").split(":")
    reader, writer = await asyncio.open_connection(host, int(port))
    writer.write(request)
    await writer.drain()
    data = await reader.read(4096)
    writer.close()
    return data


async def test_egress_proxy_blocks_rebinding_and_marks_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def evil_resolve(host: str, port: int) -> list[str]:
        return ["127.0.0.1"]

    monkeypatch.setattr(egress_proxy, "resolve", evil_resolve)
    async with EgressProxy(NetworkPolicy(("app.example.com",), False)) as proxy:
        plain = await _raw(
            proxy.url, b"GET http://app.example.com/ HTTP/1.1\r\nHost: app.example.com\r\n\r\n"
        )
        tunnel = await _raw(proxy.url, b"CONNECT app.example.com:443 HTTP/1.1\r\n\r\n")
        other = await _raw(proxy.url, b"CONNECT evil.com:443 HTTP/1.1\r\n\r\n")
    for resp in (plain, tunnel, other):
        assert resp.startswith(b"HTTP/1.1 403")
        assert BLOCKED_HEADER.encode() in resp
    assert len(proxy.blocked) == 3


async def test_egress_proxy_rejects_non_http_scheme() -> None:
    async with EgressProxy(allow("ftp://example.org/")) as proxy:
        resp = await _raw(proxy.url, b"GET ftp://example.org/ HTTP/1.1\r\n\r\n")
    assert resp.startswith(b"HTTP/1.1 403")
