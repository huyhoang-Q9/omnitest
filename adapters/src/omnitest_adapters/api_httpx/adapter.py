"""Adapter kiểm thử API bằng HTTPX. Thực thi định nghĩa khai báo, không chạy mã người dùng."""

import base64
import json
import re
import time
from typing import Any
from urllib.parse import urljoin

import httpx
import jsonschema
from jsonpath_ng.ext.parser import parse as jsonpath_parse

from omnitest_adapters.core.base import (
    CancelledByUserError,
    Capabilities,
    EnvironmentCheck,
    ExecutionContext,
    SupportStatus,
)
from omnitest_adapters.core.definitions import (
    ApiStep,
    ApiTestDefinition,
    AssertHeader,
    AssertJsonPath,
    AssertJsonSchema,
    AssertResponseTime,
    AssertStatus,
    AuthApiKey,
    AuthBasic,
    AuthBearer,
)
from omnitest_adapters.core.network import BlockedTargetError, check_url, guarded_transport
from omnitest_adapters.core.results import AdapterResult, Outcome, StepOutcome
from omnitest_adapters.core.templating import MissingVariableError, Variables

MAX_BODY_PREVIEW = 4000
MAX_REDIRECTS = 5
SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie", "proxy-authorization", "x-api-key"}


class AssertionFailedError(Exception):
    pass


def _json_values(path: str, data: Any) -> list[Any]:
    try:
        expr = jsonpath_parse(path)  # type: ignore[no-untyped-call]
    except Exception as exc:
        raise AssertionFailedError(f"JSONPath không hợp lệ: {path}") from exc
    return [m.value for m in expr.find(data)]


def _compare(actual: Any, op: str, expected: Any, found: bool) -> bool:
    match op:
        case "exists":
            return found
        case "not_exists":
            return not found
        case "equals":
            return found and actual == expected
        case "not_equals":
            return not found or actual != expected
        case "contains":
            if not found:
                return False
            if isinstance(actual, str):
                return str(expected) in actual
            if isinstance(actual, list | dict):
                return expected in actual
            return False
        case "gt":
            return found and isinstance(actual, int | float) and actual > float(expected)
        case "lt":
            return found and isinstance(actual, int | float) and actual < float(expected)
        case "matches":
            return (
                found and isinstance(actual, str) and re.search(str(expected), actual) is not None
            )
    return False


def _preview(text: str) -> str:
    return text if len(text) <= MAX_BODY_PREVIEW else text[:MAX_BODY_PREVIEW] + "...(đã cắt)"


def _safe_headers(headers: httpx.Headers | dict[str, str], variables: Variables) -> dict[str, str]:
    return {
        k: ("***" if k.lower() in SENSITIVE_HEADERS else variables.mask(v))
        for k, v in dict(headers).items()
    }


