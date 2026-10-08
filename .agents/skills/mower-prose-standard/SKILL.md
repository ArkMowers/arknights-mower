---
name: mower-prose-standard
description: Enforce contract-first prose standards across Arknights Mower documentation, code comments, docstrings, and UI copy. Eliminates fluff, chain-of-thought leakage, and enforces contract-first present-tense writing.
---

# Mower Prose Standard

Audits, reviews, and edits technical writing to conform to the contract-first prose standard.

## 1. Core Principles

- **Write for the Contract**: Prioritize invariants (`[INV-XX]`), preconditions, postconditions, and guarantees over descriptive narrative.
- **Eliminate Chain-of-Thought (CoT) Leakage**: Never document discarded implementation ideas, internal hesitation, or scratchpad reasoning in production docs or notes.
- **Present-Tense Facts**: Use present tense (`rejects`, `verifies`, `maintains`). Prohibit speculative phrasing (`should`, `will`, `might`).
- **Domain Glossary SSOT**: Use authoritative terms from `CONTEXT.md`. Ban terms in the *Avoid* list.
- **Content Placement**: Apply the [documentation routing rules](../mower-doc/references/doc-hierarchy.md#routing-rules) before editing prose. Glossary entries state concept identity; behavioral rules and implementation guarantees retain their contract destination.
- **Zero Issue Numbers**: Never introduce `#xxx` issue tracker references in commits, docstrings, comments, or markdown files.

## 2. Review Checklist

When writing or reviewing any text:
1. **Remove Decoration**: Delete introductory filler ("In order to...", "It is important to remember that..."). Start directly with the subject and action.
2. **Compress to Invariants**: If a paragraph explains a safety rule, distill it into an explicit invariant statement (e.g., `[INV-02] Target Rebinding Clears Endpoints`).
3. **Verify Links**: Ensure all cross-references use verified relative Markdown links.
