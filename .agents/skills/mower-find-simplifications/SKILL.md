---
name: mower-find-simplifications
description: Use when identifying redundant abstractions or reducing suspected complexity in Arknights Mower. Do not use as mandatory preflight for every repair or as a requirement to create a simplification record.
compatibility: Requires an Arknights Mower checkout and its repository contracts; this is a repository-local skill, not a standalone distribution.
---

# Mower Find Simplifications

## Inputs and Output

Inputs: requested audit or authorized repair, suspected complexity, relevant callers and public contracts. Output: evidence-backed findings; an authorized change also includes focused behavior verification. A clean audit is a valid result.

## Assessment

1. Inspect callers with `rg` and read their real execution paths. Check public interfaces and plugins before classifying a wrapper, option, conversion or fallback as redundant. A single caller alone is not proof of uselessness.
2. Describe the observable behavior the replacement preserves, the complexity removed and any risk. A read-only audit ends with findings and does not write a proposal.
3. For authorized changes, apply [record ownership](../../notes/AGENTS.md#1-record-ownership). Incidental simplification, review fixes and added tests update the original triplet when recording them is useful. Only an independent durable decision warrants a separate proposal.
4. For that independent proposal, optional starting points are the [English template](templates/simplification-note.md), [Chinese template](templates/simplification-note.zh.md) and [sidecar template](templates/simplification-note.sidecar.json). Replace example metadata with observed authors and actual references; the templates create no requirement for a new record.
5. Implement only authorized scope and verify the changed production path with focused offline tests. Reuse the affected invariant rather than defining one merely because a helper disappeared.

## Completion

Findings identify callers and contracts. Authorized changes preserve the stated behavior and pass necessary checks. The record choice is justified by decision ownership; no candidate or no new record is a completed outcome.
