# Documentation Subtree Contract

Local contract for documentation under `docs/` adhering to the DeepSeek Harness tier taxonomy.

## 1. Documentation Tier Taxonomy (One Home per Fact)

Apply the [documentation routing rules](../.agents/skills/mower-doc/references/doc-hierarchy.md#routing-rules) for definitions, contracts, procedures, decision rationale and incident history. Use [mower-doc](../.agents/skills/mower-doc/SKILL.md) for maintenance and [record ownership](../.agents/notes/AGENTS.md#1-record-ownership) for triplet merges.

## 2. Linking & Decentralization (No-Index)

- Centralized manual note indices are prohibited.
- Subsystem specifications link directly to the owning active decision; preserve necessary incoming and outgoing links during merges or lifecycle changes.
- All relative Markdown links must resolve to existing files.

## 3. Controlled Language & Discipline

- All documents strictly employ authoritative domain terms defined in [CONTEXT.md](../CONTEXT.md).
- Avoid-list terms are banned across all documents.
- External issue tracker numbers (`#xxx`) are strictly prohibited in documentation text and file names.
