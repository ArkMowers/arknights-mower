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
- Backup operator lists add entries to the effective Scheduling Plan; per-field removal lists remove entries after additions, in backup order. Deactivation rebuilds the effective lists from the main plan and remaining active backups.
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
- Dormitory isolation stores multiple operator groups without a member-count limit and prefers fewer same-group roommates during admission projection. Recovery priority, single-target beds, existing residents and reservations take precedence; unavoidable cohabitation is accepted without post-admission isolation correction.
- Ordinary idle operators remain eligible replacements for working or grouped dormitory positions. Primary-to-primary replacements are permitted only within the same nonempty group when at least one primary belongs to a grouped dormitory position, preserving both primary identities. Replacements between two working primaries and self-replacements are prohibited. A working primary in its same-group fixed dormitory replacement position receives recovery and return timing without opening that position as an ordinary Free bed. Grouped dormitory members neither trigger exhausted shifts nor require additional recovery beds, but participate in complete arrangements and single-target recovery confirmation.
- Completed exhausted shifts consider non-dormitory, non-workaholic group members only; grouped dormitory residents do not block completion.
- Idle recovery planning and selection share candidates and reservations, distinguish unknown readings from verified mood, and check unknown mood in the game's ascending-mood list before retaining completed residents. Primary recovery reservations take precedence over ordinary vacancy filling; ordinary filling does not acquire concentrated-recovery protection. Crafting runs as an independent task after dormitory arrangements.
- **Rescue Recovery**: Native rescue retains average-mood evaluation and ordinary rotation rules. Automatic rescue is disabled by default. After initial measured readings and schedule reconciliation, automatic rescue starts only when primaries in at least two distinct recovery groups have mood below their personal rescue thresholds, using measured readings when available and valid card estimates otherwise, at least one primary is waiting to rest, and current native rotation cannot arrange rest for the waiting primaries; entry does not depend on historical depletion rates or future mood predictions. Card estimates are used only for initial admission and native-rotation feasibility projections; they do not overwrite measured records or confirm recovery completion or rescue exit. Bound schedule groups count once, ungrouped primaries count individually, and resting groups still below their rescue thresholds count toward recovery contention. The workshop and training room retain their existing specialized tasks. Operators shared with the normal primary roster are reported at startup and remain assigned according to the rescue schedule. Normal backup-plan transitions remain frozen during recovery. Temporary assignments require card mood at least the personal normal shift-off threshold plus one. Episode recovery primaries receive no temporary working assignments before unified exit. Backup transitions and ordinary working shifts remain paused. Mood checks collect ordinary orders and manufacturing products, while normally eligible trade order runs and specialized temporary swaps continue. Recovery targets use applicable history, with the normal shift-off threshold as the insufficient-history fallback. Rescue staffing accepts known zero mood and uses normal grouping, shift-off thresholds and complete replacement matching. Rescue workers leave as a group after complete replacements are available when a member falls below their personal rescue threshold. Departing workers configured in the normal main plan, including replacement lists, may recover in Free beds under normal priorities while specialized reservations remain protected. Rescue bed planning preserves explicit priorities and uses bounded handoff projections to favor recovery combinations that unblock exit within the same priority tier. Without reliable recovery rates, remaining mood deficits estimate recovery effort rather than guaranteeing the shortest time; actual exit still requires measured verification. Rescue zero-mood worker and dormitory blacklist entries append using backup-plan rules; explicit dormitory priority order overrides the preceding setting. Unknown mood, reservation conflicts and the mood checks of crafting and mastery tasks remain enforced. Automatic rescue enters handoff when measured-ready primaries can return, unfinished groups have complete replacement and bed coverage, and no staffing conflicts or unfinished specialized compensation remain. It ends after actual staffing is verified. Exit does not require forecasting the next rotation; unknown recovery timing or work depletion rates alone do not block exit. Handoff bed coverage uses available beds in the effective normal schedule, excluding fixed manager slots temporarily opened by rescue. Operators configured as standby in the normal schedule use their personal rescue thresholds as rescue recovery targets; measured mood at or above that threshold satisfies recovery demand. Full-recovery requirements retain personal mood caps. Exhaustion workers and their groups do not enter rescue contention solely by falling below ordinary rescue thresholds. They participate according to current recovery demand when already resting, at their personal mood floor, or when an existing exhaustion shift-off task is due. Rescue training-room deployment retains trainee and assistant protections without requiring mood readings from the training selection screen.
- Automatic rescue independently configures workers, trade order operators, dormitory managers, and Fiammetta’s position and charging targets through its main and backup plans. Unconfigured specialized tasks do not inherit the normal schedule’s configuration. Free beds prioritize normal primary operators, with members of the same group preferentially resting together. Spare beds may admit replacements or other idle operators below full mood according to normal scheduling priorities. Managers yield beds as recovery requires; as demand falls, each dormitory restores one group-recovery manager first, then one single-target manager if capacity remains. Rescue may end when the normal schedule can cover groups that still need rest and sustain rotation, without every group reaching its recovery target. Unrecovered groups continue resting while other positions return to the normal schedule.
- Automatic rescue prioritizes beds for normal primaries requiring recovery. Fiammetta yields her bed when a primary is waiting for a bed. Spare capacity is assigned to Fiammetta, group-recovery managers, single-target managers, then other fillers, in that order. Fiammetta returns to her configured rescue position. This rule does not depend on charging targets reaching their recovery targets.
- Workshop and training-room assignments in the rescue schedule participate in staffing deployment. Crafting and mastery retain their existing task flows, and training-room staffing respects existing trainee and assistant protection rules.
- During automatic rescue, daily tasks, clues, drones and replenishment retain normal scheduling intervals and task time budgets instead of being disabled by rescue state. Measured-ready departures and feasible bed filling in the same round share a final dormitory arrangement, preserving personal mood-limit releases and specialized compensation. Operators configured for full recovery in the normal schedule retain their personal mood caps as recovery targets during rescue.
- Predicted automatic-rescue recovery tasks reuse idle recovery’s task-merging logic and merge-interval setting, while execution still verifies each operator’s measured mood against their recovery target.
- The automatic rescue checkbox and rescue schedule entry are located in the infrastructure section of Mower settings and are excluded from normal schedule imports and exports. Before automatic rescue starts, current conditions determine the active backup plans of both the normal and rescue schedules. Final working-facility types, levels and products must match; any mismatch identifies the facility and difference and retains normal scheduling. Static validation without runtime backup conditions does not infer incompatibility from main-plan differences; entry is decided from effective schedules after initial observations.
- **Code Mapping**: [`dorm_recovery.py`](arknights_mower/utils/dorm_recovery.py), [`resting_tier`](arknights_mower/utils/resting_priority.py)
- **_Avoid_**: `Sleep queue`, `Rest list`

