# Software Update Command Contract

`Worker.run_command` executes fixed argument lists without a shell. Each command has a monotonic deadline and respects preparation cancellation. POSIX commands own a process group; Windows commands enter a dedicated Job before execution and keep their descendants inside that Job. The installer uses the standard library.

## Subsystem Invariant

- **[INV-UPD-01] Owned Command Completion**: Windows update commands own their descendants before execution and verify tree completion within a finite budget before releasing the temporary checkout; cancellation preserves other application instances.

## Failure Boundary

Cancellation and timeout terminate only the owned command tree. Successful root-process completion also requires the Job to become empty. Cleanup failure remains an error; it never establishes successful installation or permits stopping unrelated instances.

[Command tree cleanup](../../.agents/notes/implemented/bug-fix/2026-10-02-update-command-tree-cleanup.md) records implementation and focused verification.
