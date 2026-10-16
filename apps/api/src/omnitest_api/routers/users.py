from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, select

from omnitest_api import audit
from omnitest_api.deps import DB, CurrentUser, SystemAdmin
from omnitest_api.models import ProjectMember, ProjectRole, User
from omnitest_api.schemas import UserCreate, UserOut
from omnitest_api.security.passwords import hash_password, password_problems

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
async def list_users(_: SystemAdmin, db: DB) -> list[User]:
    return list(await db.scalars(select(User).order_by(User.email)))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, admin: SystemAdmin, request: Request, db: DB) -> User:
    if problems := password_problems(body.password):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(problems))
    exists = await db.scalar(select(User.id).where(func.lower(User.email) == body.email.lower()))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email đã tồn tại")
    user = User(
        email=body.email.lower(),
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        is_system_admin=body.is_system_admin,
    )
    db.add(user)
    await db.flush()
    audit.record(
        db,
        action="user.create",
        actor=admin,
        request=request,
        target_type="user",
        target_id=user.id,
        details={"email": user.email, "system_admin": user.is_system_admin},
    )
    await db.commit()
    return user


@router.get("/lookup", response_model=list[UserOut])
async def lookup(q: str, user: CurrentUser, db: DB) -> list[User]:
    """Tìm người dùng theo email để thêm vào dự án. Chỉ quản trị hệ thống hoặc Admin của ít nhất một dự án."""
    if not user.is_system_admin:
        is_admin = await db.scalar(
            select(ProjectMember.id)
            .where(ProjectMember.user_id == user.id, ProjectMember.role == ProjectRole.ADMIN)
            .limit(1)
        )
        if not is_admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bạn không đủ quyền cho thao tác này")
    if len(q.strip()) < 3:
        return []
    pattern = q.strip().lower().replace("%", "").replace("_", "") + "%"
    return list(
        await db.scalars(
            select(User).where(func.lower(User.email).like(pattern), User.is_active).limit(10)
        )
    )
