#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_DIR="$ROOT_DIR/.reports/score_plan/$TIMESTAMP"
mkdir -p "$REPORT_DIR"

log() {
  printf '[score-plan] %s\n' "$1"
}

run_cmd() {
  local name="$1"
  shift
  local out="$REPORT_DIR/${name}.txt"
  {
    printf '$ %s\n' "$*"
    "$@" 2>&1
  } >"$out"
  local rc=$?
  if [ $rc -eq 0 ]; then
    log "OK   $name"
  else
    log "WARN $name (exit=$rc)"
  fi
  return 0
}

run_shell() {
  local name="$1"
  shift
  local cmd="$*"
  local out="$REPORT_DIR/${name}.txt"
  {
    printf '$ %s\n' "$cmd"
    bash -lc "$cmd" 2>&1
  } >"$out"
  local rc=$?
  if [ $rc -eq 0 ]; then
    log "OK   $name"
  else
    log "WARN $name (exit=$rc)"
  fi
  return 0
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

log "report dir: $REPORT_DIR"
log "phase 0: baseline snapshot"

run_cmd "git_status" git -C "$ROOT_DIR" status --short
run_shell "largest_files" \
  "cd '$ROOT_DIR' && find backend/app frontend/src -type f \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' \) -print0 | xargs -0 wc -l | sort -nr | head -n 80"
run_shell "backend_status_literals" \
  "cd '$ROOT_DIR' && rg -n \"\\\"pending\\\"|\\\"generating\\\"|\\\"generated\\\"|\\\"completed\\\"|\\\"failed\\\"|\\\"draft\\\"|\\\"parsing\\\"|\\\"parsed\\\"|\\\"composing\\\"\" backend/app/api backend/app/services backend/app/tasks -g'*.py' -S || true"
run_shell "task_center_duplicate_helpers" \
  "cd '$ROOT_DIR' && rg -n \"function renderTaskType|function renderStateLabel|function renderStateClass|function render(Result)?Summary\" frontend/src/pages/TaskHub/index.tsx frontend/src/components/TaskCenter/index.tsx -S || true"

log "phase 1: lightweight gates"
run_shell "python_compile" \
  "cd '$ROOT_DIR' && python3 -m py_compile \$(find backend/app backend/tests -type f -name '*.py')"

if has_cmd npx; then
  run_shell "frontend_tsc" \
    "cd '$ROOT_DIR/frontend' && npx tsc --noEmit --pretty false --project tsconfig.json"
else
  printf 'npx not found\n' >"$REPORT_DIR/frontend_tsc.txt"
  log "WARN frontend_tsc (npx not found)"
fi

if has_cmd python3; then
  if python3 - <<'PY' >/dev/null 2>&1
import importlib.util
import sys
sys.exit(0 if importlib.util.find_spec("pytest") else 1)
PY
  then
    run_shell "backend_pytest" \
      "cd '$ROOT_DIR/backend' && python3 -m pytest tests -q"
  else
    printf 'pytest module not found\n' >"$REPORT_DIR/backend_pytest.txt"
    log "WARN backend_pytest (pytest module not found)"
  fi
fi

log "phase 2: score snapshot"
TASK_DUP_COUNT="$(grep '^frontend/' "$REPORT_DIR/task_center_duplicate_helpers.txt" 2>/dev/null | wc -l | tr -d ' ')"
STATUS_LITERAL_COUNT="$(grep '^backend/' "$REPORT_DIR/backend_status_literals.txt" 2>/dev/null | wc -l | tr -d ' ')"
LARGE_FILE_COUNT="$(
  awk '$1 ~ /^[0-9]+$/ && $2 != "total" && $1 > 300 {count++} END {print count+0}' \
    "$REPORT_DIR/largest_files.txt" 2>/dev/null || echo 0
)"

SUMMARY="$REPORT_DIR/SUMMARY.md"
cat >"$SUMMARY" <<EOF
# Score Plan Summary

Generated at: $TIMESTAMP

## Metrics
- Task helper duplicate hits: $TASK_DUP_COUNT
- Backend status literal hits: $STATUS_LITERAL_COUNT
- Large files (>300 lines) count: $LARGE_FILE_COUNT

## Artifacts
- git status: \`git_status.txt\`
- largest files: \`largest_files.txt\`
- backend status literals: \`backend_status_literals.txt\`
- task helper duplicates: \`task_center_duplicate_helpers.txt\`
- python compile: \`python_compile.txt\`
- frontend tsc: \`frontend_tsc.txt\`
- backend pytest: \`backend_pytest.txt\`

## Next actions (execution order)
1. Deduplicate TaskHub + TaskCenter helper mapping.
2. Replace backend business status literals with centralized constants.
3. Split large files by responsibility.
4. Normalize frontend page orchestration to store-first flow.
5. Re-run this script and check metric reduction.
EOF

log "done"
log "open summary: $SUMMARY"
