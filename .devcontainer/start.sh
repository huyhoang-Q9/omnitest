#!/usr/bin/env bash
# Khởi động OmniTest bằng Docker Compose trong Codespaces (chạy lại mỗi lần codespace khởi động).
# Lần đầu: sinh secret ngẫu nhiên vào .env.codespaces, tạo tài khoản quản trị và dự án demo,
# ghi thông tin đăng nhập vào omnitest-dang-nhap.txt ngay từ đầu (các file này đều không được commit).
#
# Phần build chạy nền và ghi log vào omnitest-khoi-dong.log: đóng terminal hay bấm Ctrl+C chỉ dừng việc
# theo dõi, không dừng build. Chạy lại lệnh khi đang có lần khác chạy thì chỉ theo dõi tiếp, không build trùng.
set -uo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=.env.codespaces
LOGIN_FILE=omnitest-dang-nhap.txt
LOG_FILE=omnitest-khoi-dong.log
LOCK_FILE=.env.codespaces.lock
RESULT_FILE=.env.codespaces.result
DONE_MARK=.env.codespaces.done
COMPOSE=(docker compose -f infra/docker/compose.yaml --env-file "$ENV_FILE")
ADMIN_EMAIL=admin@omnitest.local

# ---------- Phần chạy nền: build, khởi động, tạo tài khoản ----------
if [ "${1:-}" = "--run" ]; then
  exec 9>"$LOCK_FILE"
  flock -n 9 || { echo "Đã có lần khởi động khác đang chạy."; exit 0; }
  set -e
  STEP="chuẩn bị"
  rand() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }
  log() { echo "[$(date +%H:%M:%S)] $*"; }

  write_login() {
    umask 077
    printf 'Đăng nhập OmniTest (%s)\n  Địa chỉ:  tab PORTS, cổng 8080 (OmniTest)\n  Email:    %s\n  Mật khẩu: %s\n' \
      "$1" "$ADMIN_EMAIL" "$PASSWORD" > "$LOGIN_FILE"
  }

  on_error() {
    local code=$?
    trap - ERR
    set +e
    echo
    log "LỖI ở bước: $STEP (mã thoát $code)"
    if docker info >/dev/null 2>&1; then
      "${COMPOSE[@]}" ps -a
      log "Log gần nhất của các dịch vụ:"
      "${COMPOSE[@]}" logs --tail 30 --no-color api worker web 2>&1 | tail -n 90
    fi
    [ -n "${PASSWORD:-}" ] && write_login "LỖI ở bước '$STEP', xem omnitest-khoi-dong.log rồi chạy lại bash .devcontainer/start.sh"
    echo "$code" > "$RESULT_FILE"
    exit "$code"
  }
  trap on_error ERR

  # Mật khẩu sinh một lần, giữ nguyên qua các lần chạy lại.
  if [ -f "$LOGIN_FILE" ]; then PASSWORD=$(sed -n 's/^  Mật khẩu: //p' "$LOGIN_FILE"); fi
  [ -n "${PASSWORD:-}" ] || PASSWORD="Omni-$(rand 12)-9a"
  [ -f "$DONE_MARK" ] || write_login "ĐANG KHỞI ĐỘNG, chờ dòng 'sẵn sàng' rồi mới đăng nhập"

  STEP="chờ Docker sẵn sàng"
  log "Chờ Docker trong codespace sẵn sàng..."
  for i in $(seq 1 90); do
    docker info >/dev/null 2>&1 && break
    # Docker-in-docker đôi khi chưa tự chạy sau khi codespace khởi động lại: thử bật một lần.
    if [ "$i" = 15 ] && [ -x /usr/local/share/docker-init.sh ]; then
      log "Docker chưa chạy, đang bật lại..."
      (sudo -n /usr/local/share/docker-init.sh true >/dev/null 2>&1 &) || true
    fi
    sleep 2
  done
  docker info >/dev/null

  if [ ! -f "$ENV_FILE" ]; then
    umask 077
    {
      echo "OMNITEST_MASTER_KEY=$(python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("="))')"
      echo "POSTGRES_PASSWORD=$(rand 24)"
      # Codespaces mở cổng qua HTTPS nên cookie phiên đặt cờ Secure (CI chạy qua http thì đặt false).
      echo "OMNITEST_COOKIE_SECURE=${OMNITEST_COOKIE_SECURE:-true}"
    } > "$ENV_FILE"
  fi

  STEP="build image"
  log "Build image (lần đầu mất khoảng 5 đến 10 phút)..."
  # Build tuần tự từng image để máy 2 nhân, 8 GB không quá tải; mạng chập chờn thì thử lại một lần.
  for svc in api demo worker web; do
    log "Build $svc..."
    if ! "${COMPOSE[@]}" --progress plain build "$svc"; then
      log "Build $svc lỗi, thử lại..."
      "${COMPOSE[@]}" --progress plain build "$svc"
    fi
  done

  STEP="khởi động dịch vụ"
  log "Khởi động dịch vụ..."
  "${COMPOSE[@]}" up -d

  STEP="chờ API sẵn sàng"
  log "Chờ API sẵn sàng..."
  for _ in $(seq 1 150); do
    curl -fsS http://127.0.0.1:8080/api/health >/dev/null 2>&1 && break
    sleep 2
  done
  curl -fsS http://127.0.0.1:8080/api/health >/dev/null

  if [ ! -f "$DONE_MARK" ]; then
    STEP="tạo tài khoản quản trị và dự án demo"
    # create-admin không đổi gì nếu email đã có (lần chạy trước bị ngắt giữa chừng).
    "${COMPOSE[@]}" exec -T -e OMNITEST_ADMIN_PASSWORD="$PASSWORD" api \
      omnitest-api create-admin --email "$ADMIN_EMAIL" --name "Quản trị Codespaces" || true
    "${COMPOSE[@]}" exec -T api omnitest-api seed-demo --owner-email "$ADMIN_EMAIL" --base-url http://demo:8100 || true
    touch "$DONE_MARK"
  fi
  write_login "sẵn sàng"
  echo
  log "OmniTest đã sẵn sàng: mở tab PORTS, cổng 8080 (OmniTest)."
  cat "$LOGIN_FILE"
  echo 0 > "$RESULT_FILE"
  exit 0
