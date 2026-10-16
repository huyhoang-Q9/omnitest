"""Contract chung của adapter và registry."""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from omnitest_adapters.core.network import NetworkPolicy
from omnitest_adapters.core.results import AdapterResult, StepOutcome
from omnitest_adapters.core.templating import Variables


class SupportStatus(StrEnum):
    SUPPORTED = "supported"
    EXPERIMENTAL = "experimental"
    NOT_SUPPORTED = "not_supported"


@dataclass
class Capabilities:
    test_kinds: list[str]
    features: list[str] = field(default_factory=list)


@dataclass
class EnvironmentCheck:
    ok: bool
    message: str


class CancelledByUserError(Exception):
    pass


@dataclass
class ExecutionContext:
    base_url: str
    variables: Variables
    policy: NetworkPolicy
    deadline: float  # time.monotonic()
    is_cancelled: Callable[[], Awaitable[bool]]
    on_step: Callable[[StepOutcome], Awaitable[None]] | None = None
    settings: dict[str, Any] = field(default_factory=dict)

    def remaining_ms(self) -> int:
        return max(0, int((self.deadline - time.monotonic()) * 1000))

    async def checkpoint(self) -> None:
        """Gọi giữa các bước: dừng an toàn nếu người dùng hủy."""
        if await self.is_cancelled():
            raise CancelledByUserError("Người dùng đã hủy lần chạy")


class Adapter(Protocol):
    key: str
    display_name: str
    status: SupportStatus
    test_kinds: tuple[str, ...]

    def capabilities(self) -> Capabilities: ...

    def check_environment(self) -> EnvironmentCheck: ...

    async def execute(self, ctx: ExecutionContext, definition: Any) -> AdapterResult: ...


class AdapterRegistry:
    def __init__(self) -> None:
        self._by_key: dict[str, Adapter] = {}
        self._by_kind: dict[str, Adapter] = {}

    def register(self, adapter: Adapter) -> None:
        self._by_key[adapter.key] = adapter
        for kind in adapter.test_kinds:
            self._by_kind[kind] = adapter

    def for_kind(self, kind: str) -> Adapter | None:
        return self._by_kind.get(kind)

    def all(self) -> list[Adapter]:
        return list(self._by_key.values())
