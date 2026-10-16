# Báo cáo: Sandbox chạy script code (pytest/Playwright)

Ngày: 16/10/2026. Làm theo lựa chọn "Làm ngay" của Hoàng. Thiết kế chi tiết và giới hạn: [docs/sandbox.md](../sandbox.md).

## 1. Mục tiêu

Cho phép test viết bằng code (pytest, Playwright Python) mà không chạy code người dùng trên máy chủ chính: mỗi lần
chạy là một container Docker dùng một lần, cô lập, có giới hạn, và chỉ người có quyền cao nhất trong dự án viết được.

## 2. Tiêu chí nghiệm thu và kết quả

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Tắt mặc định ở cả hai lớp: máy chủ (`OMNITEST_SANDBOX_ENABLED`) và dự án (Admin dự án bật); thiếu thì Bị chặn | Đạt | `test_blocked_when_server_disabled`, `test_run_needs_confirmation_and_is_blocked_when_disabled` |
| 2 | Chỉ Admin dự án tạo/sửa/nhân bản/import script; Manager không lách được qua đổi loại test hay import | Đạt | `test_only_project_admin_with_script_enabled_can_write_scripts`, `test_import_cannot_smuggle_scripts` |
| 3 | Chạy script luôn cần xác nhận, không tự thử lại, audit ghi số test script | Đạt | Test tích hợp, E2E `sandbox.spec.ts` |
| 4 | Không root, không capability, rootfs chỉ đọc, không Docker socket | Đạt | `test_isolated_run_passes_with_evidence` (kiểm tra từ bên trong container) |
| 5 | Mặc định không có mạng (kể cả máy chủ, metadata cloud) | Đạt | như trên, thử kết nối 1.1.1.1, 169.254.169.254, gateway Docker |
| 6 | Chế độ mạng theo môi trường: chỉ qua proxy áp chính sách; metadata, host lạ, mạng nội bộ chưa bật đều bị chặn; không đi thẳng được | Đạt | `test_network_environment_goes_through_policy_proxy`, `test_private_network_blocked_unless_enabled` |
| 7 | Giới hạn RAM, số tiến trình, thời gian, dung lượng kết quả; hủy dừng ngay | Đạt | `test_memory_limit_enforced`, `test_process_limit_enforced`, `test_timeout_kills_container`, `test_cancel_stops_container`, `test_output_limit` |
| 8 | Secret che trong log/kết quả; bằng chứng không hiển thị được HTML/JS | Đạt | `test_failed_assertion_reports_failed`, `test_artifacts_never_rendered_except_real_png` |
| 9 | Kết quả đọc như dữ liệu không tin cậy (tar chỉ file thường, XML chống entity) | Đạt | `test_untrusted_result_tar_only_regular_files`, `test_parse_junit_refuses_entity_expansion` |
| 10 | Luôn dọn container, proxy, volume | Đạt | fixture `no_leftovers` sau mỗi test Docker |
| 11 | Giao diện: công tắc dự án, trình soạn file, chọn chế độ mạng, kết quả từng hàm test, ảnh và log | Đạt | E2E desktop và mobile, không tràn ngang |
| 12 | Cô lập mạnh hơn container (gVisor/Kata), Docker rootless | **Chưa làm** | Khuyến nghị cấu hình trên máy worker, xem docs/sandbox.md |

## 3. File chính

- `adapters/src/omnitest_adapters/sandbox/adapter.py`: chạy container qua Docker CLI, proxy, giới hạn, đọc kết quả.
- `infra/docker/sandbox.Dockerfile`, `infra/docker/sandbox/`: image (Playwright Python 1.63, pytest, httpx),
  `bootstrap.py` chạy trong container, `proxy_main.py` cho container proxy.
- `core/definitions.py`: `ScriptTestDefinition`. Migration `0004_sandbox` (loại test `script`, `projects.script_enabled`).
- API: kiểm tra quyền trong `routers/test_cases.py`, lý do xác nhận trong `routers/runs.py`, trạng thái ở `/api/adapters`.
- Web: `features/script.tsx` (công tắc dự án, trình soạn), `hooks/sandbox.ts`.

## 4. Kết quả chạy test thực tế (Docker 29.8.2 trong môi trường phát triển)

```
uv run ruff format --check . && uv run ruff check .   -> sạch
uv run mypy (strict)                                  -> Success: no issues found in 62 source files
uv run pytest -q (Docker + image sandbox + Appium)    -> 263 passed (28 test sandbox, 4 test tích hợp script)
pnpm --filter @omnitest/web typecheck / lint / test   -> không lỗi / 2 cảnh báo cũ / 16 passed
vite build                                            -> thành công
npx playwright test (desktop + mobile)                -> 22 passed, 2 skipped (test "AI chưa cấu hình" tự bỏ qua)
```

CI đã thêm bước build image sandbox để các test Docker chạy thật trên GitHub Actions.

## 5. Tồn tại

- Script đọc được giá trị thật của secret; việc che chỉ áp cho log và kết quả. Chỉ bật cho dự án tin người viết.
- Worker cần quyền Docker (tương đương root trên máy đó): nên tách máy chạy worker có sandbox. Docker Compose hiện
  chưa cấu hình sẵn worker có Docker; sẽ bổ sung ở GĐ7.
- Container dùng chung kernel; với script không tin cậy hơn nên cài gVisor hoặc Kata cho Docker.
- Image dựa trên Playwright 1.63 (bản mới nhất có image chính thức), worker dùng Playwright 1.64; hai bên độc lập.
