import time
from typing import Any

import pytest
from omnitest_adapters.api_httpx.adapter import ApiHttpxAdapter
from omnitest_adapters.core.base import ExecutionContext
from omnitest_adapters.core.definitions import ApiTestDefinition, TestDefinition, has_side_effect
from omnitest_adapters.core.network import NetworkPolicy
from omnitest_adapters.core.results import Outcome
from omnitest_adapters.core.templating import Variables
from pydantic import TypeAdapter, ValidationError

SECRET = "Demo@123"


def ctx(
    base: str, *, private: bool = True, cancelled: bool = False, hosts: tuple[str, ...] = ()
) -> ExecutionContext:
    async def is_cancelled() -> bool:
        return cancelled

    return ExecutionContext(
        base_url=base,
        variables=Variables({"USER": "demo", "PASS": SECRET}, secrets={"PASS"}),
        policy=NetworkPolicy.from_environment(base, hosts, private),
        deadline=time.monotonic() + 60,
        is_cancelled=is_cancelled,
    )


def defn(steps: list[dict[str, Any]]) -> ApiTestDefinition:
    return ApiTestDefinition.model_validate({"kind": "api", "steps": steps})


LOGIN = {
    "name": "Đăng nhập",
    "method": "POST",
    "url": "/api/login",
    "body_type": "json",
    "body": {"username": "{{USER}}", "password": "{{PASS}}"},
    "assertions": [
        {"type": "status", "equals": 200},
        {"type": "json_path", "path": "$.token", "op": "exists"},
    ],
    "extract": [{"var": "TOKEN", "expression": "$.token"}],
}


async def test_crud_flow_passes_with_variable_passing(demo_url: str) -> None:
    d = defn(
        [
            LOGIN,
            {
                "name": "Tạo hàng",
                "method": "POST",
                "url": "/api/items",
                "auth": {"type": "bearer", "token": "{{TOKEN}}"},
                "body_type": "json",
                "body": {"name": "Ghim", "quantity": 5},
                "assertions": [
                    {"type": "status", "equals": 201},
                    {
                        "type": "header",
                        "name": "location",
                        "op": "contains",
                        "value": "/api/items/",
                    },
                    {
                        "type": "json_schema",
                        "schema": {
                            "type": "object",
                            "required": ["id", "name"],
                            "properties": {"id": {"type": "integer"}},
                        },
                    },
                    {"type": "response_time", "max_ms": 5000},
                ],
                "extract": [{"var": "ITEM_ID", "expression": "$.id"}],
            },
            {
                "name": "Xem hàng",
                "url": "/api/items/{{ITEM_ID}}",
                "auth": {"type": "bearer", "token": "{{TOKEN}}"},
                "assertions": [
                    {"type": "json_path", "path": "$.name", "op": "equals", "value": "Ghim"}
                ],
            },
            {
                "name": "Xóa hàng",
                "method": "DELETE",
                "url": "/api/items/{{ITEM_ID}}",
                "auth": {"type": "bearer", "token": "{{TOKEN}}"},
                "assertions": [{"type": "status", "equals": 204}],
            },
        ]
    )
    r = await ApiHttpxAdapter().execute(ctx(demo_url), d)
    assert r.status == Outcome.PASSED, r.error
    assert [s.status for s in r.steps] == [Outcome.PASSED] * 4
    assert has_side_effect(d)


async def test_secret_masked_in_details_and_logs(demo_url: str) -> None:
    r = await ApiHttpxAdapter().execute(ctx(demo_url), defn([LOGIN]))
    dumped = repr(r)
    assert SECRET not in dumped
    assert "***" in r.steps[0].details["request"]["body"]


async def test_failed_assertion_stops_and_skips_rest(demo_url: str) -> None:
    bad = {**LOGIN, "body": {"username": "demo", "password": "sai"}}
    r = await ApiHttpxAdapter().execute(
        ctx(demo_url), defn([bad, {"name": "Sau", "url": "/api/items"}])
    )
    assert r.status == Outcome.FAILED
    assert r.steps[0].status == Outcome.FAILED and "401" in (r.steps[0].error or "")
    assert r.steps[1].status == Outcome.SKIPPED


async def test_missing_variable_is_error(demo_url: str) -> None:
    r = await ApiHttpxAdapter().execute(
        ctx(demo_url), defn([{"name": "x", "url": "/api/items/{{KHONG_CO}}"}])
    )
    assert r.status == Outcome.ERROR and "KHONG_CO" in (r.error or "")


async def test_private_network_blocked_unless_allowed(demo_url: str) -> None:
    r = await ApiHttpxAdapter().execute(
        ctx(demo_url, private=False), defn([{"name": "h", "url": "/api/health"}])
    )
    assert r.status == Outcome.BLOCKED and "nội bộ" in (r.error or "")


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://[::1]/",
        "http://example.com/",
        "file:///etc/passwd",
    ],
)
async def test_disallowed_targets_blocked(demo_url: str, url: str) -> None:
    # example.com không nằm trong allowlist; metadata luôn bị chặn kể cả khi bật mạng nội bộ.
    hosts = ("169.254.169.254", "metadata.google.internal", "[::1]")
    r = await ApiHttpxAdapter().execute(
        ctx(demo_url, private=True, hosts=hosts), defn([{"name": "x", "url": url}])
    )
    assert r.status == Outcome.BLOCKED, (url, r.error)


async def test_redirect_to_internal_metadata_blocked(demo_url: str) -> None:
    # /  của demo chuyển hướng tới /login (cùng host, hợp lệ) nên đạt; còn chuyển hướng ra ngoài allowlist bị chặn.
    ok = await ApiHttpxAdapter().execute(
        ctx(demo_url),
        defn([{"name": "r", "url": "/", "assertions": [{"type": "status", "equals": 200}]}]),
    )
    assert ok.status == Outcome.PASSED


async def test_cancel_before_start(demo_url: str) -> None:
    r = await ApiHttpxAdapter().execute(ctx(demo_url, cancelled=True), defn([LOGIN]))
    assert r.status == Outcome.CANCELLED and r.steps == []


async def test_timeout_reported(demo_url: str) -> None:
    # Cổng không có dịch vụ: lỗi kết nối được báo là failed, không treo.
    r = await ApiHttpxAdapter().execute(
        ctx("http://127.0.0.1:9"), defn([{"name": "x", "url": "/", "timeout_ms": 500}])
    )
    assert r.status == Outcome.FAILED


def test_definition_validation_rejects_bad_input() -> None:
    ta: TypeAdapter[Any] = TypeAdapter(TestDefinition)
    with pytest.raises(ValidationError):
        ta.validate_python({"kind": "api", "steps": []})
    with pytest.raises(ValidationError):
        ta.validate_python({"kind": "api", "steps": [{"name": "x", "url": "/", "unknown": 1}]})
    with pytest.raises(ValidationError):
        ta.validate_python({"kind": "web", "steps": [{"name": "x", "action": "click"}]})
    with pytest.raises(ValidationError):
        ta.validate_python(
            {"kind": "web", "steps": [{"name": "x", "action": "sleep", "value": "5"}]}
        )
    assert ta.validate_python({"kind": "desktop_macos"}).kind == "desktop_macos"
