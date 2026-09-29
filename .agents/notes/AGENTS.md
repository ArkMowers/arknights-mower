# Technical Decision Notes Subtree Contract

Local contract for `.agents/notes/` managing architecture and feature decision records.

## 1. Lifecycle Taxonomy

All notes reside in one of four lifecycle directories:
- `proposed/`: Under review, design not yet committed to production code.
- `implemented/`: Active, committed, and verified in production code and test suites.
- `archived/`: Deprecated or superseded by newer architecture notes.
- `rejected/`: Evaluated and discarded; preserved to prevent repeating past design traps.

## 2. Category Taxonomy

Every note belongs to exactly one closed category:
- `architecture`: Cross-cutting system design, protocol boundaries, persistence schemas.
- `feature`: User-facing or platform-specific capability additions.
- `bug-fix`: Root-cause resolution of structural defects.
- `simplification`: Removal of dead abstractions, complexity reduction.
- `process`: CI/CD workflows, linting policies, developer experience.
- `testing`: Test harness, fixture frameworks, mock boundaries.

## 3. Bilingual Triplet Contract

Every note consists of three co-located files sharing the exact basename `YYYY-MM-DD-slug`:
1. `{YYYY-MM-DD-slug}.md`: Authoritative English specification and invariants.
2. `{YYYY-MM-DD-slug}.zh.md`: Chinese mirror strictly aligned with English specification.
3. `{YYYY-MM-DD-slug}.sidecar.json`: Machine-readable metadata conforming to the schema below.

### Sidecar Schema

```json
{
  "title": "Descriptive Title",
  "status": "implemented",
  "category": "architecture",
  "date": "YYYY-MM-DD",
  "authors": ["AuthorName"],
  "invariants": ["[INV-01]", "[INV-02]"],
  "code_symbols": ["module.path.ClassName"],
  "test_suites": ["path/to/test_file.py"]
}
```

## 4. Decentralized Linking (No-Index)

Centralized indices (such as manual `INDEX.md` or centralized note tables) are strictly prohibited.
Notes are referenced directly via relative Markdown links from subsystem specifications (`docs/subsystems/`), postmortems (`docs/postmortem/`), and related notes.

## 5. Prose Standards & Controlled Language

- **Present Tense**: Describe existing system reality (e.g., `provides`, `rejects`, `verifies`), never speculative phrasing (`should`, `will`).
- **Domain Terms**: Strictly adhere to [Domain Glossary](../../CONTEXT.md). Never use terms from the *Avoid* list.
- **Zero Issue References**: Never introduce `#xxx` issue trackers in titles, text, or metadata.
- **Concise Rationale**: State context, invariants, and implementation facts without conversational preamble.