### Depletion Rate
- **Definition**: The per-hour mood consumption metric for operators stationed in working facilities. Base consumption is 1 point/hour; operators, facilities, and skills modify the actual rate. Mower estimates it from valid working mood readings to predict mood and shift deadlines. Mood jumps caused by Fiammetta charging are excluded.
- **Code Mapping**: [`Operator.depletion_rate`](arknights_mower/utils/operators.py)
- **_Avoid_**: `Drain speed`, `Depletion cost`

### Dynamic Shift Transition
- **Definition**: The event- and condition-driven rotation mechanism executing operator replacements between facilities and dormitories. Includes off-shift rest, on-shift replacements, post-rest stationing, and specialized task triggers.
- A successful backup-plan activation or deactivation invalidates a pending dynamically generated exhausted-shift deadline only when its operators’ effective staffing or exhaustion settings change; normal planning rebuilds affected deadlines from the effective schedule and confirmed occupancy.
- **Code Mapping**: [`TaskTypes.SHIFT_OFF`](arknights_mower/utils/scheduler_task.py), [`BaseSchedulerSolver.plan_solver`](arknights_mower/solvers/base_schedule.py)
- On backup plan entry or exit, relocating the same primary between slots of the same facility type with unchanged group bindings prefers to preserve its rest state, recovery bed and return deadline, assigning available replacements to the destination. Replacement shortages retain the constrained primary recall rules. Restoring a slot on backup exit does not force its primary back to work; explicit staffing tasks on backup entry retain their specified behavior.
- **_Avoid_**: `Fixed timetable swap`, `Static worker cycle`
- Each binding of an operator assigned to multiple groups specifies its own group and replacements; the operator follows the latest triggered group with that binding’s replacements and does not contribute to group mood statistics, off-shift triggers or return deadlines.
- When primary operators, group bindings and facility types remain unchanged, backup product or replacement-list changes prefer to preserve primary shift states, recovery beds and return deadlines. Available replacements take priority; replacement shortages allow the corresponding primaries to return early from rest. Recalls respect task reservations, mastery protection and slot occupancy; infeasible arrangements defer the transition, while explicit staffing tasks retain their specified behavior.

