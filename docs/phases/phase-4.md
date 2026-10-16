# Báo cáo Giai đoạn 4: Báo cáo, import OpenAPI, kiểm thử bảo mật

Ngày: 16/10/2026. Môi trường kiểm thử: container Linux x86_64, Python 3.13, Node 22, PostgreSQL 16, Redis 7,
Chromium tại `/opt/pw-browsers/chromium`.

## 1. Mục tiêu

Báo cáo kết quả kiểm thử (một lần chạy và tổng hợp dự án) dạng HTML, CSV, Excel với số liệu khớp DB; sinh khung
test case API từ OpenAPI; bộ test bảo mật cho SSRF, IDOR, upload, che secret; bổ sung audit.

## 2. Tiêu chí nghiệm thu và kết quả

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Báo cáo lần chạy HTML/CSV/Excel: tổng quan, từng test case, bước không đạt của lần thử cuối | Đạt | `tests/integration/test_reports.py::test_run_report_formats_are_correct_and_safe` |
| 2 | Báo cáo dự án lọc theo môi trường, suite, khoảng ngày (tối đa 366 ngày, theo múi giờ hiển thị); nhóm theo môi trường, suite, test case, ngày | Đạt | `test_project_summary_matches_database_and_filters` đối chiếu bộ đếm trong DB |
| 3 | Tỷ lệ đạt không hiện 0% giả khi chưa có dữ liệu | Đạt | API trả `null`, giao diện ghi "Chưa có dữ liệu"; E2E lọc khoảng ngày tương lai |
| 4 | Xuất an toàn: HTML escape toàn bộ, CSP `sandbox` không script; CSV/Excel chống formula injection; không chứa secret | Đạt | Test kiểm tra `<script>`, ô `=HYPERLINK`, secret trong mọi sheet |
| 5 | Phân quyền báo cáo: Viewer xem được; người ngoài 404; bộ lọc trỏ tới môi trường dự án khác bị 404 (IDOR) | Đạt | `test_report_access_control` |
| 6 | Import OpenAPI 3.x (JSON/YAML): xem trước mặc định, tạo test Nháp, bỏ trùng khi import lại, biến cho giá trị chưa có ví dụ, nhận diện xác thực bearer/basic/apiKey | Đạt | `tests/unit/test_openapi_import.py` (12), `tests/integration/test_openapi_import.py` |
| 7 | Test sinh từ OpenAPI chạy thật được | Đạt | Import OpenAPI của demo-target, chạy: `GET /api/health` đạt, test thiếu biến báo `missing_variable` |
| 8 | Upload an toàn: giới hạn 2 MB (413), cấm alias YAML (billion laughs), cấm tag Python, chỉ `$ref` nội bộ, Tester không được import (403) | Đạt | `test_import_openapi_permissions_and_limits`, unit test |
| 9 | Chặn SSRF: IPv6 loopback, IPv4 ánh xạ IPv6, IP dạng thập phân/hex/bát phân, metadata cloud, DNS rebinding | Đạt | `tests/unit/test_ssrf_policy.py` (38 test) |
| 10 | Chặn chuyển hướng tới đích cấm cả trong API và **trình duyệt** | Đạt (vá lỗ thật, xem mục 4) | `test_redirect_to_forbidden_target_blocked`, `test_browser_redirect_*` |
| 11 | Audit: xuất báo cáo, import OpenAPI, loại môi trường khi tạo lần chạy | Đạt | `report.export`, `test_case.import_openapi`, `run.create.environment_kind` |
| 12 | Giao diện trang Báo cáo, nút xuất ở chi tiết lần chạy, hộp thoại OpenAPI; tốt ở 1440px và Pixel 7 | Đạt | E2E `phase4.spec.ts` 2 cấu hình, kiểm tra không tràn ngang |
| 13 | Sandbox chạy script code | **Chưa làm, cần Hoàng quyết** | Xem mục 5 |

## 3. File và module chính

- `adapters/.../web_playwright/egress_proxy.py`: proxy kiểm soát mạng cho trình duyệt; `adapter.py` chạy Chromium
  qua proxy (kể cả loopback), tắt lưu lượng nền của Chromium.
