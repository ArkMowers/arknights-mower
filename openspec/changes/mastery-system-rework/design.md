## Context

The mastery (skill upgrade) system in arknights-mower is broken. Commit 8a000046 replaced a working ~60-line state machine (`skill_upgrade()` in `base_schedule.py`) with a 615-line `TrainingStateMachine` in `training_state.py` that uses unreliable pixel-based level detection. The system has no persistence — plans exist only in-memory and vanish on restart. Users cannot schedule future masteries, retry failed attempts, or view history.

The project uses SQLite at `app/tmp/data.db` for persistence.

## Goals / Non-Goals

**Goals:**
- Restore `skill_upgrade()` to the pre-8a000046 while-tasks state machine (collect/upgrade/confirm)
- Remove `TrainingStateMachine` and all dependencies on it
- Add SQLite tables `mastery_plan` (planned/completed/failed masteries) and `mastery_route` (per-class mastery paths)
- Add REST API layer for plan/route CRUD
- Update Vue frontend to use new APIs
- Two-phase Skland sync: (A) cultivate.json skills[].level scan for auto-completing level≥3 plans; (B) building_training for REFRESH_TIME insertion
- Auto-schedule next pending plan (one per 5-min idle cycle) via mastery_route → SKILL_UPGRADE task
- On `skill_upgrade()` failure: mark `failed` in DB with reason, stop — no auto-retry
- Register MasteryDB methods as agent tools

**Non-Goals:**
- No new GUI or external dashboard
- No changes to Skland data fetching itself (only consume `player_info_cache`)
- No changes to the OCR/recognition pipeline
- No breaking DB schema changes (new tables only)

## Decisions

### Revert 8a000046 for `base_schedule.py`, keep other improvements
- **Decision**: `git revert` 8a000046 changes to `base_schedule.py` only; retain improvements to `__main__.py`, `record.py`, `mastery_recommendation.py`
- **Rationale**: The original `skill_upgrade()` was compact (60 lines), reliable, and understood. The new `TrainingStateMachine` introduced complexity without benefit (pixel-based detection is fragile). Other files in that commit had genuine improvements.
- **Alternatives considered**: Fixing `TrainingStateMachine` incrementally — rejected because the architectural approach is fundamentally flawed (pixel-based level detection cannot match game state accuracy).

### SQLite append-only plan table
- **Decision**: `mastery_plan` uses append-only design — each status change creates a new row. Current status via `SELECT MAX(id)` grouped by `(char_id, skill_index)`. History via `SELECT ... ORDER BY id DESC LIMIT 10`. No pruning — Skland completed data accumulates for audit trail.
- **Rationale**: Provides built-in audit trail. No complex status transition logic. Keeping all rows allows full history review.
- **Alternatives considered**: Pruning after 10 rows — rejected; Skland sync provides authoritative data, no need to limit history.

### Keep read_mastery_zones as standalone utility
- **Decision**: Extract `read_mastery_zones()` from `training_state.py` into `arknights_mower/utils/mastery_db.py` (or a shared helper). Delete the rest of `TrainingStateMachine`.
- **Rationale**: The old `skill_upgrade()` hours inference (before clicking confirm) is correct — it reads base training time. But once training starts, displayed time includes half-off/central bonuses, making `remaining_h` → level estimation unreliable. `read_mastery_zones()` reads pixel triangles directly from the game, accurate regardless of buffs. Used for post-training-start level detection (half-off swap scheduling, in-progress checks).

### Two-phase Skland sync
- **Decision**: Phase A — scan cultivate.json all operators' skills[].level; if level≥3, mark matching pending plan as completed (INSERT new completed row). Phase B — read building_training.trainee; if present and no SKILL_UPGRADE queued, insert REFRESH_TIME task.
- **Rationale**: Skland API provides authoritative skill level data (not OCR), so level≥3 is reliable proof of completion. building_training is a real-time snapshot — it only informs REFRESH_TIME scheduling, not completion status.
- **Alternatives considered**: Auto-complete from building_training alone — rejected because a snapshot can't distinguish "in progress" from "idle training slot".

### Failed tasks stop immediately, no retry
- **Decision**: When `skill_upgrade()` encounters an error (e.g., insufficient materials), it writes `status=failed` + `failed_reason` and `return`s. No retry. User retries via POST /mastery-plan (INSERT new pending row).
- **Rationale**: Materials shortage, wrong base layout, or network issues are not transient. Retrying would burn resources without fixing the root cause. User intervention is required.

### REFRESH_TIME task insertion
- **Decision**: When building_training has a trainee and the task queue contains no SKILL_UPGRADE entry, insert a REFRESH_TIME task to re-check training progress later.
- **Rationale**: Training takes hours. Without REFRESH_TIME, the system has no way to know when training finishes and the next cycle should run.

