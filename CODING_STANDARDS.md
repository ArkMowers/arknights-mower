# Coding Standards & Review Contracts

## 1. Core Invariants

- **[INV-01] Transient vs Persisted Isolation**: Configuration models (`DeviceProfile`, `Conf`) persist only explicit user selections. Discovery candidate lists and active connection states remain transient in memory.
- **[INV-02] Target Rebinding Clears Endpoints**: Changing preset, installation directory, manager path, configuration path, or instance identifier must immediately clear `last_serial` to prevent stale endpoint reuse.
- **[INV-03] Failure Preserves Target Identity**: Discovery, preflight, or recovery failure must never silently alter persistent configuration or automatically fallback to another online device on the host.
- **[INV-04] IPC Pair Cohesion**: MuMu IPC screenshot backend and touch backend must be selected together; neither may be used without the other.
- **[INV-05] Shared ADB Guard**: Socket-level protocol negotiation must verify shared ADB server state before running CLI operations; implicit `kill-server` invocations are strictly prohibited.
- **[INV-06] Domain Glossary Synchronization**: Any change altering base scheduling mechanics, device driver lifecycles, or configuration schemas must immediately update and preserve authoritative definitions in `CONTEXT.md`.


## 2. Subsystem Invariants

### 2.1 Base Infrastructure & Scheduling
- **[INV-SCHED-01] Empirical Depletion Rate**: Mood forecasting must dynamically measure consecutive inspection deltas; uncalibrated static assumptions are prohibited.
- **[INV-SCHED-02] Stable Recovery Position**: The target retains its final slot during recovery setup and roster restoration; earlier non-manager slots use confirmed full residents or the highest-mood eligible idle padding, with actual readback required before recording recovery.
- **[INV-SCHED-03] Bed Ownership and Release**: Beds have one occupant; release validates occupant identity and respects idle-release exclusions and full-occupancy fallback, while personal mood limits remain mandatory. Merged releases retain each occupant's original bed identity; cancellation removes only that occupant's action.
- **[INV-SCHED-04] Shift Transition Compensation**: Condition-triggered shifts (order runs, backup plans) must preserve state rollback on failure, avoiding orphaned room assignments.
- **[INV-SCHED-05] Complete Shift Projection**: Experimental ordinary shifts submit only after backup conditions, eligible rotations, cached corrections, and final bed filling stabilize on an isolated projection; failure preserves the original task and actual occupancy.
- **[INV-SCHED-06] Manufacturing Switch Boundary**: After Drone Acceleration, a manufacturing product switch tracks completion of the accelerated current unit; the next unit's countdown never postpones that switch.
- **[INV-SCHED-07] Unified Dormitory Policy**: All scheduling uses the same dormitory policy; retired mode keys neither select legacy behavior nor prevent old configuration imports.
- **[INV-SCHED-08] Unscheduled Training Slots**: Unconfigured training-room slots never produce static correction targets; automatic mastery still reads both facility slots.
- **[INV-SCHED-09] Rescue Recovery Lifecycle**: Rescue evaluates main-plan individual mood limits, preserves main-primary and priority-replacement recovery until their upper limits, and exits after majority completion without clearing occupied beds or admitting excluded workers.
- **[INV-SCHED-10] Completed Exhaust Continuation**: An exhausted-shift task whose full working group already rests preserves normal planning and run-order recalculation without reserving another bed or invoking skip.
- **[INV-SCHED-11] Maintenance Backup Ordering**: A maintenance backup checks its configured deadline, completes the existing pre-maintenance drone-accelerated order batch before switching, and suppresses all trade order generation only while its effective primary slots contain trade order agents; its maintenance condition is false from downtime start, and backup exit waits for a normal check after task restart.

