#!/usr/bin/env bash

set -u -o pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_VENV_NAME="${ABI_BACKEND_VENV_NAME:-.venv-linux}"
BACKEND_VENV_DIR="$BACKEND_DIR/$BACKEND_VENV_NAME"
PYTEST_ARGS=("$@")
TOTAL_FAIL=0

if [[ "${#PYTEST_ARGS[@]}" -eq 0 ]]; then
  PYTEST_ARGS=(-v)
fi

run_with_timeout() {
  local seconds="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$seconds" "$@"
  else
    "$@"
  fi
}

echo "============================================================"
echo " AbiWorkflow - Test Runner (Linux/WSL)"
echo "============================================================"
echo

if [[ ! -f "$BACKEND_VENV_DIR/bin/activate" ]]; then
  echo "[ERROR] Backend virtual env not found: backend/$BACKEND_VENV_NAME"
  echo "[ERROR] Run ./install.sh first."
  exit 1
fi

echo "[INFO] Activating backend virtual environment ..."
# shellcheck disable=SC1091
source "$BACKEND_VENV_DIR/bin/activate"
echo "[OK] Virtual environment activated."
echo

echo "[1/3] Running backend tests (pytest) ..."
echo
pushd "$BACKEND_DIR" >/dev/null
if ! run_with_timeout 60s pytest tests/ "${PYTEST_ARGS[@]}"; then
  echo
  echo "[FAIL] Backend tests failed."
  TOTAL_FAIL=$((TOTAL_FAIL + 1))
else
  echo
  echo "[PASS] Backend tests passed."
fi
popd >/dev/null
echo

echo "[2/3] Running backend lint (ruff) ..."
pushd "$BACKEND_DIR" >/dev/null
if ! run_with_timeout 60s ruff check app/; then
  echo
  echo "[FAIL] Backend lint has issues."
  TOTAL_FAIL=$((TOTAL_FAIL + 1))
else
  echo
  echo "[PASS] Backend lint passed."
fi
popd >/dev/null
echo

echo "[3/3] Running frontend lint (eslint) ..."
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "[SKIP] Frontend node_modules not found. Run ./install.sh first."
  TOTAL_FAIL=$((TOTAL_FAIL + 1))
else
  pushd "$FRONTEND_DIR" >/dev/null
  if ! run_with_timeout 60s npm run lint; then
    echo
    echo "[FAIL] Frontend lint has issues."
    TOTAL_FAIL=$((TOTAL_FAIL + 1))
  else
    echo
    echo "[PASS] Frontend lint passed."
  fi
  popd >/dev/null
fi
echo

echo "============================================================"
if [[ "$TOTAL_FAIL" -eq 0 ]]; then
  echo " All checks passed!"
  echo "============================================================"
  exit 0
else
  echo " $TOTAL_FAIL checks failed. See output above for details."
  echo "============================================================"
  exit 1
fi
