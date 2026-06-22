## Why

The current skill upgrade (mastery) system is broken after commit 8a000046 introduced a 615-line `TrainingStateMachine` that replaced the original ~60-line state machine. Pixel-based level detection (`read_mastery_zones()`) is unreliable, and the system has no persistence — plans are ephemeral and cannot survive restarts. Users cannot schedule masteries ahead of time or retry failed attempts.

## What Changes

- **Revert** `base_schedule.py` to the pre-8a000046 `skill_upgrade()` with the proven while-tasks state machine (collect/upgrade/confirm), keeping improvements from `__main__.py`, `record.py`, and `mastery_recommendation.py`
- **Keep `read_mastery_zones()`** extracted from `training_state.py` into `mastery_db.py` as standalone utility — needed for level detection AFTER training starts (half-off swap scheduling), where time-based estimation is inaccurate due to buffs
- **Delete** `TrainingStateMachine` in `training_state.py` and remove all dependencies on it (including revert of #875 and #880)
- **New SQLite tables** `mastery_plan` (append-only, no pruning) and `mastery_route` (profession + supports JSON blob + is_default)
- **New REST API endpoints** for plan CRUD, route management, history
- **Vue frontend** updates to call new APIs instead of localStorage
- **MasteryDB module**: `arknights_mower/utils/mastery_db.py` encapsulates all SQLite CRUD for both tables, shared by API layer, scheduler, and agent tools
- **MasterySync module**: `arknights_mower/utils/mastery_sync.py` implements the 5-min idle cycle, called from `base_schedule.py` run loop
- **Skland sync**: two-phase — (A) scan cultivate.json all operators' skills[].level, mark level≥3 pending as completed; (B) read building_training.trainee, insert REFRESH_TIME if trainee present; Phase A also checks in_progress plans with no matching trainee → mark failed (training interrupted)
- **No plan history pruning**: Skland completed data accumulates for audit trail, no deletion
- **POST /mastery-plan format**: `{"银灰": 0, "史尔特尔": 1}` (name → skill_index), server resolves name to char_id via skill_data.json
- **REFRESH_TIME**: when building_training has trainee and no SKILL_UPGRADE in queue → insert REFRESH_TIME task
- **Auto-schedule**: remaining pending after sync → read mastery_route (user must configure, is_default=0) → INSERT in_progress + push SKILL_UPGRADE to queue head with `time=datetime.now()`, sorted by insertion order (one per cycle)
- **_get_mastery_plan() DB**: replace matery_plan.json read with mastery_plan table query (pending/failed)
- **_build_route_supports() DB**: read mastery_route table instead of old methods
- **Agent tools**: register MasteryDB methods as agent tools (add_mastery_plan, list_plans, set_route, etc.)
- On failure, mark `failed` in DB with reason + stop (no retry); user retries via POST /mastery-plan

## Capabilities

### New Capabilities
- `mastery-plan-persistence`: Persistent mastery plan CRUD with SQLite tables (`mastery_plan`, `mastery_route`), `_get_mastery_plan()` DB migration, historical tracking
- `mastery-api`: REST API layer (`GET/POST /mastery-plan`, `GET /mastery-history`, `GET/POST /mastery-route`)
- `mastery-skland-sync`: Two-phase sync — cultivate.json skills[].level scan for auto-complete + building_training for REFRESH_TIME, auto-schedule next pending plan
- `mastery-agent-tools`: Register MasteryDB methods as agent tools (add_mastery_plan, list_plans, set_route, etc.)
- `mastery-ui-integration`: Vue frontend changes — `MasteryRecommendation.vue` API integration, retry button, route settings via API

### Modified Capabilities
*(None — no existing specs to modify)*

## Impact

- **`base_schedule.py`**: Full revert of 8a000046 changes, restoring original `skill_upgrade()` while-tasks loop
- **`training_state.py`**: Remove `TrainingStateMachine` class
- **`app/`**: New DB migration, new API routes, new service layer for plan/route management, agent tool registration
- **`frontend/`**: `MasteryRecommendation.vue` and settings tab route editor switch from localStorage to API
- **`agent/`**: MasteryDB methods exposed as callable agent tools
- **DB**: New tables (`mastery_plan`, `mastery_route`), no breaking schema changes
