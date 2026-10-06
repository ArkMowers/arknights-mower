# Arknights Mower Invariants & Standards Checklist

Checklist for evaluating pull requests and git diffs under the Standards axis of `mower-code-review`.

---

## 1. Universal Hygiene & Resource Contracts (All Subsystems)

- [ ] **Zero Issue Numbers**: Commit messages, code comments, docstrings, and markdown files contain zero issue tracker numbers (`#xxx`).
- [ ] **Monotonic Deadline Budgets**: All external process invocations (`subprocess.run`), socket operations, and recovery polling have finite timeouts (`time.monotonic() + timeout`).
- [ ] **Guaranteed Compensation**: Acquired runtime resources (temporary screen overrides, open sockets, child processes, file locks) register cleanup in `PreparationSession`, `close_process`, or `finally` blocks.
- [ ] **Bounded Memory**: In-memory logs, frame buffers, and queue collections have explicit capacity bounds and eviction policies.
- [ ] **Controlled Language**: Code comments, docstrings, and documentation use terms defined in `CONTEXT.md` / `CONTEXT.zh.md` and avoid all prohibited synonyms.
- [ ] **Targeted Verification Only**: Reviews run targeted, hermetic unit tests (`pytest arknights_mower/tests/...`); live emulator integration runs are strictly prohibited.

---

## 2. Subsystem Invariants

### 2.1 Device Control & Transport Domain

- [ ] **[INV-DEV-20] Command Output Ownership**: Do MuMu startup observations and default guarded ADB commands use bounded temporary-file output with independent reader positions, preserve bytes during inherited writes and binary/text and stderr semantics, and return without descendant EOF waits while timeout cleanup targets only the owned command within its finite allowance? Does an over-budget capture stay a device verdict rather than an application fault and keep the manager's repair step, do `universal_newlines` and `stdin` keep subprocess semantics while `input` is rejected outright, does a timeout's partial output keep the caller's text selection, and does the manager runner own its merged output and return-code check instead of dropping caller options?

- [ ] **[INV-DEV-19] Shared ADB Recovery**: Do all ADB routes use the guarded shared server without private ports, foreground takeover or an SDK-release requirement? Do only at least two failed host handshakes sustained for at least thirty seconds permit an explicit restart under a host-shared cross-process lock, cooldown and locked re-probe within the same Recovery Budget, with healthy re-probes skipping restart and offline targets or version mismatch alone never authorizing it? Do cancellation and budget exhaustion remain non-failure observations? Does a restart initiated by this or another process revalidate the original Instance Binding and rebuild all helpers before dispatch while preserving pending tasks and uncertain-input pauses? Does application shutdown leave the shared server running?

- [ ] **[INV-DEV-16] Absent Target Cleanup**: Does an absent DroidCast target permit idempotent cleanup and the next verified startup only after owned forwards are absent, while unconfirmed transport failures, residual owned mappings and host cleanup failures remain blocking without touching foreign resources or shared ADB state?
- [ ] **[INV-DEV-18] Recovery Cycle Continuation**: Do failed finite recovery cycles retain the same Instance Binding, wait through cancellable cooldown and accept verified readiness despite an unconfirmed reconnect response?
- [ ] **[INV-DEV-17] Pre-Input Helper Recovery**: Does helper recovery validate the same target within its budget, preserve healthy resources during input-only repair and require fresh scene or side-effect reconciliation after uncertain delivery without replay or backend substitution?

- [ ] **[INV-DEV-15] Settings Cancellation Isolation**: Do settings operations ignore stopped-task cancellation without clearing shared events, propagate independent caller-context copies to parallel discovery providers, check cancellation at manager command, polling and completion boundaries, retain shutdown and closure cancellation, restore the caller's policy, and return structured HTTP cancellation while concurrent tasks still stop?

- [ ] **[INV-DEV-14] Startup Reconnect Budget**: Do initial startup and runtime launch across supported presets retain bounded targeted retries and readiness polling after a rejected reconnect within the same deadline, without another instance, repeated restart, or suppressed binding, shared ADB and cancellation failures?

