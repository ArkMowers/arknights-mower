## ADDED Requirements

### Requirement: System Architecture Overview

The system SHALL follow a layered architecture separating the new world (`scheduler/`) from the old world (`solvers/` + `utils/`). All `scheduler/` code is pure Python (numpy + OpenCV only) and designed for Chaquopy reuse on Android without modification.

```
scheduler/                    ← New world, pure Python, Chaquopy-ready
  domain/                    ← Pure data classes
    operators.py             Operator + Dormitory + OperatorType + RestPriority
    task.py                  SchedulerTask + TaskTypes
    plan.py                  PlanConfig + Room + Plan + BaseProduct
  state.py                   SchedulerState runtime state
  queue.py                   TaskQueue (heapq priority)
  dispatch.py                TaskDispatch (register/resolve/execute)
  device_port.py             DevicePort ABC (tap/swipe/screencap/reconnect)
  graph.py                   SceneGraph (+ 88 transitions)
  navigator.py               Navigator (45 action handlers)
  scene.py                   Scene IntEnum (151 scenes)
  loop.py                    MainLoop (planner polling + task dispatch)
  hooks.py                   LifecycleHook (stub — 7 planned hooks)
  errors.py                  6 exception classes
  constants.py               Game constants + Workshop/AgentSelection enums
  bootstrap.py               Production entry point
  infra/
    pc_device_port.py        DevicePort implementation (wraps v1 Device)
    agent_selection.py       AgentSelection FSM (752 lines)
    pause_controller.py      ABC
    thread_pause.py          Threading implementation
    registry.py              STUB
  planners/                  10 planners
  executors/                 9 executors
  services/                  plan_service + task_service  
  copilot/                   Combat subsystem framework
  database/                  SQLite + repositories

utils/recognize/             Split recognition layer
  __init__.py                Recognizer (find() strategy dispatch)
```

#### Scenario: AI needs to understand where to place new code

- **WHEN** AI creates a new module
- **THEN** the module MUST be placed in the correct layer according to this architecture, with domain logic in `scheduler/domain/`, business logic in `scheduler/services/`, and platform code ONLY in `scheduler/infra/` or `utils/device/`

### Requirement: Recognition Layer Architecture

The recognition layer (`utils/recognize/`) SHALL use a three-tier strategy dispatch in `Recognizer.find()`, short-circuiting on the first successful match:

1. **ColorMatcher** — Fastest. Checks if `res` is registered in the `COLOR` constants dict. If so, crops the screenshot at the predefined (x, y) position, compares average RGB (threshold: diff ≤ 10 per channel), then verifies with SSIM (default threshold 0.9, per-resource overridable via `TEMPLATE_MATCHING_SCORE`). Returns `None` if resource not in `COLOR` dict.

2. **TemplateMatcher** — Medium. Checks if `res` is registered in `TEMPLATE_MATCHING` dict. Runs `cv2.matchTemplate(TM_CCOEFF_NORMED)` within a pre-cropped scope, then `minMaxLoc` to find best match position. Default threshold 0.9, per-resource overridable. Returns `None` if resource not in dict.

3. **FeatureMatcher** — Slowest, always runs as fallback. Uses ORB keypoints (100k features) + FLANN (LSH index, 6 tables) + Lowe's ratio test (0.7) + `cv2.estimateAffine2D` (RANSAC) for geometric verification. Final classification via 4-dimensional score (good_matches_rate, good_area_rate, aHash, SSIM) fed into a pre-trained SVM (`models/svm.model`). Supports per-resource scope/threshold overrides and DPI-aware mode for multi-resolution assets. Throws `RecognizeError` if `strict=True` and no match found.

Recognition resources are stored as template images loaded by `loadres()`. The `Recognizer.get_scene()` method (scene-driven state machine) iterates through scene detection via `find()` calls.

#### Scenario: AI adds a new scene detection

- **WHEN** AI needs to recognize a new scene or UI element
- **THEN** the recognition MUST use the existing `Recognizer.find()` dispatch; do NOT bypass it with ad-hoc matching logic

#### Scenario: AI debugs a recognition failure

- **WHEN** a resource is not being found reliably
- **THEN** the AI MUST understand which tier should match (Color → position-based, Template → template-based, Feature → ORB/SVM) and adjust constants/scope/thresholds within the existing strategy dispatch

### Requirement: Three-Layer Scheduling

The scheduling SHALL use a three-layer model:

1. **Planner** — Stateless polling with frequency + condition + make_task. Determines WHAT to do and WHEN.
2. **Dispatch** — TaskDispatch that registers executor types, resolves tasks to executors, handles DeviceError retry (x3), and wraps execution in safe_execute for exception isolation.
3. **Executor** — State machine that performs the actual UI interaction. Each executor implements a scene-driven FSM.

#### Scenario: AI implements a new scheduled task type

- **WHEN** a new type of game action needs scheduling (e.g., a new facility operation)
- **THEN** the AI MUST create both a Planner (scheduling logic) and an Executor (execution FSM), register the executor type in TaskDispatch, and connect them through SchedulerTask.type

### Requirement: InfraKit Dependency Injection

