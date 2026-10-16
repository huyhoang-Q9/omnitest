"""Sinh khung test case API từ tài liệu OpenAPI 3.x (JSON hoặc YAML).

Mỗi operation thành một test case trạng thái Nháp gồm một bước gọi API và kiểm tra mã trạng thái thành công
khai báo trong tài liệu. Đây là khung để người dùng rà soát và bổ sung, không phải test hoàn chỉnh.

An toàn:
- YAML đọc bằng SafeLoader và cấm alias/anchor (chặn "billion laughs"); giới hạn kích thước ở router.
- Chỉ giải $ref nội bộ (#/...), có giới hạn độ sâu và phát hiện vòng lặp; không tải tài liệu ngoài.
- Không lấy host từ "servers": test luôn gọi Base URL của môi trường (chỉ lấy phần đường dẫn gốc nếu có).
- Giá trị không có ví dụ được thay bằng biến {{TEN_BIEN}}; thiếu biến lúc chạy sẽ báo lỗi rõ, không đoán.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import yaml
from pydantic import ValidationError

from omnitest_api.models import TestType
from omnitest_api.schemas_tests import TestCaseCreate

METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
MAX_OPERATIONS = 300
MAX_REF_DEPTH = 12
MARKER_KEY = "openapi_operation"
SUCCESS_FALLBACK = [200, 201, 202, 204]


class OpenApiError(Exception):
    pass


class _NoAliasLoader(yaml.SafeLoader):
    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            raise OpenApiError(
                "Tài liệu YAML dùng alias/anchor, không được hỗ trợ vì lý do an toàn"
            )
        return super().compose_node(parent, index)


def parse_document(data: bytes) -> dict[str, Any]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise OpenApiError("File phải là văn bản UTF-8 (JSON hoặc YAML)") from exc
    try:
        doc = json.loads(text) if text.lstrip().startswith("{") else yaml.load(text, _NoAliasLoader)  # noqa: S506 - loader an toàn tự định nghĩa
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise OpenApiError("Không đọc được file: JSON/YAML không hợp lệ") from exc
    if not isinstance(doc, dict):
        raise OpenApiError("Tài liệu OpenAPI phải là một object")
    version = str(doc.get("openapi", ""))
    if not version.startswith("3."):
        if "swagger" in doc:
            raise OpenApiError("Chỉ hỗ trợ OpenAPI 3.x; Swagger 2.0 cần chuyển đổi sang 3.x trước")
        raise OpenApiError("Không phải tài liệu OpenAPI 3.x (thiếu trường 'openapi: 3.x')")
    if not isinstance(doc.get("paths"), dict):
        raise OpenApiError("Tài liệu không có 'paths'")
    return doc


@dataclass
class GeneratedCase:
    method: str
    path: str
    body: TestCaseCreate
    variables: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass
class ImportPlan:
    title: str
    version: str
    cases: list[GeneratedCase]
    warnings: list[str]


class _Resolver:
    def __init__(self, doc: dict[str, Any]) -> None:
        self.doc = doc

    def resolve(self, node: Any, seen: tuple[str, ...] = ()) -> Any:
        if not isinstance(node, dict) or "$ref" not in node:
            return node
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/"):
            raise OpenApiError(f"Chỉ hỗ trợ $ref nội bộ, gặp: {str(ref)[:100]}")
        if ref in seen or len(seen) >= MAX_REF_DEPTH:
            return {}
        target: Any = self.doc
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or part not in target:
                raise OpenApiError(f"$ref không tồn tại: {ref[:100]}")
            target = target[part]
        return self.resolve(target, (*seen, ref))

    def sample(self, schema: Any, seen: tuple[int, ...] = (), depth: int = 0) -> Any:
        """Giá trị mẫu tối thiểu theo schema: ưu tiên example/default/enum, chỉ điền thuộc tính bắt buộc."""
        schema = self.resolve(schema)
        if not isinstance(schema, dict) or depth > 6 or id(schema) in seen:
            return None
        seen = (*seen, id(schema))
        for key in ("example", "default"):
            if key in schema:
                return schema[key]
        if isinstance(schema.get("examples"), list) and schema["examples"]:
            return schema["examples"][0]
        if isinstance(schema.get("enum"), list) and schema["enum"]:
            return schema["enum"][0]
        for combo in ("allOf", "oneOf", "anyOf"):
            if isinstance(schema.get(combo), list) and schema[combo]:
                if combo == "allOf":
                    merged: dict[str, Any] = {}
                    for part in schema[combo]:
                        value = self.sample(part, seen, depth + 1)
                        if isinstance(value, dict):
                            merged.update(value)
                    return merged
                return self.sample(schema[combo][0], seen, depth + 1)
        kind = schema.get("type")
        if isinstance(kind, list):
            kind = next((k for k in kind if k != "null"), None)
        if kind == "object" or "properties" in schema:
            props = schema.get("properties") or {}
            required = schema.get("required") or []
            return {
                name: self.sample(props[name], seen, depth + 1)
                for name in required
                if isinstance(name, str) and name in props
            }
        if kind == "array":
            return []
        if kind == "integer":
            return 0
        if kind == "number":
            return 0
        if kind == "boolean":
            return False
        if kind == "string":
            return ""
        return None


def _var_name(*parts: str) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "_", "_".join(parts)).strip("_").upper() or "VALUE"
    if name[0].isdigit():
        name = "P_" + name
    return name[:100]


def _param_example(r: _Resolver, param: dict[str, Any]) -> Any:
    if "example" in param:
        return param["example"]
    examples = param.get("examples")
    if isinstance(examples, dict):
        for ex in examples.values():
            ex = r.resolve(ex)
            if isinstance(ex, dict) and "value" in ex:
                return ex["value"]
    schema = r.resolve(param.get("schema") or {})
    if isinstance(schema, dict):
        for key in ("example", "default"):
            if key in schema:
                return schema[key]
        if isinstance(schema.get("enum"), list) and schema["enum"]:
            return schema["enum"][0]
    return None


def _success_assertion(responses: Any) -> dict[str, Any]:
    codes: list[int] = []
    if isinstance(responses, dict):
        for key in responses:
            k = str(key)
            if k.isdigit() and 200 <= int(k) < 300:
                codes.append(int(k))
    if codes:
        codes.sort()
        return (
            {"type": "status", "equals": codes[0]}
            if len(codes) == 1
            else {"type": "status", "one_of": codes}
        )
    return {"type": "status", "one_of": SUCCESS_FALLBACK}


def _auth(
    r: _Resolver, requirements: Any, variables: list[str]
) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    """Trả (auth, query_bổ_sung, cảnh_báo). Chỉ dùng phương án đầu tiên trong danh sách security."""
    if not isinstance(requirements, list) or not requirements:
        return {"type": "none"}, {}, []
    first = requirements[0]
    if not isinstance(first, dict) or not first:
        return {"type": "none"}, {}, []
    schemes = (r.doc.get("components") or {}).get("securitySchemes") or {}
    name = next(iter(first))
    scheme = r.resolve(schemes.get(name) or {})
    kind = scheme.get("type") if isinstance(scheme, dict) else None
    if kind == "http" and str(scheme.get("scheme", "")).lower() == "basic":
        variables += ["API_USERNAME", "API_PASSWORD"]
        return (
            {"type": "basic", "username": "{{API_USERNAME}}", "password": "{{API_PASSWORD}}"},
            {},
            [],
        )
    if kind in ("http", "oauth2", "openIdConnect"):
        variables.append("API_TOKEN")
        return {"type": "bearer", "token": "{{API_TOKEN}}"}, {}, []
    if kind == "apiKey":
        variables.append("API_KEY")
        where, key = scheme.get("in"), str(scheme.get("name") or "X-API-Key")
        if where == "header":
            return {"type": "api_key", "header": key[:100], "value": "{{API_KEY}}"}, {}, []
        if where == "query":
            return {"type": "none"}, {key: "{{API_KEY}}"}, []
        return (
            {"type": "none"},
            {},
            [f"Xác thực apiKey qua {where} chưa hỗ trợ, cần bổ sung thủ công"],
        )
    return {"type": "none"}, {}, [f"Không nhận diện được cơ chế xác thực '{name}'"]


def build_plan(doc: dict[str, Any], extra_tag: str | None = None) -> ImportPlan:
    r = _Resolver(doc)
    info: dict[str, Any] = doc["info"] if isinstance(doc.get("info"), dict) else {}
    warnings: list[str] = []
    base_path = ""
    servers = doc.get("servers")
    if isinstance(servers, list) and servers and isinstance(servers[0], dict):
        url = str(servers[0].get("url") or "")
        if "{" in url:
            warnings.append("URL server có biến; bỏ qua, dùng Base URL của môi trường")
        else:
            base_path = urlsplit(url).path.rstrip("/")
            if base_path:
                warnings.append(
                    f"Đã thêm tiền tố đường dẫn '{base_path}' lấy từ servers[0]; host luôn là Base URL"
                    " của môi trường được chọn khi chạy"
                )

    cases: list[GeneratedCase] = []
    total_ops = 0
    for path, item in doc["paths"].items():
        item = r.resolve(item)
        if not isinstance(path, str) or not isinstance(item, dict):
            continue
        common = [
            r.resolve(p) for p in item.get("parameters") or [] if isinstance(r.resolve(p), dict)
        ]
        for method in METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            total_ops += 1
            if len(cases) >= MAX_OPERATIONS:
                continue
            try:
                cases.append(_build_case(r, doc, base_path, path, method, op, common, extra_tag))
            except OpenApiError as exc:
                warnings.append(f"Bỏ qua {method.upper()} {path}: {exc}")
    if total_ops > MAX_OPERATIONS:
        warnings.append(
            f"Tài liệu có {total_ops} operation, chỉ lấy {MAX_OPERATIONS} operation đầu"
        )
    if not cases:
        raise OpenApiError("Tài liệu không có operation nào")
    return ImportPlan(
        title=str(info.get("title") or "")[:200],
        version=str(info.get("version") or "")[:50],
        cases=cases,
        warnings=warnings,
    )


def _build_case(
    r: _Resolver,
    doc: dict[str, Any],
    base_path: str,
    path: str,
    method: str,
    op: dict[str, Any],
    common: list[dict[str, Any]],
    extra_tag: str | None,
) -> GeneratedCase:
    variables: list[str] = []
    warnings: list[str] = []
    params: dict[tuple[str, str], dict[str, Any]] = {}
    for p in [*common, *(r.resolve(x) for x in op.get("parameters") or [])]:
        if isinstance(p, dict) and isinstance(p.get("name"), str):
            params[(str(p.get("in")), p["name"])] = p

    url = base_path + path
    query: dict[str, str] = {}
    headers: dict[str, str] = {}
    for (where, name), p in params.items():
        example = _param_example(r, p)
        if where == "path":
            if example is None:
                var = _var_name(name)
                variables.append(var)
                value = "{{" + var + "}}"
            else:
                value = str(example)
            url = url.replace("{" + name + "}", value)
        elif where == "query" and p.get("required"):
            if example is None:
                var = _var_name(name)
                variables.append(var)
                query[name] = "{{" + var + "}}"
            else:
                query[name] = example if isinstance(example, str) else json.dumps(example)
        elif where == "header" and p.get("required"):
            if name.lower() in {"authorization", "content-type", "accept"}:
                continue
            if example is None:
                var = _var_name("HEADER", name)
                variables.append(var)
                headers[name] = "{{" + var + "}}"
            else:
                headers[name] = str(example)

    body_type, body = "none", None
    request_body = r.resolve(op.get("requestBody") or {})
    content = request_body.get("content") if isinstance(request_body, dict) else None
    if isinstance(content, dict) and content:
        json_ct = next((ct for ct in content if "json" in ct.lower()), None)
        form_ct = (
            "application/x-www-form-urlencoded"
            if "application/x-www-form-urlencoded" in content
            else None
        )
        media = r.resolve(content.get(json_ct or form_ct or "", {}))
        if json_ct or form_ct:
            sample: Any = None
            if isinstance(media, dict):
                if "example" in media:
                    sample = media["example"]
                elif isinstance(media.get("examples"), dict) and media["examples"]:
                    first = r.resolve(next(iter(media["examples"].values())))
                    sample = first.get("value") if isinstance(first, dict) else None
                else:
                    sample = r.sample(media.get("schema"))
            if json_ct:
                body_type, body = "json", sample if sample is not None else {}
            else:
                body_type = "form"
                body = {k: "" if v is None else str(v) for k, v in (sample or {}).items()}
            warnings.append("Body là dữ liệu mẫu tối thiểu, cần điền giá trị thật")
        else:
            warnings.append(f"Kiểu body {', '.join(content)[:80]} chưa hỗ trợ, bỏ trống body")

    security = op["security"] if "security" in op else doc.get("security")
    auth, auth_query, auth_warn = _auth(r, security, variables)
    query.update(auth_query)
    warnings += auth_warn
    upper = method.upper()
    step: dict[str, Any] = {
        "name": f"{upper} {path}"[:200],
        "method": upper,
        "url": url[:2048],
        "headers": headers,
        "query": query,
        "body_type": body_type,
        "body": body,
        "auth": auth,
        "assertions": [_success_assertion(op.get("responses"))],
    }
    summary = str(op.get("summary") or op.get("operationId") or "").strip()
    title = f"{upper} {path}" + (f": {summary}" if summary else "")
    tags = ["openapi"]
    if isinstance(op.get("tags"), list) and op["tags"]:
        tags.append(str(op["tags"][0])[:50])
    if extra_tag:
        tags.append(extra_tag[:50])
    description = "\n".join(
        x
        for x in (
            str(op.get("description") or "")[:5000],
            f"operationId: {op['operationId']}" if op.get("operationId") else "",
            "Sinh tự động từ OpenAPI: cần rà soát dữ liệu, biến và kiểm tra trước khi chuyển sang Sẵn sàng.",
        )
        if x
    )
    unique_vars = list(dict.fromkeys(variables))
    try:
        body_model = TestCaseCreate.model_validate(
            {
                "title": title[:300],
                "description": description,
                "test_type": TestType.API,
                "tags": tags,
                "test_data": {MARKER_KEY: f"{upper} {path}"},
                "preconditions": (
                    "Khai báo biến môi trường: " + ", ".join(unique_vars) if unique_vars else ""
                ),
                "definition": {"kind": "api", "steps": [step]},
            }
        )
    except ValidationError as exc:
        raise OpenApiError(
            f"{upper} {path}: không tạo được test case ({exc.errors()[0]['msg']})"
        ) from exc
    return GeneratedCase(upper, path, body_model, unique_vars, warnings)
