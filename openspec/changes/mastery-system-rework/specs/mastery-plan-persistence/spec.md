## ADDED Requirements

### Requirement: Mastery plan table
The system SHALL maintain a `mastery_plan` table in SQLite with columns:
`id` INTEGER PRIMARY KEY AUTOINCREMENT, `char_id` TEXT NOT NULL, `skill_index` INTEGER NOT NULL, `status` TEXT NOT NULL (pending/in_progress/completed/failed), `failed_reason` TEXT, `level` INTEGER DEFAULT 1, `skill_name` TEXT, `created_at` TEXT DEFAULT datetime('now','localtime').

#### Scenario: Insert new plan
- **WHEN** user adds a new mastery plan via API
- **THEN** a new row is inserted with `status='pending'`

#### Scenario: Status transition creates new row
- **WHEN** a plan status changes (e.g., pending → in_progress → completed)
- **THEN** a new row is inserted with the new status

#### Scenario: Query current status
- **WHEN** querying current status for all plans
- **THEN** return rows with `MAX(id)` grouped by `(char_id, skill_index)`

### Requirement: No plan history pruning
The system SHALL NOT delete old `mastery_plan` rows. All status transitions accumulate for full audit trail.

#### Scenario: No deletion on insert
- **WHEN** a new status row is inserted for `(char_id, skill_index)`
- **THEN** no rows are deleted regardless of total count

### Requirement: Mastery route table
The system SHALL maintain a `mastery_route` table with columns:
`id` INTEGER PRIMARY KEY AUTOINCREMENT, `profession` TEXT NOT NULL, `supports` TEXT NOT NULL DEFAULT '{}' (full JSON blob including supports list, half_off, optimal, controlCenter), `is_default` INTEGER NOT NULL DEFAULT 0, `created_at` TEXT, UNIQUE(profession, is_default).

#### Scenario: Save user route
- **WHEN** user saves a custom route via API
- **THEN** the route is persisted with `is_default=0` for each profession

#### Scenario: Load route for profession
- **WHEN** `skill_upgrade()` needs a route for a given profession
- **THEN** the saved user route (`is_default=0`) is loaded; if none exists, the plan is marked as failed with reason "no mastery route configured"

### Requirement: MasteryDB utility module
The system SHALL implement a `MasteryDB` class in `arknights_mower/utils/mastery_db.py` that encapsulates all SQLite CRUD operations for `mastery_plan` and `mastery_route`. It SHALL use the same `@app/tmp/data.db` database as the rest of the project.

#### Scenario: Single DB connection
- **WHEN** the API layer, agent tools, or scheduler call MasteryDB methods
- **THEN** they all read/write the same `data.db` file

#### Scenario: Agent tools use MasteryDB
- **WHEN** an agent tool (e.g., `add_mastery_plan`) is invoked
- **THEN** it calls the corresponding MasteryDB method to perform the DB operation

### Requirement: Task queue insertion order
SKILL_UPGRADE tasks pushed to the queue head SHALL use `time=datetime.now()` to ensure they are sorted first by execution time, then by insertion order for ties.

#### Scenario: Schedule next plan
- **WHEN** a new SKILL_UPGRADE task is created during sync
- **THEN** `task.time = datetime.now()`, and the task is inserted at the front of the queue

### Requirement: _get_mastery_plan() reads DB
The system SHALL replace the old `matery_plan.json` read with a DB query returning the latest status row per (char_id, skill_index) WHERE status IN ('pending', 'failed').

#### Scenario: Load pending/failed plans
- **WHEN** skill_upgrade() or agent tools request the current plan list
- **THEN** return all (char_id, skill_index) pairs whose latest status is pending or failed

### Requirement: _build_route_supports() reads mastery_route
The system SHALL read the mastery_route table to determine the upgrade order for a given profession. Only user-saved routes (is_default=0) are accepted.

#### Scenario: Load user route for profession
- **WHEN** auto-schedule needs the upgrade order for an operator's profession
- **THEN** query mastery_route WHERE profession=? AND is_default=0; if empty, mark the plan as failed

### Requirement: Agent tools registration
MasteryDB methods SHALL be registered as callable agent tools:
- `add_mastery_plan(char_id, skill_index, skill_name)` — INSERT pending plan
- `list_plans(status_filter)` — return matching plans
- `set_route(profession, ordered_plan_list)` — save user route
- `get_route(profession)` — return saved route
- `retry_plan(char_id, skill_index)` — INSERT new pending row for a previously failed plan

#### Scenario: Add plan via tool
- **WHEN** agent calls add_mastery_plan
- **THEN** INSERT pending row into mastery_plan, return result

#### Scenario: List plans via tool
- **WHEN** agent calls list_plans("pending")
- **THEN** return all plans with latest status = pending