- [ ] **[INV-DEV-12] Android Configuration Ownership**: Do all configuration boundaries retain Android-managed settings independently of desktop Device Profile values, including malformed desktop-only fields, while preserving editable game server selection, Base Plans, weekly plans and general task settings through export/import round trips?

- [ ] **[INV-DEV-13] Detection Startup Target**: Does detection start only a selected supported target after a stopped verdict, preserve ambiguous selections, and keep the separate connection test read-only?

- [ ] **[INV-DEV-11] MuMu Pro Verified Selection**: Does discovery expose distinct instances from bounded manager output, and does each connection recheck index and topology fingerprint before accepting that instance's current ADB endpoint, with lifecycle commands verifying the same identity before operating on one index?

- [ ] **[INV-DEV-10] MuMu Pro Manual Binding**: Does the MuMu Pro preset use only the selected serial after standard preflight, reject missing or mismatched targets, and avoid unverified manager start and stop commands?

- [ ] **[INV-DEV-09] Classified Failure Isolation**: Do Temporary Preparation errors retain their structured verdict and trigger owned resource cleanup without requesting application shutdown, while unclassified internal faults retain coordinated shutdown?

- [ ] **[INV-DEV-08] Uncertain Input Delivery**: Does an ADB input transmission or acknowledgement timeout reach the structured input failure boundary without replaying the command, while known read-only queries retain bounded retries?

- [ ] **[INV-DEV-07] Capture Recovery Separation**: Do normal frames use a fresh operation deadline, and does degraded ADB validate the bound target without starting the replaced helper?

- [ ] **[INV-DEV-05] Capture Preset Compatibility**: Do saves reject incompatible capture presets, do capture entry points check the host, and do UI preset changes clear incompatible draft backends without prematurely persisting a new identity?
- [ ] **[INV-DEV-06] LD Capture Binding**: Does LD screenshot enhancement verify the selected endpoint and reject changed process identity or dimensions before accepting a frame?

- [ ] **[INV-DEV-04] Launch Protection**: Does automatic restart respect the bound instance's configured startup interval, including across recovery transactions, without exceeding the Recovery Budget or ignoring cancellation?

- [ ] **[INV-DEV-03] Startup Budget Isolation**: Does each new startup establish a fresh Recovery Budget before preparation and preserve that deadline through readiness, validation and helper initialization?

- [ ] **[INV-DEV-02] Lifecycle Command Isolation**: Are lifecycle arguments passed without a shell and restricted to an explicitly identified instance, with unavailable control failing before any host-wide action?

- [ ] **[INV-01] Transient vs Persisted Isolation**: Does `DeviceProfile` or `Conf` only persist explicit user selections? Are discovery candidates, socket handles, and active connection state transient?
- [ ] **[INV-02] Target Rebinding Clears Endpoints**: Does any modification to emulator preset, path, or instance identity reset `last_serial` to null?
- [ ] **[INV-03] Failure Preserves Target Identity**: In case of device failure, timeout, or discovery error, does the session halt cleanly without drifting to other online devices on the host?
- [ ] **[INV-04] IPC Pair Cohesion**: If MuMu IPC screenshot backend is used, is IPC touch backend selected as well?
- [ ] **[INV-05] Shared ADB Guard**: Are ADB commands preceded by socket-level handshake? Is implicit `adb kill-server` prohibited?
- [ ] **[INV-DEV-01] Native Back Dispatch**: With MuMu IPC selected, does Android BACK use the owned MuMu IPC worker, and does an uncertain result interrupt the operation without input replay or ADB fallback?

