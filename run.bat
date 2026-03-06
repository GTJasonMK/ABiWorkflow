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
set "LOG_DIR=%BACKEND_DIR%\outputs\logs"

REM Default ports (override via environment: BACKEND_PORT / FRONTEND_PORT)
if not defined BACKEND_PORT set "BACKEND_PORT=8000"
if not defined FRONTEND_PORT set "FRONTEND_PORT=5173"
if not defined ENABLE_CELERY_WORKER set "ENABLE_CELERY_WORKER=0"
if not defined RUN_MODE set "RUN_MODE=desktop"
if not defined AUTO_HEAL_BACKEND_VENV set "AUTO_HEAL_BACKEND_VENV=1"
if not defined AUTO_HEAL_FRONTEND_DEPS set "AUTO_HEAL_FRONTEND_DEPS=1"
set "DESKTOP_REQUESTED=0"
set "RUN_SCHEMA_CLEANUP=0"

REM Optional arg: run.bat [web|desktop]
if /I "%~1"=="web" set "RUN_MODE=web"
if /I "%~1"=="desktop" (
    set "RUN_MODE=desktop"
    set "DESKTOP_REQUESTED=1"
)
if /I "%~1"=="gui" (
    set "RUN_MODE=desktop"
    set "DESKTOP_REQUESTED=1"
)
if /I "%~1"=="cleanup-schema" set "RUN_SCHEMA_CLEANUP=1"

REM Max port scan range (try up to 20 ports)
set "MAX_PORT_SCAN=20"
REM ------------------------------------------------------------

echo ============================================================
echo  AbiWorkflow - Development Server Launcher
echo ============================================================
echo.
echo [INFO] UI mode: %RUN_MODE%
echo.

if "%RUN_SCHEMA_CLEANUP%"=="1" (
    echo [INFO] Cleanup mode: deprecated single-track schema
    call :ensure_backend_venv
    if errorlevel 1 (
        exit /b 1
    )
    call :run_schema_cleanup
    exit /b %errorlevel%
)

REM --- Check: node ---
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] "node" is not installed. Run install.bat first or:
    echo   https://nodejs.org/
    exit /b 1
)

REM --- Check dependencies installed ---
call :ensure_backend_venv
if errorlevel 1 (
    exit /b 1
)
call :ensure_frontend_deps
if errorlevel 1 (
    exit /b 1
)
if /I "%RUN_MODE%"=="desktop" (
    if not exist "%FRONTEND_DIR%\node_modules\electron\package.json" (
        if "%DESKTOP_REQUESTED%"=="1" (
            echo [ERROR] Electron dependencies not found.
            echo [ERROR] Run: cd frontend ^&^& npm install
            exit /b 1
        ) else (
            echo [WARN] Electron dependencies not found.
            echo [WARN] Falling back to web mode for this run.
            echo [WARN] Install desktop dependencies: cd frontend ^&^& npm install
            set "RUN_MODE=web"
        )
    )
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
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
set "BACKEND_LOG=%LOG_DIR%\backend-dev.log"
set "CELERY_LOG=%LOG_DIR%\celery-dev.log"
set "BACKEND_PID="
set "CELERY_PID="
set "BACKEND_PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "BACKEND_PID_FILE=%LOG_DIR%\backend.pid"
set "CELERY_PID_FILE=%LOG_DIR%\celery.pid"
if exist "%BACKEND_PID_FILE%" del /f /q "%BACKEND_PID_FILE%" >nul 2>&1
if exist "%CELERY_PID_FILE%" del /f /q "%CELERY_PID_FILE%" >nul 2>&1

echo [INFO] Run mode: single (forced, one visible terminal)
echo [INFO] Backend reload: OFF (disabled to avoid extra terminal windows)
echo [INFO] Backend log: streaming in current terminal
start "" /B /D "%BACKEND_DIR%" "%BACKEND_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port %BE_PORT% --log-level info
REM Do not trust start /B errorlevel here: in some cmd environments it can be non-zero
REM even when child process is successfully spawned. Startup readiness is verified below
REM via PID probe and health endpoint polling.
REM Brief wait for process to register, then detect PID via CIM query
timeout /t 2 /nobreak >nul
for /f %%P in ('powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('uvicorn') -and $_.CommandLine.Contains('%BE_PORT%') } | Select-Object -First 1).ProcessId"') do (
    set "BACKEND_PID=%%P"
)
if defined BACKEND_PID (
    echo !BACKEND_PID!>"%BACKEND_PID_FILE%"
    echo [INFO] Backend PID: !BACKEND_PID!
) else (
    echo [WARN] Backend PID not detected yet; health check will confirm startup.
)

REM --- Wait backend health ready (up to 20s) ---
set /a "_health_retry=0"
:wait_backend_health
set /a "_health_retry+=1"
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%BE_PORT%/api/health' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if !errorlevel! neq 0 (
    if !_health_retry! geq 20 (
        echo [ERROR] Backend did not become ready on http://127.0.0.1:%BE_PORT%/api/health
        echo [ERROR] Please check backend startup logs above.
        if defined BACKEND_PID taskkill /PID !BACKEND_PID! /F >nul 2>&1
        exit /b 1
    )
    timeout /t 1 /nobreak >nul
    goto :wait_backend_health
)
echo [OK] Backend health check passed.

