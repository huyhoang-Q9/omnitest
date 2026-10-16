# OmniTest Automation Platform

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/huyhoang-Q9/omnitest?quickstart=1)

Chạy thử toàn bộ hệ thống ngay trên GitHub: bấm nút trên, chờ script khởi động xong rồi mở cổng 8080
([hướng dẫn](docs/codespaces.md)).

Hướng dẫn sử dụng từng bước có ảnh màn hình: [docs/huong-dan-su-dung.md](docs/huong-dan-su-dung.md) (trong ứng dụng: menu
**Hướng dẫn sử dụng**).

Nền tảng kiểm thử tự động đa dự án: quản lý dự án, môi trường, test case, chạy test Web (Playwright) và API,
báo cáo, có lớp AI hỗ trợ (tùy chọn). Kiến trúc mở rộng theo adapter cho Desktop và Mobile.

Trạng thái hiện tại: **MVP hoàn thành Giai đoạn 1 đến 7**, CI xanh (lint, type check, pytest, build web, chạy thử
stack Docker Compose kèm sandbox). Gồm: đăng nhập, phân quyền, dự án, môi trường, biến secret, audit; test case, suite,
chạy test API (HTTPX) và Web (Playwright) qua worker Dramatiq; script code pytest trong sandbox Docker; báo cáo
HTML/CSV/Excel; import OpenAPI; Trợ lý AI tùy chọn; adapter Desktop/Mobile qua Appium (thử nghiệm). Báo cáo nghiệm
thu: [docs/nghiem-thu.md](docs/nghiem-thu.md). Kế hoạch: [docs/ke-hoach-mvp.md](docs/ke-hoach-mvp.md). Báo cáo từng
giai đoạn: [docs/phases](docs/phases).

## Cấu trúc

```
apps/api          FastAPI + SQLAlchemy + Alembic (migrations trong apps/api/migrations)
apps/worker       Worker Dramatiq: nhận lần chạy từ Redis, gọi adapter, lưu kết quả và bằng chứng
apps/demo-target  Ứng dụng demo "Kho hàng mini" làm đích cho bộ test mẫu (không dùng production)
adapters          Adapter API (HTTPX), Web (Playwright), Desktop/Mobile qua Appium W3C WebDriver (thử nghiệm)
ai                Lớp AI tùy chọn: provider Anthropic/OpenAI-compatible, đề xuất test case, phân tích lỗi
apps/web          React + TypeScript + Vite + Tailwind (thành phần theo phong cách shadcn/ui)
packages/contracts  OpenAPI sinh từ Pydantic, nguồn type TypeScript cho web
infra/docker      Dockerfile, nginx, Docker Compose, image sandbox script code (sandbox.Dockerfile, sandbox/)
infra/scripts     dev.sh (chạy không cần Docker), export_openapi.py
tests/            unit, integration, security (pytest, PostgreSQL thật), e2e (Playwright)
docs/             kế hoạch, báo cáo từng giai đoạn
```

Script code pytest/Playwright chạy trong sandbox Docker cô lập (tắt mặc định): xem [docs/sandbox.md](docs/sandbox.md).

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
uv run playwright install chromium         # trình duyệt cho test Web (hoặc đặt OMNITEST_CHROMIUM_EXECUTABLE)
infra/scripts/dev.sh start                 # migration, API :8000, worker, demo-target :8100, web :5173
set -a; . ./.env; set +a
uv run omnitest-api create-admin --email admin@congty.vn   # nhập mật khẩu ẩn
uv run omnitest-api seed-demo --owner-email admin@congty.vn  # tùy chọn: dự án DEMO với 8 test mẫu
```

Mở http://127.0.0.1:5173 và đăng nhập. Dừng: `infra/scripts/dev.sh stop`.

## Chạy bằng Docker Compose

```bash
cp .env.example .env   # điền OMNITEST_MASTER_KEY, POSTGRES_PASSWORD
docker compose -f infra/docker/compose.yaml --env-file .env up --build
docker compose -f infra/docker/compose.yaml --env-file .env exec api omnitest-api create-admin --email admin@congty.vn
```

Giao diện: http://127.0.0.1:8080. Bật sandbox script code và chạy kiểm tra khói: xem
[docs/phases/phase-7.md](docs/phases/phase-7.md#6-hướng-dẫn-chạy). Dự án demo trong Compose:
`... exec api omnitest-api seed-demo --owner-email admin@congty.vn --base-url http://demo:8100`.

