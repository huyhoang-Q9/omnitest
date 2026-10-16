import uuid

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnitest_api import audit
from omnitest_api.deps import DB, CurrentUser, get_project_access, require_role, require_writable
from omnitest_api.models import Environment, Project, ProjectMember, ProjectRole, User
from omnitest_api.schemas import (
    MemberIn,
    MemberOut,
    MemberUpdate,
    Page,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


async def _counts(
    db: AsyncSession, ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    if not ids:
        return {}, {}
    envs = dict(
        (
            await db.execute(
                select(Environment.project_id, func.count())
                .where(Environment.project_id.in_(ids))
                .group_by(Environment.project_id)
            )
        ).all()
    )
    members = dict(
        (
            await db.execute(
                select(ProjectMember.project_id, func.count())
                .where(ProjectMember.project_id.in_(ids))
                .group_by(ProjectMember.project_id)
            )
        ).all()
    )
    return envs, members


def _out(p: Project, role: ProjectRole | None, envs: int, members: int) -> ProjectOut:
    out = ProjectOut.model_validate(p)
    out.my_role, out.environment_count, out.member_count = role, envs, members
    return out


@router.get("", response_model=Page[ProjectOut])
async def list_projects(
    user: CurrentUser,
    db: DB,
    q: str | None = Query(default=None, max_length=100),
    include_archived: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[ProjectOut]:
    role_col = ProjectMember.role
    stmt = select(Project, role_col).outerjoin(
        ProjectMember, (ProjectMember.project_id == Project.id) & (ProjectMember.user_id == user.id)
    )
    if not user.is_system_admin:
        stmt = stmt.where(ProjectMember.id.is_not(None))
    if not include_archived:
        stmt = stmt.where(Project.is_archived.is_(False))
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(Project.name).like(like), func.lower(Project.key).like(like))
        )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        await db.execute(
            stmt.order_by(Project.name).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    envs, members = await _counts(db, [p.id for p, _ in rows])
    items = [
        _out(
            p,
            ProjectRole.ADMIN if user.is_system_admin and r is None else r,
            envs.get(p.id, 0),
            members.get(p.id, 0),
        )
        for p, r in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate, user: CurrentUser, request: Request, db: DB
) -> ProjectOut:
    if not user.is_system_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ quản trị hệ thống được tạo dự án")
    if await db.scalar(select(Project.id).where(Project.key == body.key)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mã dự án {body.key} đã được dùng")
    project = Project(
        key=body.key, name=body.name, description=body.description, created_by_id=user.id
    )
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role=ProjectRole.ADMIN))
    audit.record(
        db,
        action="project.create",
        actor=user,
        request=request,
        project_id=project.id,
        target_type="project",
        target_id=project.id,
        details={"project_key": project.key, "name": project.name},
    )
    await db.commit()
    await db.refresh(project)
    return _out(project, ProjectRole.ADMIN, 0, 1)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, user: CurrentUser, db: DB) -> ProjectOut:
    access = await get_project_access(db, user, project_id)
    envs, members = await _counts(db, [project_id])
    return _out(access.project, access.role, envs.get(project_id, 0), members.get(project_id, 0))


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: uuid.UUID, body: ProjectUpdate, user: CurrentUser, request: Request, db: DB
) -> ProjectOut:
    access = await get_project_access(db, user, project_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in changes.items():
        setattr(access.project, k, v)
    audit.record(
        db,
        action="project.update",
        actor=user,
        request=request,
        project_id=project_id,
        target_type="project",
        target_id=project_id,
        details={"fields": sorted(changes)},
    )
    await db.commit()
    await db.refresh(access.project)
    return await get_project(project_id, user, db)


@router.post("/{project_id}/archive", response_model=ProjectOut)
async def archive_project(
    project_id: uuid.UUID, user: CurrentUser, request: Request, db: DB
) -> ProjectOut:
    """Lưu trữ thay vì xóa cứng: dữ liệu vẫn còn, có thể khôi phục."""
    access = await get_project_access(db, user, project_id)
    require_role(access, ProjectRole.ADMIN)
    access.project.is_archived = True
    audit.record(
        db,
        action="project.archive",
        actor=user,
        request=request,
        project_id=project_id,
        target_type="project",
        target_id=project_id,
    )
    await db.commit()
    await db.refresh(access.project)
    return await get_project(project_id, user, db)


@router.post("/{project_id}/restore", response_model=ProjectOut)
async def restore_project(
    project_id: uuid.UUID, user: CurrentUser, request: Request, db: DB
) -> ProjectOut:
    access = await get_project_access(db, user, project_id)
    require_role(access, ProjectRole.ADMIN)
    access.project.is_archived = False
    audit.record(
        db,
        action="project.restore",
        actor=user,
        request=request,
        project_id=project_id,
        target_type="project",
        target_id=project_id,
    )
    await db.commit()
    await db.refresh(access.project)
    return await get_project(project_id, user, db)


# ---------- Members ----------


def _member_out(m: ProjectMember) -> MemberOut:
    return MemberOut(
        id=m.id, user_id=m.user_id, role=m.role, email=m.user.email, full_name=m.user.full_name
    )


@router.get("/{project_id}/members", response_model=list[MemberOut])
async def list_members(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[MemberOut]:
    await get_project_access(db, user, project_id)
    rows = await db.scalars(
        select(ProjectMember)
        .where(ProjectMember.project_id == project_id)
        .join(User)
        .order_by(User.email)
    )
    return [_member_out(m) for m in rows]


@router.post("/{project_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
async def add_member(
    project_id: uuid.UUID, body: MemberIn, user: CurrentUser, request: Request, db: DB
) -> MemberOut:
    access = await get_project_access(db, user, project_id)
    require_role(access, ProjectRole.ADMIN)
    target = await db.scalar(
        select(User).where(func.lower(User.email) == body.email.lower(), User.is_active)
    )
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy người dùng với email này")
    exists = await db.scalar(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == target.id
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Người dùng đã là thành viên dự án")
    member = ProjectMember(project_id=project_id, user_id=target.id, role=body.role)
    db.add(member)
    await db.flush()
    audit.record(
        db,
        action="member.add",
        actor=user,
        request=request,
        project_id=project_id,
        target_type="user",
        target_id=target.id,
        details={"email": target.email, "role": body.role.value},
    )
    await db.commit()
    await db.refresh(member)
    return _member_out(member)


async def _get_member(
    db: AsyncSession, project_id: uuid.UUID, member_id: uuid.UUID
) -> ProjectMember:
    m = await db.get(ProjectMember, member_id)
    if m is None or m.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy thành viên")
    return m


async def _ensure_admin_remains(
    db: AsyncSession, project_id: uuid.UUID, member: ProjectMember
) -> None:
    if member.role != ProjectRole.ADMIN:
        return
    admins = await db.scalar(
        select(func.count()).where(
            ProjectMember.project_id == project_id, ProjectMember.role == ProjectRole.ADMIN
        )
    )
    if (admins or 0) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dự án phải còn ít nhất một Admin")


@router.patch("/{project_id}/members/{member_id}", response_model=MemberOut)
async def update_member(
    project_id: uuid.UUID,
    member_id: uuid.UUID,
    body: MemberUpdate,
    user: CurrentUser,
    request: Request,
    db: DB,
) -> MemberOut:
    access = await get_project_access(db, user, project_id)
    require_role(access, ProjectRole.ADMIN)
    member = await _get_member(db, project_id, member_id)
    if body.role != ProjectRole.ADMIN:
        await _ensure_admin_remains(db, project_id, member)
    old = member.role
    member.role = body.role
    audit.record(
        db,
        action="member.update_role",
        actor=user,
        request=request,
        project_id=project_id,
        target_type="user",
        target_id=member.user_id,
        details={"from": old.value, "to": body.role.value},
    )
    await db.commit()
    return _member_out(member)


@router.delete("/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    project_id: uuid.UUID, member_id: uuid.UUID, user: CurrentUser, request: Request, db: DB
) -> None:
    access = await get_project_access(db, user, project_id)
    require_role(access, ProjectRole.ADMIN)
    member = await _get_member(db, project_id, member_id)
    await _ensure_admin_remains(db, project_id, member)
    audit.record(
        db,
        action="member.remove",
        actor=user,
        request=request,
        project_id=project_id,
        target_type="user",
        target_id=member.user_id,
        details={"email": member.user.email},
    )
    await db.delete(member)
    await db.commit()
