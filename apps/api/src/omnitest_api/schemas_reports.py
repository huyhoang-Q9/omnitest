"""Schema báo cáo (Giai đoạn 4)."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from omnitest_api.models import RunStatus


class StatusCounts(BaseModel):
    passed: int = 0
    failed: int = 0
    error: int = 0
    blocked: int = 0
    skipped: int = 0
    cancelled: int = 0

    @property
    def executed(self) -> int:
        return self.passed + self.failed + self.error + self.blocked

    @property
    def total(self) -> int:
        return self.executed + self.skipped + self.cancelled


class GroupStat(BaseModel):
    key: str | None
    label: str
    runs: int
    items: StatusCounts
    # None khi chưa có kết quả nào được thực thi (không hiển thị 0% giả).
    pass_rate: float | None


class TestCaseStat(BaseModel):
    __test__ = False
    test_case_id: uuid.UUID | None
    code: str
    title: str
    executions: int
    items: StatusCounts
    pass_rate: float | None
    last_status: RunStatus
    last_error: str | None
    last_run_id: uuid.UUID
    last_finished_at: datetime | None


class DailyStat(BaseModel):
    date: date
    items: StatusCounts


class ReportFilters(BaseModel):
    date_from: date
    date_to: date
    timezone: str
    environment_id: uuid.UUID | None
    environment_name: str | None
    suite_id: uuid.UUID | None
    suite_name: str | None


class ProjectReportOut(BaseModel):
    project_id: uuid.UUID
    project_key: str
    project_name: str
    generated_at: datetime
    filters: ReportFilters
    runs: int
    run_statuses: dict[str, int]
    items: StatusCounts
    pass_rate: float | None
    by_environment: list[GroupStat]
    by_suite: list[GroupStat]
    test_cases: list[TestCaseStat]
    daily: list[DailyStat]
