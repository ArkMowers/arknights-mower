---
format: decision
title: Manager-owned Mower AI assistant switch
status: implemented
category: feature
date: 2026-10-13
---

# Manager-owned Mower AI assistant switch

## Problem

Multi-instance administrators need to authorize Mower AI assistant chat separately for each instance without changing standalone behavior or unrelated AI consumers. The existing entry points are [manager.py](../../../../manager.py) and the [manager UI](../../../../ui/manager/MowerManager.vue).

## Decision

Control only Mower AI assistant chat, not model services, diagnostic analysis, navigation or captcha handling. Store `ai_assistant_enabled` in each instance's `config/conf.yml`. The [Arknights Mower AI Assistant Subsystem Description](../../../../docs/subsystems/ai-assistant.md#managed-assistant-authorization) owns the defaults, confirmation and request-admission rules.

Standalone launches always permit chat and expose no switch. Manager-launched instances default to disabled until the administrator saves an enabled choice. The manager reuses its stopped-process configuration guard and edits the switch alongside Token and port; stopping automation or hiding a window is insufficient. A process-start snapshot keeps admission stable until restart rather than introducing runtime switching.

Keep the assistant entry visible so a refusal dialog explains the unavailable feature. The frontend blocks disabled chat connections, while [server.py](../../../../server.py) independently rejects disabled conversation requests before model dispatch. Ordinary settings saves preserve the saved choice and cannot change it through `/conf`.

Turning the switch on requires an acknowledged risk notice and at least five seconds of reading time before enabling the draft. This ties risk acknowledgement to granting access rather than to saving unrelated connection settings. Turning it off changes only the draft without another reading notice. Save remains the only write operation and commits Token, port and switch drafts together through the existing atomic YAML replacement. Cancelling the reading notice leaves the switch off; cancelling instance settings discards all drafts. Failed replacement preserves saved data. Each enabling attempt requires a fresh reading interval; abnormal termination retains only successfully saved choices.

## Alternatives considered

The earlier broader switch for AI and model services would also affect unrelated consumers and is no longer requested. Hiding the assistant entry would obscure the reason for unavailability; retaining it with a refusal dialog is the selected behavior. Runtime switching was considered unnecessary and conflicts with the stopped-process editing requirement.

## Consequences

The switch does not disable model services or revoke access to instance files. A standalone launch permits chat even if its configuration carries a managed false choice. File edits and configuration restoration can alter the next launch's choice; they do not change an already running process. Reading confirmation adds deliberate delay only when turning the switch on; disabling and saving unrelated settings do not wait. The notice retains the risk of local and cross-instance data disclosure without treating multi-instance operation as a security isolation boundary. Revisit the launch snapshot only if runtime authorization changes become an explicit requirement.

This decision changes behavior, not existing domain-concept definitions; no glossary change is needed. Manager locking and atomic-write limits remain governed by the [Arknights Mower Web Access Subsystem Description](../../../../docs/subsystems/web-access.md#7-desktop-instance-manager).

## Verification

Focused offline checks passed for actual startup modes, saved choices, ordinary settings saves, backend rejection before model dispatch and retained configuration after a manager subprocess exits abnormally in [managed_ai_assistant_tests.py](../../../../arknights_mower/tests/managed_ai_assistant_tests.py). [manager_instance_controls_tests.py](../../../../arknights_mower/tests/manager_instance_controls_tests.py) verifies per-instance persistence, unknown YAML preservation, running-process rejection and failed-write retention. Frontend tests passed for timed acknowledgement, cancellation, write failure and disabled or unknown chat admission.

Playwright checks using the actual manager UI with a mocked native bridge passed for the five-second acknowledgement gate, cancellation and retry, saved choice, running-state lock and dialog bounds at 320, 400 and 1024 pixels. A browser harness using the actual assistant component confirmed refusal on lazy mounting and reopening without creating a chat WebSocket. These checks do not establish native-window rendering or live model behavior. An unrelated source-snippet symlink test remains blocked by Windows symlink privileges; the store's pre-existing `sc_uri` lint error is unchanged.