fi

# ---------- Phần theo dõi: chạy nền phần trên và in log ra terminal ----------
if ! flock -n "$LOCK_FILE" true 2>/dev/null; then
  echo "Đang có lần khởi động khác chạy nền, tiếp tục theo dõi log (Ctrl+C chỉ dừng theo dõi)."
  RUNNER_PID=$(pgrep -f "start.sh --run" | head -n 1 || true)
else
  rm -f "$RESULT_FILE"
  : > "$LOG_FILE"
  nohup setsid bash "$0" --run >>"$LOG_FILE" 2>&1 </dev/null &
  RUNNER_PID=$!
  echo "Đang khởi động OmniTest chạy nền. Log đầy đủ: $LOG_FILE (Ctrl+C chỉ dừng theo dõi, không dừng build)."
fi

if [ -n "${RUNNER_PID:-}" ]; then
  tail -n +1 -f --pid="$RUNNER_PID" "$LOG_FILE"
  # setsid có thể tách thành tiến trình con mới: chờ đến khi có kết quả.
  for _ in $(seq 1 1800); do [ -f "$RESULT_FILE" ] && break; flock -n "$LOCK_FILE" true && break; sleep 1; done
fi
CODE=$(cat "$RESULT_FILE" 2>/dev/null || echo 1)
if [ "$CODE" != 0 ]; then
  echo
  echo "Khởi động chưa xong. Gửi 30 dòng cuối của $LOG_FILE cho đội phát triển:  tail -n 30 $LOG_FILE"
fi
exit "$CODE"
