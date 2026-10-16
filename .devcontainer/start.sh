#!/usr/bin/env bash
# Khởi động OmniTest bằng Docker Compose trong Codespaces (chạy lại mỗi lần codespace khởi động).
# Lần đầu: sinh secret ngẫu nhiên vào .env.codespaces, tạo tài khoản quản trị và dự án demo,
# ghi thông tin đăng nhập vào omnitest-dang-nhap.txt (cả hai file đều không được commit).
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=.env.codespaces
LOGIN_FILE=omnitest-dang-nhap.txt
COMPOSE=(docker compose -f infra/docker/compose.yaml --env-file "$ENV_FILE")
ADMIN_EMAIL=admin@omnitest.local

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

echo "Đang build và khởi động OmniTest (lần đầu mất vài phút)..."
"${COMPOSE[@]}" up -d --build

echo "Đang chờ API sẵn sàng..."
for _ in $(seq 1 120); do
  curl -fsS http://127.0.0.1:8080/api/health >/dev/null 2>&1 && break
  sleep 2
done
curl -fsS http://127.0.0.1:8080/api/health >/dev/null

if [ ! -f "$LOGIN_FILE" ]; then
  PASSWORD="Omni-$(rand 12)-9a"
  "${COMPOSE[@]}" exec -T -e OMNITEST_ADMIN_PASSWORD="$PASSWORD" api \
    omnitest-api create-admin --email "$ADMIN_EMAIL" --name "Quản trị Codespaces"
  "${COMPOSE[@]}" exec -T api omnitest-api seed-demo --owner-email "$ADMIN_EMAIL" --base-url http://demo:8100
  umask 077
  printf 'Đăng nhập OmniTest\n  Email:    %s\n  Mật khẩu: %s\n' "$ADMIN_EMAIL" "$PASSWORD" > "$LOGIN_FILE"
fi

echo
echo "OmniTest đã chạy: mở tab PORTS, cổng 8080 (OmniTest)."
cat "$LOGIN_FILE"
