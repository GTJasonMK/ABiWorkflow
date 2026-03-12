#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
ENV_EXAMPLE="$ROOT_DIR/.env.example"
ENV_FILE="$ROOT_DIR/.env"
BACKEND_VENV_NAME="${ABI_BACKEND_VENV_NAME:-.venv-linux}"
BACKEND_VENV_DIR="$BACKEND_DIR/$BACKEND_VENV_NAME"

echo "============================================================"
echo " AbiWorkflow - Dependency Installer (Linux/WSL)"
echo "============================================================"
echo

require_command() {
  local command_name="$1"
  local install_hint="$2"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "[ERROR] \"$command_name\" is not installed or not in PATH."
    echo "[ERROR] $install_hint"
    exit 1
  fi
}

require_command uv "Install uv first: https://docs.astral.sh/uv/"
require_command node "Install Node.js first: https://nodejs.org/"
require_command npm "npm is bundled with Node.js. Install Node.js first."

echo "[OK] uv found"
echo "[OK] node found"
echo "[OK] npm found"
echo

echo "[1/3] Installing backend dependencies ..."
if [[ ! -f "$BACKEND_DIR/pyproject.toml" ]]; then
  echo "[ERROR] backend/pyproject.toml not found. Is the repo intact?"
  exit 1
fi

pushd "$BACKEND_DIR" >/dev/null
export UV_PROJECT_ENVIRONMENT="$BACKEND_VENV_NAME"
if [[ -x "$BACKEND_VENV_DIR/bin/python" ]]; then
  :
else
  if [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then
    echo "[WARN] Detected legacy Linux/WSL virtual environment at backend/.venv"
    echo "[WARN] New Linux/WSL installs use backend/$BACKEND_VENV_NAME to avoid Windows conflicts."
  fi
  if [[ -x "$BACKEND_DIR/.venv-win/Scripts/python.exe" ]] || [[ -x "$BACKEND_DIR/.venv/Scripts/python.exe" ]]; then
    echo "[WARN] Detected Windows virtual environment in backend/"
    echo "[WARN] Linux/WSL install will ignore it and create backend/$BACKEND_VENV_NAME"
  fi

  echo "[INFO] Creating virtual environment ..."
  uv venv "$BACKEND_VENV_NAME"
  echo "[OK] Virtual environment created at backend/$BACKEND_VENV_NAME"
fi

echo "[INFO] Installing Python dependencies ..."
uv sync --extra dev
popd >/dev/null
echo "[OK] Backend dependencies installed."
echo

echo "[2/3] Installing frontend dependencies ..."
if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
  echo "[ERROR] frontend/package.json not found. Is the repo intact?"
  exit 1
fi

pushd "$FRONTEND_DIR" >/dev/null
npm install
popd >/dev/null
echo "[OK] Frontend dependencies installed."
echo

echo "[3/3] Checking .env file ..."
if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$ENV_EXAMPLE" ]]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo "[OK] Created .env from .env.example"
    echo "     Please edit .env and fill in your API keys."
  else
    echo "[WARN] No .env.example found. Skipping .env creation."
  fi
else
  echo "[OK] .env already exists."
fi
echo

echo "============================================================"
echo " All dependencies installed successfully!"
echo "============================================================"
echo
echo " Next steps:"
echo "   1. Edit .env with your API keys"
echo "   2. Start Redis: docker compose up -d"
echo "   3. Run the app: ./run.sh"
echo
