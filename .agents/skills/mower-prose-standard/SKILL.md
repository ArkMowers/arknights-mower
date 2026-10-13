---
name: mower-prose-standard
description: Use when writing or reviewing Arknights Mower formal prose, including documentation, skills, templates, PR or commit text, reports, comments, docstrings and UI copy. Preserve precise current facts; ordinary wording changes do not create records or glossary entries.
compatibility: Requires an Arknights Mower checkout and its repository contracts; this is a repository-local skill, not a standalone distribution.
---

# Mower Prose Standard

## Inputs and Output

Inputs: requested text and its authoritative role. Output: precise prose or read-only findings. Keep meaning and domain terms unless a semantic change is explicitly part of the request.

## Prose Review

1. Read the [terminology guide](references/mower-terminology-guide.md) and the affected bilingual entries before drafting. Reuse these sources within the task; reload them when the source version or writing scope changes.
2. Apply the [placement rules](../mower-doc/references/doc-hierarchy.md#routing-rules). Definitions identify concepts; behavior rules state observable guarantees; procedures describe actions. Refer to business rules by behavior names and direct links to their owning subsystem description.
3. State the actual subject, action and object, then retain conditions and results needed to understand the fact. Use present tense for current rules. Name whose responsibility or which boundary a modifier describes. Keep conditions, exceptions and failure consequences; connect adjacent sentences by their actual causal, conditional or parallel relationship.
4. At the first reference to a project document in standalone prose, use its approved name, explain its purpose for the current matter and link to the relevant file or section. The [Arknights Mower Coding Standards](../../../CODING_STANDARDS.md) define shared behavior rules, concurrency and resource requirements, and verification requirements; identify the relevant requirements when referencing them. Repository prose uses relative links; published PRs use the reviewed commit's accessible links. Later references may use a clear short name.
5. Separate final facts from work records. Decision rationale and postmortem history keep their authoritative role. Preserved quotations and test counterexamples need an explicit label and source, separate from current recommendations. Keep real code identifiers unchanged; backticks or code fences alone do not establish an exception.
6. Verify affected links and run the applicable [text checks](../../../scripts/README.md#formal-text-checks). Program results establish listed-term absence and source-marker validity; a reviewer still checks meaning, title scope and source relevance. Prose editing alone creates no record or lifecycle transition.

## Completion

The text states its intended facts clearly, preserves approved meaning and uses valid links. Report actual semantic changes rather than treating wording improvements as new guarantees.