### 2.2 Presentation Layer (UI)
- **[INV-UI-03] Selected Instance Persistence**: Selecting a detected instance saves its explicit identity before connection testing or startup; failure preserves that choice without an unverified endpoint, while a rejected identity save prevents lifecycle actions and preserves the previous saved Device Profile.
- **[INV-UI-01] Unpersisted Candidate State**: Discovery candidate tables must remain in ephemeral Pinia/component state without mutating persisted profile until user explicit save.
- **[INV-UI-02] Recovery Policy Binding**: Advanced recovery parameters must bidirectionally bind to backend defaults without local shadow overrides.

### 2.3 Vision & Recognition
- **[INV-REC-03] Scene Recovery Limit**: Repeated scene transition exceptions permit one game restart per navigation call, then raise a recognition failure; cancellation and device failures propagate immediately.
- **[INV-REC-01] Standard Canvas Frame Contract**: Recognition models operate exclusively on standard 1920×1080 pure RGB matrices; recognition failures must return structured verdicts without blocking the scheduler dispatch loop.
- **[INV-REC-02] Occluded Operator Selection**: A card with an obscured upper selection border is confirmed only when both vertical borders and the leading portion of its lower border are visible; adjacent card borders cannot confirm selection.
- **[INV-DIAG-01] Archive Deletion Cohesion**: Error archive deletion holds the store's archive lock and cancels its queued writes and active windows before late frames can recreate it.
- **[INV-DIAG-02] Archive Error Isolation**: Invalid metadata in one error archive produces a diagnostic without terminating the archive worker.
- **[INV-DIAG-03] Accepted Archive Drain**: Shutdown preserves accepted screenshot and archive work until the common flush deadline; work discarded after that deadline is counted and starts no further file writes.
- **[INV-DIAG-04] Encoded Recent Cache**: With ordinary history disabled, the recent error context retains encoded frames under its count and byte limits; capture submission performs no encoding and pending raw frames remain bounded.
- **[INV-DIAG-05] Shared Frame Encoding**: Each admitted RGB snapshot has at most one encoding attempt; preview, history and error context share its encoded bytes, release the source snapshot after completion, and preserve bounded admission and independent progress of newer previews.

### 2.4 Device Control & Transport
- **[INV-DEV-16] Absent Target Cleanup**: A disappeared DroidCast target with no owned forward remaining permits idempotent host-resource cleanup and subsequent verified startup; unknown transport errors, surviving owned forwards and host-resource failures remain blocking, while foreign resources and shared ADB state remain unchanged.
- **[INV-DEV-15] Settings Cancellation Isolation**: Device settings operations ignore a stopped task's cancellation signal without clearing it, retain process shutdown and device closure cancellation, and expose cancellation as a structured HTTP verdict; each parallel discovery provider inherits an independent copy of the caller's context, while concurrent task operations retain their own cancellation policy.
- **[INV-DEV-14] Startup Reconnect Budget**: Rejected ADB reconnects during startup readiness retain bounded retries and observation within the existing deadline; each retry verifies the same Instance Binding, while binding changes, shared ADB errors and cancellation remain terminal without another endpoint or repeated simulator restart.
- **[INV-DEV-12] Android Configuration Ownership**: Android-managed connection, capture, input, native appearance, screenshot history and service endpoint settings remain authoritative through configuration load, import, partial update and save/reload; desktop Device Profile values never overwrite them, while game server selection, Base Plans, weekly plans and general task settings remain editable and support export/import round trips.
- **[INV-DEV-13] Detection Startup Target**: Detection starts only a selected target whose read-only check reports a stopped instance and whose preset provides startup control; ambiguous targets and other failures never trigger startup.
- **[INV-DEV-11] MuMu Pro Verified Selection**: A selected MuMu Pro instance is verified by its saved index and topology fingerprint before its current ADB port is used; changed or ambiguous manager output fails without adopting another instance, and lifecycle commands verify that identity before operating on one index.
- **[INV-DEV-10] MuMu Pro Manual Binding**: The MuMu Pro preset checks only its saved ADB serial through the standard preflight gate; absent or mismatched targets fail without adopting another device, and unverified manager commands never start or stop an instance.
- **[INV-DEV-09] Classified Failure Isolation**: Classified device failures, including Temporary Preparation errors, request owned resource cleanup and expose their structured verdict without requesting application shutdown.
- **[INV-DEV-08] Uncertain Input Delivery**: ADB input whose transmission or acknowledgement is uncertain fails without automatic command replay; the input boundary reports a structured delivery-unknown failure.
- **[INV-DEV-07] Capture Recovery Separation**: Normal frames use a fresh per-operation deadline; a degraded ADB backend verifies its bound target without invoking the replaced capture helper.
- **[INV-DEV-05] Capture Preset Compatibility**: Configuration updates reject incompatible vendor capture presets; capture entry points also verify the host, and UI preset changes clear incompatible capture and coupled touch selections in the draft.
- **[INV-DEV-06] LD Capture Binding**: LD screenshot enhancement verifies the selected ADB endpoint against the selected instance and accepts frames only while its process identity and 1920×1080 dimensions remain unchanged.
- **[INV-DEV-04] Launch Protection**: A session preserves the bound instance's configured startup interval before a subsequent automatic restart; waiting remains inside its Recovery Budget and respects cancellation.
- **[INV-DEV-03] Startup Budget Isolation**: Each new device startup establishes its Recovery Budget before preparation; preparation, readiness, validation and helper initialization share that deadline without inheriting a previous run's deadline.
- **[INV-DEV-02] Lifecycle Command Isolation**: Simulator lifecycle commands pass literal argument lists without a shell and act only on an explicitly identified instance; unavailable instance control fails without a host-wide action.
- **[INV-DEV-01] Native Back Dispatch**: When the selected touch backend is MuMu IPC, Android BACK uses the owned MuMu IPC worker; an uncertain result stops the session without input replay or ADB fallback.

