import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import Select, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from omnitest_api import audit
from omnitest_api.config import get_settings
from omnitest_api.deps import (
    DB,
    CurrentUser,
    ProjectAccess,
    get_project_access,
    require_role,
    require_writable,
)
from omnitest_api.models import (
    Priority,
    ProjectRole,
    SuiteItem,
    TestCase,
    TestCaseStatus,
    TestCaseVersion,
    TestType,
    User,
)
from omnitest_api.schemas import Page
from omnitest_api.schemas_tests import (
    DEFINITION_ADAPTER,
    ImportResult,
    ImportRowError,
    TestCaseCreate,
    TestCaseOut,
    TestCaseUpdate,
    TestCaseVersionOut,
)
from omnitest_api.services import test_case_io
from omnitest_api.services.test_cases import (
    dump_definition,
    effective_side_effect,
    next_code,
    record_version,
    step_count,
)

router = APIRouter(tags=["test-cases"])


def to_out(tc: TestCase) -> TestCaseOut:
    out = TestCaseOut.model_validate(tc)
    out.step_count = step_count(tc.definition)
    return out


async def case_with_access(
    db: AsyncSession, user: User, case_id: uuid.UUID
) -> tuple[TestCase, ProjectAccess]:
    tc = await db.get(TestCase, case_id)
    if tc is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Không tìm thấy hoặc bạn không có quyền truy cập"
        )
    return tc, await get_project_access(db, user, tc.project_id)


def _filtered(
    project_id: uuid.UUID,
    q: str | None,
    test_type: TestType | None,
    priority: Priority | None,
    case_status: TestCaseStatus | None,
    tag: str | None,
    suite_id: uuid.UUID | None,
    include_deleted: bool,
) -> Select[TestCase]:
    stmt = select(TestCase).where(TestCase.project_id == project_id)
    if not include_deleted:
        stmt = stmt.where(TestCase.is_deleted.is_(False))
    if q:
        like = f"%{_escape_like(q.strip().lower())}%"
        stmt = stmt.where(
            or_(
                func.lower(TestCase.title).like(like, escape="\\"),
                func.lower(TestCase.code).like(like, escape="\\"),
            )
        )
    if test_type:
        stmt = stmt.where(TestCase.test_type == test_type)
    if priority:
        stmt = stmt.where(TestCase.priority == priority)
    if case_status:
        stmt = stmt.where(TestCase.status == case_status)
    if tag:
        stmt = stmt.where(cast(TestCase.tags, JSONB).contains([tag.strip().lower()]))
    if suite_id:
        stmt = stmt.where(
            TestCase.id.in_(select(SuiteItem.test_case_id).where(SuiteItem.suite_id == suite_id))
        )
    return stmt


def _escape_like(v: str) -> str:
    """Ký tự % và _ do người dùng nhập được hiểu theo nghĩa đen, không phải ký tự đại diện."""
    return v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/api/projects/{project_id}/test-cases", response_model=Page[TestCaseOut])
async def list_test_cases(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    q: str | None = Query(default=None, max_length=100),
    test_type: TestType | None = None,
    priority: Priority | None = None,
    case_status: Annotated[TestCaseStatus | None, Query(alias="status")] = None,
    tag: str | None = Query(default=None, max_length=50),
    suite_id: uuid.UUID | None = None,
    include_deleted: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
) -> Page[TestCaseOut]:
    await get_project_access(db, user, project_id)
    stmt = _filtered(
        project_id, q, test_type, priority, case_status, tag, suite_id, include_deleted
    )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.scalars(
        stmt.order_by(TestCase.seq).offset((page - 1) * page_size).limit(page_size)
    )
    return Page(items=[to_out(tc) for tc in rows], total=total, page=page, page_size=page_size)


