## 1. Revert & Cleanup

- [x] 1.1 Run `git revert -n 8a000046` and resolve conflicts on `base_schedule.py` only
- [x] 1.2 Revert #875 and #880 changes that depend on `TrainingStateMachine` in `training_state.py`
- [x] 1.3 Extract `read_mastery_zones()` from `training_state.py` into `mastery_db.py` as standalone utility function
- [x] 1.4 Delete remaining `TrainingStateMachine` code from `training_state.py`, then delete the file
- [x] 1.5 Restore pre-8a000046 `skill_upgrade()` while-tasks loop (collect/upgrade/confirm), with error handling that writes failed to DB

## 2. Database: Tables & Queries

- [x] 2.1 Create `mastery_plan` table (id, char_id, skill_index, status, failed_reason, level, skill_name, created_at)
- [x] 2.2 Create `mastery_route` table (profession TEXT, supports TEXT JSON blob, is_default INTEGER, created_at TEXT, UNIQUE(profession, is_default))
- [x] 2.3 Implement `MasteryDB` class in `arknights_mower/utils/mastery_db.py` (all CRUD in one module)
- [x] 2.4 Implement append-only INSERT + current status query via `SELECT MAX(id) GROUP BY (char_id, skill_index)`
- [x] 2.5 No history pruning needed
- [x] 2.6 Implement `_get_mastery_plan()` → query mastery_plan WHERE status IN ('pending', 'failed')
- [x] 2.7 Implement `_build_route_supports()` → read mastery_route, require is_default=0

## 3. REST API

- [x] 3.1 Implement `GET /mastery-plan` (plans + history)
- [x] 3.2 Implement `POST /mastery-plan` with validation: parse composite key, check char_id in skill_data.json, route by current status (new→added, completed→skip, failed→INSERT new pending, pending/in_progress→skip), return results array
- [x] 3.3 Implement `GET /mastery-history?char_id&skill_index` (last 10 rows)
- [x] 3.4 Implement `GET /mastery-route` / `POST /mastery-route`

## 4. Agent Tools

- [x] 4.1 Register `add_mastery_plan(char_id, skill_index, skill_name)` as callable agent tool
- [x] 4.2 Register `list_plans(status_filter)` as callable agent tool
- [x] 4.3 Register `set_route(profession, ordered_plan_list)` as callable agent tool
- [x] 4.4 Register `get_route(profession)` as callable agent tool
- [x] 4.5 Register `retry_plan(char_id, skill_index)` as callable agent tool

## 5. Skland Sync (5-min idle cycle in base_schedule.py)

- [x] 5.0 Implement `MasterySync` class in `arknights_mower/utils/mastery_sync.py` with `sync_and_schedule()` method, called from `base_schedule.py` idle loop (alongside drone/reload)
- [x] 5.1 Guards: check `no_pending_task(5)` and `not self.find_next_task(SKILL_UPGRADE)` before running
- [x] 5.2 Call Skland cultivate API, refresh cultivate.json
- [x] 5.3 Iterate all operators' skills[].level: auto-complete level≥3
- [x] 5.4 Check building_training.trainee → insert REFRESH_TIME if trainee present
- [x] 5.5 Pick first remaining pending plan, look up profession, read mastery_route (is_default=0), INSERT in_progress
- [x] 5.6 Push SKILL_UPGRADE task to queue head with `time=datetime.now()` (sorted by insertion order)
- [x] 5.7 If no user route for profession → INSERT failed row with reason "no mastery route configured"
- [x] 5.8 On any other error → INSERT failed row with error reason, log warning

## 6. Frontend

- [x] 6.1 `MasteryRecommendation.vue` loadPlan → GET /mastery-plan, savePlan → POST /mastery-plan
- [x] 6.2 Add "Retry Failed" button → submit all failed plans via POST /mastery-plan
- [x] 6.3 Route settings tab → GET /mastery-route and POST /mastery-route instead of localStorage
- [x] 6.4 Clear old localStorage keys on first load

## 7. Error Handling & Verification

- [x] 7.1 `skill_upgrade()` on error: INSERT failed row with failed_reason, return (no retry)
- [x] 7.2 Error if no user route for profession
- [x] 7.3 Run lint/typecheck on all changed files