## Trợ lý AI (tùy chọn)

Tắt mặc định. Bật bằng `OMNITEST_AI_PROVIDER` (`anthropic` hoặc `openai_compatible`), `OMNITEST_AI_API_KEY`,
`OMNITEST_AI_MODEL`, `OMNITEST_AI_BASE_URL` (xem `.env.example`). Sau đó Admin từng dự án phải bật AI cho dự án.
AI chỉ đề xuất; không có quyền ghi dữ liệu, chạy test hay chạy lệnh.

E2E giao diện AI dùng test double (không phải AI thật):
`uv run uvicorn tests.e2e.fake_llm:app --port 8199` rồi khởi động API với
`OMNITEST_AI_PROVIDER=openai_compatible OMNITEST_AI_BASE_URL=http://127.0.0.1:8199/v1`.

## Kiểm thử

```bash
# Backend: cần PostgreSQL với DB omnitest_test (đổi URL qua OMNITEST_TEST_DATABASE_URL)
uv run ruff format --check . && uv run ruff check . && uv run mypy
uv run pytest -q          # test adapter Web cần OMNITEST_CHROMIUM_EXECUTABLE, thiếu thì bị skip và được báo rõ

# Frontend
pnpm --filter @omnitest/web lint
pnpm --filter @omnitest/web typecheck
pnpm --filter @omnitest/web test

# E2E trên stack thật (đã chạy dev.sh start, có tài khoản admin và đã chạy seed-demo cho tài khoản đó)
cd apps/web
E2E_ADMIN_EMAIL=... E2E_ADMIN_PASSWORD=... npx playwright test
# Nếu bản Chromium đã cài khác bản Playwright: PW_CHROMIUM_EXECUTABLE=/đường/dẫn/chrome
```

Sau khi đổi API: `pnpm --filter @omnitest/web gen:api` để sinh lại `openapi.json` và type TypeScript.

## Nguyên tắc bảo mật

- Không commit `.env` hay bất kỳ secret nào. Secret của môi trường test được mã hóa AES-256-GCM bằng
  `OMNITEST_MASTER_KEY`; mất khóa này thì không giải mã được secret đã lưu.
- Người ngoài dự án nhận 404 cho mọi tài nguyên của dự án. Mọi thao tác quan trọng ghi audit log.
- Chức năng chưa triển khai hiển thị rõ "Chưa hỗ trợ", không trả kết quả giả. Test Desktop/Mobile cần Appium
  server (Base URL của môi trường), driver và thiết bị thật; thiếu một trong các thứ đó thì kết quả là "Bị chặn".
  Capability Appium bị giới hạn theo danh sách cho phép, "app" không được là URL.
- Worker chỉ chạy định nghĩa test dạng khai báo qua adapter, không thực thi code người dùng nhập. Script code (nếu
  máy chủ và Admin dự án cùng bật) chỉ chạy trong container sandbox: không root, rootfs chỉ đọc, không mạng mặc
  định, giới hạn tài nguyên, chỉ Admin dự án viết được (docs/sandbox.md).
- Chặn SSRF: chỉ gọi host của môi trường và danh sách host được phép; mạng nội bộ chỉ khi Admin dự án bật;
  địa chỉ metadata cloud luôn bị chặn, kiểm tra cả khi chuyển hướng và lúc kết nối. Trình duyệt của test Web đi
  qua proxy kiểm soát mạng nên chuyển hướng trong trình duyệt cũng bị kiểm tra.
- Báo cáo HTML là trang tĩnh có CSP sandbox; CSV/Excel chống formula injection. Import OpenAPI chỉ đọc YAML an toàn
  (cấm alias), chỉ giải `$ref` nội bộ.
- Chạy trên môi trường UAT/Staging hoặc test có thay đổi dữ liệu cần người dùng xác nhận; test thay đổi dữ liệu
  không tự thử lại. Secret được che trong log, kết quả bước và trace.
