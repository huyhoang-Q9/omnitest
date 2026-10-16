import uuid

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from omnitest_api import audit
from omnitest_api.deps import (
    DB,
    Cipher,
    CurrentUser,
    ProjectAccess,
    get_project_access,
    require_role,
    require_writable,
)
from omnitest_api.models import (
    Environment,
    EnvironmentKind,
    EnvironmentVariable,
    ProjectRole,
    User,
)
from omnitest_api.schemas import (
    EnvironmentCreate,
    EnvironmentOut,
    EnvironmentUpdate,
    VariableCreate,
    VariableOut,
    VariableUpdate,
)
from omnitest_api.security.crypto import SecretCipher

router = APIRouter(tags=["environments"])

CONFIRM_BY_DEFAULT = {EnvironmentKind.UAT, EnvironmentKind.STAGING}


async def _env_with_access(
    db: AsyncSession, user: User, environment_id: uuid.UUID
) -> tuple[Environment, ProjectAccess]:
    env = await db.get(Environment, environment_id)
    if env is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Không tìm thấy hoặc bạn không có quyền truy cập"
        )
    access = await get_project_access(db, user, env.project_id)
    return env, access


async def _env_out(db: AsyncSession, env: Environment) -> EnvironmentOut:
    out = EnvironmentOut.model_validate(env)
    out.variable_count = (
        await db.scalar(select(func.count()).where(EnvironmentVariable.environment_id == env.id))
        or 0
    )
    return out


@router.get("/api/projects/{project_id}/environments", response_model=list[EnvironmentOut])
async def list_environments(
    project_id: uuid.UUID, user: CurrentUser, db: DB
) -> list[EnvironmentOut]:
    await get_project_access(db, user, project_id)
    envs = await db.scalars(
        select(Environment).where(Environment.project_id == project_id).order_by(Environment.name)
    )
    return [await _env_out(db, e) for e in envs]


