@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ============================================================
REM  test.bat - Run all tests (backend + frontend lint)
REM ============================================================

REM --- Configurable variables ---------------------------------
set "BACKEND_DIR=%~dp0backend"
set "FRONTEND_DIR=%~dp0frontend"
set "PYTEST_ARGS=-v"
set "BACKEND_VENV_NAME=.venv-win"
if defined ABI_BACKEND_VENV_NAME set "BACKEND_VENV_NAME=%ABI_BACKEND_VENV_NAME%"
set "BACKEND_VENV_DIR=%BACKEND_DIR%\%BACKEND_VENV_NAME%"
REM ------------------------------------------------------------

echo ============================================================
echo  AbiWorkflow - Test Runner
echo ============================================================
echo.

set "TOTAL_FAIL=0"

REM --- Check backend venv ---
if not exist "%BACKEND_VENV_DIR%\Scripts\activate.bat" (
    echo [ERROR] Backend virtual env not found: backend\%BACKEND_VENV_NAME%
    echo [ERROR] Run install.bat first.
    exit /b 1
)

REM === Activate backend venv ===
echo [INFO] Activating backend virtual environment ...
call "%BACKEND_VENV_DIR%\Scripts\activate.bat"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    exit /b 1
)
echo [OK] Virtual environment activated.
echo.

REM === Backend: pytest ===
echo [1/3] Running backend tests (pytest) ...
echo.
pushd "%BACKEND_DIR%"
pytest tests/ %PYTEST_ARGS%
if %errorlevel% neq 0 (
    echo.
    echo [FAIL] Backend tests failed.
    set /a "TOTAL_FAIL+=1"
) else (
    echo.
    echo [PASS] Backend tests passed.
)
popd
echo.

REM === Backend: ruff lint ===
echo [2/3] Running backend lint (ruff) ...
pushd "%BACKEND_DIR%"
ruff check app/
if %errorlevel% neq 0 (
    echo.
    echo [FAIL] Backend lint has issues.
    set /a "TOTAL_FAIL+=1"
) else (
    echo.
    echo [PASS] Backend lint passed.
)
popd
echo.

REM === Frontend: eslint ===
echo [3/3] Running frontend lint (eslint) ...
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [SKIP] Frontend node_modules not found. Run install.bat first.
    set /a "TOTAL_FAIL+=1"
) else (
    pushd "%FRONTEND_DIR%"
    call npm run lint 2>&1
    if !errorlevel! neq 0 (
        echo.
        echo [FAIL] Frontend lint has issues.
        set /a "TOTAL_FAIL+=1"
    ) else (
        echo.
        echo [PASS] Frontend lint passed.
    )
    popd
)
echo.

REM === Summary ===
echo ============================================================
if !TOTAL_FAIL!==0 (
    echo  All checks passed!
    echo ============================================================
    exit /b 0
) else (
    echo  !TOTAL_FAIL! checks failed. See output above for details.
    echo ============================================================
    exit /b 1
)
