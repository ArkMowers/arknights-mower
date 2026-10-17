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
- Different mastery skills of the same operator run consecutively when at least one has reached mastery one, starting only when shared stock and permitted crafting cover their joint remaining costs, while preparing materials for the current skill only; subsequent training above mastery one inherits halving. Halving handoffs default to a ten-minute margin; only relevant operators actually entering or leaving the Control Center refresh the observed training countdown, and moves between other facilities do not trigger a refresh.
- Backup operator lists add entries to the effective Scheduling Plan; per-field removal lists remove entries after additions, in backup order. Deactivation rebuilds the effective lists from the main plan and remaining active backups.
- **Definition**: The declarative configuration specifying assigned primary operators, operator groups, replacements, facility products, and rest/shift rules. Contains baseline master plan (`plan1`) and condition-triggered backup plans (`backup_plans`).
- Maintenance backups activate at a configured lead time before announced major downtime. When their effective primary slots contain trade order agents, entry first completes one Drone Acceleration run with other trade order agents configured as their replacements and restores the original roster, then activates the maintenance primaries and pauses all trade order runs; without such replacements, entry switches directly. Otherwise, entry completes the existing pre-maintenance Drone Acceleration tasks before Dynamic Shift Transition.
- **Code Mapping**: [`PlanModel`](arknights_mower/utils/config/plan.py), [`Plan1`](arknights_mower/utils/config/plan.py), [`BackupPlan`](arknights_mower/utils/config/plan.py)
- **_Avoid_**: `Task script`, `Macro`, `Work plan`

### Trust Rotation
- **Definition**: Periodic inspection of base assistants and built activity-room occupants during daily tasks. Incumbents remain until 200% by default. With the threshold enabled, an incumbent at or above X% yields to an eligible same-kind candidate below X%; otherwise it remains until 200%. Assistant and activity-room rosters each exclude their own incumbents, permit cross-kind overlap and preserve ordinary working or resting state. Replacements prefer operators below the enabled threshold, then the lowest trust below 200%. When an ascending-trust roster confirms that all operators have 200% trust, current assignments remain and the remaining facilities are skipped for that inspection.

### Operator Mood
- **Definition**: The numerical stamina metric (0 to 24) tracking operator working and resting states. Consumed in facilities and restored in dormitories. Active skills deactivate upon reaching morale depletion at 0 mood.
- Automatic growth crafting requires known positive Operator Mood sufficient for one batch; ordinary manual-configured admission retains its greater-than-22 threshold. Operator reservations remain binding.
- **Code Mapping**: [`Operator.mood`](arknights_mower/utils/operators.py), [`Operator.current_mood()`](arknights_mower/utils/operators.py)
- **_Avoid_**: `Physical energy`, `Fatigue level`

### Base Facility
- Recycling collection statistics preserve the collection time, observed recycling-facility occupants and recognized material quantities. Sanity-value comparisons use the supplied calculator’s probability snapshot and the active saved material-valuation snapshot at equal material counts; unknown observations remain unknown.
- **Definition**: Distinct functional rooms with assignable slots in the Rhode Island infrastructure. Classified into working facilities (Control Center, Manufacturing, Trading, Power, Office, Reception, Training, Workshop, Recycling) and resting facilities (Dormitories 1-4).
- **Code Mapping**: [`Facility`](arknights_mower/utils/config/plan.py), [`base_room_list`](arknights_mower/data/__init__.py)
- **_Avoid_**: `Building slot`, `Isolated room`

