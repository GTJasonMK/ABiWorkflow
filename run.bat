@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ============================================================
REM  run.bat - Start backend + frontend dev servers
REM ============================================================

REM --- Configurable variables ---------------------------------
set "BACKEND_DIR=%~dp0backend"
set "FRONTEND_DIR=%~dp0frontend"
set "ENV_FILE=%~dp0.env"

REM Default ports (override via environment: BACKEND_PORT / FRONTEND_PORT)
if not defined BACKEND_PORT set "BACKEND_PORT=8000"
if not defined FRONTEND_PORT set "FRONTEND_PORT=5173"

REM Max port scan range (try up to 20 ports)
set "MAX_PORT_SCAN=20"
REM ------------------------------------------------------------

echo ============================================================
echo  AbiWorkflow - Development Server Launcher
echo ============================================================
echo.

REM --- Check: node ---
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] "node" is not installed. Run install.bat first or:
    echo   https://nodejs.org/
    exit /b 1
)

REM --- Check dependencies installed ---
if not exist "%BACKEND_DIR%\.venv\Scripts\activate.bat" (
    echo [ERROR] Backend virtual env not found. Run install.bat first.
    exit /b 1
)
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [ERROR] Frontend node_modules not found. Run install.bat first.
    exit /b 1
)

REM --- Check .env ---
if not exist "%ENV_FILE%" (
    echo [WARN] .env not found. Using default config. Run install.bat to create it.
)

REM --- Auto-detect backend port ---
set "BE_PORT=%BACKEND_PORT%"
set /a "_scan=0"
:find_be_port
netstat -an | findstr "LISTENING" | findstr ":%BE_PORT% " >nul 2>&1
if %errorlevel%==0 (
    set /a "_scan+=1"
    if !_scan! geq %MAX_PORT_SCAN% (
        echo [ERROR] Cannot find a free backend port after %MAX_PORT_SCAN% attempts.
        exit /b 1
    )
    echo [INFO] Port %BE_PORT% is in use, trying next ...
    set /a "BE_PORT+=1"
    goto :find_be_port
)
echo [OK] Backend port: %BE_PORT%

REM --- Auto-detect frontend port ---
set "FE_PORT=%FRONTEND_PORT%"
set /a "_scan=0"
:find_fe_port
netstat -an | findstr "LISTENING" | findstr ":%FE_PORT% " >nul 2>&1
if %errorlevel%==0 (
    set /a "_scan+=1"
    if !_scan! geq %MAX_PORT_SCAN% (
        echo [ERROR] Cannot find a free frontend port after %MAX_PORT_SCAN% attempts.
        exit /b 1
    )
    echo [INFO] Port %FE_PORT% is in use, trying next ...
    set /a "FE_PORT+=1"
    goto :find_fe_port
)
echo [OK] Frontend port: %FE_PORT%
echo.

REM --- Check Redis (optional) ---
echo [INFO] Checking Redis connectivity ...
where docker >nul 2>&1
if %errorlevel%==0 (
    docker compose -f "%~dp0docker-compose.yml" ps --status running 2>nul | findstr "redis" >nul 2>&1
    if !errorlevel! neq 0 (
        echo [INFO] Redis container not running. Starting via docker compose ...
        docker compose -f "%~dp0docker-compose.yml" up -d
        if !errorlevel! neq 0 (
            echo [WARN] Failed to start Redis. Celery tasks will not work.
            echo        Start manually: docker compose up -d
        ) else (
            echo [OK] Redis started.
        )
    ) else (
        echo [OK] Redis is already running.
    )
) else (
    echo [WARN] Docker not found. Redis/Celery features require Redis.
    echo        Install Docker Desktop: https://www.docker.com/products/docker-desktop/
    echo        Or install Redis manually.
)
echo.

REM --- Start backend (activate venv explicitly) ---
echo [INFO] Starting backend on port %BE_PORT% ...
start "AbiWorkflow-Backend" /D "%BACKEND_DIR%" cmd /c "call .venv\Scripts\activate.bat && uvicorn app.main:app --host 127.0.0.1 --port %BE_PORT% --reload"

REM --- Wait briefly for backend to start ---
timeout /t 2 /nobreak >nul

REM --- Start frontend ---
echo [INFO] Starting frontend on port %FE_PORT% ...
echo.
echo ============================================================
echo  Servers starting:
echo    Backend:  http://127.0.0.1:%BE_PORT%
echo    Frontend: http://127.0.0.1:%FE_PORT%
echo    Swagger:  http://127.0.0.1:%BE_PORT%/docs
echo ============================================================
echo.
echo  Press Ctrl+C to stop the frontend server.
echo  Close the "AbiWorkflow-Backend" window to stop the backend.
echo.

pushd "%FRONTEND_DIR%"
call npx vite --port %FE_PORT% --host 127.0.0.1
popd

exit /b 0