class ApiHttpxAdapter:
    key = "api-httpx"
    display_name = "API (HTTPX)"
    status = SupportStatus.SUPPORTED
    test_kinds = ("api",)

    def capabilities(self) -> Capabilities:
        return Capabilities(
            test_kinds=list(self.test_kinds),
            features=[
                "status",
                "json_path",
                "json_schema",
                "header",
                "response_time",
                "extract",
                "auth",
            ],
        )

    def check_environment(self) -> EnvironmentCheck:
        return EnvironmentCheck(True, "Sẵn sàng")

    async def execute(self, ctx: ExecutionContext, definition: ApiTestDefinition) -> AdapterResult:
        steps: list[StepOutcome] = []
        transport = guarded_transport(ctx.policy)
        async with httpx.AsyncClient(
            transport=transport, trust_env=False, follow_redirects=False
        ) as client:
            for index, step in enumerate(definition.steps):
                try:
                    await ctx.checkpoint()
                except CancelledByUserError:
                    return AdapterResult(Outcome.CANCELLED, steps, "Đã hủy", "cancelled")
                outcome = await self._run_step(client, ctx, index, step)
                steps.append(outcome)
                if ctx.on_step:
                    await ctx.on_step(outcome)
                if outcome.status != Outcome.PASSED:
                    # Các bước sau bỏ qua vì phụ thuộc bước trước.
                    for j, rest in enumerate(definition.steps[index + 1 :], start=index + 1):
                        steps.append(
                            StepOutcome(
                                j, rest.name, Outcome.SKIPPED, 0, ["Bỏ qua do bước trước không đạt"]
                            )
                        )
                    status = outcome.status if outcome.status != Outcome.SKIPPED else Outcome.FAILED
                    return AdapterResult(
                        status, steps, outcome.error, outcome.details.get("error_type")
                    )
        return AdapterResult(Outcome.PASSED, steps)

    async def _send(
        self,
        client: httpx.AsyncClient,
        ctx: ExecutionContext,
        request: httpx.Request,
        step: ApiStep,
        timeout: float,  # noqa: ASYNC109 - timeout truyền cho httpx, không dùng để chờ
    ) -> httpx.Response:
        """Tự theo redirect để kiểm tra từng đích (tránh redirect sang địa chỉ nội bộ)."""
        for _ in range(MAX_REDIRECTS + 1):
            await check_url(str(request.url), ctx.policy)
            response = await client.send(request, follow_redirects=False)
            if not (step.follow_redirects and response.is_redirect and response.next_request):
                return response
            await response.aclose()
            request = response.next_request
            request.extensions["timeout"] = httpx.Timeout(timeout).as_dict()
        raise AssertionFailedError(f"Quá {MAX_REDIRECTS} lần chuyển hướng")

    async def _run_step(
        self, client: httpx.AsyncClient, ctx: ExecutionContext, index: int, step: ApiStep
    ) -> StepOutcome:
        v = ctx.variables
        log: list[str] = []
        started = time.monotonic()
        details: dict[str, Any] = {}

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
                v.mask_obj(details),
            )

        try:
            url = v.render(step.url)
            if not re.match(r"^https?://", url, re.IGNORECASE):
                url = urljoin(ctx.base_url.rstrip("/") + "/", url.lstrip("/"))
            headers = {str(k): str(val) for k, val in v.render(step.headers).items()}
            params = v.render(step.query)
            auth = step.auth
            if isinstance(auth, AuthBearer):
                headers["Authorization"] = f"Bearer {v.render(auth.token)}"
            elif isinstance(auth, AuthApiKey):
                headers[auth.header] = v.render(auth.value)
            elif isinstance(auth, AuthBasic):
                raw = f"{v.render(auth.username)}:{v.render(auth.password)}".encode()
                headers["Authorization"] = "Basic " + base64.b64encode(raw).decode()

            kwargs: dict[str, Any] = {}
            if step.body_type == "json":
                kwargs["json"] = v.render(step.body)
            elif step.body_type == "text":
                kwargs["content"] = str(v.render(step.body or ""))
            elif step.body_type == "form":
                kwargs["data"] = v.render(step.body or {})
        except MissingVariableError as exc:
            return done(Outcome.ERROR, str(exc), "missing_variable")

        timeout = min(step.timeout_ms, max(ctx.remaining_ms(), 1)) / 1000
        request = client.build_request(
            step.method, url, headers=headers, params=params, timeout=timeout, **kwargs
        )
        details["request"] = {
            "method": request.method,
            "url": v.mask(str(request.url)),
            "headers": _safe_headers(request.headers, v),
            "body": _preview(v.mask(request.content.decode("utf-8", "replace")))
            if request.content
            else None,
        }
        log.append(f"{request.method} {request.url}")

        try:
            t0 = time.monotonic()
            response = await self._send(client, ctx, request, step, timeout)
            await response.aread()
            elapsed_ms = int((time.monotonic() - t0) * 1000)
        except BlockedTargetError as exc:
            log.append(f"Bị chặn: {exc}")
            return done(Outcome.BLOCKED, str(exc), "blocked_target")
        except httpx.TimeoutException:
            return done(
                Outcome.FAILED, f"Hết thời gian chờ phản hồi ({step.timeout_ms} ms)", "timeout"
            )
        except httpx.HTTPError as exc:
            return done(
                Outcome.FAILED, f"Lỗi kết nối: {exc.__class__.__name__}: {exc}", "connection_error"
            )
        except AssertionFailedError as exc:
            return done(Outcome.FAILED, str(exc), "assertion")

        text = response.text
        body_json: Any = None
        try:
            body_json = json.loads(text) if text else None
        except ValueError:
            body_json = None
        details["response"] = {
            "status": response.status_code,
            "elapsed_ms": elapsed_ms,
            "headers": _safe_headers(response.headers, v),
            "body": _preview(text),
        }
        log.append(f"-> {response.status_code} trong {elapsed_ms} ms")

        results: list[dict[str, Any]] = []
        failed: list[str] = []
        for a in step.assertions:
            ok, msg = self._check(a, response, body_json, elapsed_ms, v)
            results.append({"type": a.type, "ok": ok, "message": msg})
            log.append(("Đạt: " if ok else "KHÔNG ĐẠT: ") + msg)
            if not ok:
                failed.append(msg)
        details["assertions"] = results

        for ex in step.extract:
            if ex.source == "header":
                val = response.headers.get(ex.expression)
                found = val is not None
            else:
                vals = _json_values(ex.expression, body_json) if body_json is not None else []
                found, val = bool(vals), (vals[0] if vals else None)
            if not found:
                failed.append(f"Không trích xuất được {ex.var} từ {ex.expression}")
            else:
                v.set(ex.var, val)
                log.append(f"Trích xuất {ex.var}")
        if failed:
            return done(Outcome.FAILED, "; ".join(failed), "assertion")
        return done(Outcome.PASSED)

    def _check(
        self, a: Any, response: httpx.Response, body: Any, elapsed_ms: int, v: Variables
    ) -> tuple[bool, str]:
        if isinstance(a, AssertStatus):
            expected = [a.equals] if a.equals is not None else (a.one_of or [])
            return (
                response.status_code in expected,
                f"Mã trạng thái {response.status_code}, mong đợi {expected}",
            )
        if isinstance(a, AssertResponseTime):
            return (
                elapsed_ms <= a.max_ms,
                f"Thời gian phản hồi {elapsed_ms} ms, tối đa {a.max_ms} ms",
            )
        if isinstance(a, AssertHeader):
            actual = response.headers.get(a.name)
            want = v.render(a.value) if a.value is not None else None
            ok = _compare(actual, a.op, want, actual is not None)
            return ok, f"Header {a.name} {a.op} {want if want is not None else ''}".strip()
        if isinstance(a, AssertJsonPath):
            if body is None:
                return False, f"Phản hồi không phải JSON, không kiểm tra được {a.path}"
            try:
                vals = _json_values(a.path, body)
            except AssertionFailedError as exc:
                return False, str(exc)
            expected = v.render(a.value)
            actual = vals[0] if vals else None
            ok = _compare(actual, a.op, expected, bool(vals))
            shown = json.dumps(actual, ensure_ascii=False)[:200]
            return (
                ok,
                f"{a.path} {a.op} {json.dumps(expected, ensure_ascii=False)} (thực tế {shown})",
            )
        if isinstance(a, AssertJsonSchema):
            if body is None:
                return False, "Phản hồi không phải JSON, không kiểm tra được schema"
            try:
                jsonschema.validate(body, a.schema_)
                return True, "Khớp JSON schema"
            except jsonschema.ValidationError as exc:
                return False, f"Sai JSON schema tại {list(exc.absolute_path)}: {exc.message}"
            except jsonschema.SchemaError as exc:
                return False, f"JSON schema không hợp lệ: {exc.message}"
        return False, "Loại kiểm tra không hỗ trợ"
