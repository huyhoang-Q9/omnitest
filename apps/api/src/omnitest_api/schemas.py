"""Schema vào/ra của API. Đây là nguồn sinh OpenAPI và type TypeScript cho frontend."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Generic, TypeVar
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from omnitest_api.models import EnvironmentKind, ProjectRole

T = TypeVar("T")

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


# Không dùng EmailStr: thư viện email-validator từ chối tên miền dùng riêng như .local, .internal,
# vốn phổ biến trong mạng nội bộ doanh nghiệp. Kiểm tra cú pháp cơ bản và chuẩn hóa chữ thường.
EMAIL_RE = re.compile(
    r"^[^@\s]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def normalize_email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not EMAIL_RE.match(v):
        raise ValueError("Email không hợp lệ")
    return v


Email = Annotated[str, AfterValidator(normalize_email)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class ErrorOut(BaseModel):
    detail: str


# ---------- Auth & users ----------


class LoginIn(BaseModel):
    # Đăng nhập không kiểm tra định dạng email để không lộ quy tắc và không chặn tài khoản cũ.
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=254)]
    password: str = Field(min_length=1, max_length=256)


class UserOut(ORM):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_system_admin: bool
    last_login_at: datetime | None


class UserCreate(BaseModel):
    email: Email
    full_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    password: str = Field(min_length=1, max_length=256)
    is_system_admin: bool = False


# ---------- Projects ----------

PROJECT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]{1,15}$")


class ProjectBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: Annotated[str, StringConstraints(max_length=5000)] = ""


class ProjectCreate(ProjectBase):
    key: str = Field(description="Mã dự án, 2 đến 16 ký tự in hoa/số, VD SHOP")

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        v = v.strip().upper()
        if not PROJECT_KEY_RE.match(v):
            raise ValueError("Mã dự án gồm 2 đến 16 ký tự A-Z, 0-9 và bắt đầu bằng chữ cái")
        return v


class ProjectUpdate(BaseModel):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    description: Annotated[str, StringConstraints(max_length=5000)] | None = None
    # Chỉ Admin dự án được đổi.
    ai_enabled: bool | None = None


class ProjectOut(ORM):
    id: uuid.UUID
    key: str
    name: str
    description: str
    is_archived: bool
    ai_enabled: bool = False
    created_at: datetime
    updated_at: datetime
    my_role: ProjectRole | None = None
    environment_count: int = 0
    member_count: int = 0


class MemberIn(BaseModel):
    email: Email
    role: ProjectRole


class MemberUpdate(BaseModel):
    role: ProjectRole


class MemberOut(ORM):
    id: uuid.UUID
    user_id: uuid.UUID
    role: ProjectRole
    email: str
    full_name: str


# ---------- Environments ----------

HOST_RE = re.compile(r"^(\*\.)?[A-Za-z0-9.-]+(:\d{1,5})?$")


def _validate_base_url(v: str) -> str:
    v = v.strip()
    parts = urlsplit(v)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("Base URL phải bắt đầu bằng http:// hoặc https:// và có tên miền")
    if parts.username or parts.password:
        raise ValueError("Không đưa thông tin đăng nhập vào URL, hãy dùng biến secret")
    return v


def _validate_hosts(v: list[str]) -> list[str]:
    cleaned = []
    for h in v:
        h = h.strip().lower()
        if not h:
            continue
        if not HOST_RE.match(h):
            raise ValueError(f"Host không hợp lệ: {h}")
        cleaned.append(h)
    return sorted(set(cleaned))


class EnvironmentBase(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    kind: EnvironmentKind
    base_url: str
    description: Annotated[str, StringConstraints(max_length=5000)] = ""
    allowed_hosts: list[str] = Field(default_factory=list, max_length=100)
    requires_run_confirmation: bool | None = None

    @field_validator("base_url")
    @classmethod
    def _url(cls, v: str) -> str:
        return _validate_base_url(v)

    @field_validator("allowed_hosts")
    @classmethod
    def _hosts(cls, v: list[str]) -> list[str]:
        return _validate_hosts(v)


class EnvironmentCreate(EnvironmentBase):
    allow_private_network: bool = False


class EnvironmentUpdate(BaseModel):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None
    kind: EnvironmentKind | None = None
    base_url: str | None = None
    description: Annotated[str, StringConstraints(max_length=5000)] | None = None
    allowed_hosts: list[str] | None = Field(default=None, max_length=100)
    allow_private_network: bool | None = None
    requires_run_confirmation: bool | None = None

    @field_validator("base_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return None if v is None else _validate_base_url(v)

    @field_validator("allowed_hosts")
    @classmethod
    def _hosts(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _validate_hosts(v)


class EnvironmentOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    kind: EnvironmentKind
    base_url: str
    description: str
    allowed_hosts: list[str]
    allow_private_network: bool
    requires_run_confirmation: bool
    variable_count: int = 0
    created_at: datetime
    updated_at: datetime


VAR_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,99}$")


class VariableCreate(BaseModel):
    key: str
    value: str = Field(max_length=10000)
    is_secret: bool = False
    description: Annotated[str, StringConstraints(max_length=1000)] = ""

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        v = v.strip()
        if not VAR_KEY_RE.match(v):
            raise ValueError("Tên biến chỉ gồm A-Z, 0-9, dấu gạch dưới và không bắt đầu bằng số")
        return v


class VariableUpdate(BaseModel):
    # value = None nghĩa là giữ nguyên giá trị hiện tại (để sửa mô tả secret mà không phải nhập lại).
    value: str | None = Field(default=None, max_length=10000)
    description: Annotated[str, StringConstraints(max_length=1000)] | None = None


class VariableOut(BaseModel):
    id: uuid.UUID
    key: str
    is_secret: bool
    # Secret luôn trả None; has_value cho biết đã có giá trị hay chưa.
    value: str | None
    has_value: bool
    description: str
    updated_at: datetime


# ---------- Audit ----------


class AuditOut(ORM):
    id: uuid.UUID
    created_at: datetime
    actor_email: str | None
    project_id: uuid.UUID | None
    action: str
    target_type: str | None
    target_id: str | None
    details: dict[str, object]
