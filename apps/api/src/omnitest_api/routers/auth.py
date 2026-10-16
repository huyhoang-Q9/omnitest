from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select

from omnitest_api import audit
from omnitest_api.deps import DB, CurrentUser, SettingsDep
from omnitest_api.models import User, UserSession
from omnitest_api.schemas import LoginIn, UserOut
from omnitest_api.security.passwords import verify_password
from omnitest_api.security.sessions import hash_token, new_session_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

INVALID = "Email hoặc mật khẩu không đúng"


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginIn, request: Request, response: Response, db: DB, settings: SettingsDep
) -> User:
    now = datetime.now(UTC)
    user = await db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))

    if user is not None and user.locked_until and user.locked_until > now:
        audit.record(db, action="auth.login_locked", actor=user, request=request)
        await db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Tài khoản tạm khóa do đăng nhập sai nhiều lần, vui lòng thử lại sau",
        )

    ok = verify_password(user.password_hash if user else None, body.password)
    if not ok or user is None or not user.is_active:
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.login_max_failures:
                user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
                user.failed_login_count = 0
        audit.record(
            db, action="auth.login_failed", actor=user, actor_email=body.email, request=request
        )
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    token = new_session_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=now + timedelta(hours=settings.session_ttl_hours),
            ip=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:300],
        )
    )
    # Dọn phiên hết hạn của chính người dùng này.
    await db.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at < now)
    )
    audit.record(db, action="auth.login", actor=user, request=request)
    await db.commit()

    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: DB, settings: SettingsDep) -> None:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
        await db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
