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

- [ ] **[INV-01] Transient vs Persisted Isolation**: Does `DeviceProfile` or `Conf` only persist explicit user selections? Are discovery candidates, socket handles, and active connection state transient?
- [ ] **[INV-02] Target Rebinding Clears Endpoints**: Does any modification to emulator preset, path, or instance identity reset `last_serial` to null?
- [ ] **[INV-03] Failure Preserves Target Identity**: In case of device failure, timeout, or discovery error, does the session halt cleanly without drifting to other online devices on the host?
- [ ] **[INV-04] IPC Pair Cohesion**: If MuMu IPC screenshot backend is used, is IPC touch backend selected as well?
- [ ] **[INV-05] Shared ADB Guard**: Are ADB commands preceded by socket-level handshake? Is implicit `adb kill-server` prohibited?
- [ ] **[INV-DEV-01] Native Back Dispatch**: With MuMu IPC selected, does Android BACK use the owned MuMu IPC worker, and does an uncertain result stop the session without input replay or ADB fallback?

### 2.2 Base Infrastructure & Scheduling Domain

- [ ] **[INV-SCHED-01] Empirical Depletion Rate**: Are operator exhaustion forecasts calculated dynamically from inspection deltas rather than hardcoded assumptions?
- [ ] **[INV-SCHED-02] Stable Recovery Position**: The target retains its final slot during recovery setup and roster restoration; earlier non-manager slots use confirmed full residents or the highest-mood eligible idle padding, with actual readback required before recording recovery.
- [ ] **[INV-SCHED-03] Bed Ownership and Release**: Beds have one occupant; release validates occupant identity and respects idle-release exclusions and full-occupancy fallback, while personal mood limits remain mandatory. Merged releases retain each occupant's original bed identity; cancellation removes only that occupant's action.
- [ ] **[INV-SCHED-04] Shift Transition Compensation**: Do event-driven shifts (order runs, backup plans) handle dispatch failures gracefully without leaving facilities unassigned?
- [ ] **[INV-SCHED-05] Complete Shift Projection**: Do backup conditions, subsequent rotations, cached corrections, and final bed filling converge on a copy before one arrangement is submitted, with failure preserving actual state?
- [ ] **[INV-SCHED-06] Manufacturing Switch Boundary**: Does a switch after Drone Acceleration track the accelerated current unit and avoid treating the next unit's countdown as unfinished work?
- [ ] **[INV-SCHED-07] Unified Dormitory Policy**: All scheduling uses the same dormitory policy; retired mode keys neither select legacy behavior nor prevent old configuration imports.
- [ ] **[INV-SCHED-08] Unscheduled Training Slots**: Unconfigured training-room slots never produce static correction targets; automatic mastery still reads both facility slots.

### 2.3 Presentation Layer (UI)

- [ ] **[INV-UI-01] Unpersisted Candidate State**: Do discovery tables remain in local Pinia/component state without mutating persisted profile until user explicit save?
- [ ] **[INV-UI-02] Recovery Policy Binding**: Are advanced recovery parameters bidirectionally bound to backend defaults without local shadow overrides?

### 2.4 Vision & Recognition Domain

- [ ] **[INV-REC-01] Standard Canvas Frame Contract**: Do recognition models operate exclusively on standard 1920×1080 pure RGB matrices? Do recognition failures return structured verdicts without blocking the scheduler dispatch loop?
- [ ] **[INV-REC-02] Occluded Operator Selection**: Does an obscured upper border require both vertical borders and the leading portion of the lower border, while adjacent card borders remain insufficient?

### 2.5 Web Access

- [ ] **[INV-WEB-01] Local Log Read Boundary**: In a WebView session without a configured token, do read-only log requests require loopback and valid browser origin metadata while AI chat and mutating endpoints retain credential checks?

---

## 3. Extensibility Protocol: Adding Invariants for Future Modules

When a pull request introduces a new subsystem, driver, or solver module:

1. **Formulate Invariant**: State the invariant as a deterministic rule: `[INV-{SUBSYSTEM}-{NUMBER}] Name: Condition that must always hold true`.
2. **Propose in Decision Note**: Include the invariant identifier in the decision note triplet (`.agents/notes/proposed/...sidecar.json` under `invariants`).
3. **Register in Subsystem Spec**: Document the invariant and its failure mode in the relevant `docs/subsystems/*.md` specification.
4. **Update Checklist & Standards**: Add the new check to this file and synchronize `CODING_STANDARDS.md`.
5. **Implement Hermetic Test**: Add an offline unit test in `arknights_mower/tests/` asserting that violating the invariant raises the expected structured error.
