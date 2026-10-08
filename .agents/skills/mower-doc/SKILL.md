---
name: mower-doc
description: Guide document placement across the Arknights Mower documentation tier hierarchy (One Home per Fact), enforcing present-tense interface contracts and dead link prevention.
---

# Mower Documentation Tier Governance

Routes technical documentation to its single authoritative location within the repository.

## 1. Documentation Tier Decision Tree

When adding or modifying technical information, route to the single appropriate tier:

For concept definitions, behavioral rules or implementation contracts, first apply the [routing rules](references/doc-hierarchy.md#routing-rules). They distinguish glossary content from subsystem guarantees and handle changes to existing concepts.

| Content Type | Authoritative Destination | Format & Tone Constraints |
| :--- | :--- | :--- |
| **Concept Definitions** | `CONTEXT.md` / `CONTEXT.zh.md` | Names, meanings, boundaries and relationships; edits require explicit glossary approval. |
| **Global Pointers** | `AGENTS.md` | Ultra-lean pointers (1-3 lines per item). Zero implementation details. |
| **Subtree Rules** | `{subpath}/AGENTS.md` | Local constraints, subsystem invariants, and subtree test commands. |
| **System Panorama** | `docs/architecture.md` | Present-tense facts only. Cross-subsystem data flows and invariant matrix. |
| **Subsystem Contracts** | `docs/subsystems/*.md` | Public interfaces, data models, and protocols. No trade-off debates. |
| **Developer Recipes** | `docs/cookbook/*.md` | Actionable operational guides with numbered verification steps and code examples. |
| **Failure Retrospectives**| `docs/postmortem/*.md` | Chronological narrative permitted. Root cause analysis and invariant prevention. |
| **Decision Records** | `.agents/notes/*/*/*.md` | Bilingual triplets with machine-readable sidecars. No centralized index. |

## 2. Gate Verification
Whenever documentation is added or moved:
```bash
python scripts/verify_doc_links.py
python scripts/verify_glossary_alignment.py
```

These commands check relative links and Avoid terms. Complete concept-impact and document-placement review separately under `[INV-06]` in [Coding Standards](../../../CODING_STANDARDS.md#1-core-invariants).
