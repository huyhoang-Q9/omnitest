# Báo cáo Giai đoạn 3: Test case, suite và chạy test Web/API

Ngày: 16/10/2026. Môi trường kiểm thử: container Linux x86_64, Python 3.13, Node 22, PostgreSQL 16, Redis 7,
Chromium có sẵn tại `/opt/pw-browsers/chromium` (Playwright 1.64 dùng qua `OMNITEST_CHROMIUM_EXECUTABLE`).

## 1. Mục tiêu

Quản lý test case (API, Web; Desktop/Mobile lưu được nhưng chưa chạy), suite, chạy test qua worker nền với
adapter thật, theo dõi trực tiếp, xem kết quả từng bước kèm log, ảnh chụp, trace; dashboard dùng số liệu thật;
bộ test mẫu chạy được trên ứng dụng demo.

## 2. Tiêu chí nghiệm thu và kết quả

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Test case: tạo, sửa (khóa lạc quan theo version), lịch sử phiên bản, nhân bản, xóa mềm, khôi phục, lọc, phân trang | Đạt | `tests/integration/test_test_cases.py`, E2E `phase3.spec.ts` |
| 2 | Định nghĩa test dạng khai báo được kiểm tra chặt (không có `sleep`, không chạy code người dùng) | Đạt | `TestDefinition` trong `adapters/.../core/definitions.py`, `test_definition_validation` |
| 3 | Import/export CSV, Excel; chống CSV formula injection; nhập tất cả hoặc không; giới hạn kích thước | Đạt | `test_export_import_roundtrip...`, `test_import_row_errors...`, `test_import_rejects_bad_files` |
| 4 | Suite: tạo, sửa, sắp xếp test case, chạy theo suite | Đạt | `test_suites.py`, E2E chạy suite Smoke |
| 5 | Adapter API (HTTPX): method, header, query, body, auth, kiểm tra status/JSONPath/JSON Schema/header/thời gian, trích biến | Đạt | `tests/adapters/test_api_adapter.py` (14 test với demo-target thật) |
| 6 | Adapter Web (Playwright): các hành động khai báo, ảnh chụp, trace | Đạt | `tests/adapters/test_web_adapter.py` (5 test), `test_web_run_saves_screenshot_artifact` |
| 7 | Desktop/Mobile chưa có driver: lưu được, chạy trả **Bị chặn**, không bao giờ báo đạt giả | Đạt | `test_private_network_blocked_and_unsupported_adapter`, E2E |
| 8 | Worker nền (Dramatiq + Redis), timeout từng test, thử lại chỉ với test không thay đổi dữ liệu, hủy an toàn, khôi phục lần chạy treo | Đạt | `tests/integration/test_runs.py` (timeout, retry, hủy khi chờ và khi đang chạy, recover) và E2E qua Redis + worker thật |
| 9 | Chạy trên UAT/Staging hoặc test thay đổi dữ liệu phải xác nhận | Đạt | API trả 409 kèm lý do; `test_confirmation_required_*`; E2E hiển thị lý do và nút xác nhận |
| 10 | Chặn SSRF: ngoài host được phép, mạng nội bộ khi chưa bật, metadata cloud, chuyển hướng | Đạt | `test_api_adapter.py`, `test_private_network_blocked...` |
| 11 | Secret không lộ trong kết quả bước, log, lỗi, **trace** | Đạt | `test_pass_fail_counters_and_secret_masking`, `test_trace_redaction.py`, kiểm tra nội dung trace thật trong `test_web_run_saves_screenshot_artifact` |
| 12 | Phân quyền: Viewer xem, Tester chạy/hủy, Manager quản lý test case; người ngoài 404 cả với bằng chứng | Đạt | `test_run_access_control`, kiểm tra quyền trong `test_test_cases.py`, `test_suites.py` |
| 13 | Dashboard số liệu thật: số test case, lần chạy, tỷ lệ đạt 14 ngày, biểu đồ theo ngày, lần chạy gần đây, test cần chú ý | Đạt | `test_dashboard_run_statistics_and_attention`; tỷ lệ đạt là `null` khi chưa có dữ liệu |
| 14 | Bộ test mẫu chạy thật trên demo-target đều đạt | Đạt | `test_seed_demo_and_run_all` (8/8 đạt), lệnh `omnitest-api seed-demo` |
| 15 | Giao diện có loading, empty, error, hiển thị tốt ở 1440px và Pixel 7 | Đạt | E2E 2 cấu hình, có kiểm tra không tràn ngang |
| 16 | Docker Compose có worker và demo-target | **Chưa kiểm chứng build**: không có Docker daemon; đã kiểm tra cú pháp bằng `docker compose config` | |

## 3. File và module chính

- `adapters/src/omnitest_adapters/`: `core/` (định nghĩa, kết quả, chính sách mạng chống SSRF, biến và che
  secret, registry), `api_httpx/`, `web_playwright/` (kèm `trace_redaction.py`), khung `desktop_macos`,
  `desktop_windows`, `mobile_appium` báo chưa hỗ trợ.
