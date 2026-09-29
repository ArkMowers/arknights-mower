# Subsystem Prefix & Invariant Namespace Reference

Standard prefixes for scoping domain invariants in Arknights Mower:

| Subsystem Domain | Prefix | Scope & Responsibility | Spec Location |
| :--- | :--- | :--- | :--- |
| **Core Architecture** | `[INV-01]` ~ `[INV-06]` | Foundational lifecycle, single truth source, glossary sync | `docs/architecture.md` |
| **Device Control & Transport** | `[INV-DEV-XX]` | ADB sockets, emulator drivers, session bindings, touch/capture | `docs/subsystems/device-control.md` |
| **Base Infrastructure & Scheduling** | `[INV-SCHED-XX]` | Mood calculations, bed priorities, dynamic shifts, drone boost | `docs/subsystems/base-scheduler.md` |
| **Presentation Layer (UI)** | `[INV-UI-XX]` | Vue stores, unpersisted candidate isolation, config syncing | `ui/AGENTS.md` |
| **Vision & Recognition** | `[INV-REC-XX]` | Standard canvas frame contracts, OCR failure handling | `docs/architecture.md` |
| **Automation Solvers** | `[INV-SOLV-XX]` | Clue exchange, recruit calculation, depot inventory sync | `docs/subsystems/` |
| **Integrated Rogue Solver** | `[INV-ROGUE-XX]` | Rogue progression state machines, squad selection | `docs/subsystems/` |

---

## Invariant Formulation Quality Criteria

An invariant is valid only if:
1. **Deterministic & Falsifiable**: It can be verified true or false with zero ambiguity.
2. **Present-Tense**: Uses active present verbs (`rejects`, `clears`, `preserves`, `guarantees`).
3. **Automated Defense**: It can be protected by a hermetic offline unit test in `arknights_mower/tests/`.
