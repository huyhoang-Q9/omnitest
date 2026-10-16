import uuid

from fastapi import APIRouter, Query
from sqlalchemy import Select, func, select

from omnitest_api.deps import DB, CurrentUser, get_project_access, require_role
from omnitest_api.models import AuditLog, Environment, Project, ProjectMember, ProjectRole, User
from omnitest_api.schemas import AuditOut, DashboardOut, FeatureStat, Page

router = APIRouter(tags=["dashboard"])

PHASE3_NOTE = "Có từ Giai đoạn 3 (quản lý và chạy test)"


def _visible_projects(user: User) -> Select[uuid.UUID]:
    stmt = select(Project.id).where(Project.is_archived.is_(False))
    if not user.is_system_admin:
        stmt = stmt.join(ProjectMember, ProjectMember.project_id == Project.id).where(
            ProjectMember.user_id == user.id
        )
    return stmt


@router.get("/api/dashboard", response_model=DashboardOut)
async def dashboard(user: CurrentUser, db: DB) -> DashboardOut:
    visible = _visible_projects(user).subquery()
    projects = await db.scalar(select(func.count()).select_from(visible)) or 0
    envs = (
        await db.scalar(
            select(func.count()).where(Environment.project_id.in_(select(visible.c.id)))
        )
        or 0
    )
    members = (
        await db.scalar(
            select(func.count(func.distinct(ProjectMember.user_id))).where(
                ProjectMember.project_id.in_(select(visible.c.id))
            )
        )
        or 0
    )
    # Hoạt động gần đây: chỉ thao tác trong dự án người dùng thấy được, hoặc của chính họ.
    activity_stmt = select(AuditLog).where(
        (AuditLog.project_id.in_(select(visible.c.id))) | (AuditLog.actor_id == user.id)
    )
    if user.is_system_admin:
        activity_stmt = select(AuditLog)
    activity = await db.scalars(activity_stmt.order_by(AuditLog.created_at.desc()).limit(10))
    return DashboardOut(
        projects=projects,
        environments=envs,
        members=members,
        test_cases=FeatureStat(value=None, available=False, note=PHASE3_NOTE),
        test_runs=FeatureStat(value=None, available=False, note=PHASE3_NOTE),
        recent_activity=[AuditOut.model_validate(a) for a in activity],
    )


@router.get("/api/projects/{project_id}/audit-logs", response_model=Page[AuditOut])
async def project_audit(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> Page[AuditOut]:
    access = await get_project_access(db, user, project_id)
    require_role(access, ProjectRole.MANAGER)
    base = select(AuditLog).where(AuditLog.project_id == project_id)
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = await db.scalars(
        base.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return Page(
        items=[AuditOut.model_validate(a) for a in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
