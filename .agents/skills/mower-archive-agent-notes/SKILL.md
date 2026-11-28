---
name: mower-archive-agent-notes
description: Use when an Arknights Mower decision actually changes between proposed, implemented, archived or rejected. Do not run for routine review fixes, same-state document merges or cleanup of uncommitted duplicate records.
compatibility: Requires an Arknights Mower checkout and its repository contracts; this is a repository-local skill, not a standalone distribution.
---

# Mower Agent Note Lifecycle

## Inputs and Output

Inputs: selected owning decision record, target state and evidence that the state changed. Output: one transitioned record with aligned status, preserved references and working links.

## Transition

1. Apply [record ownership](../../notes/AGENTS.md#1-record-ownership). A same-topic repair or merge that leaves the decision active updates its record in place. Uncommitted duplication can be cleaned up without manufacturing an archived decision.
2. Verify the [target-state criteria](../../notes/AGENTS.md#2-lifecycle-taxonomy). For implementation, inspect the actual code, relevant behavior results and review findings; neither Git commit status nor a referenced file's existence proves implementation.
3. Run the [transition script](scripts/archive_note.py) only for the justified state change:

   ```bash
   python .agents/skills/mower-archive-agent-notes/scripts/archive_note.py <note-path> --to <state>
   ```

   The script moves the English and Chinese files carrying `format: decision`. Legacy records without that marker retain their three-file transition, including the sidecar. A decision marker with a sidecar is rejected; it cannot bypass legacy metadata checks. The script updates status, but does not run tests, establish approval or certify the semantic criteria. Moves are sequential and are not transactional; inspect files before retrying an interrupted transition.
4. Update affected links. Archived decisions point directly to the replacing decision; rejected proposals retain their rationale. Run `python scripts/verify_governance.py` and report its structural results separately from the state decision.

## Completion

The selected transition is supported by evidence, both language files and any legacy sidecar agree on state, and their links and references are reviewed. Unchanged state completes the assessment without invoking the script.