### 2.5 Web Access
- **[INV-WEB-01] Local Log Read Boundary**: A WebView session without a configured token permits read-only log requests from loopback with valid browser origin metadata; remote and cross-origin requests are rejected, and AI chat and mutating endpoints retain their credential checks.

### 2.6 Configuration Backup
- **[INV-CFG-01] Configuration Data Cohesion**: Configuration imports validate all archive members before writing, restore included persistent tmp data with configuration, preserve local access settings, clear saved scheduling state, and roll back file changes if any write or database restore fails.


## 3. Concurrency & Resource Lifecycle

- **Monotonic Deadline Budgets**: All external process invocations, socket I/O, and manager commands must operate within a bounded deadline (e.g., `COMMAND_TIMEOUT`, `DISCOVERY_TIMEOUT`, `RecoveryPolicy.timeout`).
- **Guaranteed Compensation**: Resources acquired during execution (temporary screen overrides, child processes, socket ports, lock files) must register compensation actions to ensure cleanup on normal completion, errors, or application shutdown.
- **Controlled Verdicts**: Subsystem failures must be classified into structured domain results (`ReadinessResult`, `PreflightError`, `SessionFailure`) with actionable remedy codes rather than raising unhandled process exits.

## 4. Code Cleanliness & Smells

- **Single Source of Truth**: Every domain concept must have a single authoritative definition and storage location.
- **No Issue References**: Commit messages, code comments, and technical documentation must not contain issue tracker numbers (`#xxx`).
- **Bounded Collections**: In-memory logs, frame queues, and discovery results must have explicit capacity limits and eviction policies.
- **Explicit Imports**: Avoid wildcard imports (`from module import *`). Use explicit symbol imports.

## 5. Verification Discipline

- **Targeted Unit Testing**: Run only focused unit test suites during development (e.g., `device_session_tests.py`, `deviceSettings.test.js`). Full integration runs against live devices are reserved for isolated environments.
- **Hermetic Unit Tests**: Unit tests must stub external processes, network sockets, and filesystem resources to ensure deterministic offline execution.
