"""Schema cho test case, suite, test run (Giai đoạn 3)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from omnitest_adapters.core.definitions import TestDefinition
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

from omnitest_api.models import Priority, RunStatus, TestCaseStatus, TestType
from omnitest_api.schemas import AuditOut

DEFINITION_ADAPTER: TypeAdapter[Any] = TypeAdapter(TestDefinition)

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
LongText = Annotated[str, StringConstraints(max_length=20000)]
Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _check_kind(test_type: TestType, definition: Any) -> None:
    if definition is not None and definition.kind != test_type.value:
        raise ValueError(
            f"Định nghĩa loại '{definition.kind}' không khớp loại test '{test_type.value}'"
        )


class TestCaseCreate(BaseModel):
    __test__ = False
    title: Title
    description: LongText = ""
    test_type: TestType
    priority: Priority = Priority.MEDIUM
    status: TestCaseStatus = TestCaseStatus.DRAFT
    tags: list[Tag] = Field(default_factory=list, max_length=20)
    preconditions: LongText = ""
    expected_result: LongText = ""
    test_data: dict[str, Any] = Field(default_factory=dict)
    definition: TestDefinition
    side_effect: bool = False
    retry_count: int = Field(default=0, ge=0, le=3)
    timeout_seconds: int = Field(default=300, ge=5, le=3600)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return sorted({t.lower() for t in v})

    @model_validator(mode="after")
    def _kind(self) -> "TestCaseCreate":
        _check_kind(self.test_type, self.definition)
        return self


class TestCaseUpdate(BaseModel):
    __test__ = False
    # Khóa lạc quan: phải gửi đúng version đang sửa, tránh ghi đè thay đổi của người khác.
    version: int = Field(ge=1)
    change_note: Annotated[str, StringConstraints(max_length=500)] = ""
    title: Title | None = None
    description: LongText | None = None
    test_type: TestType | None = None
    priority: Priority | None = None
    status: TestCaseStatus | None = None
    tags: list[Tag] | None = Field(default=None, max_length=20)
    preconditions: LongText | None = None
    expected_result: LongText | None = None
    test_data: dict[str, Any] | None = None
    definition: TestDefinition | None = None
    side_effect: bool | None = None
    retry_count: int | None = Field(default=None, ge=0, le=3)
    timeout_seconds: int | None = Field(default=None, ge=5, le=3600)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else sorted({t.lower() for t in v})


class TestCaseOut(ORM):
    __test__ = False
    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    title: str
    description: str
    test_type: TestType
    priority: Priority
    status: TestCaseStatus
    tags: list[str]
    preconditions: str
    expected_result: str
    test_data: dict[str, Any]
    definition: dict[str, Any]
    side_effect: bool
    retry_count: int
    timeout_seconds: int
    version: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    step_count: int = 0


class TestCaseVersionOut(ORM):
    __test__ = False
    id: uuid.UUID
    version: int
    changed_fields: list[str]
    change_note: str
    changed_by_email: str | None
    created_at: datetime
    snapshot: dict[str, Any]


class ImportRowError(BaseModel):
    row: int
    message: str


class ImportResult(BaseModel):
    dry_run: bool
    total_rows: int
    created: int
    updated: int
    errors: list[ImportRowError]


class OpenApiPreviewItem(BaseModel):
    method: str
    path: str
    title: str
    side_effect: bool
    variables: list[str]
    warnings: list[str]
    duplicate: bool


class OpenApiImportResult(BaseModel):
    dry_run: bool
    api_title: str
    api_version: str
    operations: int
    created: int
    skipped_duplicates: int
    items: list[OpenApiPreviewItem]
    warnings: list[str]
    created_codes: list[str] = Field(default_factory=list)


# ---------- Suites ----------


class SuiteCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    description: LongText = ""
    test_case_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)


class SuiteUpdate(BaseModel):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    description: LongText | None = None


class SuiteItemsIn(BaseModel):
    test_case_ids: list[uuid.UUID] = Field(max_length=1000)


class SuiteOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    case_count: int = 0


class SuiteCaseOut(BaseModel):
    position: int
    test_case: TestCaseOut


class SuiteDetailOut(SuiteOut):
    items: list[SuiteCaseOut] = Field(default_factory=list)


# ---------- Runs ----------


class RunCreate(BaseModel):
    environment_id: uuid.UUID
    suite_id: uuid.UUID | None = None
    test_case_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)
    # Bắt buộc true khi môi trường cần xác nhận hoặc có test side effect.
    confirm: bool = False
    title: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""

    @model_validator(mode="after")
    def _scope(self) -> "RunCreate":
        if not self.suite_id and not self.test_case_ids:
            raise ValueError("Chọn suite hoặc ít nhất một test case")
        return self


class RunOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    environment_id: uuid.UUID | None
    environment_name: str
    suite_id: uuid.UUID | None
    title: str
    status: RunStatus
    triggered_by_email: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested: bool
    total: int
    passed: int
    failed: int
    skipped: int
    blocked: int
    errored: int
    cancelled: int
    error: str | None
    duration_ms: int | None = None
    project_key: str | None = None


class ArtifactOut(ORM):
    id: uuid.UUID
    kind: str
    filename: str
    content_type: str
    size: int
    step_result_id: uuid.UUID | None
    created_at: datetime


class StepResultOut(ORM):
    id: uuid.UUID
    attempt: int
    index: int
    name: str
    status: RunStatus
    duration_ms: int
    log: list[str]
    error: str | None
    details: dict[str, Any]


class RunItemOut(ORM):
    id: uuid.UUID
    test_case_id: uuid.UUID | None
    position: int
    code: str
    title: str
    test_type: TestType
    test_case_version: int
    side_effect: bool
    max_retries: int
    status: RunStatus
    attempts: int
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    error: str | None
    error_type: str | None


class RunItemDetailOut(RunItemOut):
    definition: dict[str, Any]
    steps: list[StepResultOut]
    artifacts: list[ArtifactOut]


class RunDetailOut(RunOut):
    items: list[RunItemOut]


class AdapterOut(BaseModel):
    key: str
    display_name: str
    status: str
    test_kinds: list[str]
    environment_ok: bool
    message: str


# ---------- Dashboard ----------


class DailyRunStat(BaseModel):
    date: date
    passed: int
    failed: int
    other: int


class AttentionItem(BaseModel):
    """Test case có kết quả gần nhất là lỗi/không đạt/bị chặn."""

    run_id: uuid.UUID
    item_id: uuid.UUID
    test_case_id: uuid.UUID | None
    project_key: str
    code: str
    title: str
    status: RunStatus
    error: str | None
    environment_name: str
    finished_at: datetime | None


class DashboardOut(BaseModel):
    projects: int
    environments: int
    members: int
    test_cases: int
    runs_total: int
    active_runs: int
    period_days: int
    # Số kết quả test case trong các lần chạy kết thúc trong kỳ, theo trạng thái.
    item_totals: dict[str, int]
    # None khi trong kỳ chưa có kết quả nào (không hiển thị 0% giả).
    pass_rate: float | None
    daily: list[DailyRunStat]
    recent_runs: list[RunOut]
    attention: list[AttentionItem]
    recent_activity: list[AuditOut]
