"""Adapter kiểm thử Web bằng Playwright (Python, async).

Không dùng sleep cố định: mọi hành động dùng cơ chế auto-wait của Playwright, kiểm tra dùng expect() có timeout.
Mọi request của trình duyệt đi qua bộ lọc đích được phép của môi trường.
"""

import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page, Route, async_playwright, expect
from playwright.async_api import TimeoutError as PlaywrightTimeout

from omnitest_adapters.core.base import (
    CancelledByUserError,
    Capabilities,
    EnvironmentCheck,
    ExecutionContext,
    SupportStatus,
)
from omnitest_adapters.core.definitions import WebStep, WebTestDefinition
from omnitest_adapters.core.network import BlockedTargetError, check_url, check_url_static
from omnitest_adapters.core.results import AdapterResult, ArtifactFile, Outcome, StepOutcome
from omnitest_adapters.core.templating import MissingVariableError
from omnitest_adapters.web_playwright.trace_redaction import redact_trace

ALLOWED_INTERNAL_SCHEMES = {"data", "blob", "about"}


def chromium_executable() -> str | None:
    """Cho phép dùng Chromium có sẵn trên máy khi bản trình duyệt của Playwright chưa được cài."""
    return os.environ.get("OMNITEST_CHROMIUM_EXECUTABLE") or None


def _locator(page: Page, selector: str) -> Locator:
    """Hỗ trợ cú pháp thân thiện: role=button[name="Lưu"], label=Email, placeholder=..., testid=..., text=..."""
    m = re.fullmatch(r'role=(\w+)(?:\[name=(["\'])(.*)\2\])?', selector)
    if m:
        # Playwright khai báo role là Literal; vai trò sai sẽ báo lỗi rõ ràng lúc chạy.
        role: Any = m.group(1)
        if m.group(3) is not None:
            return page.get_by_role(role, name=m.group(3))
        return page.get_by_role(role)
    for prefix, fn in (
        ("label=", page.get_by_label),
        ("placeholder=", page.get_by_placeholder),
        ("testid=", page.get_by_test_id),
    ):
        if selector.startswith(prefix):
            return fn(selector[len(prefix) :])
    return page.locator(selector)


