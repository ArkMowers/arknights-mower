# Arknights Mower Agent Directives

Root entry point for agent operations. Read the linked contract relevant to the task.

## 1. Authoritative Context Pointers

- **[Arknights Mower Domain Glossary](CONTEXT.md)** ([中文](CONTEXT.zh.md)): Domain definitions, project document names and development/documentation language.
- **[Arknights Mower Coding Standards](CODING_STANDARDS.md)**: Shared behavior rules, concurrency and resource requirements, and verification requirements.
- **[Arknights Mower System Architecture](docs/architecture.md)**: Subsystem boundaries and implementation/verification owners.
- **[Arknights Mower Subsystem Descriptions](docs/subsystems/)**: Detailed behavior rules and interface requirements for each subsystem.
- **[Arknights Mower Development and Troubleshooting Guide](docs/cookbook/)**: Implementation, build, troubleshooting and focused verification procedures for developers and maintainers.
- **[Incident Postmortems](docs/postmortem/)**: Root-cause analysis and narrative retrospective records.

## 2. Subtree Local Contracts

- **[Backend Subtree](arknights_mower/AGENTS.md)**: Python architecture invariants, resource lifecycles, and backend test targeting. Use the [backend source map](arknights_mower/README.md) to find the implementation owner.
- **[Frontend Subtree](ui/AGENTS.md)**: Vue 3 state isolation, recovery policy binding, and frontend unit test execution.
- **[Documentation Subtree](docs/AGENTS.md)**: Tier taxonomy (One Home per Fact), prose standards, and relative linking rules. Use the [documentation map](docs/README.md) to select a task entry.
- **[Decision Notes Subtree](.agents/notes/AGENTS.md)**: Record ownership, lifecycle, bilingual decisions and legacy triplet compatibility.

## 3. Standard Development Workflow

Select the necessary workflow in [Agent Workflow](.agents/AGENTS.md#1-task-selection): read-only review, local repair, independent design decision or documentation maintenance. Skills support that selected workflow; invoking a skill does not require a note, a new invariant or a lifecycle transition.

When creating or updating a PR title or body, you must use [mower-pr](.agents/skills/mower-pr/SKILL.md).

Before writing or reviewing formal project text, read [mower-prose-standard](.agents/skills/mower-prose-standard/SKILL.md) and the affected bilingual glossary entries. Reuse them within the task; reload after a source-version or writing-scope change.

Before adding a decision record, apply [record ownership](.agents/notes/AGENTS.md#1-record-ownership). Complete [concept-impact review](CODING_STANDARDS.md#concept-impact-review); stable domain concepts require no glossary edit.

## 4. Global Execution Constraints

1. **Targeted Testing Only**: Execute only focused unit tests (e.g., `pytest arknights_mower/tests/device_session_tests.py`). Never run full integration suites against live devices.
2. **Controlled Language**: Use the [Arknights Mower Domain Glossary](CONTEXT.md) ([中文](CONTEXT.zh.md)) for domain definitions, document names and development/documentation language. Apply its formal-prose and preserved-source rules through the shared prose skill.
3. **Zero Issue Numbers**: Agent-authored commits, code, docstrings and markdown must not introduce `#xxx` issue tracker references. Preserve GitHub-generated PR references in default merge messages; follow [PR merge defaults](.agents/skills/mower-commit/SKILL.md#pr-merge).
4. **No Central Index**: Decentralize decision records via direct relative links; never maintain centralized note index tables.
5. **User Approval for Glossary Changes**: Before creating or editing `CONTEXT.md` or `CONTEXT.zh.md`, show the user the exact proposed wording or diff and explain its meaning and purpose in plain language. Write only after the user explicitly approves those changes; an existing explicit approval for the same changes remains valid. General implementation requests, sub-agent reviews, and automated checks do not constitute glossary approval. This requirement also applies to concept-impact review and glossary synchronization instructions in subtree contracts and skills.
6. **Software Update Cache**: Follow the [update cache storage contract](docs/subsystems/software-update.md#15-update-cache-storage) for software update state and temporary workspaces.
7. **Scheduling Loop Prevention**: Do not add a delay, polling task or automation stop merely because a runtime result differs from expectation. Preserve the original task, remaining work and timestamp; release dispatch to other work and require new relevant observations or a changed arrangement before retrying an exhausted failure. Keep waits justified by observed production, mood recovery, training completion or a real task dependency, together with their existing deadlines and bounds. Reject confirmed illegal configuration during schedule validation. Verify repeated unchanged-state dispatch, retained tasks and dependency release with focused offline tests. See the [task failure contract](docs/subsystems/base-scheduler.md#211-runtime-task-failure).
