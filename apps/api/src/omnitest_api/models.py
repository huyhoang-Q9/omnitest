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
