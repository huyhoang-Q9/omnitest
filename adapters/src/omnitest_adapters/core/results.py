"""Kết quả chuẩn hóa mà mọi adapter trả về."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Outcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class ArtifactFile:
    kind: str  # screenshot | trace | log
    filename: str
    content_type: str
    data: bytes


@dataclass
class StepOutcome:
    index: int
    name: str
    status: Outcome
    duration_ms: int
    log: list[str] = field(default_factory=list)
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    artifacts: list[ArtifactFile] = field(default_factory=list)


@dataclass
class AdapterResult:
    status: Outcome
    steps: list[StepOutcome] = field(default_factory=list)
    error: str | None = None
    error_type: str | None = None
    artifacts: list[ArtifactFile] = field(default_factory=list)
