"""Adapter cho nền tảng chưa triển khai: luôn trả BLOCKED kèm lý do, không bao giờ giả lập PASSED."""

from typing import Any

from omnitest_adapters.core.base import (
    Capabilities,
    EnvironmentCheck,
    ExecutionContext,
    SupportStatus,
)
from omnitest_adapters.core.results import AdapterResult, Outcome


class NotSupportedAdapter:
    status = SupportStatus.NOT_SUPPORTED

    def __init__(self, key: str, display_name: str, kinds: tuple[str, ...], reason: str) -> None:
        self.key = key
        self.display_name = display_name
        self.test_kinds = kinds
        self.reason = reason

    def capabilities(self) -> Capabilities:
        return Capabilities(test_kinds=list(self.test_kinds), features=[])

    def check_environment(self) -> EnvironmentCheck:
        return EnvironmentCheck(False, self.reason)

    async def execute(self, ctx: ExecutionContext, definition: Any) -> AdapterResult:
        return AdapterResult(
            Outcome.BLOCKED,
            [],
            f"Adapter {self.display_name} chưa được hỗ trợ: {self.reason}",
            "not_supported",
        )
