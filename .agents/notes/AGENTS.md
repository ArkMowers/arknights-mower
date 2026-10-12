# Technical Decision Notes Subtree Contract

Local contract for `.agents/notes/` managing architecture and feature decision records.

## 1. Record Ownership

A triplet belongs to a decision, not to a date, category, skill invocation or session. Before creation, search `proposed/` and `implemented/` for the same problem, governing contract and change scope; inspect candidates rather than deciding from filenames or metadata alone.

Update the existing bilingual triplet for same-topic review repairs, additional tests and incidental simplification. Keep its date, category and lifecycle unless the decision itself changes. New records require a separate, durable decision that remains useful independently of the current repair. Read-only findings can remain in the review report.

When merging duplicates, select the record that owns the decision. Preserve valid content in both languages and the union of authors, invariants, code symbols and test references. Update incoming and outgoing links and confirm the surviving record accurately describes the final state.

An uncommitted redundant triplet with no independent historical value can be removed after its valid content and links are incorporated. A published or historically meaningful decision is archived with a direct link to its replacement. Inspect Git history before choosing cleanup; identical metadata alone proves neither duplication nor historical value. Limit cleanup to the selected records.

## 2. Lifecycle Taxonomy

All notes reside in one of four lifecycle directories:
- `proposed/`: Design or decision under review; implementation and required verification are not complete.
- `implemented/`: Active implementation exists; focused behavior verification and relevant structural checks pass, and review confirms the recorded contract and scope. Evidence identifies tests or checks actually run. Git commit, push and merge state are separate and do not determine implementation status.
- `archived/`: Deprecated or superseded by newer architecture notes.
- `rejected/`: Evaluated and discarded; preserved to prevent repeating past design traps.

## 3. Category Taxonomy

Every note belongs to exactly one closed category:
- `architecture`: Cross-cutting system design, protocol boundaries, persistence schemas.
- `feature`: User-facing or platform-specific capability additions.
- `bug-fix`: Root-cause resolution of structural defects.
- `simplification`: Removal of dead abstractions, complexity reduction.
- `process`: CI/CD workflows, linting policies, developer experience.
- `testing`: Test harness, fixture frameworks, mock boundaries.

## 4. Bilingual Triplet Contract

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

## 5. References and Compatibility

For newly created or changed active triplets, invariant identifiers resolve to declarations in `CODING_STANDARDS.md` and test-suite paths identify existing repository files. Metadata arrays contain nonempty strings. List existing suites and describe planned tests in prose until files exist. A proposal can report partial implementation and tests actually run; label remaining work explicitly and apply the lifecycle criteria before presenting the whole decision as implemented.

The governance entry checks these references strictly for changed `proposed/` and `implemented/` triplets, including staged, unstaged and untracked files. For a branch or commit review, pass `--base <actual-comparison-commit>` to include committed changes from that baseline to HEAD. Unchanged historical and archived/rejected records retain structural validation; missing references are reported as compatibility warnings rather than prompting bulk edits. Outside Git, active reference checks are strict because a historical baseline cannot be established. `--all-active` on the note checker requests a full active-reference audit.

GitHub checks compare PRs against their base SHA and pushes against the prior SHA. Manual runs accept a comparison base; a new branch or a manual run without a base audits every active reference. Missing event data or an unavailable supplied base fails the check.

`code_symbols` are descriptive references whose existence is reviewed without importing production modules; the structural checker verifies their type, not runtime resolution. Metadata overlap can guide a semantic ownership review but never automatically rejects records as duplicates. File existence is not evidence that tests passed.

## 6. Decentralized Linking (No-Index)

Centralized indices (such as manual `INDEX.md` or centralized note tables) are strictly prohibited.
Notes are referenced directly via relative Markdown links from subsystem specifications (`docs/subsystems/`), postmortems (`docs/postmortem/`), and related notes.

## 7. Prose Standards & Controlled Language

- **Present Tense**: Describe existing system reality (e.g., `provides`, `rejects`, `verifies`), never speculative phrasing (`should`, `will`).
- **Domain Terms**: Strictly adhere to [Domain Glossary](../../CONTEXT.md). Never use terms from the *Avoid* list.
- **Zero Issue References**: Never introduce `#xxx` issue trackers in titles, text, or metadata.
- **Concise Rationale**: State context, invariants, and implementation facts without conversational preamble.
