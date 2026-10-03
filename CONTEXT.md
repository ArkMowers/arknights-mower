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
- **Definition**: A decoded, standard 1920×1080 RGB canvas matrix unified across ADB, DroidCast, MuMu IPC, and LD screenshot enhancement backends, excluding black borders or raw compressed bytes.
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
- Maintenance backups activate at a configured lead time before announced major downtime, complete the existing pre-maintenance Drone Acceleration tasks before Dynamic Shift Transition, and pause all trade order runs while their effective primary slots contain trade order agents.
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
- **Definition**: The process of restoring operator mood inside dormitories. Allocates beds by priority tiers and establishes stable single-target recovery positions. Shift return, idle release, and personal mood limits determine departures separately.
- Idle recovery planning and selection share candidates and reservations, distinguish unknown readings from verified mood, and check unknown mood in the game's ascending-mood list before retaining completed residents. Primary recovery reservations take precedence over ordinary vacancy filling; ordinary filling does not acquire concentrated-recovery protection. Crafting runs as an independent task after dormitory arrangements.
- **Rescue Recovery**: Native rescue retains average-mood evaluation and ordinary rotation rules. Intelligent rescue is disabled by default. After initial measured readings and schedule reconciliation, it starts only when required primary operators have measured mood below their personal rescue thresholds and current native rotation is infeasible; entry does not depend on historical depletion rates or future mood predictions. Mower assigns temporary workers using supported facility-local skill effects. Skland ownership and progression determine unlocked skills; missing data uses active skill icons on selection cards. Temporary assignments require card mood at least the personal normal shift-off threshold plus one. All trade order operators stay reserved, and episode recovery primaries receive no temporary working assignments before unified exit. Backup transitions and ordinary working shifts remain paused. Mood checks collect ordinary orders and manufacturing products, while normally eligible trade order runs and specialized temporary swaps continue. Recovery targets use applicable history, with the normal shift-off threshold plus one as the insufficient-history fallback. Measured target completion and feasible native rotation permit unified staffing restoration and exit.
- Intelligent rescue obtains complete automatic replacements for working groups under the frozen primary schedule. Dormitory admission follows individual recovery needs, shared priority and bed capacity, without requiring simultaneous admission of group members. Measured-ready primaries leave dormitories individually into reserved standby, receive no temporary working assignments before the episode ends, and do not trigger rescoring of temporary combinations upon recovery completion. Manager positions provide recovery capacity while Fiammetta retains her configured position. As demand falls, at most one group-recovery or shared-recovery manager per dormitory, including Bingniang, returns first. Remaining spare beds permit one single-target manager per dormitory with a restored group manager. Self-recovery managers leave those beds open, and restoration never displaces unfinished recovery primaries. Measured completion of required primary targets and feasible native rotation permit unified staffing restoration under the effective schedule; backup transitions remain frozen until that handoff.
- **Code Mapping**: [`dorm_recovery.py`](arknights_mower/utils/dorm_recovery.py), [`resting_tier`](arknights_mower/utils/resting_priority.py)
- **_Avoid_**: `Sleep queue`, `Rest list`

### Depletion Rate
- **Definition**: The per-hour mood consumption metric for operators stationed in working facilities. Base consumption is 1 point/hour; operators, facilities, and skills modify the actual rate. Mower estimates it from valid working mood readings to predict mood and shift deadlines. Mood jumps caused by Fiammetta charging are excluded.
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

### Complete Shift Convergence
- **Definition**: Before operator changes, calculate shifts, backup conditions, dorm rearrangement, and filling together until conditions and occupancy stabilize. Submit one final arrangement; new observations can require another planning pass.
- **Code Mapping**: [`BaseSchedulerSolver._prepare_shift_cycle`](arknights_mower/solvers/base_schedule.py)

### Actual and Projected Occupancy
- **Definition**: Actual occupancy records the most recently confirmed operator positions. Projected occupancy represents positions after hypothetical arrangements and does not move operators or overwrite actual position caches.
- **Code Mapping**: [`Operators.project_arrangements`](arknights_mower/utils/operators.py)