### Clue Collection & Exchange
- **Definition**: The workflow of assigning operators to the Reception Room to gather clues 1-7, receive and gift clues with friends, and host 24-hour Clue Parties upon completing full sets for credit rewards.
- **Code Mapping**: [`Operators.clues`](arknights_mower/utils/operators.py), [`CreditSolver`](arknights_mower/solvers/credit.py)
- **_Avoid_**: `Party mode`, `Clue trade`

### Drone Acceleration
- Disabling automatic product and order switching hides and disables Grandet product switching and its other settings, skips manufacturing product and trade order-type changes and related facility-state reads, and hides the corresponding backup-condition choices. Ordinary shifts, product collection and Grandet order runs retain their existing behavior.
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
- While automatic mastery crafting is active, candidates first follow existing dormitory priorities. Only positions occupied by ordinary idle crafting operators are reordered by interleaving non-T5, T5 and skill-summary lists at matching indices, retaining each name’s first occurrence. Other operators’ ranking positions, staffing identities, fixed dormitory positions, exclusions and reservations remain unchanged.
- **Code Mapping**: [`resting_key`](arknights_mower/utils/resting_priority.py)

### Off-Shift Candidate Order
- **Definition**: Consider operators in ascending order of current mood minus the effective lower limit, then check replacements, beds, groups, and exhaustion rules. Bed priority does not directly determine off-shift order.
- **Code Mapping**: [`BaseSchedulerSolver.resting`](arknights_mower/solvers/base_schedule.py)

### Single-Target Recovery Manager and Target
- **Definition**: Managers occupy dorm slots 1 or 2 and have the recognized single-operator recovery skill. The target occupies its final slot throughout setup. Earlier non-manager slots retain confirmed full residents or use the highest-mood eligible idle operators as padding; the remaining roster is then restored. Preserve the assignment while relevant managers and target keep their positions. The game may transfer the buff after the target becomes full. Fiammetta never becomes a single-target recovery recipient; recovery setup preserves her existing position before the target regardless of mood.
- Existing single-target recovery residents do not proactively reorder among themselves. A new arrival may preempt a lower-priority target; the displaced resident continues competing for subsequent lower-priority targets until reaching a vacancy or finding no eligible target. Equal tiers do not preempt. Ordinary departures still fill vacated targets from eligible non-target residents across dormitories and current arrivals, preferring local residents within a tier. Reserved and protected positions do not participate; mood changes without admission or departure do not relocate residents.
- When filling a vacant single-target slot, candidates in the same priority tier prefer residents of that dormitory before comparing mood deficits; higher-priority candidates from other dormitories still take precedence.
- **Code Mapping**: [`recovery_order_plan`](arknights_mower/utils/dorm_recovery.py)

### Recovery Target and Mandatory Release Limit
- **Definition**: The recovery target is the effective mood value for completed rest, not necessarily 24. Personal limits and Ling/Xi rules can mandate dorm departure. A global upper limit defines recovery completion without requiring beds to remain vacant.
- **Code Mapping**: [`Operators.has_rest_mood_limit`](arknights_mower/utils/operators.py)

### Idle Dormitory Release and Mood-Limit Release
- **Definition**: Idle release makes resting space available under the free-room setting, exclusions, and full-occupancy fallback. Mandatory mood-limit release enforces personal limits independently of those exemptions. Departure does not itself assign work; execution verifies the original occupant still owns the bed.
- When a grouped operator yields a bed after reaching their personal recovery cap, they remain idle if unfinished group members are still resting. This departure does not recall the group; ordinary return rules continue to determine group return.
- Group recovery spread is the difference between the latest and earliest predicted recovery completion times among members participating in ordinary return timing. Its delayed-return threshold is configurable in advanced plan settings and defaults to 60 minutes; the existing extra-wait limit remains enforced.
- **Switch Boundary**: The free-room setting controls only ordinary full-mood release task creation.
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
- After initial observations, fully recovered Fiammetta with configured charging targets completes charging and staffing restoration before ordinary post-initialization scheduling and automatic rescue evaluation. Personal mood-limit releases and due critical tasks retain their existing protection rules.
- **Code Mapping**: [`BaseSchedulerSolver.plan_fia`](arknights_mower/solvers/base_schedule.py)

- During automatic rescue, when all configured Fiammetta charging targets have full mood, eligible normal primary operators without special mood caps or reservation conflicts may be selected in ascending mood order under existing charging rules.
