"""Adapter Desktop (macOS, Windows) và Mobile (Android, iOS) qua Appium server, giao thức W3C WebDriver.

- URL Appium server là Base URL của môi trường; chịu cùng chính sách mạng chống SSRF như test API.
- Không có Appium server, driver hoặc thiết bị: lần chạy trả **Bị chặn** kèm lý do, không bao giờ báo đạt.
- Không chờ cố định: tìm phần tử và kiểm tra bằng vòng hỏi lại có thời hạn của từng bước.
- Mỗi lần chạy mở một phiên Appium mới và luôn đóng phiên khi xong.

Trạng thái: THỬ NGHIỆM. Giao thức đã kiểm thử với Appium server thật dùng driver "fake" chính thức của Appium;
chưa kiểm thử với thiết bị Android/iOS hay máy macOS/Windows thật.
"""

import asyncio
import base64
import time
from typing import Any

import httpx

from omnitest_adapters.core.base import (
    CancelledByUserError,
    Capabilities,
    EnvironmentCheck,
    ExecutionContext,
    SupportStatus,
)
from omnitest_adapters.core.definitions import AppStep, AppTestDefinition
from omnitest_adapters.core.network import BlockedTargetError, check_url, guarded_transport
from omnitest_adapters.core.results import AdapterResult, ArtifactFile, Outcome, StepOutcome
from omnitest_adapters.core.templating import MissingVariableError

W3C_ELEMENT = "element-6066-11e4-a52e-4f735466cecc"
STRATEGY = {
    "accessibility_id": "accessibility id",
    "id": "id",
    "name": "name",
    "xpath": "xpath",
    "class_name": "class name",
    "ios_predicate": "-ios predicate string",
    "ios_class_chain": "-ios class chain",
    "android_uiautomator": "-android uiautomator",
}
# platformName, automationName mặc định theo loại test (driver Appium tương ứng phải được cài trên server).
PLATFORM = {
    "mobile_android": ("Android", "UiAutomator2"),
    "mobile_ios": ("iOS", "XCUITest"),
    "desktop_macos": ("mac", "Mac2"),
    "desktop_windows": ("Windows", "Windows"),
}
POLL_SECONDS = 0.3
SESSION_TIMEOUT_SECONDS = 180


class WebDriverError(Exception):
    def __init__(self, error: str, message: str, status: int) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.status = status


class _Session:
    def __init__(self, client: httpx.AsyncClient, base: str) -> None:
        self.client = client
        self.base = base.rstrip("/")
        self.id: str | None = None

    async def call(
        self,
        method: str,
        path: str,
        body: Any = None,
        timeout: float = 60,  # noqa: ASYNC109 - thời gian chờ theo từng lệnh WebDriver
    ) -> Any:
        url = f"{self.base}{path}"
        res = await self.client.request(method, url, json=body, timeout=timeout)
        try:
            data = res.json()
        except ValueError:
            data = {}
        value = data.get("value") if isinstance(data, dict) else None
        if res.status_code >= 400:
            err = value if isinstance(value, dict) else {}
            raise WebDriverError(
                str(err.get("error") or f"http {res.status_code}"),
                str(err.get("message") or res.text[:300]),
                res.status_code,
            )
        return value

    async def create(self, caps: dict[str, Any]) -> None:
        value = await self.call(
            "POST",
            "/session",
            {"capabilities": {"alwaysMatch": caps, "firstMatch": [{}]}},
            timeout=SESSION_TIMEOUT_SECONDS,
        )
        sid = value.get("sessionId") if isinstance(value, dict) else None
        if not sid:
            raise WebDriverError("session not created", "Appium không trả sessionId", 500)
        self.id = str(sid)

    def s(self, path: str = "") -> str:
        return f"/session/{self.id}{path}"

    async def find(self, using: str, value: str) -> str | None:
        try:
            el = await self.call("POST", self.s("/element"), {"using": using, "value": value})
        except WebDriverError as exc:
            if exc.error == "no such element":
                return None
            raise
        if isinstance(el, dict):
            eid = el.get(W3C_ELEMENT) or el.get("ELEMENT")
            return str(eid) if eid else None
        return None

    async def close(self) -> None:
        if self.id:
            try:
                await self.call("DELETE", self.s(), timeout=30)
            except (WebDriverError, httpx.HTTPError):
                pass
            self.id = None