### Auto-schedule: one plan per idle cycle
- **Decision**: Each 5-min idle cycle picks exactly ONE remaining pending plan → INSERT in_progress → push SKILL_UPGRADE to queue head.
- **Rationale**: Mastery takes hours. Queuing multiple plans would mean only the last one actually runs when tasks execute sequentially.

### User must configure mastery route
- **Decision**: `skill_upgrade()` requires a user-saved route (`is_default=0`) for the operator's profession. Raises error with clear message if missing.
- **Rationale**: Built-in defaults go stale as new operators are released. Forcing explicit user configuration ensures the user actively chooses upgrade priorities.

### Mastery route table columns
- **Decision**: `mastery_route` uses minimal columns: `profession TEXT`, `supports TEXT` (full JSON blob including supports list, half_off, optimal, controlCenter), `is_default INTEGER`, `created_at TEXT`. UNIQUE(profession, is_default).
- **Rationale**: The existing route editor sends the full route config as one JSON object. Storing the entire blob avoids schema churn and maps 1:1 to the UI structure. `half_off` and `optimal` are UI-level toggles embedded in the blob.
- **Alternatives considered**: Separate columns for half_off/optimal — rejected; redundant since they're already in the UI JSON payload.

### Sync trigger location
- **Decision**: The five-minute idle sync SHALL be triggered inside `base_schedule.py`'s main run loop, alongside existing periodic tasks (drone, reload, party).
- **Rationale**: The run loop already has `no_pending_task()` guards and timer checks — natural fit. No need for a separate scheduled timer.

### No DB filter for /mastery-recommendation
- **Decision**: `/mastery-recommendation` SHALL NOT filter out plans already in the DB. The UI SHALL indicate which operators are already planned/in-progress.
- **Rationale**: Users need to see all options regardless of plan status. Over-filtering would hide retry-eligible operators.

### Task queue sorted by insertion order
- **Decision**: SKILL_UPGRADE tasks pushed to the queue head SHALL use `time=datetime.now()` so they sort first by time, then by insertion order for ties.
- **Rationale**: Simple, natural ordering. No special sort needed beyond the existing `self.tasks.sort(key=lambda task: task.time)`.

### MasteryDB module location
- **Decision**: `MasteryDB` SHALL live in `arknights_mower/utils/mastery_db.py`, using the same `data.db` as the rest of the project. Agent tools in `arknights_mower/agent/tools/mastery_tools.py` SHALL call MasteryDB methods.
- **Rationale**: Single DB, single connection path. CRUD logic is separate from both API layer and agent registration, keeping each layer thin.

### POST /mastery-plan format: name → skill_index
- **Decision**: The POST payload SHALL use operator name as key and skill_index as value: `{"银灰": 0, "史尔特尔": 1}`. The server resolves name → char_id via skill_data.json.
- **Rationale**: Frontend works with operator names, not char_ids. Simpler for users and avoids composite key parsing.
- **Alternatives considered**: `{"char01_0": true}` — rejected; requires frontend to maintain char_id mapping.

### In-progress timeout from Skland sync
- **Decision**: During Skland sync Phase A, if a plan has `status=in_progress` but Skland cultivate data shows `skills[].level < 3` AND no `building_training.trainee` matches this operator, INSERT a new `failed` row with reason "训练中断（未检测到进行中的训练）".
- **Rationale**: The user may have canceled training, or the system crashed mid-training. Without this check, `in_progress` plans would stay stuck forever. Sync acts as a dead-plan detector.
- **Alternatives considered**: Manual timeout after 48h — rejected; sync is more accurate than a fixed timer.

## Risks / Trade-offs

- **[Risk] Revert conflicts**: Reverting 8a000046 on `base_schedule.py` may conflict with subsequent changes. → **Mitigation**: Use `git revert -n` and manually resolve conflicts; validate by comparing with pre-8a000046 version.
- **[Risk] TrainingStateMachine references in other files**: PRs #875 and #880 may reference `TrainingStateMachine`. → **Mitigation**: Revert those PRs' changes that depend on the class; keep any unrelated improvements.
- **[Trade-off] Append-only design**: Slightly more complex queries (`SELECT MAX(id)`) vs. in-place updates. → **Acceptable**: Simpler code, no migration needed, retained history.
- **[Risk] Frontend localStorage → API migration breaks existing user data**: Users with saved routes in localStorage will lose them. → **Mitigation**: Clear old localStorage keys on first load.
- **[Risk] User forgets to configure route**: If no user route exists for a profession, the auto-schedule step fails. → **Mitigation**: Clear error message in UI + log; cycle continues for other professions.
