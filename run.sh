#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
ENV_FILE="$ROOT_DIR/.env"
LOG_DIR="$BACKEND_DIR/outputs/logs"
BACKEND_VENV_NAME="${ABI_BACKEND_VENV_NAME:-.venv-linux}"
BACKEND_VENV_DIR="$BACKEND_DIR/$BACKEND_VENV_NAME"
BACKEND_PYTHON="$BACKEND_VENV_DIR/bin/python"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
ENABLE_CELERY_WORKER="${ENABLE_CELERY_WORKER:-0}"
RUN_MODE="${RUN_MODE:-web}"
MAX_PORT_SCAN=20

case "${1:-}" in
  web)
    RUN_MODE="web"
    ;;
  desktop|gui)
    RUN_MODE="desktop"
    ;;
  "")
    ;;
  *)
    echo "[ERROR] Unsupported mode: $1"
    echo "[ERROR] Usage: ./run.sh [web|desktop]"
    exit 1
    ;;
esac

BACKEND_PID=""
CELERY_PID=""
BACKEND_PID_FILE="$LOG_DIR/backend.pid"
CELERY_PID_FILE="$LOG_DIR/celery.pid"
CLEANUP_DONE=0

print_header() {
  echo "============================================================"
  echo " AbiWorkflow - Development Server Launcher (Linux/WSL)"
  echo "============================================================"
  echo
  echo "[INFO] UI mode: $RUN_MODE"
  echo
}

cleanup() {
  if [[ "$CLEANUP_DONE" -eq 1 ]]; then
    return
  fi
  CLEANUP_DONE=1

  echo
  echo "[INFO] Frontend stopped. Cleaning background services ..."

  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi

  if [[ "$ENABLE_CELERY_WORKER" == "1" ]] && [[ -n "$CELERY_PID" ]] && kill -0 "$CELERY_PID" >/dev/null 2>&1; then
    kill "$CELERY_PID" >/dev/null 2>&1 || true
    wait "$CELERY_PID" 2>/dev/null || true
  fi

  rm -f "$BACKEND_PID_FILE" "$CELERY_PID_FILE"
}

trap cleanup EXIT INT TERM

require_command() {
  local command_name="$1"
  local install_hint="$2"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "[ERROR] \"$command_name\" is not installed or not in PATH."
    echo "[ERROR] $install_hint"
    exit 1
  fi
}

