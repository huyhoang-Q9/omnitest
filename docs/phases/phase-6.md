# Báo cáo Giai đoạn 6: Adapter Desktop/Mobile qua Appium (thử nghiệm)

Ngày: 16/10/2026.

## 1. Mục tiêu

Chạy được test Desktop (macOS, Windows) và Mobile (Android, iOS) theo cùng mô hình khai báo như Web, thông qua
Appium server do đội dự án tự vận hành. Không giả lập kết quả: thiếu Appium, driver hoặc thiết bị thì báo **Bị chặn**.

## 2. Tiêu chí nghiệm thu và kết quả

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Định nghĩa test Desktop/Mobile có cấu trúc: capability, bước (chạm, nhập, xóa, kiểm tra hiển thị/ẩn/nội dung, chụp màn hình, quay lại), locator 8 kiểu | Đạt | `AppTestDefinition` trong `core/definitions.py`, `test_step_validation` |
| 2 | Test cũ chỉ có ghi chú vẫn hợp lệ; không có bước thì kết quả Bị chặn (`no_steps`), không báo đạt | Đạt | `test_no_steps_is_blocked`, `tests/integration/test_runs.py` |
| 3 | Không kết nối được Appium, Appium thiếu driver hoặc không tạo được phiên: Bị chặn, có lý do rõ | Đạt | `test_unreachable_server_is_blocked_not_passed`, `test_real_appium_missing_driver_is_blocked` |
| 4 | Chạy thật qua giao thức W3C WebDriver: đạt khi đúng, không đạt khi thiếu phần tử hoặc sai nội dung, có ảnh chụp khi lỗi | Đạt với driver fake | `test_real_appium_flow_passes_and_masks_secret`, `..._missing_element_fails_with_screenshot`, `..._wrong_text_fails` |
| 5 | Bảo mật: Appium URL đi qua chính sách chặn SSRF (mạng nội bộ cần Admin bật); capability theo danh sách cho phép; `app` không được là URL; secret được che trong log bước | Đạt | `test_server_on_private_network_needs_opt_in`, `test_dangerous_capabilities_rejected`, test che secret |
| 6 | Worker không thử lại lỗi hạ tầng (`no_steps`, `appium_unavailable`, `appium_session`) | Đạt | `NO_RETRY_ERRORS` trong executor |
| 7 | Giao diện soạn bước Desktop/Mobile, chế độ JSON, ghi rõ "thử nghiệm" và điều kiện chạy | Đạt | E2E `phase3.spec.ts` (desktop và mobile, không tràn ngang) |
| 8 | Chạy trên thiết bị Android/iOS thật, máy Mac (Mac2) hoặc Windows (WinAppDriver/NovaWindows) thật | **Chưa kiểm chứng** | Môi trường cloud không có thiết bị và máy đó; xem mục 5 |

## 3. File và module chính

- `adapters/src/omnitest_adapters/appium/adapter.py`: `AppiumAdapter`, gọi Appium bằng HTTP (httpx) qua transport
  có kiểm tra SSRF. Ánh xạ loại test: Android UiAutomator2, iOS XCUITest, macOS Mac2, Windows driver "Windows".
- `desktop_macos`, `desktop_windows`, `mobile_appium`: dùng chung `AppiumAdapter`, trạng thái `experimental`.
- `core/definitions.py`: `AppTestDefinition`, `AppStep`, `AppLocator`, `ALLOWED_CAPABILITIES`.
- Web: `features/steps-editor.tsx` (trình soạn bước và capability), gợi ý Base URL = Appium server ở form môi trường,
  nhãn "Thử nghiệm (Appium)" / "Chưa có bước tự động" ở danh sách test case.
- CI: cài Appium 3.8.0 và `@appium/fake-driver` 6.2.4 để chạy test giao thức thật.

## 4. Kết quả chạy test thực tế

```
uv run ruff format --check . && uv run ruff check .   -> sạch
uv run mypy (strict)                                  -> Success: no issues found in 60 source files
uv run pytest -q (có Appium + fake driver)            -> 231 passed
pnpm --filter @omnitest/web typecheck / lint / test   -> không lỗi / 2 cảnh báo cũ / 15 passed
vite build                                            -> thành công
npx playwright test (desktop + mobile)                -> 20 passed, 2 skipped (test "AI chưa cấu hình" tự bỏ qua
                                                         khi API chạy với test double AI)
```

Test Appium dùng **Appium server thật** với **driver fake chính thức** của Appium (ứng dụng mô tả bằng XML). Cách
này kiểm chứng được giao thức W3C, tạo/đóng phiên, tìm phần tử, nhập, kiểm tra, ảnh chụp và xử lý lỗi; **không**
chứng minh adapter chạy ổn trên từng driver thật (UiAutomator2, XCUITest, Mac2, Windows).

## 5. Tồn tại

- Chưa chạy với thiết bị hoặc máy thật. Trước khi dùng rộng, cần thử mỗi nền tảng một test đơn giản trên Appium
  server của dự án và ghi nhận khác biệt (VD locator, thời gian khởi động ứng dụng).
- Chưa có hàng đợi/khóa thiết bị: nhiều lần chạy cùng một thiết bị có thể tranh nhau; hiện dựa vào Appium
  (`udid`) và cấu hình đồng thời của worker.
- Chưa hỗ trợ cử chỉ (vuốt, kéo), cuộn tới phần tử, chuyển ngữ cảnh WebView; định nghĩa chưa có bước tùy ý.
- File ứng dụng (`app`) phải có sẵn trên máy chạy Appium; OmniTest không tải hay phân phối file cài đặt.

## 6. Hướng dẫn dùng

1. Dựng Appium server (VD `appium --address 0.0.0.0 --port 4723`) trên máy có thiết bị/giả lập, cài driver phù hợp
   (`appium driver install uiautomator2`, `xcuitest`, `mac2`...).
2. Tạo môi trường với Base URL là địa chỉ Appium server. Nếu Appium ở mạng nội bộ, Admin dự án bật cho phép mạng nội bộ.
3. Tạo test case loại Desktop/Mobile, khai capability (VD `appPackage`, `appActivity`, `udid` hoặc `bundleId`), soạn bước.
4. Chạy như test thường; kết quả, log bước và ảnh chụp có ở trang chi tiết lần chạy.
