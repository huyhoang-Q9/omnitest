# OmniTest Automation Platform

Nền tảng kiểm thử tự động đa dự án: quản lý dự án, môi trường, test case, chạy test Web (Playwright) và API,
báo cáo, có lớp AI hỗ trợ (tùy chọn). Kiến trúc mở rộng theo adapter cho Desktop và Mobile.

Trạng thái hiện tại: **Giai đoạn 2** (nền tảng: đăng nhập, phân quyền, dự án, môi trường, biến secret, audit,
dashboard). Kế hoạch tổng thể: [docs/ke-hoach-mvp.md](docs/ke-hoach-mvp.md). Báo cáo giai đoạn:
[docs/phases](docs/phases).

## Cấu trúc

```
apps/api          FastAPI + SQLAlchemy + Alembic (migrations trong apps/api/migrations)
apps/web          React + TypeScript + Vite + Tailwind (thành phần theo phong cách shadcn/ui)
packages/contracts  OpenAPI sinh từ Pydantic, nguồn type TypeScript cho web
infra/docker      Dockerfile, nginx, Docker Compose
infra/scripts     dev.sh (chạy không cần Docker), export_openapi.py
tests/            unit, integration, security (pytest, PostgreSQL thật), e2e (Playwright)
docs/             kế hoạch, báo cáo từng giai đoạn
```

Các thư mục `apps/worker`, `adapters/*`, `ai/*`, `packages/test-sdk` được tạo ở giai đoạn tương ứng.

## Yêu cầu

- Python 3.12+ và [uv](https://docs.astral.sh/uv/)
- Node 20+ và pnpm 10 (`corepack enable`)
- PostgreSQL 16, Redis 7 (hoặc dùng Docker Compose)

## Chạy nhanh không cần Docker

```bash
cp .env.example .env
uv sync
uv run omnitest-api gen-master-key        # dán vào OMNITEST_MASTER_KEY trong .env
# sửa OMNITEST_DATABASE_URL cho đúng PostgreSQL của bạn; chạy local qua http thì đặt OMNITEST_COOKIE_SECURE=false
pnpm install
infra/scripts/dev.sh start                 # chạy migration, API :8000, web :5173
set -a; . ./.env; set +a
uv run omnitest-api create-admin --email admin@congty.vn   # nhập mật khẩu ẩn
```

Mở http://127.0.0.1:5173 và đăng nhập. Dừng: `infra/scripts/dev.sh stop`.

## Chạy bằng Docker Compose

```bash
cp .env.example .env   # điền OMNITEST_MASTER_KEY, POSTGRES_PASSWORD
docker compose -f infra/docker/compose.yaml --env-file .env up --build
docker compose -f infra/docker/compose.yaml --env-file .env exec api omnitest-api create-admin --email admin@congty.vn
```

Giao diện: http://127.0.0.1:8080.

## Kiểm thử

```bash
# Backend: cần PostgreSQL với DB omnitest_test (đổi URL qua OMNITEST_TEST_DATABASE_URL)
uv run ruff format --check . && uv run ruff check . && uv run mypy
uv run pytest -q

# Frontend
pnpm --filter @omnitest/web lint
pnpm --filter @omnitest/web typecheck
pnpm --filter @omnitest/web test

# E2E trên stack thật (đã chạy dev.sh start và đã có tài khoản admin)
cd apps/web
E2E_ADMIN_EMAIL=... E2E_ADMIN_PASSWORD=... npx playwright test
# Nếu bản Chromium đã cài khác bản Playwright: PW_CHROMIUM_EXECUTABLE=/đường/dẫn/chrome
```

Sau khi đổi API: `pnpm --filter @omnitest/web gen:api` để sinh lại `openapi.json` và type TypeScript.

## Nguyên tắc bảo mật

- Không commit `.env` hay bất kỳ secret nào. Secret của môi trường test được mã hóa AES-256-GCM bằng
  `OMNITEST_MASTER_KEY`; mất khóa này thì không giải mã được secret đã lưu.
- Người ngoài dự án nhận 404 cho mọi tài nguyên của dự án. Mọi thao tác quan trọng ghi audit log.
- Chức năng chưa triển khai hiển thị rõ "Chưa hỗ trợ", không trả kết quả giả.
