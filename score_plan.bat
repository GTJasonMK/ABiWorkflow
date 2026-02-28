@echo off
setlocal

where bash >nul 2>nul
if errorlevel 1 (
  echo [score-plan] bash is required. Use Git Bash or WSL.
  exit /b 1
)

bash scripts/run_score_plan.sh %*
exit /b %errorlevel%