### 2.2 Base Infrastructure & Scheduling Domain
- [ ] **[INV-SCHED-23] Projected Dormitory Isolation**: Do unlimited isolation groups reduce same-group cohabitation only in admission projection, preserve recovery ranking, single-target beds, existing occupants and reservations, accept unavoidable cohabitation and avoid post-admission isolation correction?
- [ ] **[INV-SCHED-22] Same-Group Primary Replacements**: Do primary replacements require distinct members of the same nonempty group with at least one grouped dormitory primary, prohibit working-to-working replacements, with ordinary idle replacements preserved, complete arrangements, primary identity retention, fixed recovery timing without Free capacity, exhaustion exclusion, reservations, personal limits, training protection and actual single-target confirmation?
- [ ] **[INV-SCHED-21] Independent Dormitory Recovery**: Does the idle-release switch affect only ordinary full-mood release task creation, while both states share candidate observation, recovery admission, replacement, projection, selection, timing, exclusions and full-occupancy fallback, preserving mandatory personal limits, reservations, actual occupancy and measured-mood isolation? Completed grouped residents may yield beds without recalling unfinished resting members or cancelling their ordinary return tasks.
- [ ] **[INV-SCHED-20] Event-Driven Recovery Allocation**: Existing single-target residents do not proactively reorder. New arrivals may preempt strictly lower tiers, and displaced targets continue toward lower-tier targets or an empty slot; equal tiers never preempt. Ordinary vacancies admit non-target residents with same-tier local preference. Reservations, live-state isolation and idle stability remain binding.
- [ ] **[INV-SCHED-19] Ungrouped Standby Return**: Does an ungrouped standby primary join the earliest eligible ordinary shift-on batch without changing its deadline, bypassing reservations, altering actual occupancy or creating an independent return, while grouped standby and exhausted replacement handling retain their existing rules?
- [ ] **[INV-SCHED-17] Mastery Order Timing**: Do genuine conflicts advance mastery handoffs while preserving order times, prioritize due handoffs over overdue orders and retain training and candidate checks without requeueing the ideal handoff time?
- [ ] **[INV-SCHED-16] Backup Validation Coverage**: Does validation exclude only logically disproven activation combinations, cover all remaining combinations with the runtime merged-plan checker, distinguish incomplete budget warnings from blocking configuration failures, enforce the shared five-second startup budget while leaving manual validation untimed, identify active backups on error and preserve the caller's active plan and actual occupancy?
- [ ] **[INV-SCHED-13] Pending Task Preservation**: Does device recovery preserve the scheduler and pending tasks through real scheduler re-entry, retain future explicit tasks during stale ordinary-plan rebuilding, refresh the Capture Frame before resuming and pause unverified side effects without ending the automation worker or replaying input?

