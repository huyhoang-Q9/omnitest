"""Định nghĩa test dạng khai báo (không phải code). Đây là contract giữa API, giao diện và adapter.

Người dùng không cần lập trình: mỗi bước là một bản ghi có cấu trúc, được kiểm tra chặt bằng Pydantic.
Biến dùng cú pháp {{TEN_BIEN}}, lấy từ biến môi trường hoặc giá trị trích xuất ở bước trước.
"""

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VAR_NAME = r"[A-Za-z_][A-Za-z0-9_]{0,99}"
VAR_NAME_RE = re.compile(rf"^{VAR_NAME}$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- API ----------

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class AuthNone(Strict):
    type: Literal["none"] = "none"


class AuthBasic(Strict):
    type: Literal["basic"]
    username: str = Field(max_length=500, description="Có thể dùng {{BIEN}}")
    password: str = Field(max_length=500, description="Nên dùng {{BIEN_SECRET}}")


class AuthBearer(Strict):
    type: Literal["bearer"]
    token: str = Field(max_length=5000)


class AuthApiKey(Strict):
    type: Literal["api_key"]
    header: str = Field(default="X-API-Key", max_length=100)
    value: str = Field(max_length=5000)


Auth = Annotated[AuthNone | AuthBasic | AuthBearer | AuthApiKey, Field(discriminator="type")]


class AssertStatus(Strict):
    type: Literal["status"]
    equals: int | None = Field(default=None, ge=100, le=599)
    one_of: list[int] | None = None

    @model_validator(mode="after")
    def _one(self) -> "AssertStatus":
        if (self.equals is None) == (self.one_of is None):
            raise ValueError("Khai báo đúng một trong equals hoặc one_of")
        return self


Comparator = Literal[
    "equals", "not_equals", "contains", "exists", "not_exists", "gt", "lt", "matches"
]


class AssertJsonPath(Strict):
    type: Literal["json_path"]
    path: str = Field(min_length=1, max_length=500, description="VD $.data.items[0].id")
    op: Comparator = "equals"
    value: Any = None


class AssertJsonSchema(Strict):
    type: Literal["json_schema"]
    schema_: dict[str, Any] = Field(alias="schema")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AssertHeader(Strict):
    type: Literal["header"]
    name: str = Field(min_length=1, max_length=200)
    op: Literal["equals", "contains", "exists", "matches"] = "exists"
    value: str | None = None


class AssertResponseTime(Strict):
    type: Literal["response_time"]
    max_ms: int = Field(ge=1, le=600_000)


ApiAssertion = Annotated[
    AssertStatus | AssertJsonPath | AssertJsonSchema | AssertHeader | AssertResponseTime,
    Field(discriminator="type"),
]


class Extract(Strict):
    var: str
    source: Literal["json_path", "header"] = "json_path"
    expression: str = Field(min_length=1, max_length=500)

    @field_validator("var")
    @classmethod
    def _var(cls, v: str) -> str:
        if not VAR_NAME_RE.match(v):
            raise ValueError("Tên biến trích xuất không hợp lệ")
        return v


class ApiStep(Strict):
    name: str = Field(min_length=1, max_length=200)
    method: HttpMethod = "GET"
    url: str = Field(
        min_length=1,
        max_length=2048,
        description="Đường dẫn tương đối theo Base URL hoặc URL đầy đủ",
    )
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    body_type: Literal["none", "json", "text", "form"] = "none"
    body: Any = None
    auth: Auth = Field(default_factory=AuthNone)
    assertions: list[ApiAssertion] = Field(default_factory=list, max_length=50)
    extract: list[Extract] = Field(default_factory=list, max_length=20)
    timeout_ms: int = Field(default=30_000, ge=100, le=300_000)
    follow_redirects: bool = True


class ApiTestDefinition(Strict):
    kind: Literal["api"] = "api"
    steps: list[ApiStep] = Field(min_length=1, max_length=50)


# ---------- Web ----------

WebAction = Literal[
    "goto",
    "click",
    "fill",
    "select",
    "check",
    "uncheck",
    "press",
    "wait_for",
    "expect_visible",
    "expect_hidden",
    "expect_text",
    "expect_url",
    "expect_title",
    "screenshot",
]

NEEDS_SELECTOR = {
    "click",
    "fill",
    "select",
    "check",
    "uncheck",
    "press",
    "wait_for",
    "expect_visible",
    "expect_hidden",
    "expect_text",
}
NEEDS_VALUE = {"goto", "fill", "select", "press", "expect_text", "expect_url", "expect_title"}


class WebStep(Strict):
    name: str = Field(min_length=1, max_length=200)
    action: WebAction
    selector: str | None = Field(
        default=None,
        max_length=1000,
        description='Locator Playwright: CSS, text=..., role=button[name="Lưu"], label=..., testid=...',
    )
    value: str | None = Field(default=None, max_length=5000)
    timeout_ms: int = Field(default=10_000, ge=100, le=120_000)

    @model_validator(mode="after")
    def _requirements(self) -> "WebStep":
        if self.action in NEEDS_SELECTOR and not self.selector:
            raise ValueError(f"Hành động {self.action} cần selector")
        if self.action in NEEDS_VALUE and (self.value is None or self.value == ""):
            raise ValueError(f"Hành động {self.action} cần giá trị")
        return self


class Viewport(Strict):
    width: int = Field(default=1280, ge=320, le=3840)
    height: int = Field(default=800, ge=320, le=2160)


class WebTestDefinition(Strict):
    kind: Literal["web"] = "web"
    browser: Literal["chromium", "firefox", "webkit"] = "chromium"
    viewport: Viewport = Field(default_factory=Viewport)
    trace: Literal["off", "on_failure", "always"] = "on_failure"
    steps: list[WebStep] = Field(min_length=1, max_length=100)


# ---------- Chưa hỗ trợ ----------


class UnsupportedDefinition(Strict):
    """Desktop/Mobile: lưu được mô tả thủ công, nhưng chạy sẽ trả blocked cho tới khi có adapter thật."""

    kind: Literal["desktop_macos", "desktop_windows", "mobile_android", "mobile_ios"]
    notes: str = Field(default="", max_length=10000)


TestDefinition = Annotated[
    ApiTestDefinition | WebTestDefinition | UnsupportedDefinition, Field(discriminator="kind")
]


def has_side_effect(defn: ApiTestDefinition | WebTestDefinition | UnsupportedDefinition) -> bool:
    """API có phương thức ghi (POST/PUT/PATCH/DELETE) được coi là có side effect."""
    if isinstance(defn, ApiTestDefinition):
        return any(s.method not in SAFE_METHODS for s in defn.steps)
    return False
