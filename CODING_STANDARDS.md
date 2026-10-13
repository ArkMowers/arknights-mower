# Coding Standards & Review Contracts

<a id="1-core-invariants"></a>
## 1. Core Contracts

### Transient vs Persisted Isolation

Configuration models (`DeviceProfile`, `Conf`) persist only explicit user selections. Discovery results and the current Device Session state remain transient in memory.

### Target Rebinding Clears Endpoints

Changing preset, installation directory, manager path, configuration path, or instance identifier must immediately clear `last_serial` to prevent stale endpoint reuse.

### Failure Preserves Target Identity

Discovery, preflight, or recovery failure must never silently alter persistent configuration or automatically fallback to another online device on the host.

### IPC Pair Cohesion

MuMu IPC screenshot backend and touch backend must be selected together; neither may be used without the other.

### Shared ADB Guard

Socket-level protocol negotiation must verify shared ADB server state before running CLI operations; implicit `kill-server` invocations are strictly prohibited.

### Concept Impact Review

Changes affecting scheduling, device control or configuration assess domain-concept names, meanings, boundaries and relationships. Changed concepts require synchronized definitions in `CONTEXT.md` and `CONTEXT.zh.md` after [explicit glossary approval](AGENTS.md#4-global-execution-constraints); unchanged concepts complete this check without glossary edits. Behavioral rules and implementation contracts follow the [documentation routing rules](.agents/skills/mower-doc/references/doc-hierarchy.md#routing-rules).


<a id="2-subsystem-invariants"></a>
## 2. Subsystem Contracts

- **[INV-REC-07] Complete LMD Amount**: Depot LMD quantities retain the complete recognized amount and its 万 or 亿 multiplier; malformed or low-confidence OCR returns an unconfirmed count without digit-template fallback. See the [depot recognition description](docs/subsystems/depot-recognition.md).

Business rules are defined once in their owning [subsystem contracts](docs/subsystems/), with behavior names, stable links and focused tests. Use the [task entry points](docs/architecture.md#2-find-the-implementation-and-verification) to locate the relevant source and verification boundary.

The workshop follows [committed inventory refresh and read-only crafting status](docs/subsystems/growth-planning.md#crafting-refresh-and-status). Automatic admission uses known mood sufficient for one batch while preserving reservations and manual thresholds.

New guarantees use behavior names and direct contract links. Historical identifiers are frozen in `scripts/legacy_invariant_ids.json` solely for existing decision metadata; historical records retain their original format and references.

The growth UI follows [Bounded Page Loading](docs/subsystems/growth-planning.md#bounded-page-loading): overview loading omits material graphs, rendered card count and retained details have explicit bounds, and stale requests cannot replace the current selection. Existing material accounting and transient-state isolation remain binding.

## 3. Concurrency & Resource Lifecycle

- **Monotonic Deadline Budgets**: All external process invocations, socket I/O, and manager commands must operate within a bounded deadline (e.g., `COMMAND_TIMEOUT`, `DISCOVERY_TIMEOUT`, `RecoveryPolicy.timeout`).
- **Guaranteed Compensation**: Resources acquired during execution (temporary screen overrides, child processes, socket ports, lock files) must register compensation actions to ensure cleanup on normal completion, errors, or application shutdown.
- **Controlled Verdicts**: Subsystem failures must be classified into structured domain results (`ReadinessResult`, `PreflightError`, `SessionFailure`) with actionable remedy codes rather than raising unhandled process exits.

## 4. Code Cleanliness & Smells

- **Single Source of Truth**: Every domain concept must have a single authoritative definition and storage location.
- **No Issue References**: Commit messages, code comments, and technical documentation must not contain issue tracker numbers (`#xxx`).
- **Bounded Collections**: In-memory logs, frame queues, and discovery results must have explicit capacity limits and eviction policies.
- **Explicit Imports**: Avoid wildcard imports (`from module import *`). Use explicit symbol imports.
- **Evidence for Scheduling Waits**: A runtime mismatch alone does not justify a new timer, repeated polling or stopping automation. Apply the [runtime task failure contract](docs/subsystems/base-scheduler.md#211-runtime-task-failure), retain unfinished work and verify progress with unchanged-state and dependency-release cases.

## 5. Verification Discipline

- **Targeted Unit Testing**: Run only focused unit test suites during development (e.g., `device_session_tests.py`, `deviceSettings.test.js`). Full integration runs against live devices are reserved for isolated environments.
- **Hermetic Unit Tests**: Isolate external device processes, network sockets and user filesystem state for deterministic offline execution. Persistence tests may exercise real file or database operations in isolated temporary locations managed by the test lifecycle.
- **Independent Expectations**: Derive expected results from the governing contract, confirmed examples or independent calculations. Avoid reproducing the production algorithm or using the behavior under test to generate its own expected result.
- **Business Logic Under Test**: Use test doubles to control external I/O, time, faults and race conditions while keeping the business decisions covered by the guarantee real. Interaction arguments, prohibited calls, counts and necessary ordering are valid assertions when they belong to that contract.
- **Fault Detection**: Choose assertions that would fail for a plausible violation of the tested contract. Check the relevant result, state, persistence, exception or side effect; a presence check is sufficient when presence itself is the guarantee. For reproducible defects, observed failure before the repair and success after it provide direct evidence when readily available.

Apply these principles during test design and review without requiring a per-test record, a fixed case count or a mutation-testing run. Coverage and passing tests provide evidence, not proof of correctness.
