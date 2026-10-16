#!/usr/bin/env bash
# Khởi động OmniTest bằng Docker Compose trong Codespaces (chạy lại mỗi lần codespace khởi động).
# Lần đầu: sinh secret ngẫu nhiên vào .env.codespaces, tạo tài khoản quản trị và dự án demo,
# ghi thông tin đăng nhập vào omnitest-dang-nhap.txt ngay từ đầu (cả hai file đều không được commit).
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=.env.codespaces
LOGIN_FILE=omnitest-dang-nhap.txt
COMPOSE=(docker compose -f infra/docker/compose.yaml --env-file "$ENV_FILE")
ADMIN_EMAIL=admin@omnitest.local
DONE_MARK=.env.codespaces.done

rand() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }

for _ in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 2; done

if [ ! -f "$ENV_FILE" ]; then
  umask 077
  {
    echo "OMNITEST_MASTER_KEY=$(python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("="))')"
    echo "POSTGRES_PASSWORD=$(rand 24)"
    # Codespaces mở cổng qua HTTPS nên cookie phiên đặt cờ Secure (CI chạy qua http thì đặt false).
    echo "OMNITEST_COOKIE_SECURE=${OMNITEST_COOKIE_SECURE:-true}"
  } > "$ENV_FILE"
fi

# Sinh mật khẩu và ghi file đăng nhập trước khi build, để người dùng thấy file ngay.
write_login() {
  umask 077
  printf 'Đăng nhập OmniTest (%s)\n  Địa chỉ:  tab PORTS, cổng 8080 (OmniTest)\n  Email:    %s\n  Mật khẩu: %s\n' \
    "$1" "$ADMIN_EMAIL" "$PASSWORD" > "$LOGIN_FILE"
}
if [ -f "$LOGIN_FILE" ]; then
  PASSWORD=$(sed -n 's/^  Mật khẩu: //p' "$LOGIN_FILE")
fi
if [ -z "${PASSWORD:-}" ]; then
  PASSWORD="Omni-$(rand 12)-9a"
fi
[ -f "$DONE_MARK" ] || write_login "ĐANG KHỞI ĐỘNG, chờ dòng 'sẵn sàng' trong terminal rồi mới đăng nhập"

echo "Đang build và khởi động OmniTest (lần đầu mất vài phút)..."
"${COMPOSE[@]}" up -d --build

echo "Đang chờ API sẵn sàng..."
for _ in $(seq 1 120); do
  curl -fsS http://127.0.0.1:8080/api/health >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS http://127.0.0.1:8080/api/health >/dev/null

if [ ! -f "$DONE_MARK" ]; then
  # create-admin không đổi gì nếu email đã có (lần chạy trước bị ngắt giữa chừng).
  "${COMPOSE[@]}" exec -T -e OMNITEST_ADMIN_PASSWORD="$PASSWORD" api \
    omnitest-api create-admin --email "$ADMIN_EMAIL" --name "Quản trị Codespaces" || true
  "${COMPOSE[@]}" exec -T api omnitest-api seed-demo --owner-email "$ADMIN_EMAIL" --base-url http://demo:8100 || true
  touch "$DONE_MARK"
fi
write_login "sẵn sàng"

echo
echo "OmniTest đã sẵn sàng: mở tab PORTS, cổng 8080 (OmniTest)."
cat "$LOGIN_FILE"
