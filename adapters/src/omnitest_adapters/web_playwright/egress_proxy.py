"""Proxy kiểm soát mạng cho trình duyệt của adapter Web.

Lý do: route của Playwright không được gọi cho các bước chuyển hướng (redirect), nên một trang được phép
có thể chuyển hướng trình duyệt tới địa chỉ nội bộ hoặc metadata cloud. Mọi kết nối của trình duyệt đi qua
proxy này (kể cả loopback, nhờ --proxy-bypass-list=<-loopback>); mỗi kết nối được kiểm tra host theo
allowlist, phân giải DNS, kiểm tra IP rồi nối tới đúng IP đã kiểm tra (chống DNS rebinding).

Hỗ trợ CONNECT (HTTPS, WebSocket bảo mật) và HTTP thường (mỗi kết nối một request, Connection: close).
"""

import asyncio
import contextlib
import logging
from urllib.parse import urlsplit

from omnitest_adapters.core.network import (
    BLOCKED_HOSTNAMES,
    BlockedTargetError,
    NetworkPolicy,
    check_ip,
    resolve,
)

log = logging.getLogger("omnitest.adapters.egress")
MAX_HEADER = 64 * 1024
# Đánh dấu phản hồi do proxy tự trả khi chặn, để adapter phân biệt với lưu lượng nền của trình duyệt.
BLOCKED_HEADER = "x-omnitest-egress-blocked"


class EgressProxy:
    def __init__(self, policy: NetworkPolicy) -> None:
        self.policy = policy
        # Mọi kết nối bị chặn (gồm cả lưu lượng nền của trình duyệt), dạng "đích: lý do".
        self.blocked: list[str] = []
        self._server: asyncio.Server | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def url(self) -> str:
        assert self._server is not None
        host, port = self._server.sockets[0].getsockname()[:2]
        return f"http://{host}:{port}"

    async def __aenter__(self) -> "EgressProxy":
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._server:
            self._server.close()
            for t in list(self._tasks):
                t.cancel()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()

    async def _open(
        self, host: str, port: int
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        host = host.strip("[]").lower().rstrip(".")
        if host in BLOCKED_HOSTNAMES:
            raise BlockedTargetError(f"Tên miền {host} bị chặn (metadata)")
        if not self.policy.host_allowed(host, port):
            raise BlockedTargetError(
                f"Host {host} không nằm trong danh sách đích được phép của môi trường"
            )
        ips = await resolve(host, port)
        for ip in ips:
            check_ip(ip, self.policy)
        return await asyncio.open_connection(ips[0], port)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task:
            self._tasks.add(task)
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            if len(head) > MAX_HEADER:
                return
            first, _, rest = head.partition(b"\r\n")
            method, target, version = first.decode("latin-1").split(" ", 2)
            if method.upper() == "CONNECT":
                host, _, port_s = target.rpartition(":")
                try:
                    up_r, up_w = await self._open(host, int(port_s))
                except (BlockedTargetError, OSError, ValueError) as exc:
                    await self._deny(writer, target, exc)
                    return
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
                await self._pipe(reader, writer, up_r, up_w)
                return

            parts = urlsplit(target)
            if parts.scheme != "http" or not parts.hostname:
                await self._deny(writer, target, BlockedTargetError("Chỉ cho phép http/https"))
                return
            port = parts.port or 80
            try:
                up_r, up_w = await self._open(parts.hostname, port)
            except (BlockedTargetError, OSError) as exc:
                await self._deny(writer, target, exc)
                return
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            headers = [
                h
                for h in rest.split(b"\r\n")
                if h
                and not h.lower().startswith((b"proxy-connection:", b"connection:", b"keep-alive:"))
            ]
            request = (
                f"{method} {path} {version}\r\n".encode("latin-1")
                + b"".join(h + b"\r\n" for h in headers)
                + b"Connection: close\r\n\r\n"
            )
            up_w.write(request)
            await up_w.drain()
            await self._pipe(reader, writer, up_r, up_w)
        except (
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            ConnectionError,
            ValueError,
        ):
            pass
        finally:
            with contextlib.suppress(Exception):
                writer.close()
            if task:
                self._tasks.discard(task)

    async def _deny(self, writer: asyncio.StreamWriter, target: str, exc: Exception) -> None:
        if isinstance(exc, BlockedTargetError):
            msg = str(exc)
            self.blocked.append(f"{target}: {msg}")
            log.info("Proxy chặn kết nối tới %s", target)
            status, extra = b"403 Forbidden", BLOCKED_HEADER.encode() + b": 1\r\n"
        else:
            msg = f"Không kết nối được: {exc.__class__.__name__}"
            status, extra = b"502 Bad Gateway", b""
        body = msg.encode()
        writer.write(
            b"HTTP/1.1 "
            + status
            + b"\r\nContent-Type: text/plain; charset=utf-8\r\n"
            + extra
            + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            + body
        )
        with contextlib.suppress(Exception):
            await writer.drain()

    @staticmethod
    async def _pipe(
        c_r: asyncio.StreamReader,
        c_w: asyncio.StreamWriter,
        u_r: asyncio.StreamReader,
        u_w: asyncio.StreamWriter,
    ) -> None:
        async def copy(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
            try:
                while data := await src.read(65536):
                    dst.write(data)
                    await dst.drain()
            except (ConnectionError, asyncio.CancelledError):
                pass
            finally:
                with contextlib.suppress(Exception):
                    dst.close()

        await asyncio.gather(copy(c_r, u_w), copy(u_r, c_w))
