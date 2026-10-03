# Agent Governance & Execution Directives

System-level agent governance and execution constraints for Arknights Mower.

## 1. Essential Context Pointers

- **[Root Directives](../AGENTS.md)**: Global standing instructions and subtree contract pointers.
- **[Domain Glossary](../CONTEXT.md)** ([中文](../CONTEXT.zh.md)): Authoritative terminology for device control, base infrastructure, and scheduling.
- **[Coding Standards](../CODING_STANDARDS.md)**: Invariants `[INV-01]` to `[INV-06]`, concurrency limits, and smell baselines.
- **[System Architecture](../docs/architecture.md)**: Panoramic system design and subsystem boundary definitions.
- **[Decision Notes Subtree](notes/AGENTS.md)**: Lifecycle states, 6 closed categories, and triplet contracts.

## 2. Agent Skills Catalog

Engineering workflow skills located in `.agents/skills/`:
- **[`mower-find-simplifications`](skills/mower-find-simplifications/SKILL.md)**: Pre-flight complexity analysis and dead abstraction elimination.
- **[`mower-define-invariant`](skills/mower-define-invariant/SKILL.md)**: Architectural invariant formulation, registration, and test scaffolding.
- **[`mower-doc`](skills/mower-doc/SKILL.md)**: Tier taxonomy routing (One Home per Fact) and contract placement.
- **[`mower-prose-standard`](skills/mower-prose-standard/SKILL.md)**: Present-tense, contract-first prose auditing (eliminates CoT leakage).
- **[`mower-code-review`](skills/mower-code-review/SKILL.md)**: Two-axis code review (Standards vs Spec) and automated gate execution.
- **[`mower-archive-agent-notes`](skills/mower-archive-agent-notes/SKILL.md)**: Automated lifecycle transition and triplet metadata synchronization.

## 3. Execution Constraints

1. **Targeted Testing Only**: Execute only targeted lightweight unit tests (e.g. `pytest arknights_mower/tests/device_session_tests.py`, `npm test -- ui/src/utils/deviceSettings.test.js`). Never trigger live device integration suites.
2. **Controlled Language**: Use exact domain terminology from [CONTEXT.md](../CONTEXT.md). Strictly avoid prohibited synonyms.
3. **Zero Issue Numbers**: Never introduce `#xxx` issue trackers in commits, code, docstrings, or documentation.
4. **Decentralized Linking**: Link decision notes directly from relevant subsystem specifications and postmortems; do not maintain centralized index tables.
5. **Domain Glossary SSOT**: Any modification to scheduling logic, device control, or configuration schemas must immediately synchronize domain terms in [CONTEXT.md](../CONTEXT.md).
