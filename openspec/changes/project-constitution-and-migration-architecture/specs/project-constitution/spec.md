## ADDED Requirements

### Requirement: Scene-Driven State Machine

All UI operations MUST use a scene-driven state machine pattern:
`while True: scene = get_scene(); if scene == A: ... elif scene == B: ...`

Each iteration MUST first determine the current scene, then decide the next action based on that scene. The `State enum + method dispatch` pattern is PROHIBITED. Reference: `solvers/base_schedule.py:generate_product()`.

#### Scenario: AI writes a new executor navigator

- **WHEN** AI implements a new executor that requires UI navigation
- **THEN** the code MUST use a `while True: scene = get_scene(); if scene == A: ...` loop structure

#### Scenario: AI refactors existing state dispatch

- **WHEN** AI encounters old code using `State enum + method dispatch`
- **THEN** the code MUST be migrated to scene-driven pattern, not kept as-is

### Requirement: Tap-Once per Iteration

Every tap/click MUST execute exactly once per loop iteration. Retry logic MUST be driven by the outer scene-driven loop (`while True: if scene == A: tap_once(); continue`). For-loop retries are PROHIBITED.

#### Scenario: AI writes a tap action handler

- **WHEN** AI implements an action handler that performs a tap
- **THEN** the handler MUST tap exactly once, and MUST NOT contain a for-loop retrying the tap

#### Scenario: Tap fails and scene unchanged

- **WHEN** a tap does not produce the expected scene transition
- **THEN** the outer scene-driven loop MUST re-detect the same scene and re-issue the tap on the next iteration

### Requirement: Task Execution Exception Isolation

Any exception during task execution MUST NOT crash the main loop. The system SHALL use `AbstractExecutor.safe_execute()` to catch and log exceptions, and the main loop SHALL continue to the next task after `pop()`.

#### Scenario: An executor throws an unexpected exception

- **WHEN** an executor's `execute()` method raises any Exception
- **THEN** `safe_execute()` MUST catch it, log the exception, and return normally; the main loop MUST pop the failed task and proceed

### Requirement: Zero Hardcoded Coordinates

Coordinates, regions, and thresholds MUST reference values from `scheduler/constants.py` or `config`. Direct numeric coordinates (e.g., `(0.35, 0.75)`) are PROHIBITED. The sole exception is `recognize.py`'s color/template_matching dictionaries (1920x1080 reference coordinates), because `Device.screencap()` guarantees 1920x1080 output.

#### Scenario: AI adds a new tap position

- **WHEN** AI needs a new screen tap location
- **THEN** the coordinate MUST be defined as a named constant in `scheduler/constants.py` (e.g., `TapPosition.XXX`)

#### Scenario: AI writes a threshold for matching

- **WHEN** AI needs a recognition threshold value
- **THEN** the value MUST be defined in `scheduler/constants.py` or sourced from config, not written inline

### Requirement: Cross-Platform from Day One

`scheduler/`, `scheduler/infra/`, `scheduler/domain/`, `scheduler/copilot/` MUST be pure Python + numpy + OpenCV with zero platform API dependencies. Platform code MUST be isolated in `utils/device/` across three layers: screencap, control, app.

All code in `scheduler/` MUST be viable for Android (Chaquopy) without modification. Specifically:
- No `subprocess`, `os.system`, or shell command execution
- No Windows-specific APIs (win32gui, win32api, ctypes.windll, CREATE_NO_WINDOW)
- File I/O MUST use relative paths or abstracted path providers; no hardcoded absolute paths
- Threading MUST use standard `threading` module (works on Android Chaquopy)
- Any state serialization MUST use cross-platform formats (JSON, SQLite via `scheduler/database/`)
- No assumptions about process management (no `taskkill`, `psutil`, process handles)

#### Scenario: AI creates a new module under scheduler/

- **WHEN** AI creates a new `.py` file under `scheduler/` or its subdirectories
- **THEN** the file MUST NOT import any platform-specific API (no `subprocess`, no `adb`, no Windows/Linux-specific calls)

