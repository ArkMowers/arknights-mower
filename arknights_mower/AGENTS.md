# Arknights Mower Backend Subtree Contract

Local contract for Python backend implementation under `arknights_mower/`.

## 1. Domain Invariants & Architecture Constraints

- **[INV-01] Persistent Isolation**: `DeviceProfile` stores only explicit user selections. Connection state, active sockets, and discovery candidates are strictly transient.
- **[INV-02] Target Clearance**: Any change to emulator preset, path, or instance identity clears `last_serial` immediately.
- **[INV-03] Failure Preserves Identity**: Device offline, discovery timeout, or boot failure must never silently bind to another online device on the host.
- **[INV-04] IPC Pair Cohesion**: MuMu IPC screenshot backend and touch backend are coupled; neither backend operates in isolation.
- **[INV-05] Shared ADB Guard**: ADB server state must be probed via socket handshake; implicit `kill-server` invocations are strictly forbidden.
- **[INV-06] Domain Glossary Synchronization**: Any modification to scheduling mechanics, device session control, or configuration schemas must immediately synchronize domain terms in [CONTEXT.md](../CONTEXT.md).

## 2. Resource & Concurrency Lifecycle

- **Monotonic Deadlines**: All external process execution, socket I/O, and session recovery operate under finite budgets (`RecoveryPolicy.timeout`, `COMMAND_TIMEOUT`).
- **Guaranteed Compensation**: Temporary display overrides (`wm size 1920x1080`), spawned child processes, and socket listeners register cleanup callbacks triggered on exit or error.
- **Standard Frame Contract**: Decoded capture output across ADB gzip, DroidCast, and MuMu IPC backends strictly conforms to the `(1080, 1920, 3)` RGB matrix.

## 3. Testing Discipline

- **Targeted Unit Testing**: Run only focused unit test suites during development (e.g., `pytest arknights_mower/tests/device_session_tests.py`).
- **Hermetic Isolation**: Tests must mock external device processes, network sockets, and filesystem state. Full integration runs against live emulators are prohibited in agent development loops.

## 4. Prose & Language Standards

- All code comments, docstrings, and commit messages adhere strictly to domain terms in [CONTEXT.md](../CONTEXT.md).
- Never introduce issue tracker numbers (`#xxx`).