All executors SHALL receive dependencies through `InfraKit`, a dataclass containing:
- `device: DevicePort` — platform device access
- `navigator: Navigator` — scene navigation and dispatch
- `agent_selector: AgentSelection` — agent arrangement FSM
- `pause: PauseController` — pause/wait mechanism

Bootstrap SHALL assemble InfraKit:
```
v1 Device -> PCDevicePort + Recognizer
                |
          InfraKit(device, navigator, agent_selector)
                |
          MainLoop(state, planners, dispatch, infra)
                |
          dispatch.execute(task, infra)
                |
          executor_cls(infra).execute(task)
```

#### Scenario: AI creates a new executor

- **WHEN** AI implements a new executor class
- **THEN** the constructor MUST accept `InfraKit` as its only dependency and MUST NOT import or construct platform-specific implementations directly

### Requirement: LifecycleHook Chain (Planned)

The system SHALL support a chain of `LifecycleHook` events triggered by the `MainLoop`, executed sequentially. The planned 7 hooks are:

1. **Maintenance Hook** — daily base maintenance operations
2. **Daily Reset Hook** — server daily reset actions
3. **Warehouse Hook** — inventory/warehouse scanning
4. **Sanity Hook** — sanity (AP) overflow management
5. **Secret Sanctum Hook** — annihilation/secret sanctum
6. **Dormancy Hook** — inactivity/idle management
7. **Update Hook** — app update check

`LifecycleHook` is currently a stub (`scheduler/hooks.py`). Implementation is pending during Phase 1 migration.

#### Scenario: AI wires hooks into MainLoop

- **WHEN** LifecycleHook is implemented
- **THEN** hooks MUST be executed sequentially in order (1-7), each wrapped in try/except so one hook's failure does not skip subsequent hooks

### Requirement: Seven-Step Migration Roadmap

The migration SHALL follow two phases:

**Phase 1 — Complete Migration (Steps 1-5 + 7):**
```
Step 1: Architecture Redesign
  |-- Step 2: Graph / Navigation
  |     |-- Step 3: Recognition Simplification
  |           |-- Step 4: Business Logic Migration
  |                 |-- Step 5: Full Chain
  |                       |-- Step 7: Android
```

**Phase 2 — New Features (after Phase 1 stable):**
```
Step 6: Copilot (autonomous combat subsystem)
```

#### Scenario: AI plans a migration task

- **WHEN** AI creates an OpenSpec change for a migration step
- **THEN** the change MUST respect this dependency graph — for example, a Step 4 Executor migration MUST NOT be started before Step 2 Navigator is complete

### Requirement: Current Migration Status

As of the baseline, the migration status SHALL be:

| Step | Phase | Status | Notes |
|------|-------|--------|-------|
| 1 | Architecture Redesign | Complete | 21 files (domain, state, queue, dispatch, DevicePort, constants) |
| 2 | Graph / Navigation | Complete | SceneGraph (74 nodes, 133 edges), Navigator (45 handlers) |
| 3 | Recognition Split | Complete | Package structure, 3 strategies (ColorMatcher/TemplateMatcher/FeatureMatcher ORB+FLANN+SVM), SCENE_RULES (50+ rules) |
| 4 | Business Logic Migration | In progress | 9 executors (1 partial: WorkshopExecutor), 10 planners, AgentSelection FSM (752 lines) |
| 5 | Full Chain | Framework | MainLoop, LifecycleHook (stub), Database (stub) |
| 6 | Copilot | Phase 2 — deferred | Combat plan, loader, tile system, deployer interface (stable but not in Phase 1 scope) |
| 7 | Android | Planning | Not started |

#### Scenario: AI checks what still needs migration

- **WHEN** AI needs to determine the next migration task
- **THEN** the AI MUST reference this status table and prioritize incomplete executors (shift, clue, run_order, exhaust, fiammetta, correction, skill) and planner interface migrations

### Requirement: Unfinished Work Items

The following SHALL be the priority backlog:

**Executors needing migration (from `solvers/base_schedule.py`):**
- ShiftExecutor — `infra_main()` shift logic
- ClueExecutor — `clue_new()` clue exchange
- RunOrderExecutor — `run_order_solver()`
- ExhaustExecutor — exhaust-and-leave logic
- FiammettaExecutor — Fiammetta threshold
- CorrectionExecutor — correction logic
- SkillExecutor — skill mastery
- WorkshopExecutor — FSM skeleton done, needs FORMULA_SCAN item_list scanning

**Planners needing AbstractPlanner interface:**
- ShiftPlanner, ExhaustPlanner, FiammettaPlanner, OrderPlanner, IdlePlanner, BackupPlanner (old interface)
- CluePlanner, SkillPlanner (stub)

**Infra issues:**
- `infra/registry.py` — STUB
- `hooks.py` — STUB (7 LifecycleHook chain pending implementation)
- Navigator `_tap()` uses hardcoded 1920/1080
- AgentSelection has 5 hardcoded coordinates
- TaskQueue priority window sorting not yet implemented

#### Scenario: AI plans next implementation session

- **WHEN** AI starts a new coding session
- **THEN** the AI MUST select the highest-priority Phase 1 unfinished item from this list and create an OpenSpec change for it. Copilot (Step 6) is Phase 2 and SHOULD NOT be started until Phase 1 is stable.
