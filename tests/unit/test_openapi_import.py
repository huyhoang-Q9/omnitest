"""Sinh khung test case từ OpenAPI: $ref, vòng lặp, an toàn khi đọc YAML, xác thực, tham số."""

import json
from typing import Any

import pytest

from omnitest_api.services.openapi_import import (
    MAX_OPERATIONS,
    OpenApiError,
    build_plan,
    parse_document,
)

SPEC: dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {"title": "Kho hàng", "version": "1.2"},
    "servers": [{"url": "https://api.example.com/v1"}],
    "security": [{"bearer": []}],
    "components": {
        "securitySchemes": {
            "bearer": {"type": "http", "scheme": "bearer"},
            "key": {"type": "apiKey", "in": "header", "name": "X-Key"},
            "basic": {"type": "http", "scheme": "basic"},
        },
        "schemas": {
            "Item": {
                "type": "object",
                "required": ["name", "qty", "parent"],
                "properties": {
                    "name": {"type": "string", "example": "Bút bi"},
                    "qty": {"type": "integer"},
                    "note": {"type": "string"},
                    "parent": {"$ref": "#/components/schemas/Item"},
                },
            }
        },
        "parameters": {"Id": {"name": "item_id", "in": "path", "required": True}},
    },
    "paths": {
        "/items": {
            "get": {
                "summary": "Danh sách",
                "tags": ["Kho"],
                "parameters": [
                    {"name": "page", "in": "query", "required": True, "schema": {"default": 1}},
                    {"name": "q", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "ok"}},
            },
            "post": {
                "security": [{"key": []}],
                "requestBody": {
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/Item"}}
                    }
                },
                "responses": {"201": {"description": "tạo"}, "400": {"description": "sai"}},
            },
        },
        "/items/{item_id}": {
            "parameters": [{"$ref": "#/components/parameters/Id"}],
            "delete": {"security": [{"basic": []}], "responses": {"204": {"description": ""}}},
            "get": {"security": [], "responses": {"default": {"description": ""}}},
        },
    },
}


def plan(spec: dict[str, Any] = SPEC) -> Any:
    return build_plan(parse_document(json.dumps(spec).encode()))


def step(p: Any, method: str, path: str) -> dict[str, Any]:
    case = next(c for c in p.cases if c.method == method and c.path == path)
    return dict(case.body.definition.model_dump(by_alias=True)["steps"][0])


def test_plan_basics_and_server_prefix() -> None:
    p = plan()
    assert (p.title, p.version, len(p.cases)) == ("Kho hàng", "1.2", 4)
    assert any("/v1" in w for w in p.warnings)
    s = step(p, "GET", "/items")
    assert s["url"] == "/v1/items" and s["query"] == {"page": "1"}  # q không bắt buộc nên bỏ
    assert s["auth"] == {"type": "bearer", "token": "{{API_TOKEN}}"}
    assert s["assertions"] == [{"type": "status", "equals": 200, "one_of": None}]
    case = p.cases[0]
    assert case.body.status.value == "draft" and case.body.tags == ["kho", "openapi"]
    assert case.body.test_data == {"openapi_operation": "GET /items"}


def test_request_body_sample_from_recursive_schema_and_api_key() -> None:
    s = step(plan(), "POST", "/items")
    assert s["body_type"] == "json"
    assert s["body"]["name"] == "Bút bi" and s["body"]["qty"] == 0 and "note" not in s["body"]
    assert s["auth"] == {"type": "api_key", "header": "X-Key", "value": "{{API_KEY}}"}
    assert s["assertions"][0]["equals"] == 201


def test_path_param_variable_basic_auth_and_public_operation() -> None:
    p = plan()
    d = step(p, "DELETE", "/items/{item_id}")
    assert d["url"] == "/v1/items/{{ITEM_ID}}"
    assert d["auth"]["type"] == "basic"
    case = next(c for c in p.cases if c.method == "DELETE")
    assert case.variables == ["ITEM_ID", "API_USERNAME", "API_PASSWORD"]
    g = step(p, "GET", "/items/{item_id}")
    assert g["auth"] == {"type": "none"}  # security: [] nghĩa là công khai
    assert g["assertions"][0]["one_of"] == [200, 201, 202, 204]


def test_yaml_supported_but_aliases_rejected() -> None:
    ok = b"openapi: 3.1.0\ninfo: {title: T, version: '1'}\npaths:\n  /a:\n    get: {responses: {'200': {}}}\n"
    assert len(build_plan(parse_document(ok)).cases) == 1
    bomb = b"openapi: 3.0.0\na: &a [x, x]\nb: [*a, *a]\npaths: {}\n"
    with pytest.raises(OpenApiError, match="alias"):
        parse_document(bomb)
    # Tag Python (thực thi lệnh khi dùng loader không an toàn) bị SafeLoader từ chối.
    with pytest.raises(OpenApiError, match="không hợp lệ"):
        parse_document(b"openapi: 3.0.0\npaths: !!python/object/apply:os.system ['id']\n")


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b'{"swagger": "2.0", "paths": {}}', "Swagger 2.0"),
        (b'{"openapi": "3.0.0"}', "paths"),
        (b"[1, 2]", "object"),
        (b"\xff\xfe\x00", "UTF-8"),
        (b"{not json", "không hợp lệ"),
        (b'{"openapi": "3.0.0", "paths": {}}', "operation"),
    ],
)
def test_invalid_documents(data: bytes, message: str) -> None:
    with pytest.raises(OpenApiError, match=message):
        build_plan(parse_document(data))


def test_external_ref_is_skipped_with_warning() -> None:
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/a": {"get": {"parameters": [{"$ref": "http://evil/x.json"}], "responses": {}}},
            "/b": {"get": {"responses": {"200": {}}}},
        },
    }
    p = plan(spec)
    assert [c.path for c in p.cases] == ["/b"]
    assert any("$ref nội bộ" in w for w in p.warnings)


def test_operation_limit() -> None:
    paths = {f"/p{i}": {"get": {"responses": {"200": {}}}} for i in range(MAX_OPERATIONS + 5)}
    p = plan({"openapi": "3.0.0", "paths": paths})
    assert len(p.cases) == MAX_OPERATIONS and any("chỉ lấy" in w for w in p.warnings)
