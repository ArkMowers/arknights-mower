# Documentation Subtree Contract

Local contract for documentation under `docs/` adhering to the DeepSeek Harness tier taxonomy.

## 1. Documentation Tier Taxonomy (One Home per Fact)

Every fact belongs to exactly one documentation tier:
- **Definitions and rules**: Before choosing a tier, classify the fact using the [documentation routing rules](../.agents/skills/mower-doc/references/doc-hierarchy.md#routing-rules).
- **`architecture.md` & `subsystems/`**: Authoritative system panorama and subsystem specifications.
  - Present-tense statements of fact (e.g., `DeviceSession manages...`, not `will manage` or `should manage`).
  - No historical trade-offs, deprecated design debates, or chronological narratives.
- **`cookbook/`**: Operational, development, and diagnostic recipes.
  - Must include numbered verification steps and code examples.
  - Focus on reproducible developer actions.
- **`postmortem/`**: Incident and regression reviews.
  - The only tier permitted to record chronological narratives, root cause analysis, and historical context.
  - Every postmortem links to the resulting invariants in `CODING_STANDARDS.md`.

## 2. Linking & Decentralization (No-Index)

- Centralized manual note indices are prohibited.
- Subsystem specifications link directly to active decision notes in `../.agents/notes/implemented/`.
- All relative Markdown links must resolve to existing files.

## 3. Controlled Language & Discipline

- All documents strictly employ authoritative domain terms defined in [CONTEXT.md](../CONTEXT.md).
- Avoid-list terms are banned across all documents.
- External issue tracker numbers (`#xxx`) are strictly prohibited in documentation text and file names.
