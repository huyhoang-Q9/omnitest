"""Nghiệp vụ test case dùng chung giữa API và import."""

import uuid
from typing import Any

from omnitest_adapters.core.definitions import has_side_effect
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnitest_api.models import Project, TestCase, TestCaseVersion, User
from omnitest_api.schemas_tests import DEFINITION_ADAPTER

SNAPSHOT_FIELDS = (
    "title",
    "description",
    "test_type",
    "priority",
    "status",
    "tags",
    "preconditions",
    "expected_result",
    "test_data",
    "definition",
    "side_effect",
    "retry_count",
    "timeout_seconds",
)


def snapshot(tc: TestCase) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in SNAPSHOT_FIELDS:
        v = getattr(tc, f)
        out[f] = v.value if hasattr(v, "value") else v
    return out


def effective_side_effect(definition: Any, flagged: bool) -> bool:
    """Người dùng đánh dấu hoặc API có phương thức ghi đều tính là side effect (không tự retry)."""
    return flagged or has_side_effect(definition)


def dump_definition(definition: Any) -> dict[str, Any]:
    data: dict[str, Any] = DEFINITION_ADAPTER.dump_python(definition, mode="json", by_alias=True)
    return data


async def next_code(db: AsyncSession, project: Project) -> tuple[int, str]:
    # Khóa hàng dự án để hai yêu cầu đồng thời không lấy trùng số thứ tự.
    await db.execute(select(Project.id).where(Project.id == project.id).with_for_update())
    current = await db.scalar(
        select(func.max(TestCase.seq)).where(TestCase.project_id == project.id)
    )
    seq = (current or 0) + 1
    return seq, f"{project.key}-TC-{seq:04d}"


def record_version(
    db: AsyncSession, tc: TestCase, user: User, changed: list[str], note: str = ""
) -> None:
    db.add(
        TestCaseVersion(
            id=uuid.uuid4(),
            test_case_id=tc.id,
            version=tc.version,
            snapshot=snapshot(tc),
            changed_fields=changed,
            change_note=note,
            changed_by_email=user.email,
        )
    )


def step_count(definition: dict[str, Any]) -> int:
    """Số bước; với script code là số file."""
    if definition.get("kind") == "script":
        files = definition.get("files")
        return len(files) if isinstance(files, dict) else 0
    steps = definition.get("steps")
    return len(steps) if isinstance(steps, list) else 0
