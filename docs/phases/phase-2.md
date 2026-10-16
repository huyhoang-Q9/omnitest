# Báo cáo Giai đoạn 2: Nền tảng

Ngày: 16/10/2026. Môi trường kiểm thử: container Linux x86_64, Python 3.13.16, Node 22.22.0,
PostgreSQL 16.15, Redis 7.0.15, Chromium (Playwright build 1194).

## 1. Mục tiêu

Dựng khung monorepo, backend, database, xác thực và phân quyền, quản lý dự án, môi trường, biến secret,
audit log, giao diện chính và Dashboard với dữ liệu thật.

## 2. Tiêu chí nghiệm thu và kết quả

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Script dev khởi động API và web; `alembic upgrade head` chạy sạch trên DB rỗng; downgrade về rỗng sạch | Đạt | `infra/scripts/dev.sh start`; migration chạy mỗi lần test (fixture `migrated_db`); đã chạy upgrade, downgrade, upgrade, `alembic check` |
| 1b | `docker compose up` | **Chưa kiểm chứng**: môi trường hiện tại không có Docker daemon. Đã kiểm tra cú pháp bằng `docker compose config`. Cần chạy thử trên máy có Docker | |
| 2 | Đăng nhập, đăng xuất; sai mật khẩu nhiều lần bị khóa tạm | Đạt | `tests/integration/test_auth.py` (khóa sau 5 lần, đăng xuất hủy phiên phía server) |
| 3 | Secret không xuất hiện trong response, log, DB dạng thuần | Đạt | `test_secret_variable_never_exposed_and_encrypted_at_rest`, `test_secret_value_not_in_logs`, E2E kiểm tra trang không chứa secret |
| 4 | Viewer không sửa được; người ngoài dự án nhận 404, chưa đăng nhập nhận 401, cho mọi endpoint | Đạt | `tests/security/test_access_control.py` (18 endpoint x 2 trường hợp) |
| 5 | Loading, empty, error state, thông báo thao tác; hiển thị tốt ở 375px và 1440px | Đạt | E2E chạy 2 cấu hình desktop 1440x900 và mobile Pixel 7; ảnh chụp trong `artifacts/e2e/screenshots` (không commit) |
| 6 | Test pass, lint và type check sạch | Đạt | Mục 4 |

## 3. File và module

- `apps/api/src/omnitest_api/`: `config`, `db`, `models`, `schemas`, `deps` (phiên, quyền theo dự án),
  `audit`, `security/` (Argon2, AES-GCM, token phiên, che log), `routers/` (auth, users, projects,
  environments, dashboard), `main` (CSRF header, security header), `cli` (tạo admin, sinh khóa).
- `apps/api/migrations/versions/0001_phase2_core_schema.py`.
- `apps/web/src/`: `components/ui` (button, input, dialog, alert-dialog, switch, table...), `components`
  (layout, state, status badge, phân trang), `features` (environments, variables, members, audit),
  `pages` (Login, Dashboard, Projects, ProjectDetail, Environments, EnvironmentDetail, Settings, các màn hình
  giai đoạn sau), `lib/api.ts` + `lib/api-types.ts` (sinh từ OpenAPI), `i18n` (vi mặc định, en).
- `packages/contracts/openapi.json`, `infra/docker/*`, `infra/scripts/*`, `.github/workflows/ci.yml`.
- `tests/unit`, `tests/integration`, `tests/security`, `tests/e2e/web`.

## 4. Kết quả chạy test thực tế

```
uv run ruff format --check . && uv run ruff check .   -> All checks passed
uv run mypy (strict)                                  -> Success: no issues found in 20 source files
uv run pytest -q                                      -> 96 passed
pnpm --filter @omnitest/web lint (oxlint)             -> 0 lỗi, 2 cảnh báo (xem mục 5)
pnpm --filter @omnitest/web typecheck                 -> không lỗi
pnpm --filter @omnitest/web test (vitest)             -> 9 passed
npx playwright test (desktop + mobile)                -> 6 passed
```

Lỗi thật phát hiện nhờ E2E và đã sửa: đăng nhập bằng email tên miền nội bộ (`.local`) bị API trả 422 do
`EmailStr` từ chối tên miền dùng riêng. Đã thay bằng kiểm tra cú pháp riêng, bỏ kiểm tra định dạng ở màn
đăng nhập, thêm test hồi quy.

## 5. Tồn tại

- Docker Compose và image chưa được build thử (thiếu Docker daemon). Cần chạy trên máy Mac hoặc CI.
- CI GitHub Actions đã viết nhưng chưa chạy lần nào.
- oxlint còn 2 cảnh báo `incompatible-library` do `form.watch()` của react-hook-form với React Compiler;
  không ảnh hưởng chức năng.
- Bundle web khoảng 650 KB (chưa chia nhỏ theo route); sẽ lazy-load ở Giai đoạn 7.
- Chuỗi giao diện: menu và trạng thái chung đã qua i18n; các trang còn chuỗi tiếng Việt trực tiếp, chuyển
  dần sang i18n khi cần thêm ngôn ngữ.
- Chưa có đổi mật khẩu, khóa/mở tài khoản, đặt lại mật khẩu qua giao diện (backlog).
- Thay đổi so với kế hoạch: dùng oxlint (mặc định của Vite 8) thay ESLint; React 19, Vite 8, TypeScript 6.

## 6. Hướng dẫn chạy

Xem `README.md`.