#### Scenario: AI reviews code for mobile compatibility

- **WHEN** AI writes or reviews any code in `scheduler/`
- **THEN** the code MUST be verified against the mobile reusability checklist: no subprocess, no Windows APIs, no hardcoded absolute paths, standard threading only, cross-platform serialization

### Requirement: No time.sleep()

All waiting MUST use `PauseController.wait_if_paused()`. Scene stability waiting MUST use `Navigator.wait_scene_stable()` utilizing pixel-diff across consecutive screenshots. `screencap()`'s built-in `screenshot_interval` provides natural throttling. Any `import time` followed by `time.sleep()` is PROHIBITED.

#### Scenario: AI needs to wait for an animation to finish

- **WHEN** AI writes code that needs to pause execution
- **THEN** the code MUST use `PauseController.wait_if_paused()` or `Navigator.wait_scene_stable()`, not `time.sleep()`

#### Scenario: AI reviews old code with time.sleep

- **WHEN** AI encounters any `time.sleep()` call in the codebase
- **THEN** the call MUST be flagged for migration to the approved waiting mechanisms

### Requirement: Screencap Recovery, Tap/Swipe Fail-Fast

`Device.screencap()` SHALL recover from failure by restarting the simulator and retrying (unbounded `while True`). On each failure, it calls `restart_simulator()` to rebuild the connection before retrying. `tap()` and `swipe()` SHALL NOT retry; they MUST throw `DeviceError` immediately.

The rationale: screenshot failure is recoverable by simulator restart; input failure indicates the device connection is dead and needs full reconnect. Retrying a broken tap wastes time.

Note: `Recognizer.start()` wraps screencap with a bounded retry (5 attempts, then `RuntimeError`) for image decode errors specifically. The unbounded recovery in `Device.screencap()` handles ADB/simulator-level failures with restart as the recovery mechanism.

#### Scenario: AI writes screencap call

- **WHEN** AI invokes `screencap()` in executor code
- **THEN** the call MUST NOT be wrapped in try/except at the callsite; recovery is handled inside `screencap()`

#### Scenario: AI writes tap/swipe in executor

- **WHEN** AI writes `tap()` or `swipe()` in an executor
- **THEN** the calls SHOULD NOT have retry logic; failures propagate as `DeviceError` to `TaskDispatch`

### Requirement: Reconnect at Dispatch Layer

`DevicePort.reconnect()` SHALL be the single reconnection path — killing and restarting the simulator, re-establishing ADB, then continuing. Only `TaskDispatch` SHALL call `reconnect()` (on `DeviceError`). Executors MUST NOT invoke reconnect directly.

#### Scenario: Executor hits a device error

- **WHEN** an executor's `tap()` or `swipe()` raises `DeviceError`
- **THEN** `TaskDispatch.execute()` MUST catch it, call `infra.device.reconnect()`, then retry the same task from scratch

#### Scenario: AI writes reconnect logic in an executor

- **WHEN** AI considers adding reconnect calls inside an executor
- **THEN** the executor MUST throw `DeviceError` instead; reconnect is `TaskDispatch`'s responsibility

### Requirement: Multi-Resolution via Device Layer

`Device.screencap()` MUST always return 1920x1080 (internally cropping the game area and resizing). `Device.tap()` MUST convert from 1920x1080 reference coordinates to actual device pixels. Recognition and business layers MUST NOT be aware of the actual device resolution.

#### Scenario: AI works with screenshot dimensions

- **WHEN** AI accesses screencap output or calculates pixel positions in recognition code
- **THEN** the code MUST assume a 1920x1080 coordinate space, without querying or adapting to actual device resolution

### Requirement: Progressive Migration with Backward Compatibility

Old `solvers/` and `utils/` code MUST remain untouched until fully migrated to `scheduler/`. Each migration step MUST be independently committable as a standalone PR/merge.

#### Scenario: AI implements a new scheduler feature

