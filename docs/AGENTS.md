# Documentation Subtree Contract

Local contract for Mower subsystem contracts, operational recipes and incident records under `docs/`.

## 1. Documentation Tier Taxonomy (One Home per Fact)

Apply the [documentation routing rules](../.agents/skills/mower-doc/references/doc-hierarchy.md#routing-rules) for definitions, contracts, procedures, decision rationale and incident history. Use [mower-doc](../.agents/skills/mower-doc/SKILL.md) for maintenance and [record ownership](../.agents/notes/AGENTS.md#1-record-ownership) for record merges.

Select document content from the affected [Mower boundary](../.agents/skills/mower-doc/references/doc-hierarchy.md#mower-contract-content). Address current behavior by a meaningful name, stable anchor and direct link; legacy identifiers remain available for decision metadata and historical references.

## 2. Linking & Decentralization (No-Index)

- Centralized manual note indices are prohibited.
- Subsystem specifications link directly to the owning active decision; preserve necessary incoming and outgoing links during merges or lifecycle changes.
- Relative documentation links resolve to existing targets, and Markdown fragments resolve to heading or explicit HTML anchors.

## 3. Controlled Language & Discipline

- All documents strictly employ authoritative domain terms defined in [CONTEXT.md](../CONTEXT.md).
- Avoid-list terms are banned across all documents.
- External issue tracker numbers (`#xxx`) are strictly prohibited in documentation text and file names.
