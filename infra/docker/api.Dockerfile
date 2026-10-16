# Image cho API. Build từ thư mục gốc repo: docker build -f infra/docker/api.Dockerfile .
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
RUN mkdir -p apps/api/src/omnitest_api && touch apps/api/src/omnitest_api/__init__.py \
    && uv sync --frozen --no-dev --no-install-workspace

COPY apps/api apps/api
RUN uv sync --frozen --no-dev

# Chạy bằng user không phải root.
RUN useradd --system --uid 10001 omnitest
USER omnitest
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
WORKDIR /app/apps/api
CMD ["sh", "-c", "alembic upgrade head && uvicorn omnitest_api.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
