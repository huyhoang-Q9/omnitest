# Chạy thử OmniTest trên GitHub Codespaces

Codespaces chạy toàn bộ OmniTest (giao diện, API, worker, PostgreSQL, Redis, ứng dụng demo) trong một máy ảo của
GitHub, mở bằng trình duyệt. Không cần cài gì trên máy.

## Mở

1. Trên trang repo GitHub, bấm nút **Open in GitHub Codespaces** ở README (hoặc **Code > Codespaces > Create
   codespace on main**).
2. Chờ script `.devcontainer/start.sh` chạy xong trong cửa sổ terminal. Lần đầu build image mất vài phút; các lần
   mở lại nhanh hơn.
3. Trình duyệt tự mở cổng **8080 (OmniTest)**. Nếu không, mở tab **PORTS** và bấm biểu tượng quả địa cầu ở cổng 8080.
4. Đăng nhập bằng thông tin trong file `omnitest-dang-nhap.txt` ở thư mục gốc (mật khẩu sinh ngẫu nhiên cho từng
   codespace, file không được commit).

## Thử kiểm thử

- Trang chủ là cổng kiểm thử. Bấm **Kiểm thử ngay**, chọn dự án **DEMO**, hệ thống **Demo**, chọn **Kiểm tra nhanh**
  và bấm **Bắt đầu kiểm thử**. Worker chạy thật trên ứng dụng demo; kết quả, ảnh chụp và log hiện trực tiếp.
- Muốn kiểm thử hệ thống của bạn: ở bước 1 bấm **Thêm hệ thống khác**, nhập URL công khai (VD `https://example.com`).
  Địa chỉ nội bộ bị chặn theo chính sách SSRF trừ khi Admin dự án cho phép.

## Lưu ý

- Cổng 8080 mặc định ở chế độ **Private**: chỉ tài khoản GitHub của bạn mở được. Không đổi sang Public nếu không cần.
- Sandbox script code và AI tắt mặc định trong Codespaces (xem `docs/sandbox.md`, phần AI trong README để bật).
- Codespaces tính vào hạn mức miễn phí hằng tháng của tài khoản GitHub. Dừng hoặc xóa codespace khi không dùng.
- Dữ liệu nằm trong codespace, mất khi xóa codespace.
