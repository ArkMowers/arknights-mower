# Base Infrastructure & Scheduling Subsystem Specification

Authoritative specification of the Base Infrastructure & Scheduling Subsystem, governing operator assignments, mood mechanics, dormitory allocation, shift transitions, and facility automation.

---

## 1. Domain Model & Workflow

```mermaid
flowchart TD
    Plan["Scheduling Plan (PlanModel / BackupPlan)"] --> Engine["BaseSchedulerSolver (plan_solver)"]
    Inspect["Room Inspection Interface"] --> GroundTruth["Ground-Truth Operator Mood"]
    GroundTruth --> RateCalc["Empirical Depletion Rate Calculation"]
    RateCalc --> Predictor["Exhaustion Deadline Prediction"]
    Predictor --> Engine

    Engine --> DormCheck{"Operator Mood <= Threshold?"}
    DormCheck -->|Yes| DormAlloc["Dormitory Recovery (Tiered Bed Allocation)"]
    DormCheck -->|No| WorkStation["Keep Stationed in Base Facility"]

    DormAlloc --> ManagerOrder["Dorm Manager Entry Sequence Enforcement"]
    ManagerOrder --> RestDone{"Operator Mood == Limit?"}
    RestDone -->|Yes| ShiftTransition["Dynamic Shift Transition (Return to Work Facility)"]

    Engine --> ClueModule["Clue Collection & Exchange (Party State Tracking)"]
    Engine --> DroneModule["Drone Acceleration (Trade / Manufacture Boost)"]
```

---

## 2. Core Concepts & Functional Contracts

### 2.1 Scheduling Plan (`Scheduling Plan`)
- Configures assigned primary operators, operator groups, replacements, products, and resting rules across all base facilities.
- Manages the baseline master plan (`plan1`) and condition-triggered backup plans (`backup_plans`).
- Condition triggers monitor facility state, clue party status (`party_time`), and operator exhaustion.

### 2.2 Operator Mood & Depletion Rate
- Tracks operator mood within the numerical range of 0 to 24.
- Captures ground-truth mood values during room inspection.
- Computes empirical depletion rate dynamically between consecutive inspections (`(m1 - m2) / delta_t`) rather than relying on hardcoded rates.
- Evaluates predicted exhaustion deadlines to dispatch timely dynamic shift transitions before morale depletion occurs.

### 2.3 Base Facilities
- Encapsulates distinct working facilities (Control Center, Manufacturing Station, Trading Post, Power Plant, HR Office, Reception Room, Training Room, Workshop) and resting facilities (Dormitories 1 through 4).
- Serves as the primary operational unit for operator assignment, production monitoring, and capacity validation.

### 2.4 Dormitory Recovery
- Allocates beds based on multi-tiered resting priorities: high-priority main operators, regular main operators, low-priority main operators, replacement operators, and standby operators.
- Enforces strict dorm entry order to guarantee that single-target dorm manager buffs correctly target designated priority operators.
- Releases dormitory beds automatically upon reaching operator mood limits, immediately triggering dynamic shift transitions.

### 2.5 Dynamic Shift Transition
- Replaces static timetable rotations with condition-driven transitions between work facilities and dormitories.
- Handles off-shift rotation for exhausted operators, on-shift deployment for replacements, post-rest stationing, trade order runs (Proviso, Tequila, Closure), and Fiammetta energy charges.

- Experimental ordinary shifts converge backup conditions, subsequent eligible off-shift groups, cached corrections, and final empty-bed filling in an isolated projection. Failed convergence preserves actual occupancy and the original task.
- Temporary Fiammetta dorm visits retain the measured work depletion rate; mood and sample timestamps still refresh.
- Decision record: [Complete shift convergence](../../.agents/notes/implemented/simplification/2026-09-29-complete-shift-convergence.md).

### 2.6 Clue Collection & Exchange
- Directs operators stationed in the Reception Room to gather clues 1 through 7, receive clues from friends, and gift surplus clues.
- Initiates 24-hour Clue Parties upon completing full clue sets and tracks active party state (`party_time`) to activate corresponding backup plans.

### 2.7 Drone Acceleration
- Consumes Power Plant drones (each drone deducting 3 minutes) to accelerate manufacturing lines or trading post orders.
- Deconflicts concurrent trade order runs with scheduled acceleration windows.
- Calculates precise single-unit drone counts before manufacturing product switches, preventing partial progress loss.

### 2.8 Operator Selection Verification
- Confirms a selected card by its blue border before committing a facility assignment.
- When a scrolling notice obscures the upper border, the remaining two vertical borders and the leading portion of the lower border confirm selection. Ambiguous borders retain the existing bounded recognition retry.
- The [operator selection decision](../../.agents/notes/implemented/bug-fix/2026-09-29-notice-occluded-operator-selection.md) records the failure case and verification.

---

## 3. Subsystem Invariants

- **[INV-SCHED-01] Empirical Depletion Rate**: Operator exhaustion forecasts must be derived dynamically from sequential inspection deltas rather than uncalibrated static assumptions.
- **[INV-SCHED-02] Dormitory Entry Sequence**: Dorm bed assignment must dispatch operators in strict priority tier sequence to guarantee single-target dorm buffs hit designated priority operators.
- **[INV-SCHED-03] Bed Exclusivity & Prompt Release**: Dormitory beds are strictly single-occupancy; operators reaching maximum mood must immediately release beds to unblock rotation queues.
- **[INV-SCHED-04] Shift Transition Compensation**: Condition-triggered shifts (order runs, backup plans) must preserve state rollback on failure, avoiding orphaned room assignments.
- **[INV-REC-02] Occluded Operator Selection**: A card with an obscured upper selection border is confirmed only when both vertical borders and the leading portion of its lower border are visible; adjacent card borders cannot confirm selection.
- **[INV-SCHED-05] Complete Shift Projection**: Experimental ordinary shifts submit only after backup conditions, eligible rotations, cached corrections, and final bed filling stabilize on an isolated projection; failure preserves the original task and actual occupancy.

---

## 4. Subsystem Implementation Boundaries

- Configuration parser: [`PlanModel`](../../arknights_mower/utils/config/plan.py), [`PlanConfig`](../../arknights_mower/utils/plan.py).
- Scheduler solver: [`BaseSchedulerSolver`](../../arknights_mower/solvers/base_schedule.py).
- Operator data model: [`Operator`](../../arknights_mower/utils/operators.py), [`Operators`](../../arknights_mower/utils/operators.py).
- Dormitory recovery engine: [`dorm_recovery.py`](../../arknights_mower/utils/dorm_recovery.py), [`resting_priority.py`](../../arknights_mower/utils/resting_priority.py).
- Facility acceleration: [`drone_plan`](../../arknights_mower/utils/manufacture_product.py).
