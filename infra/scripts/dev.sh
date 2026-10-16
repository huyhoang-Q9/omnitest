#!/usr/bin/env bash
# Chạy môi trường phát triển không cần Docker: API (uvicorn) + web (Vite).
# Yêu cầu: PostgreSQL và Redis đang chạy, file .env ở thư mục gốc (xem .env.example).
#   infra/scripts/dev.sh start | stop | status
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN="$ROOT/.run"
mkdir -p "$RUN"

start() {
  [[ -f "$ROOT/.env" ]] || { echo "Thiếu $ROOT/.env (sao chép từ .env.example)"; exit 1; }
  set -a; . "$ROOT/.env"; set +a
  (cd "$ROOT/apps/api" && uv run alembic upgrade head)
  (cd "$ROOT" || exit 1; setsid nohup uv run uvicorn omnitest_api.main:app --host 127.0.0.1 --port 8000 </dev/null >"$RUN/api.log" 2>&1 & echo $! >"$RUN/api.pid")
  (cd "$ROOT/apps/web" || exit 1; setsid nohup pnpm dev --host 127.0.0.1 </dev/null >"$RUN/web.log" 2>&1 & echo $! >"$RUN/web.pid")
  for _ in $(seq 1 30); do curl -sf http://127.0.0.1:8000/api/health >/dev/null && break; sleep 1; done
  echo "API: http://127.0.0.1:8000/api/docs  Web: http://127.0.0.1:5173  Log: $RUN"
}

stop() {
  for svc in api web; do
    if [[ -f "$RUN/$svc.pid" ]]; then
      pid="$(cat "$RUN/$svc.pid")"
      # Mỗi dịch vụ chạy trong process group riêng (setsid): dừng cả nhóm (uv -> uvicorn, pnpm -> vite).
      kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
      rm -f "$RUN/$svc.pid"
    fi
  done
  echo "Đã dừng."
}

status() {
  curl -sf http://127.0.0.1:8000/api/health && echo " API ok" || echo "API không chạy"
  curl -sf -o /dev/null http://127.0.0.1:5173 && echo "Web ok" || echo "Web không chạy"
}

case "${1:-}" in start) start ;; stop) stop ;; status) status ;; *) echo "Dùng: $0 start|stop|status"; exit 1 ;; esac
