# Chạy thử OmniTest trên GitHub Codespaces

Codespaces chạy toàn bộ OmniTest (giao diện, API, worker, PostgreSQL, Redis, ứng dụng demo) trong một máy ảo của
GitHub, mở bằng trình duyệt. Không cần cài gì trên máy.

## Mở

1. Trên trang repo GitHub, bấm nút **Open in GitHub Codespaces** ở README (hoặc **Code > Codespaces > Create
   codespace on main**).
2. Script `.devcontainer/start.sh` tự chạy khi codespace khởi động. Lần đầu build image mất vài phút; các lần mở
   lại nhanh hơn.
3. Mở file `omnitest-dang-nhap.txt` ở thư mục gốc (khung Explorer bên trái) để lấy Email và Mật khẩu. File có ngay từ
   đầu; chỉ đăng nhập khi dòng đầu file ghi **sẵn sàng**. Mật khẩu sinh ngẫu nhiên cho từng codespace, file không
   được commit.
4. Mở tab **PORTS**, bấm biểu tượng quả địa cầu ở cổng **8080 (OmniTest)** và đăng nhập.

Không thấy file hoặc file vẫn ghi "ĐANG KHỞI ĐỘNG" quá lâu: mở Terminal (☰ > Terminal > New Terminal) và chạy

```bash
bash .devcontainer/start.sh
```

Lệnh chạy lại nhiều lần vẫn an toàn và in Email, Mật khẩu ở cuối.

## Khi lệnh khởi động dừng giữa chừng

- Build chạy nền và ghi log vào `omnitest-khoi-dong.log`. Đóng terminal hoặc bấm Ctrl+C chỉ dừng phần theo dõi,
  build vẫn chạy tiếp. Xem lại tiến trình bằng `tail -f omnitest-khoi-dong.log`.
- Nếu có lỗi, script in rõ **LỖI ở bước: ...** cùng trạng thái và log các dịch vụ, đồng thời ghi lỗi vào dòng đầu
  `omnitest-dang-nhap.txt`. Chạy lại `bash .devcontainer/start.sh` (lỗi mạng tạm thời thường tự hết khi chạy lại).
- Codespace tạo trước ngày 16/10/2026 dùng script cũ: chạy `git pull` rồi chạy lại lệnh trên.
- Vẫn lỗi: gửi kết quả của `tail -n 30 omnitest-khoi-dong.log` cho đội phát triển.

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