- [ ] **[INV-SCHED-01] Empirical Depletion Rate**: Are operator exhaustion forecasts calculated dynamically from inspection deltas rather than hardcoded assumptions?
- [ ] **[INV-SCHED-02] Stable Recovery Position**: The target retains its final slot during recovery setup and roster restoration; earlier non-manager slots use confirmed full residents or the highest-mood eligible idle padding, with actual readback required before recording recovery. Fiammetta retains her preceding position regardless of mood and never competes for single-target recovery.
- [ ] **[INV-SCHED-03] Bed Ownership and Release**: Beds have one occupant; release validates occupant identity and respects idle-release exclusions and full-occupancy fallback, while personal mood limits remain mandatory. Unchanged personal-limit releases retain task identity and their reserved operation start across normal and rescue replanning. Merged releases retain each occupant's original bed identity; cancellation removes only that occupant's action. Automatic rescue keeps personal mood-limit release deadlines scheduled while ordinary shifts remain frozen. Automatic rescue retains configured operator identities and personal limits while manager positions provide episode-local recovery capacity, including the configured Fiammetta position when primaries await beds. Pending releases reserve their occupants and original beds; completed personal-limit recovery does not re-enter emergency beds or vacant fixed dormitory positions through correction, backup transitions or handoff. Fiammetta yields to waiting primaries and returns to her effective rescue position before managers; restoring managers never displaces unfinished recovery primaries. Collection, each room observation, staffing operations and handoff yield before strict release operation windows, preserving partial progress and occupant-matched deadlines; partial observations never authorize staffing or exit. Each completed room observation rebuilds strict releases before the next operation; unchanged handoff residents retain deadlines until newer measured deadlines replace them. Startup observations without an active rescue episode obey the same release windows, persist unread rooms and allow selected releases to dispatch before initialization resumes. Disabling automatic rescue retains unfinished initialization; completed initialization clears persisted progress, and later startups ignore completed-snapshot room lists.
- [ ] **[INV-SCHED-04] Shift Transition Compensation**: Does initial measured full-mood Fiammetta charging retain priority through restoration before ordinary work and rescue evaluation, while preserving due critical-task protection? Do event-driven shifts (order runs, backup plans) handle dispatch failures gracefully without leaving facilities unassigned? Do specialized swaps during automatic rescue restore observed temporary staffing, including explicit vacant slots? Do started order retries retain compensation and original-worker reservations across filtering and room changes, and wait for workers occupied in other facilities? Expired started order runs become original-roster restoration without another insertion; timeout queue rebuilding retains restoration responsibilities and worker reservations.
- [ ] **[INV-SCHED-05] Complete Shift Projection**: Do backup conditions, subsequent rotations, cached corrections, and final bed filling converge on a copy before one arrangement is submitted, with failure preserving actual state?
- [ ] **[INV-SCHED-06] Manufacturing Switch Boundary**: Does a switch after Drone Acceleration track the accelerated current unit and avoid treating the next unit's countdown as unfinished work?
- [ ] **[INV-SCHED-07] Unified Dormitory Policy**: All scheduling uses the same dormitory policy; retired mode keys neither select legacy behavior nor prevent old configuration imports. Automatic rescue uses shared recovery-tier admission with episode-local manager-position capacity; normal dormitory configuration is restored at final handoff. Active automatic mastery crafting reorders only the ranking positions already occupied by ordinary idle crafting candidates using interleaved configured lists; other candidates retain their ranking positions, and identity tiers, exclusions and reservations remain authoritative.
- [ ] **[INV-SCHED-08] Unscheduled Training Slots**: Unconfigured training-room slots never produce static correction targets; automatic mastery still reads both facility slots.
- [ ] **[INV-SCHED-18] Unscheduled Workshop Slot**: Do cache reads and physical readback use one workshop slot without requiring or inserting static staff, with actual pre-selection occupants establishing the batch restoration snapshot and other facility capacities retaining their contracts?
- [ ] **[INV-SCHED-09] Rescue Recovery Lifecycle**: Do measured entry, isolated projections, matching rescue facility types, staffing capacities and products before entry, complete configured rescue staffing, personal-limit release windows, shared initial observations, event-driven dispatch, resident-detail restoration after product inspection, reserved standby and measured handoff follow the [Rescue Recovery lifecycle contract](../../../../docs/subsystems/base-scheduler.md#3-subsystem-invariants)? Configured rescue workshop and training-room staffing uses existing arrangement and specialized-task protection; protected training slots do not block completion of other staffing. Initial admission uses measured mood or valid card estimates in isolated projections; recovery completion and final exit require measured mood. Daily tasks, clues, drones and replenishment retain ordinary time budgets during rescue. Measured departures and feasible bed filling share one final arrangement; normal full-recovery requirements retain personal mood caps. Available single-target managers precede ordinary fillers even when a group-recovery manager is unavailable. Rescue recovery queue regeneration uses the shared merge interval without crossing specialized tasks or strict personal-limit releases; measured targets remain individual. Does exit verify current normal staffing and beds without requiring a forecast of the next rotation? Do rescue worker replacements use personal rescue thresholds, normal-main referenced standby retain spare-bed eligibility, and bounded recovery-order projections preserve explicit priority and live observations? Do exhaustion groups retain their own shift timing in admission and current native projections, and do training staffing checks bypass unavailable training-card mood while preserving slot protections?
- [ ] **[INV-SCHED-10] Completed Exhaust Continuation**: Do resting recovery-requiring working members permit completed exhausted shifts regardless of dormitory residents or workaholics, and do successful backup changes invalidate only affected empty-plan exhaust deadlines while preserving unchanged schedules, failed activation, actual occupancy and concrete arrangements?
- [ ] **[INV-SCHED-11] Maintenance Backup Ordering**: A maintenance backup checks its configured deadline, completes the existing pre-maintenance drone-accelerated order batch before switching, and suppresses all trade order generation only while its effective primary slots contain trade order agents; its maintenance condition is false from downtime start, and backup exit waits for a normal check after task restart.
- [ ] **[INV-SCHED-12] Idle Lifecycle Ownership**: Does idle shutdown use the authoritative Device Profile and verified lifecycle adapter, revalidate selected identity before shutdown within the same deadline, record a wake only after confirmed shutdown, and preserve ownership, Android isolation and unsupported-control refusal without legacy commands?
- [ ] **[INV-SCHED-13] Dormitory Candidate Consistency**: Do planning and selection share candidate states and reservations, confirm unknown mood in the game, replan recovery after completed crafting and staff restoration, and preserve ordinary vacancy-fill identity through projection and runtime snapshot restoration? Do eligible low selection-card estimates permit replacing completed ordinary residents despite prior full-occupancy retention or exhausted-search flags while preserving selection-page confirmation and measured-mood isolation?
- [ ] **[INV-SCHED-14] Complete Group Replacement Matching**: A grouped shift considers all eligible replacement assignments and accepts a complete matching whenever one exists; insufficient replacements preserve the group's original working arrangement. Ordinary rotation also requires complete group beds; automatic rescue prefers group admission within shared priorities without a complete-group bed requirement.
- [ ] **[INV-SCHED-15] Selection Estimate Isolation**: Selection-card mood estimates support candidate screening, ordering, and primary shift selection only; they never overwrite measured mood, timestamps, depletion rates, recovery deadlines, or mandatory personal limits. Facility-completion events refresh only affected candidates and preserve unrelated estimates and search checks. Regular candidate planning scans cards only when no eligible idle recovery candidate has valid measured or estimated mood.

### 2.3 Presentation Layer (UI)
- [ ] **[INV-UI-06] Chip Priority Selection**: Does the chip-limit button select all chip stages on weekdays permitted by the availability filter, promote their rows and preserve existing selections and daily settings, while manual sorting and saved-order loading retain the chosen annihilation position?
- [ ] **[INV-UI-05] Chip Limit Preset Isolation**: Does the button bind both endpoint-provided drops for every chip stage at 5 small chips or 8 chip packs, replace existing chip rules with enabled AND conditions without duplicates, and preserve other stage rules and inventory enablement?
- [ ] **[INV-UI-04] Weekly Availability Display**: Does disabling the weekly availability filter remove unavailable placeholders and styling, permit every weekday, and preserve saved selections through filter changes?

- [ ] **[INV-UI-03] Selected Instance Persistence**: Does selecting a detected instance save its identity before connection testing, preserve it on failure, avoid unverified endpoint persistence, and prevent startup after an identity save failure?

- [ ] **[INV-UI-01] Unpersisted Candidate State**: Do discovery tables remain in local Pinia/component state without mutating persisted profile until user explicit save?
- [ ] **[INV-UI-02] Recovery Policy Binding**: Are advanced recovery parameters bidirectionally bound to backend defaults without local shadow overrides?

### 2.4 Vision & Recognition Domain

- [ ] **[INV-REC-05] Training Panel Identity**: Does training identity use full-name templates on the current Capture Frame with score, closing-bracket and distinct-name margin checks, while unknown readings retain bounded retry without an OCR name fallback or plan-derived occupant?
- [ ] **[INV-DIAG-06] Error Notification Evidence**: Does every ERROR notification log before mail configuration checks or delivery, while only explicit visual failures request screenshots, including disabled email, through the existing archive store?

- [ ] **[INV-REC-03] Scene Recovery Limit**: Do recognition failures retain one game restart per navigation call, ordinary navigation input faults recover and refresh inside that call, and cancellation and unverified side effects propagate without input replay?

- [ ] **[INV-DIAG-01] Archive Deletion Cohesion**: Do expiry and capacity deletion use the store's archive lock and cancel queued writes and active windows so late frames cannot recreate retired archives?
- [ ] **[INV-DIAG-02] Archive Error Isolation**: Does malformed archive metadata leave the worker able to process subsequent archives?

- [ ] **[INV-DIAG-03] Accepted Archive Drain**: Does shutdown preserve accepted screenshot and archive work through one flush deadline, then count discarded work and stop new file writes?
- [ ] **[INV-DIAG-07] Archive Observation Cohesion**: Do regression assertions over a manifest and invalidated logs acquire the archive lock after observing the relevant transition, instead of treating log removal as manifest completion?
- [ ] **[INV-DIAG-04] Encoded Recent Cache**: With ordinary history disabled, does the recent cache retain encoded frames within count and byte bounds, while raw submission remains non-blocking and bounded?
- [ ] **[INV-DIAG-05] Shared Frame Encoding**: Does each RGB snapshot encode at most once, release its source after completion, share encoded bytes across consumers and preserve capacity, newer preview progress and the shutdown deadline?

- [ ] **[INV-REC-01] Standard Canvas Frame Contract**: Do recognition models operate exclusively on standard 1920×1080 pure RGB matrices? Do recognition failures return structured verdicts without blocking the scheduler dispatch loop?
- [ ] **[INV-REC-02] Occluded Operator Selection**: Does an obscured upper border require both vertical borders and the leading portion of the lower border, while adjacent card borders remain insufficient?
- [ ] **[INV-REC-04] Selection Border Geometry**: Does normal card border detection remain independent of name-region widening, recognize dim blue borders, and preserve bounded recovery for genuinely clipped or ambiguous cards without selecting neighbors?

### 2.5 Web Access

- [ ] **[INV-WEB-01] Local Log Read Boundary**: In a WebView session without a configured token, do read-only log requests require loopback and valid browser origin metadata while AI chat and mutating endpoints retain credential checks?

### 2.6 Configuration Backup
- [ ] **[INV-CFG-02] Running Plan Restore Cohesion**: Does running-plan restoration include actual startup advanced settings, preserve unrelated configuration and previous models/files on failure, and reload both frontend stores before resuming autosave?

- [ ] **[INV-CFG-01] Configuration Data Cohesion**: Does import validate configuration and tmp data before writing, preserve local access settings, clear saved scheduling state, and restore original files when any write or database restore fails?

### 2.7 Software Update

- [ ] **[INV-UPD-01] Owned Command Completion**: Does each Windows update command own descendants before execution, verify completion within its budget, and preserve other instances when preparation is cancelled?
- [ ] **[INV-UPD-02] Complete Registration Scan**: Do strict registration scans retry within one shared monotonic budget, preserve unverified registrations and raise `InstanceScanError` instead of returning an incomplete snapshot after budget exhaustion?

---

## 3. Extensibility Protocol: Adding Invariants for Future Modules

When a pull request introduces a new subsystem, driver, or solver module:

1. **Formulate Invariant**: State the invariant as a deterministic rule: `[INV-{SUBSYSTEM}-{NUMBER}] Name: Condition that must always hold true`.
2. **Propose in Decision Note**: Include the invariant identifier in the decision note triplet (`.agents/notes/proposed/...sidecar.json` under `invariants`).
3. **Register in Subsystem Spec**: Document the invariant and its failure mode in the relevant `docs/subsystems/*.md` specification.
4. **Update Checklist & Standards**: Add the new check to this file and synchronize `CODING_STANDARDS.md`.
5. **Implement Hermetic Test**: Add an offline unit test in `arknights_mower/tests/` asserting that violating the invariant raises the expected structured error.
