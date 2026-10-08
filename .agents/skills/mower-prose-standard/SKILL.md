---
name: mower-prose-standard
description: Use when writing or reviewing Arknights Mower documentation, comments, docstrings or UI copy for precise current facts. Do not turn prose cleanup into invariant registration, record creation or glossary edits without concept impact.
compatibility: Requires an Arknights Mower checkout and its repository contracts; this is a repository-local skill, not a standalone distribution.
---

# Mower Prose Standard

## Inputs and Output

Inputs: requested text and its authoritative role. Output: precise prose or read-only findings. Keep meaning and domain terms unless a semantic change is explicitly part of the request.

## Prose Review

1. Apply the [placement rules](../mower-doc/references/doc-hierarchy.md#routing-rules) before phrasing. Definitions describe concept identity; contracts describe guarantees; procedures describe actions. Existing invariants can be referenced without registering a new one.
2. State the subject and its observable behavior directly. Describe current contracts in present tense. Decision rationale and postmortem context retain their own role rather than becoming scratchpad reasoning or duplicate specifications.
3. Consult the [terminology guide](references/mower-terminology-guide.md) to reach the authoritative glossary and approval rules. Use canonical terms, keep valid factual constraints and remove filler.
4. Verify affected relative links and apply structural checks appropriate to the change. Prose editing alone creates no record or lifecycle transition.

## Completion

The text states its intended facts clearly, preserves approved meaning and uses valid links. Report actual semantic changes rather than treating wording improvements as new guarantees.
