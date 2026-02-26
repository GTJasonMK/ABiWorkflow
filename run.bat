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
set "DESKTOP_REQUESTED=0"

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

REM Max port scan range (try up to 20 ports)
set "MAX_PORT_SCAN=20"
REM ------------------------------------------------------------

echo ============================================================
echo  AbiWorkflow - Development Server Launcher
echo ============================================================
echo.
echo [INFO] UI mode: %RUN_MODE%
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
powershell -NoProfile -Command "$p = Start-Process -FilePath '%BACKEND_PYTHON%' -WorkingDirectory '%BACKEND_DIR%' -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','%BE_PORT%','--log-level','info') -NoNewWindow -PassThru; [System.IO.File]::WriteAllText('%BACKEND_PID_FILE%', [string]$p.Id)"
if !errorlevel! neq 0 (
    echo [ERROR] Failed to start backend in single mode.
    exit /b 1
)
if exist "%BACKEND_PID_FILE%" (
    set /p BACKEND_PID=<"%BACKEND_PID_FILE%"
)
if not defined BACKEND_PID (
    echo [ERROR] Backend started but PID not found.
    exit /b 1
)
echo [INFO] Backend PID: !BACKEND_PID!

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
    powershell -NoProfile -Command "$p = Start-Process -FilePath '%BACKEND_PYTHON%' -WorkingDirectory '%BACKEND_DIR%' -ArgumentList @('-m','celery','-A','app.tasks.celery_app','worker','-P','solo','-l','info') -NoNewWindow -PassThru; [System.IO.File]::WriteAllText('%CELERY_PID_FILE%', [string]$p.Id)"
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to start Celery in single mode.
        exit /b 1
    )
    if exist "%CELERY_PID_FILE%" (
        set /p CELERY_PID=<"%CELERY_PID_FILE%"
    )
    if not defined CELERY_PID (
        echo [ERROR] Celery started but PID not found.
        exit /b 1
    )
    echo [INFO] Celery PID: !CELERY_PID!
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
    echo [INFO] Electron renderer: http://127.0.0.1:%ELECTRON_RENDERER_PORT%
    echo [INFO] Electron API: %ELECTRON_API_BASE_URL% ^(proxy -^> http://%VITE_BACKEND_HOST%:%VITE_BACKEND_PORT%^)
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
    echo [INFO] Frontend proxy target: http://%VITE_BACKEND_HOST%:%VITE_BACKEND_PORT%
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
