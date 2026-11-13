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

The [incomplete-task continuation contract](../../../../docs/subsystems/ai-assistant.md#continue-incomplete-task) extends the same execution record to an explicit new turn after stopping. Reusing bounded saved evidence, unfinished text and the original goal avoids a second summarization call or another persistence framework. The write journal remains authoritative for matching attempts; earlier approval identities cannot authorize the new turn. The continuation tests cover read progress reaching the model, repeated continuation after source pruning and storage reopening, accepted and uncertain write deduplication, and fresh approval after stopping. They use offline model responses and the existing WebSocket and control handlers. Saved progress can be truncated or stale, and matching arguments cannot detect every semantically equivalent write.

Continuation requirements remain separate from uncertain progress evidence so a model can apply a later user correction without treating tool output as an instruction. Their bounded cumulative list is rejected on overflow rather than silently discarding restrictions, and remains available after source-turn pruning. Persisted failure categories distinguish an accepted user stop from provider timeout, provider connection failure and other interrupted work; browser disconnection remains an observer condition. The focused execution and UI tests cover requirement propagation into model calls, new confirmation despite new instructions, bounded rejection, history restoration and stopping while a provider later times out.

The shared composer now uses icon controls for sending and stopping, with mode and summary actions in its ellipsis menu. [Conversation attachments](../../../../docs/subsystems/ai-assistant.md#conversation-attachments) reuse the history database, Pillow and standard-library document parsing; retained references preserve inputs used by a stopped turn without adding a document framework. Offline route and model-protocol checks cover actual file content, authorization, ownership, limits and continuation; frontend checks cover selection, drop, paste and restoration after rejected admission. Live provider file support remains unverified. When downgrading, restate additional requirements and reattach required files: older versions do not apply these inputs.
