# Sandbox chạy script code (pytest/Playwright)

Trạng thái: **thử nghiệm**, tắt mặc định. Dành cho test khó diễn tả bằng bước khai báo. Script do **Admin dự án**
viết, chạy trong container Docker dùng một lần, không bao giờ chạy trong tiến trình API hay worker.

## Ai được làm gì

| Việc | Điều kiện |
|---|---|
| Bật sandbox trên máy chủ | Quản trị hệ thống đặt `OMNITEST_SANDBOX_ENABLED=true`, có Docker và image sandbox trên máy worker |
| Bật "cho phép script code" cho dự án | Admin dự án (ghi audit `project.update`) |
| Tạo, sửa, nhân bản, import test script | Admin dự án, và dự án đang bật script code |
| Chạy test script | Tester trở lên, luôn phải xác nhận; không tự thử lại |

Admin tắt script code thì các lần chạy đang chờ cũng bị chặn (worker đọc lại cờ lúc chạy). Thiếu bất kỳ điều kiện
nào, kết quả là **Bị chặn** kèm lý do, không bao giờ là Đạt.

## Cô lập (đã kiểm chứng bằng Docker thật, xem `tests/adapters/test_sandbox_adapter.py`)

- Người dùng uid 10001 không root, bỏ mọi Linux capability (`CapEff = 0`), `no-new-privileges`.
- Rootfs chỉ đọc; chỉ `/tmp` ghi được (tmpfs có hạn mức, mặc định 512 MB).
- Giới hạn RAM (không swap), CPU, số tiến trình, số file mở, thời gian (timeout của test case). Vượt RAM báo
  "vượt giới hạn bộ nhớ"; quá giờ, hủy, hoặc kết quả vượt hạn mức thì container bị dừng ngay.
- Không mount thư mục hay Docker socket của máy chủ. Code vào qua stdin, kết quả ra qua stdout (dạng tar), được
  đọc như dữ liệu không tin cậy: chỉ lấy file thường, giới hạn kích thước, XML đọc bằng defusedxml.
- Mạng:
  - `none` (mặc định): container không có card mạng nào.
  - `environment`: container vẫn không có card mạng; chỉ ra ngoài qua một container proxy riêng (nối bằng Unix
    socket trên volume tạm). Proxy áp đúng chính sách của môi trường: chỉ host được phép, mạng nội bộ cần Admin bật,
    luôn chặn metadata cloud, kiểm tra IP sau khi phân giải DNS. Kết nối bị chặn được lưu thành bằng chứng.
- Bằng chứng: chỉ ảnh PNG đúng chữ ký được hiển thị; mọi file khác lưu dạng tải về (`application/octet-stream`).
- Mỗi lần chạy dọn sạch container, proxy và volume (có nhãn `omnitest.sandbox=1`).

## Giới hạn cần biết

- **Script đọc được giá trị thật của secret** trong môi trường (qua `OMNITEST_VAR_*`). OmniTest che secret trong
  log, nhưng script cố tình biến đổi (VD mã hóa base64) thì không che được. Chỉ bật script code cho dự án mà Admin
  tin người viết script.
- **Worker cần quyền gọi Docker daemon**, tương đương quyền root trên máy đó. Khuyến nghị chạy worker có sandbox
  trên máy riêng (không chứa cơ sở dữ liệu hay dữ liệu khác), hoặc dùng Docker rootless.
- Cô lập dựa trên container Linux (namespaces, cgroups), không phải máy ảo. Với script không tin cậy hơn, nên
  thêm gVisor (`runsc`) hoặc Kata cho Docker trên máy worker.
- Các container chạy song song dùng chung kernel; giới hạn tài nguyên áp cho từng container.

## Cài đặt

```bash
docker build -f infra/docker/sandbox.Dockerfile -t omnitest-sandbox:latest .
# trên máy chạy worker:
export OMNITEST_SANDBOX_ENABLED=true   # và các giới hạn trong .env.example nếu cần
```

Dọn thủ công nếu worker bị dừng đột ngột:
`docker rm -f $(docker ps -aq --filter label=omnitest.sandbox=1); docker volume rm $(docker volume ls -q --filter label=omnitest.sandbox=1)`

## Viết script

- Tên file phẳng, đuôi .py .json .csv .txt .yaml .yml; cần ít nhất một `test_*.py`; tối đa 20 file, 256 KB.
- Có sẵn: pytest, httpx, Playwright (Chromium, Firefox, WebKit) và pytest-playwright (fixture `page`, `base_url`).
- Biến: `OMNITEST_BASE_URL`, `OMNITEST_VAR_<TÊN_BIẾN>`; ghi file vào `OMNITEST_ARTIFACTS_DIR` để giữ làm bằng chứng.
- Mỗi hàm test là một bước trong kết quả; log đầy đủ ở `pytest-output.txt`.