class WebPlaywrightAdapter:
    key = "web-playwright"
    display_name = "Web UI (Playwright)"
    status = SupportStatus.SUPPORTED
    test_kinds = ("web",)

    def capabilities(self) -> Capabilities:
        return Capabilities(
            test_kinds=list(self.test_kinds), features=["chromium", "screenshot", "trace"]
        )

    def check_environment(self) -> EnvironmentCheck:
        exe = chromium_executable()
        if exe and not Path(exe).exists():
            return EnvironmentCheck(False, f"Không tìm thấy Chromium tại {exe}")
        return EnvironmentCheck(True, "Sẵn sàng")

    async def execute(self, ctx: ExecutionContext, definition: WebTestDefinition) -> AdapterResult:
        v = ctx.variables
        steps: list[StepOutcome] = []
        artifacts: list[ArtifactFile] = []
        blocked: list[str] = []

        async def guard(route: Route) -> None:
            url = route.request.url
            scheme = urlsplit(url).scheme
            if scheme in ALLOWED_INTERNAL_SCHEMES:
                await route.continue_()
                return
            try:
                if route.request.is_navigation_request():
                    await check_url(url, ctx.policy)
                else:
                    check_url_static(url, ctx.policy)
            except BlockedTargetError as exc:
                blocked.append(f"{url}: {exc}")
                await route.abort("blockedbyclient")
                return
            await route.continue_()

        async with async_playwright() as pw:
            browser_type = getattr(pw, definition.browser)
            launch: dict[str, Any] = {"headless": True}
            if definition.browser == "chromium" and chromium_executable():
                launch["executable_path"] = chromium_executable()
            try:
                browser = await browser_type.launch(**launch)
            except PlaywrightError as exc:
                return AdapterResult(
                    Outcome.BLOCKED,
                    [],
                    f"Không khởi động được trình duyệt {definition.browser}: {exc.message}",
                    "browser_unavailable",
                )
            try:
                context = await browser.new_context(
                    viewport={
                        "width": definition.viewport.width,
                        "height": definition.viewport.height,
                    },
                    base_url=ctx.base_url,
                    ignore_https_errors=False,
                    service_workers="block",
                )
                await context.route("**/*", guard)
                if definition.trace != "off":
                    await context.tracing.start(screenshots=True, snapshots=True)
                page = await context.new_page()
                status = Outcome.PASSED
                error: str | None = None
                error_type: str | None = None
                for index, step in enumerate(definition.steps):
                    try:
                        await ctx.checkpoint()
                    except CancelledByUserError:
                        status, error, error_type = Outcome.CANCELLED, "Đã hủy", "cancelled"
                        break
                    outcome = await self._run_step(page, ctx, index, step, blocked)
                    steps.append(outcome)
                    if ctx.on_step:
                        await ctx.on_step(outcome)
                    if outcome.status != Outcome.PASSED:
                        status = outcome.status
                        error, error_type = outcome.error, outcome.details.get("error_type")
                        try:
                            png = await page.screenshot(full_page=True)
                            outcome.artifacts.append(
                                ArtifactFile(
                                    "screenshot", f"step-{index + 1}-loi.png", "image/png", png
                                )
                            )
                        except PlaywrightError:
                            pass
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
                keep_trace = definition.trace == "always" or (
                    definition.trace == "on_failure" and status != Outcome.PASSED
                )
                if definition.trace != "off":
                    if keep_trace:
                        with tempfile.TemporaryDirectory() as tmp:
                            trace_path = Path(tmp) / "trace.zip"
                            await context.tracing.stop(path=str(trace_path))
                            redacted = redact_trace(trace_path.read_bytes(), v.secret_values)
                            if redacted is not None:
                                artifacts.append(
                                    ArtifactFile("trace", "trace.zip", "application/zip", redacted)
                                )
                            else:
                                artifacts.append(
                                    ArtifactFile(
                                        "log",
                                        "trace-khong-luu.txt",
                                        "text/plain",
                                        "Không lưu trace vì không che được hết secret trong trace.".encode(),
                                    )
                                )
                    else:
                        await context.tracing.stop()
                await context.close()
            finally:
                await browser.close()
        return AdapterResult(status, steps, v.mask(error) if error else None, error_type, artifacts)

    async def _run_step(
        self, page: Page, ctx: ExecutionContext, index: int, step: WebStep, blocked: list[str]
    ) -> StepOutcome:
        v = ctx.variables
        started = time.monotonic()
        log: list[str] = []
        details: dict[str, Any] = {"action": step.action, "selector": step.selector}
        artifacts: list[ArtifactFile] = []
        timeout = min(step.timeout_ms, max(ctx.remaining_ms(), 1))
        blocked_before = len(blocked)

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
            selector = v.render(step.selector) if step.selector else None
        except MissingVariableError as exc:
            return done(Outcome.ERROR, str(exc), "missing_variable")
        loc = _locator(page, selector) if selector else None
        # Hiển thị giá trị đã che secret (VD mật khẩu nhập vào form).
        log.append(
            f"{step.action} {selector or ''} {v.mask(value) if value is not None else ''}".strip()
        )

        try:
            match step.action:
                case "goto":
                    assert value is not None
                    target = (
                        value
                        if re.match(r"^https?://", value)
                        else urljoin(ctx.base_url.rstrip("/") + "/", value.lstrip("/"))
                    )
                    await check_url(target, ctx.policy)
                    await page.goto(target, timeout=timeout, wait_until="load")
                case "click":
                    assert loc is not None
                    await loc.click(timeout=timeout)
                case "fill":
                    assert loc is not None and value is not None
                    await loc.fill(value, timeout=timeout)
                case "select":
                    assert loc is not None and value is not None
                    await loc.select_option(value, timeout=timeout)
                case "check":
                    assert loc is not None
                    await loc.check(timeout=timeout)
                case "uncheck":
                    assert loc is not None
                    await loc.uncheck(timeout=timeout)
                case "press":
                    assert loc is not None and value is not None
                    await loc.press(value, timeout=timeout)
                case "wait_for":
                    assert loc is not None
                    await loc.wait_for(state="visible", timeout=timeout)
                case "expect_visible":
                    assert loc is not None
                    await expect(loc).to_be_visible(timeout=timeout)
                case "expect_hidden":
                    assert loc is not None
                    await expect(loc).to_be_hidden(timeout=timeout)
                case "expect_text":
                    assert loc is not None and value is not None
                    await expect(loc).to_contain_text(value, timeout=timeout)
                case "expect_url":
                    assert value is not None
                    await expect(page).to_have_url(re.compile(re.escape(value)), timeout=timeout)
                case "expect_title":
                    assert value is not None
                    await expect(page).to_have_title(re.compile(re.escape(value)), timeout=timeout)
                case "screenshot":
                    png = await page.screenshot(full_page=True, timeout=timeout)
                    artifacts.append(
                        ArtifactFile("screenshot", f"step-{index + 1}.png", "image/png", png)
                    )
        except BlockedTargetError as exc:
            return done(Outcome.BLOCKED, str(exc), "blocked_target")
        except PlaywrightTimeout:
            msg = f"Hết {timeout} ms mà điều kiện chưa thỏa"
            if len(blocked) > blocked_before:
                return done(
                    Outcome.BLOCKED,
                    "Request bị chặn: " + "; ".join(blocked[blocked_before:])[:500],
                    "blocked_target",
                )
            return done(Outcome.FAILED, msg, "timeout")
        except AssertionError as exc:
            msg = str(exc).splitlines()[0] if str(exc) else "Kiểm tra không đạt"
            return done(Outcome.FAILED, msg[:1000], "assertion")
        except PlaywrightError as exc:
            if len(blocked) > blocked_before:
                return done(
                    Outcome.BLOCKED,
                    "Request bị chặn: " + "; ".join(blocked[blocked_before:])[:500],
                    "blocked_target",
                )
            return done(Outcome.FAILED, exc.message.splitlines()[0][:1000], "browser_error")
        details["url"] = v.mask(page.url)
        return done(Outcome.PASSED)
