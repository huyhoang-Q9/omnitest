"""Container proxy của sandbox: nghe trên Unix socket dùng chung với container chạy test, cho ra mạng theo
đúng chính sách của môi trường (allowlist host, chặn mạng nội bộ nếu chưa bật, luôn chặn metadata cloud)."""

import asyncio
import json
import os
import signal

from omnitest_adapters.core.network import NetworkPolicy
from omnitest_adapters.web_playwright.egress_proxy import EgressProxy

SOCK = "/run/omnitest/proxy.sock"


async def main() -> None:
    cfg = json.loads(os.environ["OMNITEST_PROXY_POLICY"])
    policy = NetworkPolicy(tuple(cfg["allowed_hosts"]), bool(cfg["allow_private_network"]))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, stop.set)
    async with EgressProxy(
        policy, unix_path=SOCK, on_block=lambda m: print(f"BLOCKED {m}", flush=True)
    ):
        print("READY", flush=True)
        await stop.wait()


if __name__ == "__main__":
    if os.path.exists(SOCK):
        os.unlink(SOCK)
    asyncio.run(main())