- `adapters/.../core/network.py`: sửa phân loại `::1` (trước đây Python xếp vào dải dự trữ nên luôn bị chặn).
- `apps/api/.../services/reports.py`, `routers/reports.py`, `schemas_reports.py`: truy vấn và kết xuất báo cáo.
- `apps/api/.../services/openapi_import.py`, endpoint `POST /api/projects/{id}/test-cases/import-openapi`.
- `apps/web/src/pages/ReportsPage.tsx`, `features/openapi-import.tsx`, nút xuất ở `RunDetailPage.tsx`.
- Nhãn trạng thái thống nhất: `failed` là "Không đạt", `error` là "Lỗi hệ thống" (giao diện và báo cáo).
- `apps/demo-target`: thêm `/api/redirect` (open redirect có chủ đích) để kiểm thử chặn chuyển hướng.

## 4. Kết quả chạy test thực tế

```
uv run ruff format --check . && uv run ruff check .   -> All checks passed
uv run mypy (strict)                                  -> Success: no issues found in 54 source files
uv run pytest -q (có Chromium)                        -> 203 passed
pnpm --filter @omnitest/web lint (oxlint)             -> 0 lỗi, 2 cảnh báo cũ của Giai đoạn 2
pnpm --filter @omnitest/web typecheck                 -> không lỗi
pnpm --filter @omnitest/web test (vitest)             -> 15 passed
pnpm --filter @omnitest/web build                     -> thành công
npx playwright test (desktop + mobile, stack thật)    -> 18 passed
```

Lỗi thật phát hiện và đã sửa:

- **SSRF qua chuyển hướng trong trình duyệt**: `route` của Playwright không được gọi cho các bước chuyển hướng,
  nên một trang được phép có thể chuyển hướng trình duyệt tới 127.0.0.1 khác cổng, `169.254.169.254` hay host
  ngoài allowlist. Đã chứng minh bằng thí nghiệm rồi vá bằng proxy: mọi kết nối của trình duyệt (HTTP, HTTPS
  CONNECT) được kiểm tra host, phân giải DNS, kiểm tra IP và nối tới đúng IP đã kiểm tra. Bước đi tới đích bị
  chặn được báo **Bị chặn** kèm lý do.
- `::1` luôn bị chặn kể cả khi Admin bật mạng nội bộ.
- Test cũ `test_redirect_to_internal_metadata_blocked` không thật sự kiểm tra chuyển hướng; đã thay bằng test
  chuyển hướng thật tới metadata, `metadata.google.internal`, `::ffff:169.254.169.254`, host ngoài allowlist.

## 5. Tồn tại và việc cần Hoàng quyết

- **Sandbox script code chưa làm.** Kế hoạch có chạy script Python/Playwright do người dùng viết trong
  container cô lập. Môi trường hiện tại không có Docker để kiểm chứng cô lập, và đây là chức năng rủi ro cao
  (chạy code tùy ý). Tôi đề xuất giữ nguyên chỉ chạy định nghĩa khai báo cho MVP; nếu cần, làm sandbox ở bản
  sau trên máy có Docker (container không mạng mặc định, không quyền root, giới hạn CPU/RAM/thời gian, Admin dự
  án bật riêng và ghi audit).
- Proxy kiểm soát mạng đã kiểm thử với Chromium; Firefox/WebKit dùng cùng cấu hình proxy nhưng chưa chạy thử.
  WebSocket đi qua CONNECT nên cũng bị kiểm tra nhưng chưa có test riêng.
- Báo cáo HTML không nhúng ảnh chụp và trace (xem trong OmniTest). Chưa có xuất PDF; có thể in trang HTML ra PDF.
- Import OpenAPI chỉ sinh kiểm tra mã trạng thái; chưa sinh kiểm tra JSON Schema từ response (schema OpenAPI 3.0
  khác JSON Schema ở một số điểm, dễ báo sai). Swagger 2.0 chưa hỗ trợ.
- Bundle web khoảng 1,1 MB, chia nhỏ theo route ở Giai đoạn 7. Docker image chưa build thử (Giai đoạn 7 chạy trong CI).

## 6. Hướng dẫn dùng

- Báo cáo dự án: menu **Báo cáo**, chọn dự án, môi trường, suite, khoảng ngày; nút HTML (mở trang in được), Excel, CSV.
  API: `GET /api/projects/{id}/reports/summary` và `.../summary/export?format=html|csv|xlsx`.
- Báo cáo một lần chạy: nút ở trang chi tiết lần chạy; API `GET /api/runs/{id}/report?format=html|csv|xlsx`.
- Import OpenAPI: trang **Test case**, nút **Từ OpenAPI** (Manager trở lên), xem trước rồi tạo. Khai báo các biến
  được liệt kê (VD `API_TOKEN`) trong môi trường trước khi chạy.
