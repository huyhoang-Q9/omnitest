"""Điểm vào FastAPI."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from omnitest_api.config import get_settings
from omnitest_api.routers import auth, dashboard, environments, projects, users
from omnitest_api.security.redaction import RedactingFilter

CSRF_HEADER = "x-omnitest-csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class SecurityMiddleware(BaseHTTPMiddleware):
    """Chống CSRF bằng header tùy biến (trình duyệt không gửi được header này cross-site nếu CORS không cho)
    và gắn security header cho mọi phản hồi."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            request.method not in SAFE_METHODS
            and request.url.path.startswith("/api/")
            and request.headers.get(CSRF_HEADER) != "1"
        ):
            return JSONResponse({"detail": "Thiếu header chống CSRF"}, status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    for name in ("uvicorn.access", "uvicorn.error", "omnitest"):
        logging.getLogger(name).addFilter(RedactingFilter())

    app = FastAPI(
        title="OmniTest API",
        version="0.1.0",
        docs_url="/api/docs" if settings.env != "production" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.env != "production" else None,
    )
    app.add_middleware(SecurityMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["content-type", CSRF_HEADER],
        )

    for r in (auth.router, users.router, projects.router, environments.router, dashboard.router):
        app.include_router(r)

    @app.get("/api/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
