---
format: decision
title: Confirmed assistant operations and retained execution evidence
status: implemented
category: architecture
date: 2026-11-12
---

# Confirmed assistant operations and retained execution evidence

## Problem

The [AI Assistant](../../../../docs/subsystems/ai-assistant.md) previously mixed progress with answers and relied on model instructions for write confirmation. Text history alone cannot establish which tools actually ran or prevent a retried interrupted request from repeating a write.

## Decision

Keep bounded tool evidence and operation outcomes with each stored turn through [the execution owner](../../../../arknights_mower/agent/execution.py), which handles tool classification, exact-argument confirmation, cooperative cancellation and retry deduplication. Persist the attempt before a write and retain an uncertain outcome after interruption. Only the newest interrupted turn can be retried; its operation records follow the retry. Model-facing progress remains separate from final answer context. Explicitly reviewed summaries can supplement bounded recent context.

## Alternatives considered

Prompt-only confirmation cannot enforce the actual arguments. Resuming graph checkpoints could repeat operations after an uncertain crash. Automatically retrying SMTP or database actions cannot establish exactly-once delivery. The chosen approach refuses to repeat an attempted write during retry, including uncertain attempts, and asks the user to inspect its effects.

## Verification

Focused offline tests passed through the real WebSocket and HTTP control paths in [execution tests](../../../../arknights_mower/tests/ai_execution_tests.py). They cover concrete confirmation and changed state, rejection and timeout before side effects, stop during confirmation and an already-started write, interrupted retries, a child process exiting during a write, read-only SQL, verified readback, schema migration and explicit summary adoption. Protocol tests exercise stored streaming chat through mocked HTTP responses for both OpenAI formats and automatic fallback. The feedback inspection test runs real evidence collection and MIME generation with a simulated confirmation and SMTP transport. Frontend tests cover evidence, confirmation, stop, retry and summary controls. No live provider, SMTP delivery or game device was exercised.

## Consequences

Stopping cannot undo an already-started operation; provider reads finish at the next streamed chunk or existing timeout. Email acceptance does not prove recipient delivery. Evidence and summaries are bounded and may omit older records; model wording remains an inference rather than an execution receipt. Confirmation expires after a finite wait and blocks profile activation while the request owns that profile.


Current operational rules belong to the [AI Assistant subsystem description](../../../../docs/subsystems/ai-assistant.md#confirmed-tool-execution). Existing configuration profile, mastery plan and Scheduling Plan concepts keep their meanings; no glossary change is required.

The [live reconnection contract](../../../../docs/subsystems/ai-assistant.md#live-conversation-reconnection) keeps the original execution alive independently of its viewer. Reusing the request handler and bounded in-memory snapshots avoids adding a task service or another framework. A returning viewer can inspect and decide the same pending operation before its original deadline, without reissuing model or tool calls. Process restart deliberately retains the existing invalid-confirmation and explicit-retry boundary. `ai_resume_tests.py` verifies viewer reconnection, lost acknowledgements, confirmation decisions and ownership through the real route handlers with offline model responses.
