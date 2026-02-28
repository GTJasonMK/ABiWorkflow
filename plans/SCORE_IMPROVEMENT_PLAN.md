# SCORE IMPROVEMENT PLAN

## Goal
- Reduce duplication and coupling.
- Increase reuse and readability.
- Keep feature behavior unchanged.

## One-click entry
- Linux/macOS/WSL:
  - `bash scripts/run_score_plan.sh`
- Windows:
  - Double click `score_plan.bat` or run `score_plan.bat`

## Phase plan

## Progress
- [x] Phase 1 completed
- [x] Phase 2 completed
- [~] Phase 3 in progress
- [ ] Phase 4 not started
- [ ] Phase 5 ongoing (gates run after each phase)

### Latest Snapshot (2026-02-27)
- Task helper duplicate hits: `0`
- Backend status literal hits: `0`
- Large files (>300 lines) count: `6`
- Report: `.reports/score_plan/20260227_224531/SUMMARY.md`

### Phase 1: Frontend task center deduplication
- Scope:
  - `frontend/src/pages/TaskHub/index.tsx`
  - `frontend/src/components/TaskCenter/index.tsx`
- Action:
  - Extract shared render helpers to one module (task type/state/summary mapping).
- Done criteria:
  - No duplicated helper functions in both files.
  - Both UI entries use the same helper module.

### Phase 2: Backend status literal cleanup
- Scope:
  - `backend/app/api/*.py`
  - `backend/app/services/*.py`
  - `backend/app/tasks/*.py`
- Action:
  - Replace direct status string literals with centralized constants when business status is involved.
- Done criteria:
  - Status transition code paths rely on `project_status.py` / `scene_status.py`.
  - String literals remain only for payload labels or provider protocol mappings.

### Phase 3: Large file decomposition
- Priority files:
  - `backend/app/services/video_editor.py`
  - `backend/app/api/projects.py`
  - `backend/app/api/scenes.py`
  - `frontend/src/pages/VideoGeneration/index.tsx`
- Action:
  - Split by responsibility (assembly/validation/orchestration/view blocks).
- Done criteria:
  - Core file size reduced.
  - Existing tests still pass.

### Phase 4: Frontend data flow normalization
- Scope:
  - `frontend/src/pages/*`
  - `frontend/src/stores/*`
- Action:
  - Normalize page -> store action pattern.
  - Reduce direct API calls inside page components where store already owns the same domain behavior.
- Done criteria:
  - Each page has one primary state orchestration path.
  - No mixed duplicated orchestration.

### Phase 5: Quality gates
- Required:
  - Python syntax compile
  - TypeScript type check
  - Pytest (if available in local env)
- Done criteria:
  - All available gates pass.
  - Report generated under `.reports/score_plan/`.

## Notes
- This plan is non-destructive and does not reset user changes.
- The script is safe to run repeatedly.
