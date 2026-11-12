---
format: decision
title: Local assistant conversation history
status: implemented
category: architecture
date: 2026-11-12
---

# Local assistant conversation history

## Problem

Previously, conversation state existed only in the browser component and socket. Reloading lost that state, and the server retained only the final streamed chunk for subsequent requests. The [AI Assistant contract](../../../../docs/subsystems/ai-assistant.md#persistent-conversation-history) now defines persistent conversation history.

## Decision

Persist textual turns in an instance-owned SQLite database outside configuration archives, keyed by the stable configuration profile identifier. Store a pending turn before model dispatch and complete it only after the full stream finishes. Restoring history reads text; it never resumes a tool workflow. Keep bounded historical text separately from bounded complete-turn model context.

## Alternatives considered

Browser storage would not survive changing browsers and would require trusting client-supplied context. Provider-side conversation identifiers would couple recovery to a model service and its retention policy. Saving graph execution checkpoints could resume a mutating tool after a restart; textual history deliberately gives up that capability.

## Consequences

History contains user text and model output on local disk. Bounded retention removes older records; interrupted output is visible but excluded from later model context. A process crash can lose partial output after the pending turn was saved, and tool effects already completed cannot be rolled back by deleting history. Configuration export intentionally excludes these records.

## Verification

Focused offline tests passed: 41 backend checks in `ai_history_tests.py`, `ai_security_tests.py` and `config_profile_chat_tests.py`, and 38 frontend checks in `ChatBot.test.js`. They cover restored complete streams, profile and instance isolation, authentication before storage, active-turn conflicts, retained interrupted records, a separate process exiting during a turn, corruption and bounded retention. History reads do not dispatch the model. Playwright inspected the actual component with simulated history at desktop, 390-pixel and 320-pixel widths; the narrow layout has no horizontal overflow and retains the composer. Ruff, ESLint, Prettier and repository governance checks passed. No live model, game device or native desktop window was exercised.

The existing profile and instance concepts retain their meanings; this decision adds a conversation storage boundary without changing glossary definitions.