- **WHEN** AI writes new code in `scheduler/`
- **THEN** the code MUST NOT modify any file under `solvers/` or the business logic in `utils/`

#### Scenario: A scheduler feature supersedes old code

- **WHEN** a new `scheduler/` module fully replaces an old `solvers/` module
- **THEN** the old code removal MUST be done in a separate, subsequent PR, not mixed with new code

### Requirement: Core Principles

All new code MUST follow three core principles:
1. **Simplify** — Only add what is currently needed. Do NOT add parameters, methods, or fields "for future use".
2. **Confirm before acting** — Before creating a new file, class, or method, state the intent in one sentence and wait for user confirmation.
3. **Do not modify old business logic** — `utils/` changes are limited to Device/solver layer adaptations for resolution. Core logic in recognize/image/operators is off-limits.
4. **Fix the root cause, not the symptom** — When a bug occurs, trace to the source and fix it there. Prohibited: adding retry loops, if-guards, or try/except to mask an underlying issue (e.g., a wrong coordinate, a missing template, or a misidentified scene). If the fix belongs in a different layer or requires a new capability, make that change directly rather than patching around it.

#### Scenario: AI considers adding a "future-proof" parameter

- **WHEN** AI is about to add a parameter or field that is not needed by current requirements
- **THEN** the parameter MUST NOT be added

#### Scenario: AI needs to create a new file

- **WHEN** AI determines a new file is needed
- **THEN** the AI MUST first state the intent and get user confirmation before creating the file

### Requirement: Prohibitions

The following are PROHIBITED in all code:
- Hardcoded coordinates (e.g., `(0.35, 0.75)`)
- Hardcoded thresholds (e.g., `0.6`, `24`, `3`)
- Parameters/methods/fields reserved "for future use"
- `time.sleep()` calls (see Requirement: No time.sleep())
- New code depending on `utils/device/Device` (MUST depend on `scheduler/device_port.py`'s `DevicePort` abstract interface instead)

#### Scenario: AI writes new code importing device

- **WHEN** AI creates a new module that needs device access
- **THEN** the module MUST import `DevicePort` from `scheduler.device_port`, NOT `Device` from `utils.device`

### Requirement: Data Class Boundaries

Data classes in `domain/` MAY only contain:
- Derived properties (pure field-reading, no parameters)
- Pure computation (fields + parameters, no side effects)
- String representation (`__str__`, `__repr__`)

Data classes MUST NOT contain:
- Methods with side effects (logging, file writes, network calls)
- Hardcoded game-specific values (operator names, room names)
- Cross-object logic (calling other non-derived methods)

Business logic (side effects, hardcoded values, cross-object logic) MUST live in `scheduler/services/` as stateless functions accepting domain objects as the first parameter.

#### Scenario: AI adds a method to a domain class

- **WHEN** AI considers adding a method to a class in `scheduler/domain/`
- **THEN** the method MUST NOT contain logging, file I/O, network calls, or hardcoded game values

#### Scenario: AI needs hardcoded operator names for business logic

- **WHEN** business logic requires game-specific values like operator names
- **THEN** those values MUST be placed in `scheduler/services/` functions, not in `domain/` data classes

### Requirement: File Organization and Naming

The codebase SHALL follow:
- Classes: PascalCase (`TaskQueue`, `AgentSelection`)
- Methods/variables: snake_case (`find_next_task`, `agent_list`)
- Constants: UPPER_SNAKE_CASE (`MAX_SWIPE`, `SCREEN_WIDTH`)
- No abbreviations in names
- One class per file, files under 300 lines
- Directory structure: `scheduler/domain/` (data), `scheduler/services/` (stateless logic), `scheduler/infra/` (UI primitives), `scheduler/copilot/` (combat), `scheduler/database/` (persistence)

#### Scenario: AI creates a new class file

- **WHEN** AI creates a new file in `scheduler/`
- **THEN** the file MUST contain exactly one class, be named with snake_case matching the class name, and not exceed 300 lines