REM --- Verify key API route ---
echo [INFO] Verifying API route /api/projects ...
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%BE_PORT%/api/projects?page=1&page_size=1' -TimeoutSec 3; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] API route check failed: GET /api/projects returned non-200.
    echo [ERROR] This usually means current port points to a wrong service or backend startup is incomplete.
    if defined BACKEND_PID taskkill /PID !BACKEND_PID! /F >nul 2>&1
    exit /b 1
)
echo [OK] API route check passed.

REM --- Verify newly added API routes are loaded ---
echo [INFO] Verifying new API routes (/api/system/runtime, /api/projects/{project_id}/assets) ...
powershell -NoProfile -Command "try { $doc = Invoke-RestMethod -UseBasicParsing -Uri 'http://127.0.0.1:%BE_PORT%/openapi.json' -TimeoutSec 3; $paths = @($doc.paths.PSObject.Properties.Name); if (($paths -contains '/api/system/runtime') -and ($paths -contains '/api/projects/{project_id}/assets')) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] New API routes are missing from current backend process.
    echo [ERROR] Required routes:
    echo [ERROR]   - /api/system/runtime
    echo [ERROR]   - /api/projects/{project_id}/assets
    echo [ERROR] Please ensure the backend is restarted with latest source code.
    if defined BACKEND_PID taskkill /PID !BACKEND_PID! /F >nul 2>&1
    exit /b 1
)
echo [OK] New API routes are available.
set "VITE_PROBE_OPTIONAL_ENDPOINTS=true"
echo [INFO] Optional endpoint probe enabled for frontend (VITE_PROBE_OPTIONAL_ENDPOINTS=true).

REM --- Wait briefly for backend to start ---
timeout /t 1 /nobreak >nul

REM --- Start celery worker (optional) ---
if "%ENABLE_CELERY_WORKER%"=="1" (
    echo [INFO] Starting Celery worker ...
    echo [INFO] Celery log: streaming in current terminal
    start "" /B /D "%BACKEND_DIR%" "%BACKEND_PYTHON%" -m celery -A app.tasks.celery_app worker -P solo -l info
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to start Celery.
        exit /b 1
    )
    timeout /t 2 /nobreak >nul
    for /f %%P in ('powershell -NoProfile -Command "(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains('celery') -and $_.CommandLine.Contains('app.tasks.celery_app') } | Select-Object -First 1).ProcessId"') do (
        set "CELERY_PID=%%P"
    )
    if defined CELERY_PID (
        echo !CELERY_PID!>"%CELERY_PID_FILE%"
        echo [INFO] Celery PID: !CELERY_PID!
    ) else (
        echo [WARN] Celery PID not detected yet; worker may still be starting.
    )
)

