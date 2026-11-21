---
format: decision
title: Structured Log Delivery for WebUI and Runtime Log
status: implemented
category: architecture
date: 2026-11-01
---

# Structured Log Delivery for WebUI and Runtime Log

## Problem

The original WebUI and runtime.log shared a text stream containing user outcomes, developer parameters, raw operator lists and internal identifiers. A survey of 169 hourly files, about ten days and 2.14 million records, counted 35,640 scene-detection lines among 80,995 genuine INFO records. The frontend reconstructed dates, severity, facilities and operators with regular expressions despite the backend already knowing those facts. The store retained only 100 plain-text lines, so verbose details could displace useful summaries. Searching runtime.log by subsystem also required parsing source paths and message wording.

The initial work coordinated with a separate log-page rewrite and therefore introduced transport before changing presentation. That ordering constrained implementation at the time; it is no longer an outstanding dependency. The shared logger and existing text-file readers remain the maintenance boundaries.

## Decision

[`log.py`](../../../../arknights_mower/utils/log.py) captures structured, bounded snapshots before asynchronous queue transfer. [`log_stream.py`](../../../../arknights_mower/utils/log_stream.py) delivers both `records` and legacy `data`, while [`mower.js`](../../../../ui/src/stores/mower.js) accepts the new protocol and older text messages. Required source text remains readable when optional metadata is invalid or too large. The [Arknights Mower Web Access Subsystem Description](../../../../docs/subsystems/web-access.md#live-log-records) owns fields, capacity limits and authorization; this record preserves the reasons for keeping source text alongside structured display data.

Business emitters supply facilities, operator lists, task forecasts, recruitment results and explicit operation identities. These facts let the page update an operation's original heading and show its associated details without guessing association from nearby lines. A task forecast captures its historical labels and staffing positions; later plan edits cannot rename it. The [Arknights Mower Base Scheduling Subsystem Description](../../../../docs/subsystems/base-scheduler.md#task-presentation) owns the meaning of task actions and confirmed progress. Display snapshots do not prepare tasks, alter dispatch or establish actual completion by themselves.

The backend owns the retained source window through [`log_history.py`](../../../../arknights_mower/utils/log_history.py). An operation and explicitly associated details count together; additional record and serialized-byte limits bound memory. Stable stream and sequence identities allow reconnect snapshots to replace the frontend window without duplicates. Retaining anchors and state together prevents detail eviction from inventing a running operation or scene wait. The [retained log window](../../../../docs/subsystems/web-access.md#retained-log-window) owns the full policy. This replaces the original plain-line limit because concise-mode hiding alone could not keep summaries in history.

The [Application Logging rules in the Arknights Mower Coding Standards](../../../../CODING_STANDARDS.md#6-application-logging) separate user milestones from recurring diagnostics. Selected high-volume calls follow those rules; a rewrite of every call site was not required. Repeated identical scenes, profession-filter steps, screenshot telemetry and internal identifiers remain available at DEBUG. User-facing results use Chinese prose. Explicit `log_group` values describe mixed-business calls; otherwise [`log_groups.py`](../../../../arknights_mower/utils/log_groups.py) derives a group from the source path. Unknown sources remain ungrouped.

The file and terminal `BASIC_FORMAT` add an explicitly supplied business prefix after the timestamp, while runtime.log remains text. Structured delivery resolves grouping independently, avoiding mutation of the field used by the file formatter. Existing diagnostic timeline readers continue to accept old and prefixed lines.

[`LogOutput.vue`](../../../../ui/src/components/LogOutput.vue) presents business dividers, captured task arrangements, operation progress, recruitment summaries and scene waits. Detailed and concise modes preserve original text and chronology for copying. Explicit identities, not proximity, own operation associations. [`Log.vue`](../../../../ui/src/pages/Log.vue) presents screenshots and the queue beside the log on wide panes and stacks them on narrow panes. The [running-log presentation rules](../../../../docs/subsystems/web-access.md#running-log-presentation) own the complete rendering and scroll behavior; the [daily-status decision](2026-11-01-daily-completion-status.md) separately owns checklist data and selection. Log levels, metadata and display layouts do not change Scheduling Plan or Actual Occupancy definitions, so the [Arknights Mower Domain Glossary](../../../../CONTEXT.md) remains unchanged.

## Alternatives considered

- Rewriting all 1,583 surveyed call sites together would have coupled message changes to a concurrently changing renderer and made individual regressions harder to review. Introducing transport first and updating selected emitters kept compatibility testable.
- Improving wording alone across the roughly 1,500 distinct INFO-or-higher call sites would help file readers but leave the frontend reconstructing business meaning with regular expressions.
- Switching runtime.log to JSON Lines would make structured searches easier but require replacing existing viewers and the diagnostic timeline parser. A business prefix preserves those text consumers.

## Verification

The following measurements and test results were recorded during the original 2026-11-01 to 2026-11-04 work. They are historical evidence, not a fresh replay during this review:

- Initial transport tests covered live delivery, history, gap-free subscription, token-authenticated forwarding, the local log-read exception and both frontend payload shapes. Queue consumers and screenshot/archive tests passed after changing from text to structured records.
- Replaying the 169 local hourly files from 2026-10-22 to 2026-11-01 reduced `get_scene` INFO from 35,000 to 17,797 (49.2%), all scene INFO from 35,385 to 18,182 (48.6%), and all INFO from 79,932 to 62,729 (21.5%). Quiet periods from 30 to 300 seconds produced `get_scene` reductions between 48.7% and 49.4%; 2,592 remaining transitions were between base scenes 205 and 201. The maintainer accepted the measured reduction on 2026-11-01 instead of changing behavior to reach the proposed 50% target. The original estimate that this change alone halved all INFO was incorrect.
- The missed-order analyzer remained unchanged. A continuing `Scene 9998` still produced INFO every 60 seconds, but 3.46% of previously matching two-minute windows, slid by one second, lost that INFO. Their waiting-scene lines occurred only in the first minute, with another same-scene report less than a minute before the window began.
- Nine clue-flow identifiers moved to DEBUG. Their 1,705 lines were 78.7% of 2,167 clue-flow INFO lines and about 2.2% of that replay's 79,188 INFO lines. Combined with scene filtering, INFO became 60,414 (23.7% lower). The focused clue test failed before the repair and passed afterward.
- Profession-filter telemetry removed 10,286 former live INFO lines; its focused suite passed 27 tests. Screenshot telemetry removed 1,910 former INFO lines with two focused tests passing. Changing archive-warning rate limiting from 30 to 600 seconds reduced 1,196 replayed warnings, with a 30.3-second median interval, to 65; its focused test passed.
- Staffing prose and structured room/operator fields replaced raw list output; 44 empty lists among 2,170 shift announcements became DEBUG. Two selection tests failed before the change and passed afterward, and queue-delivery tests verified the fields. The frontend did not yet consume those fields at that intermediate point; the final renderer does.
- Native operation and player-info messages were reclassified with 233 tests across 15 files passing. Those files had no records in the replay, so no volume reduction was measured for them. Failed, abandoned and unrecognized stages retain the possibility of later-stage execution; their messages no longer incorrectly say the entire run ended. A later 32-call scheduler rewrite, corrected from an initial undercount of 19, had 14 new tests fail before the change and pass afterward; its regression batch passed 657 tests.
- Derived grouping passed a 58-test, 133-subtest batch, including 15 group tests. Task forecasts later passed backend checks for naming, backup boundaries, stopping, snapshots and authenticated queue reads; six frontend files passed 330 tests and the production build passed. An offline browser inspected five queued tasks and a forecast with eight facilities and 27 positions in light, dark and narrow layouts without horizontal overflow or broken portraits. No live device was observed.

The 2026-11-07–08 review passed focused transport, retention, authentication, business-log and frontend suites. [`log_history_tests.py`](../../../../arknights_mower/tests/log_history_tests.py) and [`log_stream_tests.py`](../../../../arknights_mower/tests/log_stream_tests.py) cover retained history and delivery, while [`log_display_payload_tests.py`](../../../../arknights_mower/tests/log_display_payload_tests.py) checks display snapshots. [`LogOutput.test.js`](../../../../ui/src/components/LogOutput.test.js) and [`mower.test.js`](../../../../ui/src/stores/mower.test.js) cover source copying, grouping, progress, scrolling and reconnection. The queue-order regression failed before the repair and passed after restricting same-time refresh grouping to adjacent tasks.

This review performed no new browser or device run and did not repeat the historical volume replay. The unchanged upstream MAA daily-refresh fixture requires `time.tzset` and cannot run on Windows; that suite is not a passing result. Historical browser and build results describe their earlier source version.

## Consequences

Structured snapshots remove the need to infer supported business associations from prose, but legacy text fallback remains a compatibility cost. Unsupported or malformed metadata must leave readable text. New group values require coordination with their documented owner; absent groups remain valid.

The bounded live window can lose older details or entire operations under pressure. Copying reconstructs retained source records, not records already evicted; the runtime file remains the fuller diagnostic source under its existing retention policy. Reduced INFO improves readability while accepting the measured missed-order-window loss described above.

Message changes in the large scheduler still require checks of actual business callers: display improvements must not change scheduling decisions, failures or recovery. The accepted design keeps complete interface rules in subsystem descriptions and decision rationale here, rather than requiring another record for each emitter or UI adjustment.