@router.post("/api/projects/{project_id}/test-cases", response_model=TestCaseOut, status_code=201)
async def create_test_case(
    project_id: uuid.UUID, body: TestCaseCreate, user: CurrentUser, request: Request, db: DB
) -> TestCaseOut:
    access = await get_project_access(db, user, project_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    tc = await _insert_case(db, access, user, body)
    audit.record(
        db,
        action="test_case.create",
        actor=user,
        request=request,
        project_id=project_id,
        target_type="test_case",
        target_id=tc.id,
        details={"code": tc.code, "name": tc.title},
    )
    await db.commit()
    await db.refresh(tc)
    return to_out(tc)


async def _insert_case(
    db: AsyncSession, access: ProjectAccess, user: User, body: TestCaseCreate
) -> TestCase:
    seq, code = await next_code(db, access.project)
    tc = TestCase(
        id=uuid.uuid4(),
        project_id=access.project.id,
        seq=seq,
        code=code,
        title=body.title,
        description=body.description,
        test_type=body.test_type,
        priority=body.priority,
        status=body.status,
        tags=body.tags,
        preconditions=body.preconditions,
        expected_result=body.expected_result,
        test_data=body.test_data,
        definition=dump_definition(body.definition),
        side_effect=effective_side_effect(body.definition, body.side_effect),
        retry_count=body.retry_count,
        timeout_seconds=body.timeout_seconds,
        version=1,
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    db.add(tc)
    await db.flush()
    record_version(db, tc, user, ["created"], "Tạo mới")
    return tc


@router.get("/api/test-cases/{case_id}", response_model=TestCaseOut)
async def get_test_case(case_id: uuid.UUID, user: CurrentUser, db: DB) -> TestCaseOut:
    tc, _ = await case_with_access(db, user, case_id)
    return to_out(tc)


def _apply_update(tc: TestCase, body: TestCaseUpdate) -> list[str]:
    changes = body.model_dump(exclude_unset=True, exclude={"version", "change_note"})
    changed: list[str] = []
    new_type = body.test_type or tc.test_type
    definition = body.definition
    if definition is None and body.test_type and body.test_type != tc.test_type:
        raise HTTPException(422, "Đổi loại test cần gửi kèm định nghĩa mới phù hợp")
    if definition is not None and definition.kind != new_type.value:
        raise HTTPException(
            422, f"Định nghĩa loại '{definition.kind}' không khớp loại test '{new_type.value}'"
        )
    for key in changes:
        if key == "definition" and definition is not None:
            new_def = dump_definition(definition)
            if new_def != tc.definition:
                tc.definition = new_def
                changed.append(key)
            continue
        value = getattr(body, key)
        if value is None or getattr(tc, key) == value:
            continue
        setattr(tc, key, value)
        changed.append(key)
    parsed = DEFINITION_ADAPTER.validate_python(tc.definition)
    flagged = body.side_effect if body.side_effect is not None else tc.side_effect
    tc.side_effect = effective_side_effect(parsed, flagged)
    return changed


@router.patch("/api/test-cases/{case_id}", response_model=TestCaseOut)
async def update_test_case(
    case_id: uuid.UUID, body: TestCaseUpdate, user: CurrentUser, request: Request, db: DB
) -> TestCaseOut:
    tc, access = await case_with_access(db, user, case_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    if tc.is_deleted:
        raise HTTPException(409, "Test case đã bị xóa, cần khôi phục trước khi sửa")
    if body.version != tc.version:
        raise HTTPException(
            409,
            f"Test case đã được người khác sửa (phiên bản hiện tại {tc.version}). Hãy tải lại trước khi lưu.",
        )
    changed = _apply_update(tc, body)
    if changed:
        tc.version += 1
        tc.updated_by_id = user.id
        tc.updated_at = datetime.now(UTC)
        record_version(db, tc, user, changed, body.change_note)
        audit.record(
            db,
            action="test_case.update",
            actor=user,
            request=request,
            project_id=tc.project_id,
            target_type="test_case",
            target_id=tc.id,
            details={"code": tc.code, "fields": changed},
        )
    await db.commit()
    await db.refresh(tc)
    return to_out(tc)


@router.post("/api/test-cases/{case_id}/duplicate", response_model=TestCaseOut, status_code=201)
async def duplicate_test_case(
    case_id: uuid.UUID, user: CurrentUser, request: Request, db: DB
) -> TestCaseOut:
    src, access = await case_with_access(db, user, case_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    body = TestCaseCreate.model_validate(
        {
            "title": f"{src.title} (bản sao)"[:300],
            "description": src.description,
            "test_type": src.test_type,
            "priority": src.priority,
            "status": TestCaseStatus.DRAFT,
            "tags": src.tags,
            "preconditions": src.preconditions,
            "expected_result": src.expected_result,
            "test_data": src.test_data,
            "definition": src.definition,
            "side_effect": src.side_effect,
            "retry_count": src.retry_count,
            "timeout_seconds": src.timeout_seconds,
        }
    )
    tc = await _insert_case(db, access, user, body)
    audit.record(
        db,
        action="test_case.duplicate",
        actor=user,
        request=request,
        project_id=tc.project_id,
        target_type="test_case",
        target_id=tc.id,
        details={"code": tc.code, "from": src.code},
    )
    await db.commit()
    await db.refresh(tc)
    return to_out(tc)


@router.delete("/api/test-cases/{case_id}", status_code=204)
async def delete_test_case(case_id: uuid.UUID, user: CurrentUser, request: Request, db: DB) -> None:
    """Xóa mềm: ẩn khỏi danh sách, gỡ khỏi suite, giữ lịch sử và kết quả chạy cũ; có thể khôi phục."""
    tc, access = await case_with_access(db, user, case_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    if tc.is_deleted:
        return
    tc.is_deleted = True
    for item in await db.scalars(select(SuiteItem).where(SuiteItem.test_case_id == tc.id)):
        await db.delete(item)
    audit.record(
        db,
        action="test_case.delete",
        actor=user,
        request=request,
        project_id=tc.project_id,
        target_type="test_case",
        target_id=tc.id,
        details={"code": tc.code},
    )
    await db.commit()


@router.post("/api/test-cases/{case_id}/restore", response_model=TestCaseOut)
async def restore_test_case(
    case_id: uuid.UUID, user: CurrentUser, request: Request, db: DB
) -> TestCaseOut:
    tc, access = await case_with_access(db, user, case_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    tc.is_deleted = False
    audit.record(
        db,
        action="test_case.restore",
        actor=user,
        request=request,
        project_id=tc.project_id,
        target_type="test_case",
        target_id=tc.id,
        details={"code": tc.code},
    )
    await db.commit()
    await db.refresh(tc)
    return to_out(tc)


@router.get("/api/test-cases/{case_id}/versions", response_model=list[TestCaseVersionOut])
async def list_versions(case_id: uuid.UUID, user: CurrentUser, db: DB) -> list[TestCaseVersion]:
    await case_with_access(db, user, case_id)
    return list(
        await db.scalars(
            select(TestCaseVersion)
            .where(TestCaseVersion.test_case_id == case_id)
            .order_by(TestCaseVersion.version.desc())
        )
    )


# ---------- Import / export ----------


@router.get("/api/projects/{project_id}/test-cases/export")
async def export_test_cases(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    request: Request,
    fmt: Annotated[Literal["csv", "xlsx"], Query(alias="format")] = "csv",
) -> Response:
    access = await get_project_access(db, user, project_id)
    cases = list(
        await db.scalars(
            select(TestCase)
            .where(TestCase.project_id == project_id, TestCase.is_deleted.is_(False))
            .order_by(TestCase.seq)
        )
    )
    audit.record(
        db,
        action="test_case.export",
        actor=user,
        request=request,
        project_id=project_id,
        details={"format": fmt, "count": len(cases)},
    )
    await db.commit()
    name = f"{access.project.key}-test-cases.{fmt}"
    if fmt == "xlsx":
        data = test_case_io.export_xlsx(cases)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        data = test_case_io.export_csv(cases)
        media = "text/csv; charset=utf-8"
    return Response(
        data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'}
    )


@router.post("/api/projects/{project_id}/test-cases/import", response_model=ImportResult)
async def import_test_cases(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    request: Request,
    file: Annotated[UploadFile, File()],
    dry_run: bool = Query(default=True),
) -> ImportResult:
    access = await get_project_access(db, user, project_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File vượt quá {limit // 1024} KB")
    try:
        rows = test_case_io.read_rows(file.filename or "", data)
    except test_case_io.ImportFileError as exc:
        raise HTTPException(422, str(exc)) from exc

    existing = {
        tc.code: tc
        for tc in await db.scalars(select(TestCase).where(TestCase.project_id == project_id))
    }
    errors: list[ImportRowError] = []
    parsed: list[tuple[TestCase | None, TestCaseCreate]] = []
    for i, row in enumerate(rows, start=2):  # dòng 1 là tiêu đề
        try:
            code, data_row = test_case_io.parse_row(row)
        except ValueError as exc:
            errors.append(ImportRowError(row=i, message=str(exc)))
            continue
        target = None
        if code:
            target = existing.get(code)
            if target is None:
                errors.append(
                    ImportRowError(row=i, message=f"Không có test case mã {code} trong dự án")
                )
                continue
        parsed.append((target, data_row))

    created = sum(1 for t, _ in parsed if t is None)
    updated = len(parsed) - created
    result = ImportResult(
        dry_run=dry_run or bool(errors),
        total_rows=len(rows),
        created=created,
        updated=updated,
        errors=errors,
    )
    if dry_run or errors:
        return result

    for target, body in parsed:
        if target is None:
            await _insert_case(db, access, user, body)
            continue
        upd = TestCaseUpdate.model_validate({"version": target.version, **body.model_dump()})
        changed = _apply_update(target, upd)
        if target.is_deleted:
            target.is_deleted = False
            changed.append("restored")
        if changed:
            target.version += 1
            target.updated_by_id = user.id
            record_version(db, target, user, changed, "Import")
    audit.record(
        db,
        action="test_case.import",
        actor=user,
        request=request,
        project_id=project_id,
        details={"file": (file.filename or "")[:100], "created": created, "updated": updated},
    )
    await db.commit()
    return result
