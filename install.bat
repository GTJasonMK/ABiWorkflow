@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ============================================================
REM  install.bat - Install all dependencies (backend + frontend)
REM ============================================================

REM --- Configurable variables ---------------------------------
set "BACKEND_DIR=%~dp0backend"
set "FRONTEND_DIR=%~dp0frontend"
set "ENV_EXAMPLE=%~dp0.env.example"
set "ENV_FILE=%~dp0.env"
REM ------------------------------------------------------------

echo ============================================================
echo  AbiWorkflow - Dependency Installer
echo ============================================================
echo.

REM --- Check: uv ---
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] "uv" is not installed or not in PATH.
    echo.
    echo   Install options:
    echo     1. pip install uv
    echo     2. winget install astral-sh.uv
    echo     3. powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    echo.
    exit /b 1
)

REM --- Check: node ---
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] "node" is not installed or not in PATH.
    echo.
    echo   Install from: https://nodejs.org/
    echo   Or: winget install OpenJS.NodeJS.LTS
    echo.
    exit /b 1
)

REM --- Check: npm ---
where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] "npm" is not installed or not in PATH.
    echo.
    echo   npm is bundled with Node.js. Install Node.js first.
    echo   https://nodejs.org/
    echo.
    exit /b 1
)

echo [OK] uv found
echo [OK] node found
echo [OK] npm found
echo.

REM --- Backend: create venv + install dependencies ---
echo [1/3] Installing backend dependencies ...
if not exist "%BACKEND_DIR%\pyproject.toml" (
    echo [ERROR] backend/pyproject.toml not found. Is the repo intact?
    exit /b 1
)
pushd "%BACKEND_DIR%"
if not exist ".venv\Scripts\activate.bat" (
    echo [INFO] Creating virtual environment ...
    uv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        popd
        exit /b 1
    )
    echo [OK] Virtual environment created at backend\.venv
)
echo [INFO] Installing Python dependencies ...
uv sync --extra dev
if %errorlevel% neq 0 (
    echo [ERROR] Backend dependency installation failed.
    popd
    exit /b 1
)
popd
echo [OK] Backend dependencies installed.
echo.

REM --- Frontend dependencies ---
echo [2/3] Installing frontend dependencies ...
if not exist "%FRONTEND_DIR%\package.json" (
    echo [ERROR] frontend/package.json not found. Is the repo intact?
    exit /b 1
)
pushd "%FRONTEND_DIR%"
call npm install
if %errorlevel% neq 0 (
    echo [ERROR] Frontend dependency installation failed.
    popd
    exit /b 1
)
popd
echo [OK] Frontend dependencies installed.
echo.

REM --- Copy .env if missing ---
echo [3/3] Checking .env file ...
if not exist "%ENV_FILE%" (
    if exist "%ENV_EXAMPLE%" (
        copy "%ENV_EXAMPLE%" "%ENV_FILE%" >nul
        echo [OK] Created .env from .env.example
        echo      Please edit .env and fill in your API keys.
    ) else (
        echo [WARN] No .env.example found. Skipping .env creation.
    )
) else (
    echo [OK] .env already exists.
)
echo.

echo ============================================================
echo  All dependencies installed successfully!
echo ============================================================
echo.
echo  Next steps:
echo    1. Edit .env with your API keys (LLM_PROVIDER, OPENAI_API_KEY, etc.)
echo    2. Start Redis:  docker compose up -d
echo    3. Run the app:  run.bat
echo.

exit /b 0
