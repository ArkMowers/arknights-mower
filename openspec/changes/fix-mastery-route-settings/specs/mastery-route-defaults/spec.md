## ADDED Requirements

### Requirement: GET /mastery-route returns default routes when DB is empty
The system SHALL return default route data from `training_route.json` for any profession that has no user-saved route in the `mastery_route` table. The response SHALL include a `backups` field with the `_backups` map from `training_route.json`.

#### Scenario: DB is empty
- **WHEN** `GET /mastery-route` is called and the `mastery_route` table has no rows
- **THEN** the response SHALL contain `routes` with 8 entries (one per profession) and `backups` with 8 backup operator names

#### Scenario: DB has some user-saved routes
- **WHEN** `GET /mastery-route` is called and 3 professions have user-saved routes (`is_default=0`)
- **THEN** the response SHALL contain those 3 user-saved routes plus 5 default routes for the remaining professions

#### Scenario: Backend file load fails
- **WHEN** `training_route.json` cannot be read or parsed
- **THEN** `GET /mastery-route` SHALL return `{routes: [], backups: {}}` without a 500 error

### Requirement: POST /mastery-route stores the supports array
The system SHALL accept a `profession` string and `supports` JSON array from the request body, and store them as a row in `mastery_route` with `is_default=0`.

#### Scenario: Valid save
- **WHEN** `POST /mastery-route` receives `{profession: "近卫", supports: "[{...}]"}`
- **THEN** the supports array SHALL be stored in the `mastery_route` table, and the response SHALL be `{status: "ok"}`

#### Scenario: Missing profession
- **WHEN** `POST /mastery-route` receives a request without a `profession` field
- **THEN** the response SHALL return `{error: "profession is required"}` with status 400

### Requirement: Frontend loads route data lazily when modal opens
The frontend SHALL fetch route data from `GET /mastery-route` when the user clicks "专精路线", before the modal opens. The response's `backups` SHALL be stored in `defaultsCache._backups` for use by `newSupport()`.

#### Scenario: First time opening modal
- **WHEN** the user clicks "专精路线" and no data has been loaded yet
- **THEN** the frontend SHALL call `GET /mastery-route`, wait for the response, populate `routeSettings` and `defaultsCache`, then open the modal

#### Scenario: Subsequent opens reuse cached data
- **WHEN** the user opens the modal a second time
- **THEN** the frontend SHALL NOT re-fetch data if `defaultsCache` is already populated

### Requirement: "添加专精工具人" uses defaultsCache._backups
The `newSupport()` function SHALL look up the backup operator name from `defaultsCache._backups[profession]` to create a new support entry when the "optimal" checkbox is not checked and no higher-level reference is found.

#### Scenario: Add first support operator
- **WHEN** the user clicks "添加专精工具人" for "近卫" with empty supports and `defaultsCache._backups` containing `{"近卫": "史尔特尔"}`
- **THEN** a new support entry SHALL be added with `name: "史尔特尔"`, `skill_level: 1`, `efficiency: 60`, `swap: true`, `swap_name: "史尔特尔"`, `match: false`

#### Scenario: No backup available
- **WHEN** `defaultsCache._backups` is empty or the profession has no backup
- **THEN** `newSupport()` SHALL return `null` and the button SHALL do nothing

### Requirement: "恢复默认" restores from defaultsCache
The `resetRoute()` function SHALL restore `routeSettings` entries from `defaultsCache` for each profession that has default data.

#### Scenario: Reset to defaults
- **WHEN** the user clicks "恢复默认"
- **THEN** each profession's supports SHALL be replaced with a shallow copy of the default supports array, `half_off` SHALL be set to `true`, `optimal` SHALL be set to `false`

### Requirement: "保存" only shows success on actual saves
The `saveRoute()` function SHALL only call `message.success('已保存')` and close the modal if at least one `POST /mastery-route` request succeeded.

#### Scenario: Save with data
- **WHEN** the user clicks "保存" with 3 professions having non-empty supports
- **THEN** the frontend SHALL call `POST /mastery-route` for each profession, and show "已保存" only if at least one request succeeds

#### Scenario: Save with no data
- **WHEN** the user clicks "保存" with all professions having empty supports
- **THEN** the frontend SHALL NOT call any API, and the modal SHALL stay open without showing "已保存"

### Requirement: Error logging instead of silent catch
All API call catch blocks SHALL log errors to `console.error` instead of silently swallowing them.

#### Scenario: API call fails
- **WHEN** any `axios` call in `loadRoute()`, `saveRoute()`, or other mastery functions throws an error
- **THEN** the error SHALL be logged to `console.error` with a descriptive message
