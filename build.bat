@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ============================================================
REM  build.bat - Build frontend production bundle
REM ============================================================

REM --- Configurable variables ---------------------------------
set "FRONTEND_DIR=%~dp0frontend"
set "DIST_DIR=%FRONTEND_DIR%\dist"
REM ------------------------------------------------------------

echo ============================================================
echo  AbiWorkflow - Production Build
echo ============================================================
echo.

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
    echo   npm is bundled with Node.js. Install Node.js first.
    exit /b 1
)

REM --- Check dependencies ---
if not exist "%FRONTEND_DIR%\node_modules" (
    echo [ERROR] Frontend node_modules not found. Run install.bat first.
    exit /b 1
)

REM --- Clean previous build ---
if exist "%DIST_DIR%" (
    echo [INFO] Cleaning previous build ...
    rmdir /s /q "%DIST_DIR%"
)

REM --- Build ---
echo [1/2] Building frontend (tsc + vite build) ...
echo.
pushd "%FRONTEND_DIR%"
call npm run build
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Frontend build failed.
    popd
    exit /b 1
)
popd
echo.

REM --- Verify output ---
echo [2/2] Verifying build output ...
if not exist "%DIST_DIR%\index.html" (
    echo [ERROR] Build output not found: dist/index.html
    exit /b 1
)

REM --- Summary ---
echo ============================================================
echo  Build successful!
echo.
echo  Output: frontend\dist\
echo.

REM Show file count and total size
set "FILE_COUNT=0"
for /r "%DIST_DIR%" %%f in (*) do set /a "FILE_COUNT+=1"
echo  Files: !FILE_COUNT!
echo ============================================================
echo.
echo  To preview: cd frontend ^&^& npm run preview
echo.

exit /b 0
