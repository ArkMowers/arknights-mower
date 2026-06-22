## ADDED Requirements

### Requirement: Trigger inside base_schedule.py idle loop
The five-minute idle sync SHALL be triggered inside `base_schedule.py`'s main run loop, alongside existing periodic tasks (drone, reload, party). It SHALL use the existing `no_pending_task()` guard pattern.

#### Scenario: Trigger alongside existing periodic tasks
- **WHEN** the run loop reaches the periodic tasks section and `no_pending_task(5)` is true
- **THEN** the mastery sync cycle is eligible to run

### Requirement: Skip cycle if queue already busy
On each 5-min idle trigger, the system SHALL first check if the task queue already contains a SKILL_UPGRADE entry. If so, the entire sync cycle SHALL be skipped.

#### Scenario: Queue has SKILL_UPGRADE → skip
- **WHEN** the 5-min timer fires and the task queue contains a SKILL_UPGRADE entry
- **THEN** no cultivate.json read, no plan status changes, no REFRESH_TIME insertion, no auto-scheduling

### Requirement: Cultivate.json skills level scan
The system SHALL call the Skland cultivate API, refresh cultivate.json, and iterate all operators' skills[].level data.

#### Scenario: Auto-complete level≥3
- **WHEN** an operator in mastery_plan has status=pending and cultivate.json shows skills[].level ≥ 3
- **THEN** INSERT a new mastery_plan row with status=completed (old pending row stays for history)

#### Scenario: Skip non-level≥3
- **WHEN** an operator in mastery_plan has status=pending and cultivate.json shows skills[].level < 3
- **THEN** the plan remains pending unchanged

#### Scenario: In-progress timeout detection
- **WHEN** an operator in mastery_plan has status=in_progress but cultivate.json shows skills[].level < 3 AND building_training.trainee does not match this operator
- **THEN** INSERT a new failed row with reason "训练中断（未检测到进行中的训练）"

### Requirement: Building training REFRESH_TIME
After the cultivate.json scan, if building_training has a trainee, the system SHALL insert a REFRESH_TIME task to re-check training progress later.

#### Scenario: Insert REFRESH_TIME
- **WHEN** building_training.trainee is present
- **THEN** a REFRESH_TIME task is inserted into the queue

### Requirement: Auto-schedule next pending plan
The system SHALL pick the first remaining pending plan, look up its profession, read the user's mastery_route (is_default=0) for that profession, INSERT in_progress, and push a SKILL_UPGRADE task to the queue head.

#### Scenario: Schedule next plan
- **WHEN** pending plans remain after level≥3 cleanup and REFRESH_TIME insertion
- **THEN** the first pending plan is processed: INSERT in_progress + SKILL_UPGRADE task at queue head

#### Scenario: Missing route → failed
- **WHEN** no user-saved route (is_default=0) exists for the operator's profession
- **THEN** the plan is INSERTed as failed with reason "no mastery route configured for {profession}"

#### Scenario: Processing error → failed
- **WHEN** any step errors (DB write, route read, task insert)
- **THEN** the plan is INSERTed as failed with the error reason; the cycle stops for this plan

#### Scenario: No pending → end
- **WHEN** all pending plans are either completed or failed
- **THEN** the cycle ends with no SKILL_UPGRADE task queued
