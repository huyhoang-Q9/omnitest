"""Báo cáo: lần chạy (HTML/CSV/Excel) và tổng hợp dự án theo môi trường, suite, khoảng ngày."""

import uuid
from datetime import date, timedelta
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, Response

from omnitest_api import audit
from omnitest_api.config import get_settings
from omnitest_api.deps import DB, CurrentUser, ProjectAccess, get_project_access
from omnitest_api.models import Environment, TestSuite
from omnitest_api.routers.runs import NOT_FOUND, run_with_access
from omnitest_api.schemas_reports import ProjectReportOut
from omnitest_api.services import reports

router = APIRouter(tags=["reports"])
Format = Literal["html", "csv", "xlsx"]
MEDIA = {
    "html": "text/html; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
# Báo cáo HTML là trang tĩnh: không script, không tải tài nguyên ngoài, mở trong sandbox.
HTML_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"


def _file_response(content: bytes, fmt: str, filename: str) -> Response:
    # Tên file có thể chứa tiếng Việt: dùng filename* theo RFC 5987, kèm tên ASCII dự phòng.
    ascii_name = filename.encode("ascii", "ignore").decode() or f"bao-cao.{fmt}"
    disposition = "inline" if fmt == "html" else "attachment"
    headers = {
        "Content-Disposition": (
            f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
        ),
        "Cache-Control": "private, no-store",
    }
    if fmt == "html":
        headers["Content-Security-Policy"] = HTML_CSP
    return Response(content, media_type=MEDIA[fmt], headers=headers)


@router.get(
    "/api/runs/{run_id}/report",
    responses={200: {"content": {m: {} for m in MEDIA.values()}}},
    response_class=Response,
)
async def run_report(
    run_id: uuid.UUID,
    user: CurrentUser,
    request: Request,
    db: DB,
    format: Format = "html",
) -> Response:
    run, access = await run_with_access(db, user, run_id)
    tz = get_settings().display_timezone
    rr = await reports.load_run_report(db, run, access.project, tz)
    render = {
        "html": reports.run_report_html,
        "csv": reports.run_report_csv,
        "xlsx": reports.run_report_xlsx,
    }[format]
    content = render(rr)
    audit.record(
        db,
        action="report.export",
        actor=user,
        request=request,
        project_id=run.project_id,
        target_type="run",
        target_id=run.id,
        details={"format": format},
    )
    await db.commit()
    stamp = (run.finished_at or run.created_at).strftime("%Y%m%d-%H%M")
    return _file_response(content, format, f"{access.project.key}-lan-chay-{stamp}.{format}")


async def _project_report(
    db: DB,
    access: ProjectAccess,
    date_from: date | None,
    date_to: date | None,
    environment_id: uuid.UUID | None,
    suite_id: uuid.UUID | None,
) -> ProjectReportOut:
    tz = get_settings().display_timezone
    d_from, d_to = reports.default_range(tz)
    date_to = date_to or d_to
    date_from = date_from or (date_to - (d_to - d_from))
    if date_from > date_to:
        raise HTTPException(422, "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc")
    if date_to - date_from > timedelta(days=reports.MAX_RANGE_DAYS - 1):
        raise HTTPException(422, f"Khoảng thời gian tối đa {reports.MAX_RANGE_DAYS} ngày")
    env_name = suite_name = None
    project_id = access.project.id
    if environment_id:
        env = await db.get(Environment, environment_id)
        if env is None or env.project_id != project_id:
            raise HTTPException(404, NOT_FOUND)
        env_name = env.name
    if suite_id:
        suite = await db.get(TestSuite, suite_id)
        if suite is None or suite.project_id != project_id:
            raise HTTPException(404, NOT_FOUND)
        suite_name = suite.name
    return await reports.project_report(
        db,
        access.project,
        reports.ProjectReportQuery(date_from, date_to, environment_id, suite_id),
        tz,
        environment_name=env_name,
        suite_name=suite_name,
    )


@router.get("/api/projects/{project_id}/reports/summary", response_model=ProjectReportOut)
async def project_summary(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    date_from: date | None = None,
    date_to: date | None = None,
    environment_id: uuid.UUID | None = None,
    suite_id: uuid.UUID | None = None,
) -> ProjectReportOut:
    access = await get_project_access(db, user, project_id)
    return await _project_report(db, access, date_from, date_to, environment_id, suite_id)


@router.get(
    "/api/projects/{project_id}/reports/summary/export",
    responses={200: {"content": {m: {} for m in MEDIA.values()}}},
    response_class=Response,
)
async def project_summary_export(
    project_id: uuid.UUID,
    user: CurrentUser,
    request: Request,
    db: DB,
    format: Format = "xlsx",
    date_from: date | None = None,
    date_to: date | None = None,
    environment_id: uuid.UUID | None = None,
    suite_id: uuid.UUID | None = None,
) -> Response:
    access = await get_project_access(db, user, project_id)
    r = await _project_report(db, access, date_from, date_to, environment_id, suite_id)
    render = {
        "html": reports.project_report_html,
        "csv": reports.project_report_csv,
        "xlsx": reports.project_report_xlsx,
    }[format]
    content = render(r)
    audit.record(
        db,
        action="report.export",
        actor=user,
        request=request,
        project_id=project_id,
        target_type="project",
        target_id=project_id,
        details={
            "format": format,
            "date_from": r.filters.date_from.isoformat(),
            "date_to": r.filters.date_to.isoformat(),
            "environment": r.filters.environment_name,
            "suite": r.filters.suite_name,
        },
    )
    await db.commit()
    name = f"{access.project.key}-bao-cao-{r.filters.date_from:%Y%m%d}-{r.filters.date_to:%Y%m%d}"
    return _file_response(content, format, f"{name}.{format}")
