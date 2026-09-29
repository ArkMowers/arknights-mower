# Arknights Mower Domain Glossary

[English](CONTEXT.md) | [中文](CONTEXT.zh.md)

Authoritative domain terminology, code mappings, and invariants for Arknights Mower. All architecture notes, specifications, code, and agent communications adhere strictly to these definitions.

---

## 1. Device & Transport Domain

### Device Profile
- **Definition**: The user's explicit, persisted device configuration selecting target simulator preset, paths, identity keys, and capture/touch backends, strictly isolated from transient runtime states.
- **Code Mapping**: [`DeviceProfile`](arknights_mower/utils/config/device_profile.py), [`Conf.device`](arknights_mower/utils/config/device_profile.py)
- **_Avoid_**: `Device runtime state`, `Discovery candidate`, `Active connection`

### Instance Binding
- **Definition**: An immutable association to a specific simulator instance identity that strictly maintains target uniqueness upon disconnection or restart, preventing silent fallback or target drift.
- **Code Mapping**: [`DeviceSession.bind()`](arknights_mower/utils/device/session.py), [`DeviceSession.target_serial`](arknights_mower/utils/device/session.py)
- **_Avoid_**: `Dynamic device selection`, `Floating target`, `Auto fallback`

### Readiness Verdict
- **Definition**: A structured classification of device and transport readiness states (`absent`, `offline`, `booting`, `ready`) providing actionable status codes and remedy guidance.
- **Code Mapping**: [`ReadinessResult`](arknights_mower/utils/device/session.py), [`DeviceSession.readiness`](arknights_mower/utils/device/session.py)
- **_Avoid_**: `Raw exception`, `Unformatted error string`

### Recovery Budget
- **Definition**: A finite, monotonic deadline budget and retry limit for reconnecting, waiting for boot completion, or restarting a confirmed instance, preventing unbounded retry loops.
- **Code Mapping**: [`RecoveryPolicy`](arknights_mower/utils/device/session.py), `recovery_timeout`, `recovery_attempts`
- **_Avoid_**: `Infinite retry`, `Unconstrained loop`, `Background sleep`

### Topology Fingerprint
- **Definition**: A deterministic cryptographic hash or configuration identity extracted from VM configurations used to stably verify instance identity across port shifts and index changes.
- **Code Mapping**: `topology_fingerprint`, `instance_name`
- **_Avoid_**: `Vague identifier`, `Simulator metadata`, `Transient serial`

### Temporary Preparation
- **Definition**: A single-session resolution and density override applied to physical Android devices with guaranteed compensation restoring original display geometry on shutdown or error.
- **Code Mapping**: [`PreparationSession`](arknights_mower/utils/device/preparation.py), `restore_screen_resolution`
- **_Avoid_**: `Permanent configuration`, `Unmanaged resolution change`

### Capture Frame
- **Definition**: A decoded, standard 1920×1080 RGB canvas matrix unified across ADB, DroidCast, and MuMu IPC backends, excluding black borders or raw compressed bytes.
- **Code Mapping**: `CanvasFrame`, `FrameBuffer`
- **_Avoid_**: `Scaled preview`, `Raw stream byte`

### Shared ADB Guard
- **Definition**: A service governance mechanism probing shared ADB server status via socket-level handshakes and strictly prohibiting implicit `kill-server` invocations to safely coexist with other debug tools.
- **Code Mapping**: [`guard_adb`](arknights_mower/utils/device/adb_client/server.py), [`probe_adb_server`](arknights_mower/utils/device/adb_client/server.py)
- **_Avoid_**: `Direct kill-server`, `Unguarded CLI call`

---

## 2. Facility & Scheduling Domain

### Scheduling Plan
- **Definition**: The declarative configuration specifying assigned primary operators, operator groups, replacements, facility products, and rest/shift rules. Contains baseline master plan (`plan1`) and condition-triggered backup plans (`backup_plans`).
- **Code Mapping**: [`PlanModel`](arknights_mower/utils/config/plan.py), [`Plan1`](arknights_mower/utils/config/plan.py), [`BackupPlan`](arknights_mower/utils/config/plan.py)
- **_Avoid_**: `Task script`, `Macro`, `Work plan`

### Operator Mood
- **Definition**: The numerical stamina metric (0 to 24) tracking operator working and resting states. Consumed in facilities and restored in dormitories. Active skills deactivate upon reaching morale depletion at 0 mood.
- **Code Mapping**: [`Operator.mood`](arknights_mower/utils/operators.py), [`Operator.current_mood()`](arknights_mower/utils/operators.py)
- **_Avoid_**: `Physical energy`, `Fatigue level`

### Base Facility
- **Definition**: Distinct functional rooms with assignable slots in the Rhode Island infrastructure. Classified into working facilities (Control Center, Manufacturing, Trading, Power, Office, Reception, Training, Workshop) and resting facilities (Dormitories 1-4).
- **Code Mapping**: [`Facility`](arknights_mower/utils/config/plan.py), [`base_room_list`](arknights_mower/data/__init__.py)
- **_Avoid_**: `Building slot`, `Isolated room`

### Dormitory Recovery
- **Definition**: The process of restoring operator mood inside dormitories. Allocates beds by priority tiers, enforces entry sequence for single-target dorm manager buffs, and releases beds upon reaching mood limits.
- **Code Mapping**: [`dorm_recovery.py`](arknights_mower/utils/dorm_recovery.py), [`resting_tier`](arknights_mower/utils/resting_priority.py)
- **_Avoid_**: `Sleep queue`, `Rest list`

### Depletion Rate
- **Definition**: The per-hour mood consumption metric for operators stationed in working facilities. Baseline is 1.0 point/hour, calculated dynamically from empirical differences between readings to predict exhaustion deadlines.
- **Code Mapping**: [`Operator.depletion_rate`](arknights_mower/utils/operators.py)
- **_Avoid_**: `Drain speed`, `Depletion cost`

### Dynamic Shift Transition
- **Definition**: The event- and condition-driven rotation mechanism executing operator replacements between facilities and dormitories. Includes off-shift rest, on-shift replacements, post-rest stationing, and specialized task triggers.
- **Code Mapping**: [`TaskTypes.SHIFT_OFF`](arknights_mower/utils/scheduler_task.py), [`BaseSchedulerSolver.plan_solver`](arknights_mower/solvers/base_schedule.py)
- **_Avoid_**: `Fixed timetable swap`, `Static worker cycle`

### Clue Collection & Exchange
- **Definition**: The workflow of assigning operators to the Reception Room to gather clues 1-7, receive and gift clues with friends, and host 24-hour Clue Parties upon completing full sets for credit rewards.
- **Code Mapping**: [`Operators.clues`](arknights_mower/utils/operators.py), [`CreditSolver`](arknights_mower/solvers/credit.py)
- **_Avoid_**: `Party mode`, `Clue trade`

### Drone Acceleration
- **Definition**: The mechanism of consuming base drones recharged by Power Plants (1 drone = 3 minutes deduction) to accelerate production or trade orders.
- **Code Mapping**: [`drone_plan`](arknights_mower/utils/manufacture_product.py), [`DRONE_SECONDS`](arknights_mower/utils/manufacture_product.py)
- **_Avoid_**: `Speed up`, `Drone boost`
