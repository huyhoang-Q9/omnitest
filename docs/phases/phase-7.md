# Báo cáo Giai đoạn 7: Tối ưu, CI/CD, chạy thử Docker Compose

Ngày: 16/10/2026. Commit: `6234ef5`, `1bd3c38` trên `main` và `dev`.

## 1. Mục tiêu

Đưa MVP về trạng thái bàn giao được: giao diện tải nhanh hơn, image Docker build được, stack Docker Compose đầy đủ
(kể cả sandbox script code) được chạy thử tự động trên CI mỗi lần push, tài liệu cập nhật.

## 2. Tiêu chí nghiệm thu và kết quả

| # | Tiêu chí | Kết quả | Bằng chứng |
|---|---|---|---|
| 1 | Giao diện tải theo nhu cầu: mỗi trang là một chunk riêng, thư viện biểu đồ tách khỏi chunk chính | Đạt | `App.tsx` dùng `lazy()`; chunk chính từ khoảng 1,1 MB còn 471 KB, biểu đồ 369 KB tải khi mở trang có biểu đồ |
| 2 | Image `web` build được bằng `pnpm install --frozen-lockfile` | Đạt (đã sửa lỗi thật) | `web.Dockerfile` thiếu `package.json` gốc nên lockfile không khớp; sửa và build thử thành công |
| 3 | `docker compose up` khởi động đủ postgres, redis, api, worker, demo, web; health qua nginx | Đạt | Job CI `compose` (run 38859402915) |
| 4 | Luồng thật qua nginx: tạo quản trị, tạo dự án demo, chạy suite Smoke (API + Web bằng Chromium trong container worker) | Đạt | CI: `DEMO-TC-0001=passed, DEMO-TC-0002=passed, DEMO-TC-0003=passed, DEMO-TC-0005=passed` |
| 5 | Worker trong Compose gọi được sandbox: script pytest chạy trong container cô lập, không mạng, không root | Đạt | CI: `OK script pytest chạy trong sandbox từ worker container` (script tự kiểm tra không kết nối được 1.1.1.1 và uid khác 0) |
| 6 | CI chạy lint, type check, toàn bộ pytest (gồm Docker sandbox và Appium fake driver), build web, kiểm contract OpenAPI | Đạt | Job `backend`: `263 passed`, 0 skip; job `frontend` xanh |
| 7 | Không có secret trong CI: file env sinh ngẫu nhiên mỗi lần chạy, xóa cùng volume sau khi chạy | Đạt | Bước "Tạo file env tạm" và `down -v` luôn chạy trong `ci.yml` |
| 8 | Hỗ trợ mạng doanh nghiệp có proxy TLS: build image với chứng chỉ CA bổ sung, không lưu vào image | Đạt | `--secret id=extra_ca,...` trong `api.Dockerfile`, `web.Dockerfile`, `sandbox.Dockerfile` |

## 3. File thay đổi chính

- `apps/web/src/App.tsx`, `components/app-layout.tsx`: route tải theo nhu cầu, Suspense; xóa `ComingSoonPage.tsx` không còn dùng.
- `infra/docker/web.Dockerfile`: copy `package.json` gốc; CA bổ sung tùy chọn.
- `infra/docker/api.Dockerfile`: CA bổ sung tùy chọn; target mới `worker-sandbox` (thêm Docker CLI, chỉ client).
- `infra/docker/compose.yaml`: tmpfs HOME của worker thuộc user 10001 (lỗi thật phát hiện nhờ CI: asyncpg không
  đọc được `~/.postgresql` nên worker không kết nối được DB, mọi lần chạy kẹt ở "Đang chờ").
- `infra/docker/compose.sandbox.yaml`: lớp phủ bật sandbox cho worker (mount Docker socket, `group_add` DOCKER_GID).
- `infra/scripts/compose_smoke.py`: smoke test chỉ dùng thư viện chuẩn, đi qua nginx như người dùng thật.
- `.github/workflows/ci.yml`: action phiên bản mới (checkout v5, setup-node v5, setup-uv v7), job `compose`.

## 4. Kết quả chạy test thực tế

CI GitHub Actions, run 38859402915 (main, commit `1bd3c38`), cả 3 job xanh:

```
backend : ruff format/check sạch, mypy sạch, build image sandbox, pytest -> 263 passed in 84.40s; OpenAPI không lệch
frontend: lint, typecheck, vitest, vite build -> thành công
compose : OK  API và web sẵn sàng qua nginx
          OK  tạo quản trị, dự án demo
          OK  suite Smoke qua worker: DEMO-TC-0001=passed, DEMO-TC-0002=passed, DEMO-TC-0003=passed, DEMO-TC-0005=passed
          OK  script pytest chạy trong sandbox từ worker container
```

Trên môi trường cloud phát triển (trước commit `6234ef5`): pytest 263 passed, vitest 16 passed, E2E Playwright
22 passed, 2 skipped (2 test "AI chưa cấu hình" tự bỏ qua khi API chạy với test double AI).

Lần chạy CI đầu của GĐ7 (commit `6234ef5`) **đỏ** ở 2 job: `setup-node@v5` tự bật cache pnpm ở job không cài pnpm,
và lỗi quyền HOME của worker nói trên. Cả hai đã sửa ở `1bd3c38`, không bỏ qua bước nào.

## 5. Tồn tại

- Image `worker` không build được trên môi trường cloud phát triển (apt bị chặn); chỉ được kiểm chứng trên CI.
- E2E giao diện chưa chạy trên CI (chạy trên môi trường phát triển); có thể thêm job E2E chạy trên stack Compose.
- Chưa có pipeline phát hành (đẩy image lên registry, gắn tag phiên bản) và chưa triển khai lên máy chủ thật.
- `npm i appium@3.8.0` trên CI báo 6 lỗ hổng "critical" trong cây phụ thuộc của Appium; chỉ dùng trong CI để kiểm
  giao thức, không có trong image phát hành. Cần xem lại khi triển khai Appium server thật.
- Worker có quyền Docker khi bật sandbox (tương đương root trên máy đó); khuyến nghị máy worker riêng, Docker
  rootless hoặc gVisor (docs/sandbox.md).

## 6. Hướng dẫn chạy

```bash
cp .env.example .env              # điền OMNITEST_MASTER_KEY, POSTGRES_PASSWORD
docker compose -f infra/docker/compose.yaml --env-file .env up -d --build
# Bật sandbox script code (đọc docs/sandbox.md trước):
docker build -f infra/docker/sandbox.Dockerfile -t omnitest-sandbox:latest .
echo "DOCKER_GID=$(stat -c %g /var/run/docker.sock)" >> .env
docker compose -f infra/docker/compose.yaml -f infra/docker/compose.sandbox.yaml --env-file .env up -d --build
# Kiểm tra khói:
python3 infra/scripts/compose_smoke.py -f infra/docker/compose.yaml -f infra/docker/compose.sandbox.yaml \
    --env-file .env --sandbox
```
