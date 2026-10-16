"""Mô hình dữ liệu Giai đoạn 2: người dùng, phiên, dự án, thành viên, môi trường, biến, audit."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ProjectRole(enum.StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    TESTER = "tester"
    VIEWER = "viewer"


ROLE_RANK = {
    ProjectRole.VIEWER: 1,
    ProjectRole.TESTER: 2,
    ProjectRole.MANAGER: 3,
    ProjectRole.ADMIN: 4,
}


class EnvironmentKind(enum.StrEnum):
    DEV = "dev"
    TEST = "test"
    UAT = "uat"
    STAGING = "staging"


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserSession(Base):
    """Phiên đăng nhập phía server. Chỉ lưu hash SHA-256 của token, không lưu token gốc."""

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))

    user: Mapped[User] = relationship(lazy="joined")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class ProjectMember(TimestampMixin, Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[ProjectRole] = mapped_column(
        Enum(ProjectRole, name="project_role", values_callable=lambda e: [m.value for m in e])
    )

    user: Mapped[User] = relationship(lazy="joined")


class Environment(TimestampMixin, Base):
    __tablename__ = "environments"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[EnvironmentKind] = mapped_column(
        Enum(
            EnvironmentKind, name="environment_kind", values_callable=lambda e: [m.value for m in e]
        )
    )
    base_url: Mapped[str] = mapped_column(String(2048))
    description: Mapped[str] = mapped_column(Text, default="")
    # Danh sách host đích được phép (dùng cho chặn SSRF ở Giai đoạn 4).
    allowed_hosts: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Cho phép đích là mạng nội bộ (IP private). Chỉ Admin dự án được bật.
    allow_private_network: Mapped[bool] = mapped_column(Boolean, default=False)
    # Môi trường cần xác nhận trước khi chạy test (UAT/Staging mặc định bật).
    requires_run_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)


class EnvironmentVariable(TimestampMixin, Base):
    __tablename__ = "environment_variables"
    __table_args__ = (UniqueConstraint("environment_id", "key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(100))
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    # Biến thường: lưu ở value. Secret: value = NULL, lưu bản mã AES-GCM ở encrypted_value.
    value: Mapped[str | None] = mapped_column(Text)
    encrypted_value: Mapped[bytes | None] = mapped_column(LargeBinary)
    description: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_email: Mapped[str | None] = mapped_column(String(254))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_type: Mapped[str | None] = mapped_column(String(50))
    target_id: Mapped[str | None] = mapped_column(String(64))
    # Chi tiết không bao giờ chứa giá trị secret.
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64))


# ---------- Giai đoạn 3: test case, suite, run ----------


def _enum(e: type[enum.Enum], name: str) -> Enum:
    return Enum(e, name=name, values_callable=lambda x: [m.value for m in x])


class TestType(enum.StrEnum):
    API = "api"
    WEB = "web"
    DESKTOP_MACOS = "desktop_macos"
    DESKTOP_WINDOWS = "desktop_windows"
    MOBILE_ANDROID = "mobile_android"
    MOBILE_IOS = "mobile_ios"


class Priority(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TestCaseStatus(enum.StrEnum):
    DRAFT = "draft"
    READY = "ready"
    DEPRECATED = "deprecated"


class RunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    ERROR = "error"


FINAL_RUN_STATUSES = {
    RunStatus.PASSED,
    RunStatus.FAILED,
    RunStatus.SKIPPED,
    RunStatus.BLOCKED,
    RunStatus.CANCELLED,
    RunStatus.ERROR,
}


class TestCase(TimestampMixin, Base):
    __tablename__ = "test_cases"
    __table_args__ = (UniqueConstraint("project_id", "seq"),)
    __test__ = False  # không để pytest hiểu nhầm là lớp test

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    # Mã ổn định, không đổi khi sửa: <KEY>-TC-0001
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    test_type: Mapped[TestType] = mapped_column(_enum(TestType, "test_type"))
    priority: Mapped[Priority] = mapped_column(
        _enum(Priority, "test_priority"), default=Priority.MEDIUM
    )
    status: Mapped[TestCaseStatus] = mapped_column(
        _enum(TestCaseStatus, "test_case_status"), default=TestCaseStatus.DRAFT
    )
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    preconditions: Mapped[str] = mapped_column(Text, default="")
    expected_result: Mapped[str] = mapped_column(Text, default="")
    test_data: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    definition: Mapped[dict[str, object]] = mapped_column(JSON)
    # Có tác động dữ liệu (tự suy ra cho API có POST/PUT/PATCH/DELETE, hoặc người dùng đánh dấu).
    side_effect: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class TestCaseVersion(Base):
    __tablename__ = "test_case_versions"
    __table_args__ = (UniqueConstraint("test_case_id", "version"),)
    __test__ = False

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    test_case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    change_note: Mapped[str] = mapped_column(String(500), default="")
    changed_by_email: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TestSuite(TimestampMixin, Base):
    __tablename__ = "test_suites"
    __table_args__ = (UniqueConstraint("project_id", "name"),)
    __test__ = False

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")


class SuiteItem(Base):
    __tablename__ = "suite_items"
    __table_args__ = (UniqueConstraint("suite_id", "test_case_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    suite_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_suites.id", ondelete="CASCADE"), index=True
    )
    test_case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)


class TestRun(Base):
    __tablename__ = "test_runs"
    __test__ = False

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    environment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("environments.id", ondelete="SET NULL")
    )
    environment_name: Mapped[str] = mapped_column(String(100))
    suite_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("test_suites.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[RunStatus] = mapped_column(
        _enum(RunStatus, "run_status"), default=RunStatus.QUEUED, index=True
    )
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    triggered_by_email: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    blocked: Mapped[int] = mapped_column(Integer, default=0)
    errored: Mapped[int] = mapped_column(Integer, default=0)
    cancelled: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class TestRunItem(Base):
    __tablename__ = "test_run_items"
    __test__ = False

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_runs.id", ondelete="CASCADE"), index=True
    )
    test_case_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("test_cases.id", ondelete="SET NULL")
    )
    position: Mapped[int] = mapped_column(Integer)
    # Ảnh chụp test case tại thời điểm chạy, để kết quả không đổi khi test case bị sửa sau này.
    code: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    test_type: Mapped[TestType] = mapped_column(_enum(TestType, "test_type"))
    test_case_version: Mapped[int] = mapped_column(Integer)
    definition: Mapped[dict[str, object]] = mapped_column(JSON)
    side_effect: Mapped[bool] = mapped_column(Boolean, default=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=0)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    status: Mapped[RunStatus] = mapped_column(
        _enum(RunStatus, "run_status"), default=RunStatus.QUEUED
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[str | None] = mapped_column(String(50))


class StepResult(Base):
    __tablename__ = "step_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    run_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_run_items.id", ondelete="CASCADE"), index=True
    )
    attempt: Mapped[int] = mapped_column(Integer)
    index: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus, "run_status"))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    log: Mapped[list[str]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_runs.id", ondelete="CASCADE"), index=True
    )
    run_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("test_run_items.id", ondelete="CASCADE")
    )
    step_result_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("step_results.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(30))
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