### Dormitory Recovery
- Dormitories have no minimum manager count; recovery capacity follows effective Free positions.
- **Definition**: The process of restoring operator mood inside dormitories. Allocates beds by priority tiers and establishes stable single-target recovery positions. Shift return, idle release, and personal mood limits determine departures separately.
- Dormitory isolation stores multiple operator groups without a member-count limit and prioritizes fewer same-group roommates during admission projection. It may exchange dynamic-bed residents and move a new single-target recipient to an ordinary bed. Among equally isolated arrangements, recovery tiers determine bed allocation. Fixed staffing, existing single-target-bed residents and reservations remain protected; unavoidable cohabitation is accepted without post-admission isolation correction.
- Ordinary idle operators remain eligible replacements for working or grouped dormitory positions. Primary-to-primary replacements are permitted only between distinct primaries within the same nonempty configured group regardless of facility type, preserving both primary identities. Self-replacements are prohibited. Dynamic bed demand counts only required recovering primaries not selected as replacements in the complete assignment; working covers remain at work, and fixed dormitory covers use their assigned recovery positions. A working primary in its same-group fixed dormitory replacement position receives recovery and return timing without opening that position as an ordinary Free bed. Grouped dormitory members neither trigger exhausted shifts nor require additional recovery beds, but participate in complete arrangements and single-target recovery confirmation.
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
- Each group records its confirmed on/off-shift state. Groups sharing a primary can rest concurrently when every shared slot has a common available replacement; otherwise the new group waits. Shared primaries retain their replacements until the last dependent group returns, and contribute no group mood, off-shift trigger or return deadline. Shared primaries configured to work at zero mood require no recovery bed. Planning and failed execution do not commit live group state.
- When primary operators, group bindings and facility types remain unchanged, backup product or replacement-list changes prefer to preserve primary shift states, recovery beds and return deadlines. Available replacements take priority; replacement shortages allow the corresponding primaries to return early from rest. Recalls respect task reservations, mastery protection and slot occupancy; infeasible arrangements defer the transition, while explicit staffing tasks retain their specified behavior.
- The thirty-minute return window starts at the first planning pass of a recovery episode and does not restart on replanning; changed staffing targets or recovery positions start a new window, while full-recovery rules and task reservations remain binding.
- Facility arrangement tasks must not exceed the slot count of the current facility roster; excess named operators or placeholders (including Current) produce an explicit error and stop automation, preserving the original task without retry or silent truncation.
- Backup plans preserve the primary production facility types and slot counts; manufacturing and trading facility levels are validated by slot count. When automatic product and order switching is disabled, backup plans cannot specify product or order targets that differ from the primary plan. Explicit staffing tasks cannot exceed primary slot counts, including Current placeholders. These conflicts produce explicit errors before combination analysis and prevent startup.
- Automatic product and order switching defaults to disabled; legacy configurations without the switch are treated as disabled, while explicitly saved enabled states remain enabled.

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
- Occupied beds of explicitly prioritized operators, normal primaries, low-priority primaries and priority replacements cannot be taken over by other recovery applicants. These four tiers may take over beds occupied by standby primaries, ordinary replacements or idle operators. Standby primaries may take over ordinary replacement and idle beds, and ordinary replacements may take over idle beds; applicants in these two tiers require a valid mood reading and current mood no greater than 80% of their own mood upper limit. Applicants do not take over beds within the same tier. Tier order continues to govern vacant-bed and single-target position allocation; ordinary returns, ordinary full-mood releases, mandatory personal-limit departures and explicit staffing tasks retain their respective rules.
- Dormitory priority defaults to 1, 2, 3, 4, representing each dormitory’s high-priority bed. Users can insert low-priority options for individual dormitories; omitted low-priority options come last. Backup transitions that change the effective order, or changes in single-target ownership, reallocate movable residents by recovery tier and personal mood deficit; otherwise existing residents retain their positions. Admission isolation takes precedence over bed order, same-tier mood deficits and ordinary-resident retention. Among equally isolated arrangements, recovery tiers continue to govern allocation; fixed staffing, existing single-target-bed residents and reservations remain protected.
- While automatic mastery crafting is active, candidates first follow existing dormitory priorities. Only positions occupied by ordinary idle crafting operators are reordered by interleaving non-T5, T5 and skill-summary lists at matching indices, retaining each name’s first occurrence. Other operators’ ranking positions, staffing identities, fixed dormitory positions, exclusions and reservations remain unchanged.
- **Code Mapping**: [`resting_key`](arknights_mower/utils/resting_priority.py)

