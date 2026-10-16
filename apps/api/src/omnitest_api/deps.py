"""Dependency dùng chung: phiên đăng nhập, kiểm tra quyền theo dự án."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnitest_api.config import Settings, get_settings
from omnitest_api.db import get_db
from omnitest_api.models import ROLE_RANK, Project, ProjectMember, ProjectRole, User, UserSession
from omnitest_api.security.crypto import SecretCipher
from omnitest_api.security.sessions import hash_token

DB = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

NOT_FOUND = "Không tìm thấy hoặc bạn không có quyền truy cập"


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def get_current_user(request: Request, db: DB, settings: SettingsDep) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chưa đăng nhập")
    sess = await db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    if sess is None or sess.expires_at <= datetime.now(UTC) or not sess.user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Phiên đăng nhập đã hết hạn")
    return sess.user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_system_admin(user: CurrentUser) -> User:
    if not user.is_system_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ quản trị hệ thống được thực hiện")
    return user


SystemAdmin = Annotated[User, Depends(require_system_admin)]


@dataclass
class ProjectAccess:
    project: Project
    user: User
    role: ProjectRole

    def can(self, minimum: ProjectRole) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[minimum]


async def get_project_access(db: AsyncSession, user: User, project_id: uuid.UUID) -> ProjectAccess:
    """Người ngoài dự án nhận 404 (không lộ sự tồn tại của dự án). Quản trị hệ thống có quyền admin."""
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    if user.is_system_admin:
        return ProjectAccess(project, user, ProjectRole.ADMIN)
    member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
        )
    )
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return ProjectAccess(project, user, member.role)


def require_role(access: ProjectAccess, minimum: ProjectRole) -> None:
    if not access.can(minimum):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Bạn không đủ quyền cho thao tác này")


def get_cipher(settings: SettingsDep) -> SecretCipher:
    return SecretCipher(settings.master_key.get_secret_value())


Cipher = Annotated[SecretCipher, Depends(get_cipher)]


def require_writable(access: ProjectAccess) -> None:
    if access.project.is_archived:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Dự án đã lưu trữ, cần khôi phục trước khi chỉnh sửa"
        )