class AppiumAdapter:
    status = SupportStatus.EXPERIMENTAL

    def __init__(self, key: str, display_name: str, kinds: tuple[str, ...]) -> None:
        self.key = key
        self.display_name = display_name
        self.test_kinds = kinds

    def capabilities(self) -> Capabilities:
        return Capabilities(
            test_kinds=list(self.test_kinds), features=["appium", "w3c", "screenshot"]
        )

    def check_environment(self) -> EnvironmentCheck:
        return EnvironmentCheck(
            True,
            "Thử nghiệm: cần Appium server (Base URL của môi trường), driver và thiết bị/ứng dụng thật; "
            "thiếu thì lần chạy báo Bị chặn",
        )

    def _caps(self, ctx: ExecutionContext, definition: AppTestDefinition) -> dict[str, Any]:
        platform, automation = PLATFORM[definition.kind]
        override = ctx.settings.get("appium_platform_override")
        if isinstance(override, dict):
            platform = str(override.get("platformName", platform))
            automation = str(override.get("automationName", automation))
        caps: dict[str, Any] = {"platformName": platform, "appium:automationName": automation}
        for key, value in definition.capabilities.items():
            bare = key.removeprefix("appium:")
            caps[f"appium:{bare}"] = (
                ctx.variables.render(value) if isinstance(value, str) else value
            )
        return caps

    async def execute(self, ctx: ExecutionContext, definition: AppTestDefinition) -> AdapterResult:
        v = ctx.variables
        if not definition.steps:
            return AdapterResult(
                Outcome.BLOCKED,
                [],
                "Test chưa có bước tự động (chỉ có mô tả thủ công). Thêm bước Appium để chạy được.",
                "no_steps",
            )
        try:
            await check_url(ctx.base_url, ctx.policy)
            caps = self._caps(ctx, definition)
        except BlockedTargetError as exc:
            return AdapterResult(Outcome.BLOCKED, [], str(exc), "blocked_target")
        except MissingVariableError as exc:
            return AdapterResult(Outcome.ERROR, [], str(exc), "missing_variable")

        steps: list[StepOutcome] = []
        async with httpx.AsyncClient(
            transport=guarded_transport(ctx.policy), trust_env=False, follow_redirects=False
        ) as client:
            session = _Session(client, ctx.base_url)
            try:
                await session.create(caps)
            except (httpx.HTTPError, BlockedTargetError) as exc:
                return AdapterResult(
                    Outcome.BLOCKED,
                    [],
                    f"Không kết nối được Appium server tại {ctx.base_url}: {exc.__class__.__name__}",
                    "appium_unavailable",
                )
            except WebDriverError as exc:
                return AdapterResult(
                    Outcome.BLOCKED,
                    [],
                    v.mask(
                        f"Appium không tạo được phiên (driver, thiết bị hoặc ứng dụng chưa sẵn sàng): {exc.message[:500]}"
                    ),
                    "appium_session",
                )
            status, error, error_type = Outcome.PASSED, None, None
            try:
                for index, step in enumerate(definition.steps):
                    try:
                        await ctx.checkpoint()
                    except CancelledByUserError:
                        status, error, error_type = Outcome.CANCELLED, "Đã hủy", "cancelled"
                        break
                    outcome = await self._run_step(session, ctx, index, step)
                    steps.append(outcome)
                    if ctx.on_step:
                        await ctx.on_step(outcome)
                    if outcome.status != Outcome.PASSED:
                        status, error = outcome.status, outcome.error
                        error_type = outcome.details.get("error_type")
                        png = await self._screenshot(session)
                        if png:
                            outcome.artifacts.append(
                                ArtifactFile(
                                    "screenshot", f"step-{index + 1}-loi.png", "image/png", png
                                )
                            )
                        for j, rest in enumerate(definition.steps[index + 1 :], start=index + 1):
                            steps.append(
                                StepOutcome(
                                    j,
                                    rest.name,
                                    Outcome.SKIPPED,
                                    0,
                                    ["Bỏ qua do bước trước không đạt"],
                                )
                            )
                        break
            finally:
                await session.close()
        return AdapterResult(status, steps, v.mask(error) if error else None, error_type)

    @staticmethod
    async def _screenshot(session: _Session) -> bytes | None:
        try:
            data = await session.call("GET", session.s("/screenshot"), timeout=30)
            return base64.b64decode(data) if isinstance(data, str) else None
        except (WebDriverError, httpx.HTTPError, ValueError):
            return None

    async def _run_step(
        self, session: _Session, ctx: ExecutionContext, index: int, step: AppStep
    ) -> StepOutcome:
        v = ctx.variables
        started = time.monotonic()
        log: list[str] = []
        details: dict[str, Any] = {"action": step.action}
        artifacts: list[ArtifactFile] = []
        timeout_s = min(step.timeout_ms, max(ctx.remaining_ms(), 1)) / 1000
        deadline = time.monotonic() + timeout_s

        def done(
            status: Outcome, error: str | None = None, error_type: str | None = None
        ) -> StepOutcome:
            if error_type:
                details["error_type"] = error_type
            return StepOutcome(
                index,
                step.name,
                status,
                int((time.monotonic() - started) * 1000),
                [v.mask(x) for x in log],
                v.mask(error) if error else None,
                details,
                artifacts,
            )

        try:
            value = v.render(step.value) if step.value is not None else None
            locator = v.render(step.locator.value) if step.locator else None
        except MissingVariableError as exc:
            return done(Outcome.ERROR, str(exc), "missing_variable")
        using = STRATEGY[step.locator.strategy] if step.locator else None
        if step.locator:
            details["locator"] = v.mask(f"{step.locator.strategy}={locator}")
        log.append(
            f"{step.action} {details.get('locator', '')} {v.mask(value) if value is not None else ''}".strip()
        )

        async def wait_element() -> str | None:
            assert using and locator
            while True:
                eid = await session.find(using, locator)
                if eid or time.monotonic() >= deadline:
                    return eid
                await asyncio.sleep(POLL_SECONDS)

        try:
            match step.action:
                case "tap" | "type" | "clear":
                    eid = await wait_element()
                    if not eid:
                        return done(
                            Outcome.FAILED,
                            f"Không tìm thấy phần tử sau {step.timeout_ms} ms",
                            "not_found",
                        )
                    if step.action == "tap":
                        await session.call("POST", session.s(f"/element/{eid}/click"), {})
                    elif step.action == "clear":
                        await session.call("POST", session.s(f"/element/{eid}/clear"), {})
                    else:
                        await session.call(
                            "POST", session.s(f"/element/{eid}/value"), {"text": value}
                        )
                case "expect_visible" | "expect_text":
                    last = ""
                    while True:
                        eid = await session.find(using or "", locator or "")
                        if eid:
                            if step.action == "expect_visible":
                                if (
                                    await session.call(
                                        "GET", session.s(f"/element/{eid}/displayed")
                                    )
                                    is True
                                ):
                                    break
                            else:
                                last = str(
                                    await session.call("GET", session.s(f"/element/{eid}/text"))
                                    or ""
                                )
                                if value is not None and value in last:
                                    break
                        if time.monotonic() >= deadline:
                            if step.action == "expect_visible":
                                return done(
                                    Outcome.FAILED,
                                    f"Phần tử không hiển thị sau {step.timeout_ms} ms",
                                    "assertion",
                                )
                            return done(
                                Outcome.FAILED,
                                f"Nội dung '{last[:200]}' không chứa '{value}' sau {step.timeout_ms} ms",
                                "assertion",
                            )
                        await asyncio.sleep(POLL_SECONDS)
                case "expect_hidden":
                    while True:
                        eid = await session.find(using or "", locator or "")
                        if (
                            not eid
                            or await session.call("GET", session.s(f"/element/{eid}/displayed"))
                            is False
                        ):
                            break
                        if time.monotonic() >= deadline:
                            return done(
                                Outcome.FAILED,
                                f"Phần tử vẫn hiển thị sau {step.timeout_ms} ms",
                                "assertion",
                            )
                        await asyncio.sleep(POLL_SECONDS)
                case "screenshot":
                    png = await self._screenshot(session)
                    if png is None:
                        return done(
                            Outcome.ERROR, "Appium không trả ảnh chụp màn hình", "screenshot"
                        )
                    artifacts.append(
                        ArtifactFile("screenshot", f"step-{index + 1}.png", "image/png", png)
                    )
                case "back":
                    await session.call("POST", session.s("/back"), {})
        except WebDriverError as exc:
            return done(
                Outcome.FAILED, f"Appium báo lỗi '{exc.error}': {exc.message[:500]}", "appium_error"
            )
        except (httpx.HTTPError, BlockedTargetError) as exc:
            return done(
                Outcome.ERROR,
                f"Mất kết nối Appium server: {exc.__class__.__name__}",
                "appium_unavailable",
            )
        return done(Outcome.PASSED)