### Off-Shift Candidate Order
- **Definition**: Consider operators in ascending order of current mood minus the effective lower limit, then check replacements, beds, groups, and exhaustion rules. Bed priority does not directly determine off-shift order.
- **Code Mapping**: [`BaseSchedulerSolver.resting`](arknights_mower/solvers/base_schedule.py)

### Single-Target Recovery Manager and Target
- **Definition**: Recovery setup checks all five dormitory slots and selects only the first operator with a single-target recovery skill as its manager; without one, extra recovery setup is skipped. The target occupies its final slot throughout setup. Before the target, operators with single-target recovery skills and Fiammetta retain their positions regardless of mood. Other preceding slots retain full-mood residents or use eligible full-mood idle operators without single-target recovery skills as padding; a green smiley on a selection card counts as full mood without an additional numeric reading. Roster readback precedes recovery confirmation and restoration of the remaining roster; insufficient eligible padding prevents confirmation. Operators with single-target recovery skills are not actively assigned a locked target position; they prefer ordinary beds or single-Free dormitories in configured order. A sole eligible unfinished resident may receive another operator’s single-target recovery, but never their own skill. A valid ordinary target remains until full recovery, departure or manager change, after which the game selects the eligible resident with the lowest mood. Fiammetta never becomes a single-target recovery recipient; recovery setup preserves her existing position before the target regardless of mood.
- Admission, departure or recovery-configuration changes allocate movable residents by recovery tier and complete configured bed order. Explicit ordinary-position options retain independent order and may precede single-target positions; omitted ordinary positions follow single-target positions in configured dormitory order. While single-target ownership is unchanged, existing equal-tier targets and same-room ordinary residents retain positions where compatible with tier allocation. When ownership changes, all movable same-tier residents compare mood deficits from personal upper limits; idle crafting candidates retain crafting order. Mood changes alone do not relocate residents, and each release batch uses one allocation. Admission isolation may override this position allocation; among equally isolated arrangements, single-target recipients follow recovery tiers. Full-mood fillers do not move merely to fill faster vacancies. Reservations, fixed replacements, protected positions and mandatory personal-limit departures remain binding.
- Actual dormitory composition changes require fresh recovery-time observations for every recovery bed in the room, including stationary residents and fixed replacement recovery positions. Changed single-target recipients or managers require renewed recovery confirmation; final-roster observations precede rebuilding completion, release and return tasks. Failure retries also refresh timing. Projections invalidate old deadlines only in their copies without writing actual positions, mood or recovery observations.
- **Code Mapping**: [`recovery_order_plan`](arknights_mower/utils/dorm_recovery.py)

### Recovery Target and Mandatory Release Limit
- **Definition**: The recovery target is the effective mood value for completed rest, not necessarily 24. Personal limits and Ling/Xi rules can mandate dorm departure. A global upper limit defines recovery completion without requiring beds to remain vacant.
- **Code Mapping**: [`Operators.has_rest_mood_limit`](arknights_mower/utils/operators.py)

### Idle Dormitory Release and Mood-Limit Release
- **Definition**: Idle release makes resting space available under the free-room setting, exclusions, and full-occupancy fallback. Mandatory mood-limit release enforces personal limits independently of those exemptions. Departure does not itself assign work; execution verifies the original occupant still owns the bed.
- When a grouped operator yields a bed after reaching their personal recovery cap, they remain idle if unfinished group members are still resting. This departure does not recall the group; ordinary return rules continue to determine group return.
- Group recovery spread compares the latest and earliest predicted recovery completion times of non-standby working primaries bound to this group alone. Its delayed-return threshold is configurable in advanced plan settings and defaults to 75 minutes. Once triggered, this cycle waits for all such primaries to recover fully. All working primaries explicitly requiring full recovery must also finish, including low-priority and shared primaries. These requirements accumulate; the extra-wait cap applies only to spread-triggered waiting. Zero means unlimited, and explicit full-recovery requirements are never shortened by the cap. Execution may accept observed recovery within the existing dormitory-operation allowance, while personal-cap release retains its scheduled advance; standby operators, replacements, fixed dormitory managers and workaholics do not extend the group wait.
- **Switch Boundary**: The free-room setting controls only ordinary full-mood release task creation.
- **Code Mapping**: [`BaseSchedulerSolver.prepare_release_dorm`](arknights_mower/solvers/base_schedule.py)

