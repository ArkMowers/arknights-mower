## ADDED Requirements

### Requirement: MasteryRecommendation.vue uses API
The `MasteryRecommendation.vue` component SHALL call `GET /mastery-plan` to load plans and `POST /mastery-plan` to save plans, replacing the current in-memory/localStorage approach. The POST payload SHALL use `{"银灰": 0}` format (operator name → skill index).

#### Scenario: Load plans from API
- **WHEN** the recommendation page loads
- **THEN** it fetches `GET /mastery-plan` and renders `plans` + `history` data

#### Scenario: Save plans via API
- **WHEN** user clicks save on the recommendation page
- **THEN** it calls `POST /mastery-plan` with `{"operator_name": skill_index, ...}` and displays the results (added/skipped/retry flags)

### Requirement: Retry failed items button
The settings tab SHALL include a "Retry Failed" button that, when clicked, re-submits all `failed` plans as pending via `POST /mastery-plan`.

#### Scenario: Retry all failed
- **WHEN** user clicks "Retry Failed"
- **THEN** all plans with `status=failed` at `GET /mastery-plan` are re-submitted to `POST /mastery-plan` with `status=added` or `retry`

### Requirement: Route settings via API
The settings tab route editor SHALL read routes from `GET /mastery-route` and save via `POST /mastery-route`, replacing localStorage-based persistence.

#### Scenario: Load routes from API
- **WHEN** the route settings page loads
- **THEN** it fetches `GET /mastery-route` and populates the editor

#### Scenario: Save routes via API
- **WHEN** user saves route customizations
- **THEN** it calls `POST /mastery-route` with the route data

### Requirement: Clear old localStorage on first load
On first load after upgrade, the system SHALL clear any old localStorage keys related to mastery routes to prevent stale data.

#### Scenario: Migrate from localStorage
- **WHEN** the updated frontend loads for the first time
- **THEN** old localStorage keys for mastery routes are cleared