### Dormitory Bed Priority
- **Definition**: Determines bed allocation, single-target recovery allocation, and eligible preemption of lower-priority residents. Within a tier, larger mood deficits from individual upper limits rank first. Existing residents remain subject to position-preservation rules.
- **Code Mapping**: [`resting_key`](arknights_mower/utils/resting_priority.py)

### Off-Shift Candidate Order
- **Definition**: Consider operators in ascending order of current mood minus the effective lower limit, then check replacements, beds, groups, and exhaustion rules. Bed priority does not directly determine off-shift order.
- **Code Mapping**: [`BaseSchedulerSolver.resting`](arknights_mower/solvers/base_schedule.py)

### Single-Target Recovery Manager and Target
- **Definition**: Managers occupy dorm slots 1 or 2 and have the recognized single-operator recovery skill. The target occupies its final slot throughout setup. Earlier non-manager slots retain confirmed full residents or use the highest-mood eligible idle operators as padding; the remaining roster is then restored. Preserve the assignment while relevant managers and target keep their positions. The game may transfer the buff after the target becomes full.
- **Code Mapping**: [`recovery_order_plan`](arknights_mower/utils/dorm_recovery.py)

### Recovery Target and Mandatory Release Limit
- **Definition**: The recovery target is the effective mood value for completed rest, not necessarily 24. Personal limits and Ling/Xi rules can mandate dorm departure. A global upper limit defines recovery completion without requiring beds to remain vacant.
- **Code Mapping**: [`Operators.has_rest_mood_limit`](arknights_mower/utils/operators.py)

### Idle Dormitory Release and Mood-Limit Release
- **Definition**: Idle release makes resting space available under the free-room setting, exclusions, and full-occupancy fallback. Mandatory mood-limit release enforces personal limits independently of those exemptions. Departure does not itself assign work; execution verifies the original occupant still owns the bed.
- **Code Mapping**: [`BaseSchedulerSolver.prepare_release_dorm`](arknights_mower/solvers/base_schedule.py)

### Dynamic Free Slot and Vacant Bed
- **Definition**: A Free plan slot has no fixed primary occupant; a Free task placeholder delegates the occupant to selection. A vacant bed has no confirmed cached occupant and still requires reservation checks before filling.
- **Code Mapping**: [`vacant_dorm_slots`](arknights_mower/utils/dorm_candidates.py)

### Valid Mood Cache and Default Mood
- **Definition**: A valid mood cache requires a measured value, timestamp, and usable prediction. Without it, candidate screening, ordering, and primary shift selection use selection-card estimates for up to one hour: green faces map to 24, red faces to 0, and yellow faces use approximate bar values strictly between 0 and 24. Unreadable cards remain unknown. Estimates do not establish measured full recovery, sample timestamps, depletion rates, recovery deadlines, or completion at mandatory personal limits.
- **Code Mapping**: [`has_resting_mood`](arknights_mower/utils/resting_priority.py)

### Initial Mood Observation
- **Definition**: Startup reads actual room occupancy and estimates missing mood on an ordinary facility selection page before backup evaluation and cached correction. Observation does not select operators or confirm arrangements. Bounded scanning preserves partial estimates and continues startup when cards are unreadable. Normal room inspection calibrates measured mood and recovery time.
- **Code Mapping**: [`BaseSchedulerSolver._read_initial_card_mood`](arknights_mower/solvers/base_schedule.py)

### Fiammetta Charging
- **Definition**: A special sequence uses Fiammetta to restore a target operator’s mood, including temporary placements, charging, and follow-up arrangements. Suspend backup switching during the sequence. Update mood and timestamps while preserving the work depletion rate for later calibration from normal work readings.
- **Code Mapping**: [`BaseSchedulerSolver.plan_fia`](arknights_mower/solvers/base_schedule.py)
