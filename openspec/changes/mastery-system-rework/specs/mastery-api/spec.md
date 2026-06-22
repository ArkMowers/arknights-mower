## ADDED Requirements

### Requirement: GET /mastery-plan
The system SHALL return all current mastery plans with their latest status, organized as `{ plans: { "charId_skillIndex": { status, skill_name } }, history: [...] }`.

#### Scenario: Returns current plans
- **WHEN** client calls GET /mastery-plan
- **THEN** response contains `plans` object keyed by composite key with each plan's latest status and skill name, plus recent history entries

### Requirement: POST /mastery-plan
The system SHALL accept `{"银灰": 0, "史尔特尔": 1}` (operator name → skill_index) and process each entry:
- Resolve operator name to `char_id` via `skill_data.json` (reverse lookup)
- Validate `char_id` exists and `skill_index` in 0..2
- If no existing plan → INSERT pending, return `added`
- If existing `completed` → skip, return `already_completed`
- If existing `failed` → INSERT new pending row (old failed stays), return `retry`
- If existing `pending/in_progress` → skip, return `already_planned`
- Return `{ results: [{ key, status, name, skill }] }`

#### Scenario: Add new plan
- **WHEN** user submits a valid `char01_0: true` with no existing plan
- **THEN** a new `pending` row is inserted and response includes `"status": "added"`

#### Scenario: Skip completed plan
- **WHEN** user submits a plan that already has `status=completed`
- **THEN** no insert occurs and response includes `"status": "already_completed"`

#### Scenario: Retry failed plan
- **WHEN** user submits a plan that has `status=failed`
- **THEN** a new pending row is INSERTed (old failed row stays for history) and response includes `"status": "retry"`

#### Scenario: Skip already planned
- **WHEN** user submits a plan that has `status=pending` or `in_progress`
- **THEN** no change and response includes `"status": "already_planned"`

#### Scenario: Invalid operator name is skipped
- **WHEN** user submits a name not found in `skill_data.json`
- **THEN** that entry is skipped with an error in the response results

### Requirement: GET /mastery-history
The system SHALL return the last 10 status rows for a given `(char_id, skill_index)`.

#### Scenario: Query history
- **WHEN** client calls GET /mastery-history?char_id=xxx&skill_index=0
- **THEN** response contains up to 10 most recent rows ordered by id DESC

### Requirement: GET /mastery-route
The system SHALL return saved mastery routes (default + user custom), merged.

#### Scenario: Load routes
- **WHEN** client calls GET /mastery-route
- **THEN** response contains default routes and user-saved routes

### Requirement: POST /mastery-route
The system SHALL save user-customized mastery routes.

#### Scenario: Save route
- **WHEN** client calls POST /mastery-route with route data
- **THEN** the route is persisted with `is_default=0`
