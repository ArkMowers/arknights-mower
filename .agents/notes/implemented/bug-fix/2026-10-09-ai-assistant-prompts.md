---
title: AI Assistant Tool Instructions
status: implemented
category: bug-fix
date: 2026-10-09
---

# AI Assistant Tool Instructions

## Contract

[INV-AI-01] keeps model-visible instructions aligned with registered tools, actual arguments, mutation scope and response formatting. The [AI assistant contract](../../../../docs/subsystems/ai-assistant.md) owns the interface details.

## Pre-flight Simplification

The existing system instruction and tool definitions remain the only prompt sources. Redundant unconditional FAQ and stack-extraction requirements are removed; no prompt framework, additional tool or runtime dispatch layer is introduced. No redundant production abstraction requires removal in this scope.

## Implementation

The system instruction selects tools by user intent, uses one local time snapshot and separates evidence from inference. Database examples use the actual schema and SQLite time conversion. FAQ misses request relevant evidence. Feedback arguments use datetime strings. Mastery filters use stored statuses and retry instructions disclose the batch scope. Progress text uses neutral operation descriptions. Scheduling, device control and configuration schemas are unchanged; no glossary edit is required.

## Verification

Offline checks execute published SQL examples against the production schema, exercise advertised mastery filters, submit example datetime arguments through a mocked email sender and verify prompt propagation through the manual tool loop. Model behavior remains probabilistic; prompts do not enforce runtime mutation permissions.

## Standards Findings

Pass: the change retains existing dispatch and resource ownership, adds no abstraction, uses no new glossary terms and passes Ruff and repository governance checks.

## Spec Findings

Pass: system and tool instructions agree on formatting, tool prerequisites, datetime arguments and mastery operation scope. The focused prompt, AI feature and governance suites pass with 25 tests and 12 subtests. Email sending is mocked and no online model is invoked. The dedicated missed-order confirmation flow retains its existing behavior.
