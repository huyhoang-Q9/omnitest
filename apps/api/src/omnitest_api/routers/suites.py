import uuid

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from omnitest_api import audit
from omnitest_api.deps import (
    DB,
    CurrentUser,
    ProjectAccess,
    get_project_access,
    require_role,
    require_writable,
)
from omnitest_api.models import ProjectRole, SuiteItem, TestCase, TestSuite, User
from omnitest_api.routers.test_cases import to_out
from omnitest_api.schemas_tests import (
    SuiteCaseOut,
    SuiteCreate,
    SuiteDetailOut,
    SuiteItemsIn,
    SuiteOut,
    SuiteUpdate,
)

router = APIRouter(tags=["suites"])


async def suite_with_access(
    db: AsyncSession, user: User, suite_id: uuid.UUID
) -> tuple[TestSuite, ProjectAccess]:
    s = await db.get(TestSuite, suite_id)
    if s is None:
        raise HTTPException(404, "Không tìm thấy hoặc bạn không có quyền truy cập")
    return s, await get_project_access(db, user, s.project_id)


async def _set_items(db: AsyncSession, suite: TestSuite, case_ids: list[uuid.UUID]) -> None:
    ids = list(dict.fromkeys(case_ids))  # bỏ trùng, giữ thứ tự
    if ids:
        valid = set(
            await db.scalars(
                select(TestCase.id).where(
                    TestCase.id.in_(ids),
                    TestCase.project_id == suite.project_id,
                    TestCase.is_deleted.is_(False),
                )
            )
        )
        invalid = [str(i) for i in ids if i not in valid]
        if invalid:
            raise HTTPException(
                422, f"Test case không thuộc dự án hoặc đã xóa: {', '.join(invalid[:5])}"
            )
    await db.execute(delete(SuiteItem).where(SuiteItem.suite_id == suite.id))
    for pos, cid in enumerate(ids):
        db.add(SuiteItem(suite_id=suite.id, test_case_id=cid, position=pos))


async def _detail(db: AsyncSession, suite: TestSuite) -> SuiteDetailOut:
    rows = (
        await db.execute(
            select(SuiteItem.position, TestCase)
            .join(TestCase, TestCase.id == SuiteItem.test_case_id)
            .where(SuiteItem.suite_id == suite.id)
            .order_by(SuiteItem.position)
        )
    ).all()
    out = SuiteDetailOut.model_validate(suite)
    out.items = [SuiteCaseOut(position=pos, test_case=to_out(tc)) for pos, tc in rows]
    out.case_count = len(out.items)
    return out


@router.get("/api/projects/{project_id}/suites", response_model=list[SuiteOut])
async def list_suites(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[SuiteOut]:
    await get_project_access(db, user, project_id)
    counts = dict(
        (
            await db.execute(
                select(SuiteItem.suite_id, func.count())
                .join(TestSuite)
                .where(TestSuite.project_id == project_id)
                .group_by(SuiteItem.suite_id)
            )
        ).all()
    )
    suites = await db.scalars(
        select(TestSuite).where(TestSuite.project_id == project_id).order_by(TestSuite.name)
    )
    out = []
    for s in suites:
        o = SuiteOut.model_validate(s)
        o.case_count = counts.get(s.id, 0)
        out.append(o)
    return out


@router.post("/api/projects/{project_id}/suites", response_model=SuiteDetailOut, status_code=201)
async def create_suite(
    project_id: uuid.UUID, body: SuiteCreate, user: CurrentUser, request: Request, db: DB
) -> SuiteDetailOut:
    access = await get_project_access(db, user, project_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    suite = TestSuite(
        id=uuid.uuid4(), project_id=project_id, name=body.name, description=body.description
    )
    db.add(suite)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, f"Suite {body.name} đã tồn tại") from None
    await _set_items(db, suite, body.test_case_ids)
    audit.record(
        db,
        action="suite.create",
        actor=user,
        request=request,
        project_id=project_id,
        target_type="suite",
        target_id=suite.id,
        details={"name": suite.name},
    )
    await db.commit()
    await db.refresh(suite)
    return await _detail(db, suite)


@router.get("/api/suites/{suite_id}", response_model=SuiteDetailOut)
async def get_suite(suite_id: uuid.UUID, user: CurrentUser, db: DB) -> SuiteDetailOut:
    suite, _ = await suite_with_access(db, user, suite_id)
    return await _detail(db, suite)


@router.patch("/api/suites/{suite_id}", response_model=SuiteDetailOut)
async def update_suite(
    suite_id: uuid.UUID, body: SuiteUpdate, user: CurrentUser, request: Request, db: DB
) -> SuiteDetailOut:
    suite, access = await suite_with_access(db, user, suite_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in changes.items():
        setattr(suite, k, v)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Tên suite đã tồn tại") from None
    audit.record(
        db,
        action="suite.update",
        actor=user,
        request=request,
        project_id=suite.project_id,
        target_type="suite",
        target_id=suite.id,
        details={"fields": sorted(changes)},
    )
    await db.commit()
    await db.refresh(suite)
    return await _detail(db, suite)


@router.put("/api/suites/{suite_id}/items", response_model=SuiteDetailOut)
async def set_suite_items(
    suite_id: uuid.UUID, body: SuiteItemsIn, user: CurrentUser, request: Request, db: DB
) -> SuiteDetailOut:
    suite, access = await suite_with_access(db, user, suite_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    await _set_items(db, suite, body.test_case_ids)
    audit.record(
        db,
        action="suite.set_items",
        actor=user,
        request=request,
        project_id=suite.project_id,
        target_type="suite",
        target_id=suite.id,
        details={"name": suite.name, "count": len(body.test_case_ids)},
    )
    await db.commit()
    await db.refresh(suite)
    return await _detail(db, suite)


@router.delete("/api/suites/{suite_id}", status_code=204)
async def delete_suite(suite_id: uuid.UUID, user: CurrentUser, request: Request, db: DB) -> None:
    """Xóa suite không xóa test case bên trong; lần chạy cũ vẫn giữ kết quả."""
    suite, access = await suite_with_access(db, user, suite_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    audit.record(
        db,
        action="suite.delete",
        actor=user,
        request=request,
        project_id=suite.project_id,
        target_type="suite",
        target_id=suite.id,
        details={"name": suite.name},
    )
    await db.delete(suite)
    await db.commit()
