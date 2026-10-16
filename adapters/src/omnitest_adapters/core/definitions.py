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


# ---------- Desktop / Mobile (Appium) ----------

AppKind = Literal["desktop_macos", "desktop_windows", "mobile_android", "mobile_ios"]
LocatorStrategy = Literal[
    "accessibility_id",
    "id",
    "name",
    "xpath",
    "class_name",
    "ios_predicate",
    "ios_class_chain",
    "android_uiautomator",
]
# Chỉ cho phép capability phục vụ mở ứng dụng và chọn thiết bị; không cho capability trỏ tới file thực thi
# hay đổi hành vi bảo mật của Appium server.
ALLOWED_CAPABILITIES = {
    "app",
    "bundleId",
    "appPackage",
    "appActivity",
    "appWaitActivity",
    "deviceName",
    "platformVersion",
    "udid",
    "noReset",
    "fullReset",
    "newCommandTimeout",
    "language",
    "locale",
    "orientation",
    "autoGrantPermissions",
    "appArguments",
    "appWorkingDir",
    "arguments",
}
APP_ACTIONS_NEED_LOCATOR = {
    "tap",
    "type",
    "clear",
    "expect_visible",
    "expect_hidden",
    "expect_text",
}


class AppLocator(Strict):
    strategy: LocatorStrategy = "accessibility_id"
    value: str = Field(min_length=1, max_length=2000)


class AppStep(Strict):
    name: str = Field(min_length=1, max_length=200)
    action: Literal[
        "tap",
        "type",
        "clear",
        "expect_visible",
        "expect_hidden",
        "expect_text",
        "screenshot",
        "back",
    ]
    locator: AppLocator | None = None
    value: str | None = Field(default=None, max_length=5000)
    timeout_ms: int = Field(default=10_000, ge=100, le=120_000)

    @model_validator(mode="after")
    def _check(self) -> "AppStep":
        if self.action in APP_ACTIONS_NEED_LOCATOR and self.locator is None:
            raise ValueError(f"Hành động {self.action} cần locator")
        if self.action in {"type", "expect_text"} and self.value is None:
            raise ValueError(f"Hành động {self.action} cần value")
        return self


class AppTestDefinition(Strict):
    """Desktop/Mobile chạy qua Appium server (URL lấy từ Base URL của môi trường).

    Test cũ chỉ có "notes" vẫn hợp lệ; không có bước thì khi chạy trả Bị chặn (không có gì để tự động hóa).
    """

    kind: AppKind
    notes: str = Field(default="", max_length=10000)
    capabilities: dict[str, str | int | float | bool] = Field(default_factory=dict)
    steps: list[AppStep] = Field(default_factory=list, max_length=100)

    @field_validator("capabilities")
    @classmethod
    def _caps(cls, v: dict[str, str | int | float | bool]) -> dict[str, str | int | float | bool]:
        for key, value in v.items():
            bare = key.removeprefix("appium:")
            if bare not in ALLOWED_CAPABILITIES:
                raise ValueError(
                    f"Capability '{key}' không được phép. Được dùng: {', '.join(sorted(ALLOWED_CAPABILITIES))}"
                )
            if (
                bare == "app"
                and isinstance(value, str)
                and re.match(r"^[a-z][a-z0-9+.-]*://", value, re.I)
            ):
                raise ValueError(
                    "Capability 'app' phải là đường dẫn trên máy chạy Appium, không dùng URL tải về"
                )
        return v


# Giữ tên cũ cho mã đang import.
UnsupportedDefinition = AppTestDefinition


# ---------- Script code (pytest) chạy trong sandbox ----------

SCRIPT_FILE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}\.(py|json|csv|txt|yaml|yml)$")
SCRIPT_MAX_FILES = 20
SCRIPT_MAX_TOTAL_CHARS = 256 * 1024


class ScriptTestDefinition(Strict):
    """Script pytest do người dùng viết, chỉ chạy trong container sandbox (không chạy trên máy chủ chính).

    files: tên file (phẳng, không thư mục con) -> nội dung. Cần ít nhất một file test_*.py hoặc *_test.py.
    network: "none" (mặc định) không có mạng; "environment" chỉ ra ngoài qua proxy kiểm soát theo môi trường.
    """

    kind: Literal["script"]
    runner: Literal["pytest"] = "pytest"
    files: dict[str, str]
    network: Literal["none", "environment"] = "none"
    notes: str = Field(default="", max_length=10000)

    @field_validator("files")
    @classmethod
    def _files(cls, v: dict[str, str]) -> dict[str, str]:
        if not v:
            raise ValueError("Cần ít nhất một file test")
        if len(v) > SCRIPT_MAX_FILES:
            raise ValueError(f"Tối đa {SCRIPT_MAX_FILES} file")
        for name in v:
            if not SCRIPT_FILE_RE.match(name):
                raise ValueError(
                    f"Tên file '{name}' không hợp lệ: chỉ chữ, số, _ . -, không thư mục con, "
                    "đuôi .py .json .csv .txt .yaml .yml"
                )
        if sum(len(c) for c in v.values()) > SCRIPT_MAX_TOTAL_CHARS:
            raise ValueError(f"Tổng nội dung vượt {SCRIPT_MAX_TOTAL_CHARS // 1024} KB")
        if not any(
            n.endswith(".py") and (n.startswith("test_") or n.endswith("_test.py")) for n in v
        ):
            raise ValueError("Cần ít nhất một file test_*.py hoặc *_test.py")
        return v


TestDefinition = Annotated[
    ApiTestDefinition | WebTestDefinition | AppTestDefinition | ScriptTestDefinition,
    Field(discriminator="kind"),
]


def has_side_effect(
    defn: ApiTestDefinition | WebTestDefinition | AppTestDefinition | ScriptTestDefinition,
) -> bool:
    """API có phương thức ghi (POST/PUT/PATCH/DELETE) được coi là có side effect.

    Script code có thể làm bất cứ gì nên luôn tính là có side effect (không tự thử lại, cần xác nhận khi chạy).
    """
    if isinstance(defn, ApiTestDefinition):
        return any(s.method not in SAFE_METHODS for s in defn.steps)
    return isinstance(defn, ScriptTestDefinition)