### Dynamic Free Slot and Vacant Bed
- **Definition**: A Free plan slot has no fixed primary occupant; a Free task placeholder delegates the occupant to selection. A vacant bed has no confirmed cached occupant and still requires reservation checks before filling.
- When a grouped dormitory primary has Free as its replacement, its departure adds group-scoped recovery capacity rather than reserving a physical position. This capacity admits working primaries going off shift in the same group, or standby primaries, ordinary replacements and idle operators; other applicants in the first four tiers can use only ordinary Free capacity. Both admission and takeover must satisfy these capacity limits; occupied-bed protection and takeover mood thresholds continue to apply.
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

### Medicine Expiry Threshold
- **Definition**: `medicine_expire_days` controls expiring sanity potion use independently of weekday. MAA Fight receives the configured remaining-day threshold; local operation enables its existing expiring-potion recognition when the threshold is positive. Zero disables expiring-potion use. Retired weekend-only settings have no effect.

### MAA Update Policy
- **Definition**: MAA core and resource updates have independent automatic-check and automatic-install switches. Automatic installation requires a matching update check and an idle MAA engine.
- **Code Mapping**: [`MaaPart`](arknights_mower/utils/config/conf.py)

---

## 3. Development & Documentation Language

### Project Document Names
- **Definition**: Names identify a project's own documents and their purpose. At the first reference in a standalone text, use the name below, explain why the document matters to the current change, and link to the relevant file or section. Repository prose uses relative links; published PRs use links to the reviewed commit. Later references may use an unambiguous short name.

| Document | English name | Purpose |
| :--- | :--- | :--- |
| [CONTEXT.md](CONTEXT.md), [CONTEXT.zh.md](CONTEXT.zh.md) | Arknights Mower Domain Glossary | Defines domain concepts and development/documentation language in both languages. |
| [CODING_STANDARDS.md](CODING_STANDARDS.md) | Arknights Mower Coding Standards | Defines shared behavior rules, concurrency and resource requirements, and verification requirements. |
| [AGENTS.md](AGENTS.md) | Arknights Mower Agent Directives | Routes agent tasks and states global execution constraints. |
| [.agents/AGENTS.md](.agents/AGENTS.md) | Arknights Mower Agent Workflow | Selects the task workflow, skills and verification/reporting responsibilities. |
| [docs/architecture.md](docs/architecture.md) | Arknights Mower System Architecture | Explains subsystem boundaries and points to implementation and verification owners. |
| [docs/subsystems/](docs/subsystems/) | Arknights Mower Subsystem Descriptions | Defines each subsystem's behavior rules and interface requirements; name the specific subsystem when referencing a file. |
| [docs/cookbook/](docs/cookbook/) | Arknights Mower Development and Troubleshooting Guide | Provides implementation, build, troubleshooting and focused verification procedures for developers and maintainers. |
| [.agents/notes/README.md](.agents/notes/README.md) | Arknights Mower Decision Record Guide | Defines record ownership, formats and lifecycle content. |

### Meaning-specific Technical Expressions
- **Definition**: Choose wording by the fact being described. A behavior rule states an observable result under stated conditions; an interface requirement states what callers and implementations must provide; a subsystem description is the document containing those details. Describe a change to workflow, documents or checks by naming what changed. These expressions do not rename code identifiers or weaken existing domain rules.
- **Recommended**: `behavior rule`, `interface requirement`, `subsystem description`, `workflow change`, `documentation change`, `check change`.
- **_Avoid_**: `governance commit`

### Formal Prose and Preserved Source Text
- **Definition**: Recommended names and Avoid lists apply to newly written formal prose, including skills, templates and PR titles/bodies. Historical quotations and test counterexamples preserve their source wording only when explicitly labelled and separated from current instructions or recommendations. Keep real code identifiers unchanged. Labels do not exempt surrounding formal prose or current domain rules from checking.
