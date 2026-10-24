---
name: mower-define-invariant
description: Use when assessing an Arknights Mower behavioral guarantee or designing its focused offline tests. Reuse the owning contract or add a named rule there; historical identifiers are compatibility references.
compatibility: Requires an Arknights Mower checkout and its repository contracts; this is a repository-local skill, not a standalone distribution.
---

# Mower Define Invariant

## Inputs and Output

Inputs: required guarantee, relevant contract and production callers. Output: a reused or independently new named guarantee plus focused evidence of its actual behavior. The skill name remains compatible with existing invocations.

## Guarantee and Verification

1. Read [Coding Standards](../../../CODING_STANDARDS.md) and the owning subsystem contract. If an existing guarantee covers the defect, extend its evidence. Put the conclusion in the change report or existing owning record when useful.
2. A genuinely independent business guarantee gets a behavior name and stable anchor in its owning subsystem, using the [contract example](templates/invariant-entry.md). New business rules require no identifier or central registration. Use a heading when the rule and its related explanation form an independent section. Reviews link to that contract or ask a distinct verification question instead of copying it.
3. Apply [record ownership](../../notes/AGENTS.md#1-record-ownership) only when there is a durable design rationale to retain. Maintain existing records in their existing format; routine test additions require no record or lifecycle transition.
4. Specify the actual observable guarantee: return value, state preservation, persistence, side effect or exception. Design its tests under the [verification discipline](../../../CODING_STANDARDS.md#5-verification-discipline). Exercise the production call path and a condition that exposes the defect; then assert the correct outcome. A preserved field or suppressed side effect need not throw an error.
5. Run the focused offline suite and relevant document checks. Keep a proposed record proposed until [implementation-state criteria](../../notes/AGENTS.md#2-lifecycle-taxonomy) are met; registration or a structurally valid test file does not prove behavior.

## Scheduling Progress Evidence

For a native or simulated scheduling guard, reuse the [Runtime Task Failure contract](../../../docs/subsystems/base-scheduler.md#211-runtime-task-failure). Test the actual dispatch path under repeated unchanged observations, an unrelated ready task, and a relevant new observation or released dependency. Assert that retries do not multiply, independent work executes, and the original remaining work resumes without losing its identity or timestamp. Include persistence when the guarded state survives restart, and verify the corresponding simulator path when both implementations are affected.

An assertion that an action was blocked is insufficient. Show how the prerequisite can be satisfied without that blocked action; if it cannot, repair the dependency rather than adding another wait or stop. Retain focused negative cases for real shared replacements, started handoffs and illegal configurations, without broadening them to unrelated work.

## Completion

The guarantee has a reachable authoritative contract and behavior evidence suited to its real callers. Report test commands and results, including any evidence not yet available. Structural governance checks remain separate from these results.
