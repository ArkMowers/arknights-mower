# Software Update Contract

## 1. Command Execution

`Worker.run_command` executes fixed argument lists without a shell. Each command has a monotonic deadline and respects preparation cancellation. POSIX commands own a process group; Windows commands enter a dedicated Job before execution and keep their descendants inside that Job. The installer uses the standard library.

## 2. Global Update Drop

`GlobalUpdateDrop` excludes local upload targets, editable controls, draggable elements and elements marked `data-no-update-drop`, including their descendants. The Scheduling Plan facility layout carries one marker covering every card, background and gap, including fixed facilities and cards locked during import. The marker does not cover the surrounding page or the editing section below the layout. Entering or hovering over an excluded target clears the update drag hint, including when a local handler consumes the event. Other page regions accept update packages through the existing confirmation flow.

[Facility layout drop boundary](../../.agents/notes/implemented/simplification/2026-10-06-facility-layout-drop-boundary.md) records the decision and focused verification.

## 3. Subsystem Invariants

- **[INV-UPD-03] Nightly Direction Evidence**: Same-alpha Nightly updates use valid publication times or verified upstream commit ancestry to determine direction; missing index history alone never establishes a downgrade, and unverified direction retains manual confirmation.
- **[INV-UPD-01] Owned Command Completion**: Windows update commands own their descendants before execution and verify tree completion within a finite budget before releasing the temporary checkout; cancellation preserves other application instances.
- **[INV-UPD-02] Complete Registration Scan**: Strict registration scans retry unreadable files within one shared monotonic budget, preserve unverified registrations and raise `InstanceScanError` when that budget expires instead of returning an incomplete snapshot.
- **[INV-UI-07] Facility Update Drop Isolation**: The Scheduling Plan facility layout, including every card, background and gap, suppresses and clears global update drag hints without intercepting facility sorting; other page regions retain update-package drops.

## 4. Registration Scan Boundary

`update_runtime.instances` returns a complete live-registration snapshot in strict mode. Its default five-second retry budget covers the entire scan. A zero timeout performs one attempt and reports unreadable registrations immediately. `strict=False` explicitly permits best-effort results. Read failures never establish process termination or authorize deletion of an unverified registration.

[Restart readiness scan budget](../../.agents/notes/implemented/testing/2026-10-06-restart-readiness-scan-budget.md) records the focused test correction.

## 5. Failure Boundary

Cancellation and timeout terminate only the owned command tree. Successful root-process completion also requires the Job to become empty. Cleanup failure remains an error; it never establishes successful installation or permits stopping unrelated instances.

[Command tree cleanup](../../.agents/notes/implemented/bug-fix/2026-10-02-update-command-tree-cleanup.md) records implementation and focused verification.

## 6. Nightly Version Direction

`release_is_downgrade` compares semantic version components before resolving same-alpha Nightly builds. Valid, timezone-aware publication dates in the channel index determine direction without another request. Missing history or invalid dates trigger one upstream GitHub commit comparison from the installed SHA to the target SHA, using the selected HTTP proxy and existing finite request timeout. `ahead` and `identical` permit updating; `behind`, `diverged`, malformed responses and request failures retain manual confirmation. Identical version names need no comparison. Offline package inspection remains network-free and retains confirmation when SHA ordering is unknown.

[Nightly direction evidence](../../.agents/notes/implemented/bug-fix/2026-10-07-nightly-direction-evidence.md) records the contract and focused verification.
