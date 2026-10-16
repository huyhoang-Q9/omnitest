# Image Python dùng chung cho API, worker và demo-target (chọn bằng --target).
# Build từ thư mục gốc repo: docker build -f infra/docker/api.Dockerfile --target api .
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
WORKDIR /app

# Cài thư viện trước (tận dụng cache), mã nguồn sau.
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
COPY apps/demo-target/pyproject.toml apps/demo-target/pyproject.toml
COPY adapters/pyproject.toml adapters/pyproject.toml
COPY ai/pyproject.toml ai/pyproject.toml
RUN for p in apps/api/src/omnitest_api apps/worker/src/omnitest_worker \
        apps/demo-target/src/omnitest_demo_target adapters/src/omnitest_adapters ai/src/omnitest_ai; do \
        mkdir -p "$p" && touch "$p/__init__.py"; done \
    && uv sync --frozen --no-dev --no-install-workspace

COPY apps/api apps/api
COPY apps/worker apps/worker
COPY apps/demo-target apps/demo-target
COPY adapters adapters
COPY ai ai
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --system --uid 10001 --create-home omnitest \
    && mkdir -p /data/artifacts && chown omnitest /data/artifacts

FROM base AS api
USER omnitest
EXPOSE 8000
WORKDIR /app/apps/api
CMD ["sh", "-c", "alembic upgrade head && uvicorn omnitest_api.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]

FROM base AS worker
# Chromium và thư viện hệ thống cho adapter Web (Playwright).
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install --with-deps chromium && chmod -R a+rX /ms-playwright
USER omnitest
CMD ["dramatiq", "omnitest_worker.actors", "--processes", "1", "--threads", "2"]

FROM base AS demo
USER omnitest
EXPOSE 8100
CMD ["uvicorn", "omnitest_demo_target.app:app", "--host", "0.0.0.0", "--port", "8100"]