@router.post(
    "/api/projects/{project_id}/environments",
    response_model=EnvironmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_environment(
    project_id: uuid.UUID, body: EnvironmentCreate, user: CurrentUser, request: Request, db: DB
) -> EnvironmentOut:
    access = await get_project_access(db, user, project_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    if body.allow_private_network:
        require_role(access, ProjectRole.ADMIN)
    confirm = body.requires_run_confirmation
    env = Environment(
        project_id=project_id,
        name=body.name,
        kind=body.kind,
        base_url=body.base_url,
        description=body.description,
        allowed_hosts=body.allowed_hosts,
        allow_private_network=body.allow_private_network,
        requires_run_confirmation=(body.kind in CONFIRM_BY_DEFAULT) if confirm is None else confirm,
    )
    db.add(env)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Môi trường {body.name} đã tồn tại"
        ) from None
    audit.record(
        db,
        action="environment.create",
        actor=user,
        request=request,
        project_id=project_id,
        target_type="environment",
        target_id=env.id,
        details={
            "name": env.name,
            "kind": env.kind.value,
            "private_network": env.allow_private_network,
        },
    )
    await db.commit()
    await db.refresh(env)
    return await _env_out(db, env)


@router.get("/api/environments/{environment_id}", response_model=EnvironmentOut)
async def get_environment(environment_id: uuid.UUID, user: CurrentUser, db: DB) -> EnvironmentOut:
    env, _ = await _env_with_access(db, user, environment_id)
    return await _env_out(db, env)


@router.patch("/api/environments/{environment_id}", response_model=EnvironmentOut)
async def update_environment(
    environment_id: uuid.UUID, body: EnvironmentUpdate, user: CurrentUser, request: Request, db: DB
) -> EnvironmentOut:
    env, access = await _env_with_access(db, user, environment_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if (
        "allow_private_network" in changes
        and changes["allow_private_network"] != env.allow_private_network
    ):
        require_role(access, ProjectRole.ADMIN)
    for k, v in changes.items():
        setattr(env, k, v)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Tên môi trường đã tồn tại") from None
    audit.record(
        db,
        action="environment.update",
        actor=user,
        request=request,
        project_id=env.project_id,
        target_type="environment",
        target_id=env.id,
        details={"fields": sorted(changes)},
    )
    await db.commit()
    await db.refresh(env)
    return await _env_out(db, env)


@router.delete("/api/environments/{environment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_environment(
    environment_id: uuid.UUID, user: CurrentUser, request: Request, db: DB
) -> None:
    env, access = await _env_with_access(db, user, environment_id)
    require_role(access, ProjectRole.ADMIN)
    require_writable(access)
    audit.record(
        db,
        action="environment.delete",
        actor=user,
        request=request,
        project_id=env.project_id,
        target_type="environment",
        target_id=env.id,
        details={"name": env.name},
    )
    await db.delete(env)
    await db.commit()


# ---------- Variables ----------


def _var_out(v: EnvironmentVariable) -> VariableOut:
    return VariableOut(
        id=v.id,
        key=v.key,
        is_secret=v.is_secret,
        value=None if v.is_secret else v.value,
        has_value=bool(v.encrypted_value) if v.is_secret else v.value is not None,
        description=v.description,
        updated_at=v.updated_at,
    )


def _store_value(var: EnvironmentVariable, value: str, cipher: SecretCipher) -> None:
    if var.is_secret:
        var.value = None
        var.encrypted_value = cipher.encrypt(value, context=f"envvar:{var.id}")
    else:
        var.value = value
        var.encrypted_value = None


@router.get("/api/environments/{environment_id}/variables", response_model=list[VariableOut])
async def list_variables(environment_id: uuid.UUID, user: CurrentUser, db: DB) -> list[VariableOut]:
    await _env_with_access(db, user, environment_id)
    rows = await db.scalars(
        select(EnvironmentVariable)
        .where(EnvironmentVariable.environment_id == environment_id)
        .order_by(EnvironmentVariable.key)
    )
    return [_var_out(v) for v in rows]


@router.post(
    "/api/environments/{environment_id}/variables",
    response_model=VariableOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_variable(
    environment_id: uuid.UUID,
    body: VariableCreate,
    user: CurrentUser,
    request: Request,
    db: DB,
    cipher: Cipher,
) -> VariableOut:
    env, access = await _env_with_access(db, user, environment_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    if await db.scalar(
        select(EnvironmentVariable.id).where(
            EnvironmentVariable.environment_id == environment_id,
            EnvironmentVariable.key == body.key,
        )
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Biến {body.key} đã tồn tại trong môi trường này"
        )
    var = EnvironmentVariable(
        id=uuid.uuid4(),
        environment_id=environment_id,
        key=body.key,
        is_secret=body.is_secret,
        description=body.description,
    )
    _store_value(var, body.value, cipher)
    db.add(var)
    await db.flush()
    audit.record(
        db,
        action="variable.create",
        actor=user,
        request=request,
        project_id=env.project_id,
        target_type="variable",
        target_id=var.id,
        details={"variable": var.key, "environment": env.name, "masked": var.is_secret},
    )
    await db.commit()
    await db.refresh(var)
    return _var_out(var)


async def _get_var(
    db: AsyncSession, environment_id: uuid.UUID, variable_id: uuid.UUID
) -> EnvironmentVariable:
    v = await db.get(EnvironmentVariable, variable_id)
    if v is None or v.environment_id != environment_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy biến")
    return v


@router.patch(
    "/api/environments/{environment_id}/variables/{variable_id}", response_model=VariableOut
)
async def update_variable(
    environment_id: uuid.UUID,
    variable_id: uuid.UUID,
    body: VariableUpdate,
    user: CurrentUser,
    request: Request,
    db: DB,
    cipher: Cipher,
) -> VariableOut:
    env, access = await _env_with_access(db, user, environment_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    var = await _get_var(db, environment_id, variable_id)
    fields = []
    if body.value is not None:
        _store_value(var, body.value, cipher)
        fields.append("value")
    if body.description is not None:
        var.description = body.description
        fields.append("description")
    audit.record(
        db,
        action="variable.update",
        actor=user,
        request=request,
        project_id=env.project_id,
        target_type="variable",
        target_id=var.id,
        details={
            "variable": var.key,
            "environment": env.name,
            "fields": fields,
            "masked": var.is_secret,
        },
    )
    await db.commit()
    await db.refresh(var)
    return _var_out(var)


@router.delete(
    "/api/environments/{environment_id}/variables/{variable_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_variable(
    environment_id: uuid.UUID, variable_id: uuid.UUID, user: CurrentUser, request: Request, db: DB
) -> None:
    env, access = await _env_with_access(db, user, environment_id)
    require_role(access, ProjectRole.MANAGER)
    require_writable(access)
    var = await _get_var(db, environment_id, variable_id)
    audit.record(
        db,
        action="variable.delete",
        actor=user,
        request=request,
        project_id=env.project_id,
        target_type="variable",
        target_id=var.id,
        details={"variable": var.key, "environment": env.name},
    )
    await db.delete(var)
    await db.commit()