REM --- Start frontend ---
set "FRONTEND_EXIT=0"
if /I "%RUN_MODE%"=="desktop" (
    echo [INFO] Starting Electron desktop GUI ...
    set "ELECTRON_RENDERER_PORT=%FE_PORT%"
    set "VITE_BACKEND_HOST=127.0.0.1"
    set "VITE_BACKEND_PORT=%BE_PORT%"
    REM Desktop dev uses Vite proxy to avoid browser CORS issues
    set "ELECTRON_API_BASE_URL=/api"
    set "ELECTRON_WS_BASE_URL=/ws"
    echo [INFO] Electron renderer: http://127.0.0.1:!ELECTRON_RENDERER_PORT!
    echo [INFO] Electron API: !ELECTRON_API_BASE_URL! ^(proxy -^> http://!VITE_BACKEND_HOST!:!VITE_BACKEND_PORT!^)
    echo.
    echo ============================================================
    echo  Services starting:
    echo    Backend:  http://127.0.0.1:%BE_PORT%
    echo    Desktop:  Electron GUI
    echo    Swagger:  http://127.0.0.1:%BE_PORT%/docs
    echo ============================================================
    echo.
    echo  Close Electron window or press Ctrl+C to stop all services.
    echo.

    pushd "%FRONTEND_DIR%"
    call npm run desktop:dev
    set "FRONTEND_EXIT=!errorlevel!"
    popd
) else (
    echo [INFO] Starting frontend on port %FE_PORT% ...
    set "VITE_BACKEND_HOST=127.0.0.1"
    set "VITE_BACKEND_PORT=%BE_PORT%"
    echo [INFO] Frontend proxy target: http://!VITE_BACKEND_HOST!:!VITE_BACKEND_PORT!
    echo.
    echo ============================================================
    echo  Servers starting:
    echo    Backend:  http://127.0.0.1:%BE_PORT%
    echo    Frontend: http://127.0.0.1:%FE_PORT%
    echo    Swagger:  http://127.0.0.1:%BE_PORT%/docs
    echo ============================================================
    echo.
    echo  Press Ctrl+C to stop frontend. Backend/Celery will be cleaned up automatically.
    echo.

    pushd "%FRONTEND_DIR%"
    call npx vite --port %FE_PORT% --host 127.0.0.1
    set "FRONTEND_EXIT=!errorlevel!"
    popd
)

echo.
echo [INFO] Frontend stopped. Cleaning background services ...
if defined BACKEND_PID (
    taskkill /PID !BACKEND_PID! /F >nul 2>&1
) else (
    call :kill_processes_by_keyword "uvicorn app.main:app --host 127.0.0.1 --port %BE_PORT%"
)
if "%ENABLE_CELERY_WORKER%"=="1" (
    if defined CELERY_PID (
        taskkill /PID !CELERY_PID! /F >nul 2>&1
    ) else (
        call :kill_processes_by_keyword "celery -A app.tasks.celery_app worker -P solo -l info"
    )
)

exit /b %FRONTEND_EXIT%

:kill_processes_by_keyword
set "KEYWORD=%~1"
for /f %%P in ('powershell -NoProfile -Command "$k = \"%KEYWORD%\"; (Get-CimInstance Win32_Process ^| Where-Object { $_.CommandLine -and $_.CommandLine.Contains($k) }).ProcessId"') do (
    taskkill /PID %%P /F >nul 2>&1
)
exit /b 0

:run_schema_cleanup
set "BACKEND_PYTHON_EXE=%BACKEND_DIR%\.venv\Scripts\python.exe"
if not exist "%BACKEND_PYTHON_EXE%" (
    echo [ERROR] Backend python not found: %BACKEND_PYTHON_EXE%
    exit /b 1
)

echo [INFO] Running deprecated single-track schema cleanup ...
pushd "%BACKEND_DIR%"
"%BACKEND_PYTHON_EXE%" scripts\cleanup_single_track_schema.py
set "SCHEMA_CLEANUP_EXIT=%errorlevel%"
popd

if not "%SCHEMA_CLEANUP_EXIT%"=="0" (
    echo [ERROR] Schema cleanup failed.
    exit /b %SCHEMA_CLEANUP_EXIT%
)

echo [OK] Schema cleanup completed.
exit /b 0

:ensure_frontend_deps
set "FRONTEND_NODE_MODULES=%FRONTEND_DIR%\node_modules"
set "FRONTEND_VITE_BIN=%FRONTEND_DIR%\node_modules\.bin\vite.cmd"
set "ROLLUP_WIN_MSVC=%FRONTEND_DIR%\node_modules\@rollup\rollup-win32-x64-msvc\rollup.win32-x64-msvc.node"
set "ROLLUP_WIN_GNU=%FRONTEND_DIR%\node_modules\@rollup\rollup-win32-x64-gnu\rollup.win32-x64-gnu.node"
set "NEED_FRONTEND_HEAL=0"

if not exist "%FRONTEND_NODE_MODULES%" set "NEED_FRONTEND_HEAL=1"
if not exist "%FRONTEND_VITE_BIN%" set "NEED_FRONTEND_HEAL=1"
if not exist "%ROLLUP_WIN_MSVC%" if not exist "%ROLLUP_WIN_GNU%" set "NEED_FRONTEND_HEAL=1"

if "%NEED_FRONTEND_HEAL%"=="0" (
    exit /b 0
)

if not "%AUTO_HEAL_FRONTEND_DEPS%"=="1" (
    echo [ERROR] Frontend dependencies are missing or incompatible.
    echo [ERROR] Required files:
    echo [ERROR]   - frontend\node_modules\.bin\vite.cmd
    echo [ERROR]   - frontend\node_modules\@rollup\rollup-win32-x64-^(msvc^|gnu^)\*.node
    echo [ERROR] Auto-heal disabled ^(AUTO_HEAL_FRONTEND_DEPS=%AUTO_HEAL_FRONTEND_DEPS%^).
    echo [ERROR] Please run: cd frontend ^&^& npm install
    exit /b 1
)

echo [WARN] Frontend dependencies are missing or incompatible.
echo [WARN] Auto-heal: reinstalling frontend dependencies ...

pushd "%FRONTEND_DIR%"
call npm install
if errorlevel 1 (
    echo [WARN] npm install failed. Retrying with clean reinstall ...
    if exist node_modules rmdir /s /q node_modules
    if exist package-lock.json del /f /q package-lock.json
    call npm install
    if errorlevel 1 (
        echo [ERROR] Frontend auto-heal failed at npm install.
        popd
        exit /b 1
    )
)
popd

if not exist "%FRONTEND_VITE_BIN%" (
    echo [ERROR] Frontend auto-heal finished but vite.cmd is still missing.
    exit /b 1
)
if not exist "%ROLLUP_WIN_MSVC%" if not exist "%ROLLUP_WIN_GNU%" (
    echo [ERROR] Frontend auto-heal finished but Windows rollup binary is still missing.
    echo [ERROR] Please run frontend install in Windows terminal ^(not WSL^) and retry.
    exit /b 1
)

echo [OK] Auto-heal completed: frontend dependencies are ready.
exit /b 0

:ensure_backend_venv
set "BACKEND_ACTIVATE=%BACKEND_DIR%\.venv\Scripts\activate.bat"
set "BACKEND_PYTHON_EXE=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "NEED_HEAL=0"
set "HAS_UNIX_STYLE=0"

if exist "%BACKEND_DIR%\.venv\bin\activate.bat" set "HAS_UNIX_STYLE=1"
if not exist "%BACKEND_ACTIVATE%" set "NEED_HEAL=1"
if not exist "%BACKEND_PYTHON_EXE%" set "NEED_HEAL=1"

if "%NEED_HEAL%"=="0" (
    exit /b 0
)

if not "%AUTO_HEAL_BACKEND_VENV%"=="1" (
    if "%HAS_UNIX_STYLE%"=="1" (
        echo [ERROR] Detected Unix-style backend virtual env: backend\.venv\bin
        echo [ERROR] run.bat requires Windows-style venv: backend\.venv\Scripts
    ) else (
        echo [ERROR] Backend virtual env not found at backend\.venv\Scripts
    )
    echo [ERROR] Auto-heal disabled ^(AUTO_HEAL_BACKEND_VENV=%AUTO_HEAL_BACKEND_VENV%^).
    echo [ERROR] Please run install.bat manually.
    exit /b 1
)

echo [WARN] Backend virtual env is missing or incompatible.
if "%HAS_UNIX_STYLE%"=="1" (
    echo [WARN] Detected Unix-style venv ^(backend\.venv\bin^), will recreate Windows-style venv.
)
echo [INFO] Auto-heal: rebuilding backend virtual environment ...

where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] "uv" is not installed or not in PATH.
    echo [ERROR] Auto-heal requires uv. Please run install.bat after installing uv.
    exit /b 1
)

