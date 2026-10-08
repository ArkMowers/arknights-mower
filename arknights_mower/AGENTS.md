# Arknights Mower Backend Subtree Contract

Local contract for Python backend implementation under `arknights_mower/`.

## 1. Domain Invariants & Architecture Constraints

- Apply `[INV-01]` through `[INV-06]` from [Coding Standards](../CODING_STANDARDS.md#1-core-invariants) and the affected [subsystem contract](../docs/subsystems/).
- Select only necessary stages through [Agent Workflow](../.agents/AGENTS.md#1-task-selection); document placement follows the [routing rules](../.agents/skills/mower-doc/references/doc-hierarchy.md#routing-rules).

## 2. Resource & Concurrency Lifecycle

- **Monotonic Deadlines**: All external process execution, socket I/O, and session recovery operate under finite budgets (`RecoveryPolicy.timeout`, `COMMAND_TIMEOUT`).
- **Guaranteed Compensation**: Temporary display overrides (`wm size 1920x1080`), spawned child processes, and socket listeners register cleanup callbacks triggered on exit or error.
- **Standard Frame Contract**: Decoded capture output across ADB gzip, DroidCast, and MuMu IPC backends strictly conforms to the `(1080, 1920, 3)` RGB matrix.
- **Scheduling Projection Isolation**: Full `Operators` deep copies reuse the read-only `eval_model` through the deepcopy memo, while mutable operators, dormitory beds, plans and configuration remain isolated. Follow the existing projection boundaries in the [Base Scheduling Contract](../docs/subsystems/base-scheduler.md); runtime builtins and extension handles are not copied.

## 3. Testing Discipline

- **Targeted Unit Testing**: Run only focused unit test suites during development (e.g., `pytest arknights_mower/tests/device_session_tests.py`).
- **Hermetic Isolation**: Tests must mock external device processes, network sockets, and filesystem state. Full integration runs against live emulators are prohibited in agent development loops.

## 4. Prose & Language Standards

- All code comments, docstrings, and commit messages adhere strictly to domain terms in [CONTEXT.md](../CONTEXT.md).
- Never introduce issue tracker numbers (`#xxx`).