- `apps/worker/src/omnitest_worker/`: `executor.py` (chạy lần chạy, ghi từng bước trực tiếp, bằng chứng,
  heartbeat, hủy, timeout, thử lại), `actors.py` (Dramatiq).
- `apps/demo-target/`: ứng dụng "Kho hàng mini" (đăng nhập, form đăng ký có kiểm tra dữ liệu, CRUD, API JSON).
- `apps/api/src/omnitest_api/`: `routers/test_cases.py`, `suites.py`, `runs.py`, `dashboard.py` (viết lại),
  `services/` (phiên bản, import/export, seed demo), `queue.py`, `schemas_tests.py`, migration `0002_phase3`.
- `apps/web/src/`: trang Test case, trình soạn test case (soạn bước API/Web có cấu trúc, chế độ JSON, lịch sử
  phiên bản), Test suite, Lần chạy, Chi tiết lần chạy (bước, log, request/response đã che, ảnh, trace),
  Đang thực thi; hộp thoại chạy có luồng xác nhận; Dashboard có biểu đồ.
- `infra/docker/api.Dockerfile` (target api, worker có Chromium, demo), `compose.yaml`, `infra/scripts/dev.sh`
  (thêm worker, demo-target), CI cài Chromium để chạy test adapter Web.

## 4. Kết quả chạy test thực tế

```
uv run ruff format --check . && uv run ruff check .   -> All checks passed
uv run mypy (strict)                                  -> Success: no issues found in 49 source files
uv run pytest -q (có Chromium)                        -> 140 passed
uv run pytest -q (không có Chromium)                  -> 134 passed, 6 skipped (test Web, báo lý do rõ)
alembic downgrade base / upgrade head / check         -> sạch, không còn bảng hay enum sau downgrade
pnpm --filter @omnitest/web lint (oxlint)             -> 0 lỗi, 2 cảnh báo cũ của Giai đoạn 2
pnpm --filter @omnitest/web typecheck                 -> không lỗi
pnpm --filter @omnitest/web test (vitest)             -> 13 passed
npx playwright test (desktop + mobile, stack thật)    -> 12 passed (API, worker Dramatiq, Redis, demo-target)
```

Lỗi thật phát hiện trong giai đoạn và đã sửa:

- Trace Playwright lưu nguyên giá trị nhập vào form (mật khẩu lấy từ biến secret). Đã thêm bước che secret
  trong mọi entry của trace (dạng thô, escape JSON, URL-encode); nếu không che hết thì không lưu trace.
- Trình soạn test case bị tràn ngang trên điện thoại khi tên bước dài (grid không co). Phát hiện bằng E2E
  mobile, đã sửa và thêm kiểm tra không tràn ngang cho các trang mới.
- Lọc test case: ký tự `%` và `_` bị hiểu là ký tự đại diện; lọc theo nhãn tiếng Việt không khớp do so chuỗi
  JSON. Đã escape LIKE và chuyển lọc nhãn sang JSONB containment, có test hồi quy.

## 5. Tồn tại

- Docker image và Compose chưa build thử (thiếu Docker daemon). Image worker cài Chromium bằng
  `playwright install --with-deps`, cần chạy thử trên máy có Docker.
- E2E chưa chạy trong CI (cần cả stack); CI chạy pytest có Chromium, lint, typecheck, vitest, build.
- Ảnh chụp màn hình có thể chứa secret nếu trang hiển thị secret dạng chữ thường (ô mật khẩu thì không).
  Khuyến nghị không hiển thị secret trên giao diện hệ thống được test.
- Hủy lần chạy có hiệu lực giữa các bước; một bước đang chờ phản hồi dài sẽ chạy hết thời gian chờ của bước.
- Worker đánh dấu lần chạy mất heartbeat quá 15 phút là lỗi khi khởi động; bước đơn lẻ dài hơn 15 phút cần
  tăng `OMNITEST_STALE_RUN_MINUTES`.
- Test Web hiện chạy Chromium; Firefox/WebKit chọn được trong định nghĩa nhưng chưa kiểm thử trên môi trường này.
- Bundle web khoảng 1 MB (thêm biểu đồ), chưa chia nhỏ theo route; dự kiến lazy-load ở Giai đoạn 7.
- Bằng chứng lưu trên đĩa (`OMNITEST_ARTIFACTS_DIR`), chưa có dọn dẹp theo thời hạn; S3/MinIO và chính sách
  lưu giữ để Giai đoạn 4 hoặc 7.

## 6. Hướng dẫn chạy

Xem `README.md`. Tóm tắt: `infra/scripts/dev.sh start` (API, worker, demo-target, web), tạo admin, rồi
`uv run omnitest-api seed-demo --owner-email <email>` để có dự án DEMO với 8 test mẫu và 2 suite.