if not exist "%BACKEND_DIR%\pyproject.toml" (
    echo [ERROR] Missing backend\pyproject.toml. Cannot auto-heal backend venv.
    exit /b 1
)

if exist "%BACKEND_DIR%\.venv" (
    rmdir /s /q "%BACKEND_DIR%\.venv"
    if errorlevel 1 (
        echo [ERROR] Failed to remove old backend\.venv. Please close any process using it and retry.
        exit /b 1
    )
)

pushd "%BACKEND_DIR%"
uv venv
if errorlevel 1 (
    echo [ERROR] Auto-heal failed at: uv venv
    popd
    exit /b 1
)

uv sync --extra dev
if errorlevel 1 (
    echo [ERROR] Auto-heal failed at: uv sync --extra dev
    popd
    exit /b 1
)
popd

if not exist "%BACKEND_ACTIVATE%" (
    echo [ERROR] Auto-heal finished but activate.bat is still missing: backend\.venv\Scripts\activate.bat
    exit /b 1
)
if not exist "%BACKEND_PYTHON_EXE%" (
    echo [ERROR] Auto-heal finished but python.exe is still missing: backend\.venv\Scripts\python.exe
    exit /b 1
)

echo [OK] Auto-heal completed: backend virtual env rebuilt.
exit /b 0
