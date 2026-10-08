---
name: mower-define-invariant
description: Use when assessing an Arknights Mower guarantee or designing its focused behavioral tests, including a genuinely new independent invariant. Do not assign a new identifier merely because a defect, test or implementation changes.
compatibility: Requires an Arknights Mower checkout and its repository contracts; this is a repository-local skill, not a standalone distribution.
---

# Mower Define Invariant

## Inputs and Output

Inputs: required guarantee, relevant contract, existing registered identifiers and production callers. Output: a reused or independently new guarantee plus focused evidence of its actual behavior. Reuse preserves the existing identifier.

## Guarantee and Verification

1. Search [Coding Standards](../../../CODING_STANDARDS.md) and the owning subsystem contract. If an existing guarantee covers the defect, use its identifier and extend its evidence. Record the reuse decision in the existing review or owning triplet.
2. Only a new independent guarantee receives a new identifier. Consult the [namespace reference](references/subsystem-prefixes.md) and [registration template](templates/invariant-entry.md) before registering its concise guarantee in Coding Standards. The subsystem owns the detailed contract; reviews link to that contract or ask a distinct verification question instead of copying it.
3. Apply [record ownership](../../notes/AGENTS.md#1-record-ownership) when recording a design decision. Update the owning triplet's invariant and test references. Routine test additions need neither another triplet nor another lifecycle transition.
4. Specify the actual observable guarantee: return value, state preservation, persistence, side effect or exception. Exercise the production call path and a condition that exposes the defect; then assert the correct outcome. A preserved field or suppressed side effect need not throw an error.
5. Run the focused offline suite and relevant document checks. Keep a proposed record proposed until [implementation-state criteria](../../notes/AGENTS.md#2-lifecycle-taxonomy) are met; registration or a structurally valid test file does not prove behavior.

## Completion

The guarantee has one registered identifier, a reachable authoritative contract and behavior evidence suited to its real callers. Report test commands and results, including any evidence not yet available. Structural governance checks remain separate from these results.
