---
name: mower-doc
description: Use when placing, updating or merging Arknights Mower documentation, including concept definitions and decision records. Do not create a record for every documentation edit or use glossary synchronization for unchanged concepts.
compatibility: Requires an Arknights Mower checkout and its repository contracts; this is a repository-local skill, not a standalone distribution.
---

# Mower Documentation

## Inputs and Output

Inputs: facts being changed, their current authoritative homes and affected links. Output: correctly placed, aligned documents with necessary structural verification. A review-only request produces findings.

## Placement and Editing

1. Classify each fact with the [routing rules](references/doc-hierarchy.md#routing-rules). Keep its full definition in the authoritative home; use direct links elsewhere.
2. For records, search and apply [ownership rules](../../notes/AGENTS.md#1-record-ownership) before deciding to create, update, merge or archive. Preserve both languages and valid metadata. A merge of same-decision documents normally retains the owner's lifecycle.
3. For concepts, assess `[INV-06]` in [Coding Standards](../../../CODING_STANDARDS.md#1-core-invariants). Stable concepts need no glossary edit. An actual glossary edit requires the exact bilingual diff and [explicit root approval](../../../AGENTS.md#4-global-execution-constraints) before writing, including edits to existing definitions.
4. Write for the selected document's role using [mower-prose-standard](../mower-prose-standard/SKILL.md). Update affected relative links; retain historical rationale only where the routing rules permit it.
5. Run `python scripts/verify_governance.py` for changed documents. If scripts changed, run their focused suite as well. Pure document maintenance requires no production tests solely to finish a lifecycle.

## Completion

Each changed fact has one full authoritative definition, affected links resolve, mirrors and metadata remain aligned, and necessary structural checks pass. Record any unresolved semantic or historical question separately from the program results.
