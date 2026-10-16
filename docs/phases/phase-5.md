# Báo cáo Giai đoạn 5: Trợ lý AI (tùy chọn)

Ngày: 16/10/2026.

## 1. Mục tiêu

Lớp AI độc lập, tắt mặc định: đề xuất test case từ mô tả yêu cầu và phân tích lỗi của test không đạt. AI chỉ
đề xuất; người dùng duyệt mới lưu; AI không có đường ghi DB, không chạy lệnh, không chạy test.

## 2. Tiêu chí nghiệm thu và kết quả

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Tắt AI (mặc định) thì mọi chức năng khác hoạt động bình thường; giao diện ghi rõ "AI chưa được cấu hình" | Đạt | `test_ai_disabled_by_default`, E2E phase2 |
| 2 | Khóa API chỉ lấy từ cấu hình máy chủ, không trả về client, không có trong thông báo lỗi hay audit | Đạt | `test_errors_are_clear_and_never_contain_key`, `/api/ai/status` không có khóa |
| 3 | Dữ liệu dự án chỉ gửi đi khi Admin dự án bật AI; Manager không bật được | Đạt | `test_project_toggle_requires_project_admin`, `test_suggest_returns_drafts_without_saving` (không gửi request nào khi chưa bật) |
| 4 | Kết quả hiển thị giả định, mức không chắc chắn, lý do; đề xuất không hợp lệ được đánh dấu, không lưu được | Đạt | `test_invalid_definitions_are_flagged_not_dropped`, E2E `phase5.spec.ts` |
| 5 | Chỉ lưu sau khi người dùng duyệt; lưu qua API tạo test case thường, trạng thái Nháp, nhãn `ai` | Đạt | Đếm test case = 0 sau khi đề xuất; E2E lưu 1 test đã chọn |
| 6 | Phân tích lỗi: nguyên nhân, phân loại, độ tin cậy, căn cứ, gợi ý, giả định; dữ liệu gửi đi đã che secret | Đạt | `test_analyze_failure_sends_masked_context_only` kiểm tra nội dung request không có mật khẩu |
| 7 | Chống prompt injection ở mức thiết kế: dữ liệu người dùng đặt trong thẻ dữ liệu, kết quả chỉ là JSON được kiểm tra schema, không có công cụ nào cho AI | Đạt | `tasks.py`, test định dạng request |
| 8 | Phân quyền: đề xuất cần Manager; phân tích cần Tester; người ngoài 404 | Đạt | Test tích hợp |
| 9 | Audit ghi tác vụ, nhà cung cấp, mô hình, số token; không ghi nội dung | Đạt | Kiểm tra audit không chứa yêu cầu |
| 10 | Sinh script code nháp | **Không làm** | Script code chưa có sandbox (xem báo cáo GĐ4); AI chỉ sinh test dạng khai báo |
| 11 | Chất lượng đề xuất với mô hình thật | **Chưa kiểm chứng** | Môi trường không có khóa API; xem mục 5 |

## 3. File và module chính

- `ai/src/omnitest_ai/providers.py`: Anthropic (Messages API) và OpenAI-compatible (`/chat/completions`, dùng được
  với OpenAI, Ollama, vLLM, gateway nội bộ). Lỗi được dịch sang thông báo tiếng Việt an toàn.
- `ai/src/omnitest_ai/tasks.py`: prompt, trích JSON, kiểm tra schema, kiểm tra định nghĩa test bằng đúng schema của worker.
- `apps/api/.../routers/ai.py`: `GET /api/ai/status`, `POST /api/projects/{id}/ai/suggest-test-cases`,
  `POST /api/run-items/{id}/ai/analyze`. Migration `0003_phase5` thêm `projects.ai_enabled`.
- Web: trang **Trợ lý AI**, công tắc AI ở chi tiết dự án (Admin dự án), nút **Phân tích lỗi bằng AI** ở test không đạt.
- `tests/ai/fakes.py`, `tests/e2e/fake_llm.py`: **test double** của nhà cung cấp (nội dung viết sẵn, ghi rõ không phải AI thật).

## 4. Kết quả chạy test thực tế

```
uv run ruff format --check . && uv run ruff check .   -> sạch
uv run mypy (strict)                                  -> Success: no issues found in 58 source files
uv run pytest -q                                      -> 220 passed
alembic downgrade base / upgrade head / check         -> sạch
pnpm --filter @omnitest/web typecheck / lint / test   -> không lỗi / 2 cảnh báo cũ / 15 passed
npx playwright test (desktop + mobile)                -> 20 passed, 2 skipped (test "AI chưa cấu hình" tự bỏ qua
                                                         khi API chạy với test double; đã chạy đạt ở lượt không bật AI)
```

Các test AI dùng test double ở tầng HTTP (httpx.MockTransport, máy chủ giả lập cho E2E), nên kiểm tra được định
dạng request, xử lý phản hồi, lỗi, schema, phân quyền, audit và giao diện; **không** chứng minh chất lượng câu trả
lời của mô hình thật.

## 5. Tồn tại

- Chưa gọi thử nhà cung cấp thật. Khi có khóa, đặt `OMNITEST_AI_PROVIDER=anthropic`, `OMNITEST_AI_API_KEY`,
  `OMNITEST_AI_MODEL` rồi thử ở trang Trợ lý AI; tôi khuyến nghị đánh giá trên vài yêu cầu thật của dự án trước khi dùng rộng.
- Định nghĩa test do người dùng nhập thẳng giá trị nhạy cảm (không dùng biến secret) sẽ được gửi khi phân tích lỗi.
  Giao diện nhắc dùng biến; dữ liệu từ biến secret luôn được che.
- Chưa có hạn mức sử dụng AI theo người dùng/dự án; hiện dựa vào hạn mức của nhà cung cấp.
- Đề xuất Web dựa trên mô tả, AI không xem được trang thật nên selector có thể sai; vì vậy luôn lưu ở trạng thái Nháp.

## 6. Hướng dẫn dùng

1. Quản trị hệ thống cấu hình AI trên máy chủ (xem `.env.example`).
2. Admin dự án bật "Cho phép dùng Trợ lý AI trong dự án" ở trang chi tiết dự án.
3. Manager vào **Trợ lý AI**, nhập mô tả, chọn loại test, xem đề xuất, chọn và lưu (Nháp).
4. Tester mở test không đạt trong chi tiết lần chạy, bấm **Phân tích lỗi bằng AI**.
