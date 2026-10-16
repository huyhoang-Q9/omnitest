"""Trợ lý AI (tùy chọn): đề xuất test case, phân tích lỗi.

- AI tắt (không cấu hình) thì các endpoint trả 503 rõ ràng; mọi chức năng khác không phụ thuộc AI.
- Dự án phải được Admin dự án bật AI trước khi gửi dữ liệu của dự án ra nhà cung cấp.
- Kết quả chỉ trả về cho người dùng xem; không endpoint nào ở đây ghi test case. Người dùng duyệt rồi lưu qua
  API tạo test case thông thường (có kiểm tra quyền và schema như mọi test case khác).
- Audit chỉ ghi tác vụ, nhà cung cấp, mô hình, số token; không ghi nội dung gửi đi.
"""

import json
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Request
from omnitest_ai.providers import AIConfig, AIError, AIProvider, build_provider
from omnitest_ai.tasks import (
    FailureAnalysisResult,
    SuggestionResult,
    analyze_failure,
    suggest_test_cases,
)
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select

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
from omnitest_api.models import ProjectRole, RunStatus, StepResult, TestRun, TestRunItem
from omnitest_api.routers.runs import NOT_FOUND

router = APIRouter(tags=["ai"])


class AIStatusOut(BaseModel):
    configured: bool
    provider: str
    model: str | None


class SuggestIn(BaseModel):
    requirement: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=10, max_length=20000)
    ]
    test_type: Literal["api", "web"] = "api"
    count: int = Field(default=5, ge=1, le=10)


def ai_config() -> AIConfig:
    s = get_settings()
    return AIConfig(
        provider=s.ai_provider,
        model=s.ai_model,
        api_key=s.ai_api_key.get_secret_value() if s.ai_api_key else None,
        base_url=s.ai_base_url,
        timeout_seconds=s.ai_timeout_seconds,
        max_output_tokens=s.ai_max_output_tokens,
    )


def get_provider() -> AIProvider | None:
    return build_provider(ai_config())


def _require_ai(access: ProjectAccess) -> AIProvider:
    provider = get_provider()
    if provider is None:
        raise HTTPException(
            503, "AI chưa được cấu hình trên máy chủ. Các chức năng khác vẫn dùng bình thường."
        )
    if not access.project.ai_enabled:
        raise HTTPException(
            403,
            "Dự án chưa bật AI. Admin dự án bật trong trang chi tiết dự án nếu đồng ý gửi dữ liệu.",
        )
    return provider


@router.get("/api/ai/status", response_model=AIStatusOut)
async def ai_status(_: CurrentUser) -> AIStatusOut:
    cfg = ai_config()
    return AIStatusOut(
        configured=cfg.enabled, provider=cfg.provider, model=cfg.model if cfg.enabled else None
    )


@router.post("/api/projects/{project_id}/ai/suggest-test-cases", response_model=SuggestionResult)
async def ai_suggest_test_cases(
    project_id: uuid.UUID, body: SuggestIn, user: CurrentUser, request: Request, db: DB
) -> SuggestionResult:
    access = await get_project_access(db, user, project_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    provider = _require_ai(access)
    try:
        result = await suggest_test_cases(provider, body.requirement, body.test_type, body.count)
    except AIError as exc:
        _audit(db, user, request, project_id, "ai.suggest_test_cases", provider, error=str(exc))
        await db.commit()
        raise HTTPException(502, str(exc)) from exc
    _audit(
        db,
        user,
        request,
        project_id,
        "ai.suggest_test_cases",
        provider,
        tokens=(result.input_tokens, result.output_tokens),
        extra={"drafts": len(result.drafts), "valid": sum(d.valid for d in result.drafts)},
    )
    await db.commit()
    return result


@router.post("/api/run-items/{item_id}/ai/analyze", response_model=FailureAnalysisResult)
async def ai_analyze_failure(
    item_id: uuid.UUID, user: CurrentUser, request: Request, db: DB
) -> FailureAnalysisResult:
    item = await db.get(TestRunItem, item_id)
    if item is None:
        raise HTTPException(404, NOT_FOUND)
    run = await db.get(TestRun, item.run_id)
    assert run is not None
    access = await get_project_access(db, user, run.project_id)
    require_role(access, ProjectRole.TESTER)
    if item.status not in (RunStatus.FAILED, RunStatus.ERROR, RunStatus.BLOCKED):
        raise HTTPException(422, "Chỉ phân tích test case không đạt, lỗi hoặc bị chặn")
    provider = _require_ai(access)
    context = await _failure_context(db, run, item)
    try:
        result = await analyze_failure(provider, context)
    except AIError as exc:
        _audit(db, user, request, run.project_id, "ai.analyze_failure", provider, error=str(exc))
        await db.commit()
        raise HTTPException(502, str(exc)) from exc
    _audit(
        db,
        user,
        request,
        run.project_id,
        "ai.analyze_failure",
        provider,
        tokens=(result.input_tokens, result.output_tokens),
        extra={"run_item": str(item.id)},
    )
    await db.commit()
    return result


async def _failure_context(db: DB, run: TestRun, item: TestRunItem) -> dict[str, Any]:
    """Dữ liệu gửi cho AI: định nghĩa test (biến ở dạng {{TEN}}) và kết quả các bước đã được worker che secret.
    Không gửi giá trị biến môi trường, không gửi ảnh chụp hay trace."""
    steps = await db.scalars(
        select(StepResult)
        .where(StepResult.run_item_id == item.id, StepResult.attempt == item.attempts)
        .order_by(StepResult.index)
    )
    return {
        "test_case": {
            "code": item.code,
            "title": item.title,
            "type": item.test_type.value,
            "status": item.status.value,
            "error_type": item.error_type,
            "error": item.error,
            "attempts": item.attempts,
        },
        "environment": run.environment_name,
        "definition": item.definition,
        "steps": [
            {
                "index": s.index + 1,
                "name": s.name,
                "status": s.status.value,
                "duration_ms": s.duration_ms,
                "error": s.error,
                "log": s.log[-20:],
                "details": json.dumps(s.details, ensure_ascii=False, default=str)[:3000],
            }
            for s in steps
        ],
    }


def _audit(
    db: DB,
    user: Any,
    request: Request,
    project_id: uuid.UUID,
    action: str,
    provider: AIProvider,
    *,
    tokens: tuple[int | None, int | None] | None = None,
    error: str | None = None,
    extra: dict[str, object] | None = None,
) -> None:
    details: dict[str, object] = {
        "provider": provider.name,
        "model": provider.model,
        **(extra or {}),
    }
    if tokens:
        # Không dùng khóa chứa "token": bộ lọc audit coi đó là dữ liệu nhạy cảm và che đi.
        details["usage"] = {"input": tokens[0], "output": tokens[1]}
    if error:
        details["error"] = error[:300]
    audit.record(
        db, action=action, actor=user, request=request, project_id=project_id, details=details
    )
