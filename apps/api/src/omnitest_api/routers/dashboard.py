import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query
from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import distinct_on

from omnitest_api.config import get_settings
from omnitest_api.deps import DB, CurrentUser, get_project_access, require_role
from omnitest_api.models import (
    AuditLog,
    Environment,
    Project,
    ProjectMember,
    ProjectRole,
    RunStatus,
    TestCase,
    TestRun,
    TestRunItem,
    User,
)
from omnitest_api.routers.runs import run_out
from omnitest_api.schemas import AuditOut, Page
from omnitest_api.schemas_tests import AttentionItem, DailyRunStat, DashboardOut

router = APIRouter(tags=["dashboard"])

PERIOD_DAYS = 14
ATTENTION_STATUSES = (RunStatus.FAILED, RunStatus.ERROR, RunStatus.BLOCKED)
RESULT_STATUSES = (
    RunStatus.PASSED,
    RunStatus.FAILED,
    RunStatus.ERROR,
    RunStatus.BLOCKED,
    RunStatus.SKIPPED,
    RunStatus.CANCELLED,
)


def _visible_projects(user: User) -> Select[uuid.UUID]:
    stmt = select(Project.id).where(Project.is_archived.is_(False))
    if not user.is_system_admin:
        stmt = stmt.join(ProjectMember, ProjectMember.project_id == Project.id).where(
            ProjectMember.user_id == user.id
        )
    return stmt


@router.get("/api/dashboard", response_model=DashboardOut)
async def dashboard(user: CurrentUser, db: DB) -> DashboardOut:
    visible_ids = select(_visible_projects(user).subquery().c.id)
    projects = await db.scalar(select(func.count()).select_from(visible_ids.subquery())) or 0
    envs = await db.scalar(select(func.count()).where(Environment.project_id.in_(visible_ids)))
    members = await db.scalar(
        select(func.count(func.distinct(ProjectMember.user_id))).where(
            ProjectMember.project_id.in_(visible_ids)
        )
    )
    cases = await db.scalar(
        select(func.count()).where(
            TestCase.project_id.in_(visible_ids), TestCase.is_deleted.is_(False)
        )
    )
    runs_total = await db.scalar(select(func.count()).where(TestRun.project_id.in_(visible_ids)))
    active = await db.scalar(
        select(func.count()).where(
            TestRun.project_id.in_(visible_ids),
            TestRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
        )
    )

    # Số liệu theo ngày (múi giờ hiển thị) của các lần chạy đã kết thúc trong kỳ.
    tz = get_settings().display_timezone
    today = datetime.now(ZoneInfo(tz)).date()
    first_day = today - timedelta(days=PERIOD_DAYS - 1)
    since = datetime.combine(first_day, datetime.min.time(), ZoneInfo(tz)).astimezone(UTC)
    day = func.date(func.timezone(tz, TestRun.finished_at))
    rows = (
        await db.execute(
            select(
                day,
                func.sum(TestRun.passed),
                func.sum(TestRun.failed),
                func.sum(TestRun.errored),
                func.sum(TestRun.blocked),
                func.sum(TestRun.skipped),
                func.sum(TestRun.cancelled),
            )
            .where(TestRun.project_id.in_(visible_ids), TestRun.finished_at >= since)
            .group_by(day)
        )
    ).all()
    per_day: dict[date, tuple[int, ...]] = {r[0]: tuple(int(x or 0) for x in r[1:]) for r in rows}
    daily: list[DailyRunStat] = []
    totals = dict.fromkeys((s.value for s in RESULT_STATUSES), 0)
    for i in range(PERIOD_DAYS):
        d = first_day + timedelta(days=i)
        passed, failed, errored, blocked, skipped, cancelled = per_day.get(d, (0,) * 6)
        daily.append(
            DailyRunStat(
                date=d,
                passed=passed,
                failed=failed + errored,
                other=blocked + skipped + cancelled,
            )
        )
        for key, n in zip(
            RESULT_STATUSES, (passed, failed, errored, blocked, skipped, cancelled), strict=True
        ):
            totals[key.value] += n
    executed = totals["passed"] + totals["failed"] + totals["error"] + totals["blocked"]
    pass_rate = round(totals["passed"] / executed * 100, 1) if executed else None

    recent = (
        await db.execute(
            select(TestRun, Project.key)
            .join(Project, Project.id == TestRun.project_id)
            .where(TestRun.project_id.in_(visible_ids))
            .order_by(TestRun.created_at.desc())
            .limit(8)
        )
    ).all()

    # Kết quả gần nhất của từng test case (trong kỳ); chỉ giữ những cái đang lỗi.
    latest = (
        select(TestRunItem.id)
        .join(TestRun, TestRun.id == TestRunItem.run_id)
        .where(
            TestRun.project_id.in_(visible_ids),
            TestRunItem.test_case_id.is_not(None),
            TestRunItem.finished_at >= since,
            TestRunItem.status.in_(RESULT_STATUSES),
        )
        .ext(distinct_on(TestRunItem.test_case_id))
        .order_by(TestRunItem.test_case_id, TestRunItem.finished_at.desc())
    )
    attention_rows = (
        await db.execute(
            select(TestRunItem, TestRun.environment_name, Project.key)
            .join(TestRun, TestRun.id == TestRunItem.run_id)
            .join(Project, Project.id == TestRun.project_id)
            .where(TestRunItem.id.in_(latest), TestRunItem.status.in_(ATTENTION_STATUSES))
            .order_by(TestRunItem.finished_at.desc())
            .limit(8)
        )
    ).all()

    # Hoạt động gần đây: chỉ thao tác trong dự án người dùng thấy được, hoặc của chính họ.
    activity_stmt = select(AuditLog).where(
        (AuditLog.project_id.in_(visible_ids)) | (AuditLog.actor_id == user.id)
    )
    if user.is_system_admin:
        activity_stmt = select(AuditLog)
    activity = await db.scalars(activity_stmt.order_by(AuditLog.created_at.desc()).limit(10))
    return DashboardOut(
        projects=projects,
        environments=envs or 0,
        members=members or 0,
        test_cases=cases or 0,
        runs_total=runs_total or 0,
        active_runs=active or 0,
        period_days=PERIOD_DAYS,
        item_totals=totals,
        pass_rate=pass_rate,
        daily=daily,
        recent_runs=[run_out(r, key) for r, key in recent],
        attention=[
            AttentionItem(
                run_id=item.run_id,
                item_id=item.id,
                test_case_id=item.test_case_id,
                project_key=key,
                code=item.code,
                title=item.title,
                status=item.status,
                error=item.error,
                environment_name=env_name,
                finished_at=item.finished_at,
            )
            for item, env_name, key in attention_rows
        ],
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
