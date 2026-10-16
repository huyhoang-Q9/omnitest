"""Chặn SSRF: chỉ cho test gọi tới đích được phép.

Quy tắc:
- Chỉ http/https.
- Host phải khớp host của Base URL hoặc danh sách allowed_hosts của môi trường (hỗ trợ *.domain).
- Luôn chặn: link-local (gồm 169.254.169.254 metadata cloud), multicast, địa chỉ không xác định, dải dự trữ,
  tên miền metadata đã biết.
- Mạng nội bộ (loopback, 10/8, 172.16/12, 192.168/16, 100.64/10, fc00::/7) chỉ cho phép khi môi trường
  bật allow_private_network.
- Kiểm tra lại tại thời điểm mở kết nối TCP (GuardedNetworkBackend) để chống DNS rebinding cho HTTPX.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpcore
import httpx

BLOCKED_HOSTNAMES = {
    "metadata.google.internal",
    "metadata",
    "instance-data",
    "metadata.azure.internal",
}
CGNAT = ipaddress.ip_network("100.64.0.0/10")


class BlockedTargetError(Exception):
    """Đích bị chặn bởi chính sách mạng của môi trường."""


@dataclass(frozen=True)
class NetworkPolicy:
    allowed_hosts: tuple[str, ...]
    allow_private_network: bool = False
    extra: dict[str, Any] = field(default_factory=dict, compare=False)

    @classmethod
    def from_environment(
        cls, base_url: str, allowed_hosts: Iterable[str], allow_private_network: bool
    ) -> "NetworkPolicy":
        hosts = {h.lower() for h in allowed_hosts if h}
        base = urlsplit(base_url)
        if base.hostname:
            hosts.add(base.hostname.lower())
            if base.port:
                hosts.add(f"{base.hostname.lower()}:{base.port}")
        return cls(tuple(sorted(hosts)), allow_private_network)

    def host_allowed(self, host: str, port: int | None) -> bool:
        host = host.lower().rstrip(".")
        for pattern in self.allowed_hosts:
            p_host, _, p_port = pattern.partition(":")
            if p_port and (port is None or str(port) != p_port):
                continue
            if p_host.startswith("*."):
                suffix = p_host[1:]
                if host.endswith(suffix) and host != suffix.lstrip("."):
                    return True
            elif host == p_host:
                return True
        return False


def classify_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """Trả 'blocked', 'private' hoặc 'public'."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return "blocked"
    if ip.is_loopback or ip.is_private or (isinstance(ip, ipaddress.IPv4Address) and ip in CGNAT):
        return "private"
    if not ip.is_global:
        return "blocked"
    return "public"


def check_ip(ip_text: str, policy: NetworkPolicy) -> None:
    ip = ipaddress.ip_address(ip_text.split("%", 1)[0])
    kind = classify_ip(ip)
    if kind == "blocked":
        raise BlockedTargetError(
            f"Địa chỉ {ip} thuộc dải luôn bị chặn (link-local, metadata cloud, multicast...)"
        )
    if kind == "private" and not policy.allow_private_network:
        raise BlockedTargetError(
            f"Địa chỉ {ip} thuộc mạng nội bộ. Admin dự án cần bật 'Cho phép đích mạng nội bộ' cho môi trường"
        )


async def resolve(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BlockedTargetError(f"Không phân giải được tên miền {host}") from exc
    return sorted({str(info[4][0]) for info in infos})


def check_url_static(url: str, policy: NetworkPolicy) -> tuple[str, int]:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise BlockedTargetError(
            f"Giao thức {parts.scheme or '(trống)'} không được phép, chỉ http/https"
        )
    host = (parts.hostname or "").lower()
    if not host:
        raise BlockedTargetError("URL không có tên máy chủ")
    if parts.username or parts.password:
        raise BlockedTargetError("Không đưa thông tin đăng nhập vào URL")
    if host in BLOCKED_HOSTNAMES:
        raise BlockedTargetError(f"Tên miền {host} bị chặn (metadata)")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if not policy.host_allowed(host, parts.port):
        raise BlockedTargetError(
            f"Host {host} không nằm trong danh sách đích được phép của môi trường"
        )
    return host, port


async def check_url(url: str, policy: NetworkPolicy) -> list[str]:
    host, port = check_url_static(url, policy)
    ips = await resolve(host, port)
    for ip in ips:
        check_ip(ip, policy)
    return ips


class GuardedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Phân giải và kiểm tra IP ngay lúc kết nối, rồi kết nối tới đúng IP đã kiểm tra."""

    def __init__(self, policy: NetworkPolicy) -> None:
        self._policy = policy
        self._inner = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - chữ ký của httpcore
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        if host.lower() in BLOCKED_HOSTNAMES:
            raise BlockedTargetError(f"Tên miền {host} bị chặn (metadata)")
        ips = await resolve(host, port)
        for ip in ips:
            check_ip(ip, self._policy)
        return await self._inner.connect_tcp(
            ips[0],
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(self, *args: Any, **kwargs: Any) -> httpcore.AsyncNetworkStream:
        raise BlockedTargetError("Không cho phép kết nối unix socket")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def guarded_transport(policy: NetworkPolicy) -> httpx.AsyncHTTPTransport:
    transport = httpx.AsyncHTTPTransport(retries=0)
    # httpx chưa cho truyền network_backend qua tham số; gắn vào pool bên trong (httpcore 1.x).
    transport._pool._network_backend = GuardedNetworkBackend(policy)
    return transport
