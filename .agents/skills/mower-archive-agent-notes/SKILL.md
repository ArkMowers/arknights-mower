---
name: mower-archive-agent-notes
description: Manage the lifecycle transitions of technical decision notes between proposed, implemented, archived, and rejected states, preserving triplet metadata and invariant links in Arknights Mower.
---

# Mower Agent Note Lifecycle Management

Orchestrates state transitions for decision notes under `.agents/notes/`.

## 1. Lifecycle Transitions

```
[ proposed/ ] ──(Implementation Verified)──> [ implemented/ ]
      │                                             │
 (Discarded)                                   (Superseded)
      ↓                                             ↓
[ rejected/ ]                                 [ archived/ ]
```

## 2. Transition Rules

1. **Proposed to Implemented**:
   - Move triplet `{slug}.md`, `{slug}.zh.md`, `{slug}.sidecar.json` from `proposed/{category}/` to `implemented/{category}/`.
   - Update `status: implemented` in frontmatter of both markdown files and in the sidecar JSON.
   - Verify all referenced code symbols and unit test suites exist.

2. **Implemented to Archived**:
   - When a newer note supersedes an existing architecture or feature note, move the old triplet to `archived/{category}/`.
   - Update `status: archived`.
   - Add a top-level notice in the archived note pointing to the superseding note.

3. **Proposed to Rejected**:
   - Move triplet from `proposed/{category}/` to `rejected/{category}/`.
   - Update `status: rejected`.
   - Record the concrete rejection rationale (e.g., performance regression, architectural mismatch).

## 3. Verification
After any transition:
```bash
python scripts/verify_agent_note_format.py
python scripts/verify_doc_links.py
```