ensure_backend_venv() {
  if [[ ! -f "$BACKEND_DIR/pyproject.toml" ]]; then
    echo "[ERROR] backend/pyproject.toml not found."
    exit 1
  fi
  if [[ -x "$BACKEND_PYTHON" ]]; then
    return
  fi
  if [[ -x "$BACKEND_DIR/.venv-win/Scripts/python.exe" ]] || [[ -x "$BACKEND_DIR/.venv/Scripts/python.exe" ]]; then
    echo "[WARN] Detected Windows virtual environment under backend/"
    echo "[WARN] Linux/WSL launcher will ignore it and use backend/$BACKEND_VENV_NAME"
  fi
  if [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then
    echo "[ERROR] Detected legacy Linux/WSL virtual environment in backend/.venv"
    echo "[ERROR] Linux/WSL scripts now use backend/$BACKEND_VENV_NAME to avoid Windows conflicts."
    echo "[ERROR] Please run ./install.sh once to create backend/$BACKEND_VENV_NAME"
    exit 1
  fi
  echo "[ERROR] Backend virtual environment not found: backend/$BACKEND_VENV_NAME"
  echo "[ERROR] Run: ./install.sh"
  exit 1
}

ensure_frontend_deps() {
  if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
    echo "[ERROR] frontend/package.json not found."
    exit 1
  fi
  if [[ ! -f "$FRONTEND_DIR/node_modules/vite/package.json" ]]; then
    echo "[ERROR] Frontend dependencies not found."
    echo "[ERROR] Run: cd frontend && npm install"
    exit 1
  fi
}

find_free_port() {
  local start_port="$1"
  local current_port="$start_port"
  local tries=0

  while (( tries < MAX_PORT_SCAN )); do
    if "$BACKEND_PYTHON" - "$current_port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    sock.bind(("127.0.0.1", port))
except OSError:
    sys.exit(1)
finally:
    sock.close()
sys.exit(0)
PY
    then
      printf '%s\n' "$current_port"
      return 0
    fi

    echo "[INFO] Port $current_port is in use, trying next ..." >&2
    current_port=$((current_port + 1))
    tries=$((tries + 1))
  done

  return 1
}

check_url_status() {
  local url="$1"
  local expected_status="$2"
  "$BACKEND_PYTHON" - "$url" "$expected_status" <<'PY'
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
expected_status = int(sys.argv[2])
try:
    with urllib.request.urlopen(url, timeout=3) as response:
        sys.exit(0 if response.status == expected_status else 1)
except (urllib.error.URLError, TimeoutError):
    sys.exit(1)
PY
}

check_openapi_paths() {
  local openapi_url="$1"
  shift
  "$BACKEND_PYTHON" - "$openapi_url" "$@" <<'PY'
import json
import sys
import urllib.request

url = sys.argv[1]
required_paths = set(sys.argv[2:])
try:
    with urllib.request.urlopen(url, timeout=3) as response:
        payload = json.load(response)
except Exception:
    sys.exit(1)

paths = set((payload.get("paths") or {}).keys())
missing = required_paths - paths
sys.exit(0 if not missing else 1)
PY
}

start_redis_if_possible() {
  echo "[INFO] Checking Redis connectivity ..."
  if ! command -v docker >/dev/null 2>&1; then
    echo "[WARN] Docker not found. Redis/Celery features require Redis."
    echo "[WARN] Install Docker or start Redis manually."
    echo
    return
  fi

  if docker compose -f "$ROOT_DIR/docker-compose.yml" ps --status running 2>/dev/null | grep -q "redis"; then
    echo "[OK] Redis is already running."
    echo
    return
  fi

  echo "[INFO] Redis container not running. Starting via docker compose ..."
  if docker compose -f "$ROOT_DIR/docker-compose.yml" up -d; then
    echo "[OK] Redis started."
  else
    echo "[WARN] Failed to start Redis. Celery tasks will not work."
    echo "[WARN] Start manually: docker compose up -d"
  fi
  echo
}

print_header
require_command node "Install Node.js first: https://nodejs.org/"
require_command npm "npm is bundled with Node.js. Install Node.js first."
ensure_backend_venv
ensure_frontend_deps

if [[ "$RUN_MODE" == "desktop" ]] && [[ ! -f "$FRONTEND_DIR/node_modules/electron/package.json" ]]; then
  echo "[ERROR] Electron dependencies not found."
  echo "[ERROR] Run: cd frontend && npm install"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[WARN] .env not found. Using default config. Run ./install.sh to create it."
fi

mkdir -p "$LOG_DIR"
rm -f "$BACKEND_PID_FILE" "$CELERY_PID_FILE"

BE_PORT="$(find_free_port "$BACKEND_PORT")" || {
  echo "[ERROR] Cannot find a free backend port after $MAX_PORT_SCAN attempts."
  exit 1
}
echo "[OK] Backend port: $BE_PORT"

FE_PORT="$(find_free_port "$FRONTEND_PORT")" || {
  echo "[ERROR] Cannot find a free frontend port after $MAX_PORT_SCAN attempts."
  exit 1
}
echo "[OK] Frontend port: $FE_PORT"
echo

start_redis_if_possible

echo "[INFO] Starting backend on port $BE_PORT ..."
(
  cd "$BACKEND_DIR"
  exec "$BACKEND_PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$BE_PORT" --log-level info
) &
BACKEND_PID=$!
printf '%s\n' "$BACKEND_PID" >"$BACKEND_PID_FILE"
echo "[INFO] Backend PID: $BACKEND_PID"

for (( retry = 1; retry <= 20; retry++ )); do
  if check_url_status "http://127.0.0.1:$BE_PORT/api/health" 200; then
    echo "[OK] Backend health check passed."
    break
  fi

  if (( retry == 20 )); then
    echo "[ERROR] Backend did not become ready on http://127.0.0.1:$BE_PORT/api/health"
    echo "[ERROR] Please check backend startup logs above."
    exit 1
  fi
  sleep 1
done

echo "[INFO] Verifying API route /api/projects ..."
if ! check_url_status "http://127.0.0.1:$BE_PORT/api/projects?page=1&page_size=1" 200; then
  echo "[ERROR] API route check failed: GET /api/projects returned non-200."
  exit 1
fi
echo "[OK] API route check passed."

echo "[INFO] Verifying new API routes (/api/system/runtime, /api/projects/{project_id}/assets) ..."
if ! check_openapi_paths "http://127.0.0.1:$BE_PORT/openapi.json" "/api/system/runtime" "/api/projects/{project_id}/assets"; then
  echo "[ERROR] New API routes are missing from current backend process."
  echo "[ERROR] Required routes:"
  echo "[ERROR]   - /api/system/runtime"
  echo "[ERROR]   - /api/projects/{project_id}/assets"
  exit 1
fi
echo "[OK] New API routes are available."
export VITE_PROBE_OPTIONAL_ENDPOINTS=true
echo "[INFO] Optional endpoint probe enabled for frontend (VITE_PROBE_OPTIONAL_ENDPOINTS=true)."
echo

if [[ "$ENABLE_CELERY_WORKER" == "1" ]]; then
  echo "[INFO] Starting Celery worker ..."
  (
    cd "$BACKEND_DIR"
    exec "$BACKEND_PYTHON" -m celery -A app.tasks.celery_app worker -P solo -l info
  ) &
  CELERY_PID=$!
  printf '%s\n' "$CELERY_PID" >"$CELERY_PID_FILE"
  echo "[INFO] Celery PID: $CELERY_PID"
fi

if [[ "$RUN_MODE" == "desktop" ]]; then
  echo "[INFO] Starting Electron desktop GUI ..."
  export ELECTRON_RENDERER_PORT="$FE_PORT"
  export VITE_BACKEND_HOST=127.0.0.1
  export VITE_BACKEND_PORT="$BE_PORT"
  export ELECTRON_API_BASE_URL=/api
  export ELECTRON_WS_BASE_URL=/ws

  echo
  echo "============================================================"
  echo " Services starting:"
  echo "   Backend:  http://127.0.0.1:$BE_PORT"
  echo "   Desktop:  Electron GUI"
  echo "   Swagger:  http://127.0.0.1:$BE_PORT/docs"
  echo "============================================================"
  echo
  echo " Close Electron window or press Ctrl+C to stop all services."
  echo

  pushd "$FRONTEND_DIR" >/dev/null
  set +e
  npm run desktop:dev
  FRONTEND_EXIT=$?
  set -e
  popd >/dev/null
else
  echo "[INFO] Starting frontend on port $FE_PORT ..."
  export VITE_BACKEND_HOST=127.0.0.1
  export VITE_BACKEND_PORT="$BE_PORT"

  echo
  echo "============================================================"
  echo " Servers starting:"
  echo "   Backend:  http://127.0.0.1:$BE_PORT"
  echo "   Frontend: http://127.0.0.1:$FE_PORT"
  echo "   Swagger:  http://127.0.0.1:$BE_PORT/docs"
  echo "============================================================"
  echo
  echo " Press Ctrl+C to stop frontend. Backend/Celery will be cleaned up automatically."
  echo

  pushd "$FRONTEND_DIR" >/dev/null
  set +e
  npx vite --port "$FE_PORT" --host 127.0.0.1
  FRONTEND_EXIT=$?
  set -e
  popd >/dev/null
fi

exit "${FRONTEND_EXIT:-0}"
