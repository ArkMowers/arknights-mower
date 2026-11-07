---
format: decision
title: Read-only daily completion status for the run log
status: implemented
category: architecture
date: 2026-11-01
---

# Read-only daily completion status for the run log

## Problem

The original run-log proposal needed to show which tasks enabled in 全部设置 had been processed for the game day. The frontend knew the selected tasks through [`model.js`](../../../../ui/src/task-workflow/model.js), but completion belonged to scheduler attributes and the ordinary runtime snapshot. The browser's calendar date could differ from the scheduler's game day, which changes at 04:00 China time. [`/status`](../../../../server.py) already controlled Start and Stop, so failures or extra snapshot reads for a checklist needed an independent boundary.

Daily records cannot describe every enabled activity. Recruitment, depot scanning, trust rotation, clue exchange, shopping, training, workshop work, stage plans and long tasks use intervals, conditions or queue progress. A check may return without completing its business operation. Treating these facts as daily completion would change their meaning.

## Decision

The read-only `GET /daily-status` separates scheduler facts from frontend selection. The backend owns the game day and record interpretation; the frontend selects enabled daily tasks and presents their states. The [Arknights Mower Base Scheduling Subsystem Description](../../../../docs/subsystems/base-scheduler.md#29-worker-status) owns the complete record, activity, source and initialization rules. The [Arknights Mower Web Access Subsystem Description](../../../../docs/subsystems/web-access.md#1-session-boundary) requires the current instance token before state or filesystem reads and keeps a failure independent of `/status`.

The response retains `game_day`, `source` and `records`, with independent `activities` for recent checks, eligibility, queue facts, actual execution observations and matching long-task progress. Daily `done` means that the scheduler will skip that work for the rest of the game day; `attempted` remains distinct for event sign-in and friend visits. Missing activity facts stay unknown. Reading the endpoint does not change scheduling, task identity or order, timestamps, configuration or persisted state, and reading long-task progress does not create or save a run.

`live` reads a living worker's restored scheduler, copying callback-owned mappings without invoking the expensive full runtime snapshot. `saved` reads what an ordinary start would restore, omits live-only check clocks and treats a formerly running observation as stopped. `none` covers incomplete restoration and unavailable saved data. The saved-row cache avoids repeatedly parsing an unchanged row; malformed snapshots do not affect `/status`.

Execution observations for stage plans, depot scans, annihilation and task-reward checks come from their real entry and exit paths. Native battle counts describe the latest single-stage dispatch. MAA observations accept only the current callback generation and accepted task ID and do not invent a battle count. Annihilation observations expire at the game-week boundary; only an observed 1800 cap means `reward_full`. Long-task progress requires the configured queue identity. Queue inspection is bounded, with lower-bound counts and no invented earliest time after truncation. These display facts use existing save points and add no persistence trigger.

Fresh schedulers initialize all five native daily dates to the preceding game day and leave attempt dates empty; restored dates remain unchanged. Previously, local-date subtraction could initialize report, Skland and friend-visit dates to the current game day on clocks east of UTC+8, for example at UTC+9 between 04:00 and 05:00 local time. That skipped first-start work and would have displayed a false `done` result.

The final checklist shows only enabled tasks with game-day records and only while the scheduler supplies live records. On 2026-11-07 the user replaced the original stopped-state saved-record display because it appeared, disappeared during restoration and appeared again during startup. The API retains its saved view. Periodic activities remain separate response facts after horizontal and expandable activity lists were considered. Wide desktop panes show daily capsules; stacked panes switch between 运行日志 and 今日任务 through the title. The [run-log display rules](../../../../docs/subsystems/web-access.md#task-configuration) own selection, layout, refresh and cancellation. This decision adds no domain concept and changes no existing completion meaning, so the [Arknights Mower Domain Glossary](../../../../CONTEXT.md), which owns those definitions, remains unchanged.

## Alternatives considered

- Adding fields to `/status` would reuse its five-second poll, but the application shell and plan editor would receive unused daily data, stopped-state polling would inspect snapshots unnecessarily, and daily-read failures would share the response driving Start and Stop.
- Reporting only a live scheduler would avoid saved-state parsing. The original design retained `saved` for inspection after stopping; hiding the checklist later did not require removing that API capability.
- Deriving completion from browser log text would depend on changing wording and a browser clock that does not follow the game day.
- WebSocket pushes would update immediately, but these records change infrequently and a polled read already restores the display after navigation or reconnection.
- Adding daily-completion dates to interval tasks would require a new meaning of completion and new scheduler state. Separate activity facts preserve partial work, queued work and unknown data without duplicating this record's responsibility.

## Verification

Historical evidence from 2026-11-01 covered the original daily strip: [`daily_status_tests.py`](../../../../arknights_mower/tests/daily_status_tests.py) passed 11 tests and 50 subtests, including game-day states, token rejection, live/saved/none sources, unchanged state and one parse per saved row. [`daily_default_date_tests.py`](../../../../arknights_mower/tests/daily_default_date_tests.py) passed 18 cases across UTC-5 to UTC+14 and three server hours. The four frontend files `Log.test.js`, `LogOutput.test.js`, `model.test.js` and `mock.test.js` passed; an offline 1440×900 browser preview covered both themes, saved-source labeling and then-current mobile hiding. The structural check passed. Those results describe the earlier display and do not establish the later checklist layout.

The 2026-11-07–08 review passed focused backend interface and activity suites, including [`daily_status_tests.py`](../../../../arknights_mower/tests/daily_status_tests.py) and [`activity_observations_tests.py`](../../../../arknights_mower/tests/activity_observations_tests.py). They cover authorization before reads, live and saved facts, unchanged queue order and persistence, current-week annihilation, matching long-task progress, truncation and accepted callback observations.

The current [`Log.test.js`](../../../../ui/src/pages/Log.test.js) suite passed, covering daily-task selection, partial reward selection, empty and unavailable records, live-only display, cancellation and late-response rejection.

No new live-device or real-browser observation was performed in this review. The unchanged upstream `maa_daily_refresh_tests.py` suite could not run on Windows because its fixture requires `time.tzset`; it is not counted as passed. The older browser evidence does not verify the current layout.

## Consequences

- The checklist reports scheduler facts, not independently verified game outcomes. Mail is done when its solver returns; MAA friend visits have no attempt record and `maa_mail` has no daily record. Activity checks, queue entries and long-task progress do not imply daily completion, and MAA chain completion supplies no battle count.
- Runtime snapshots still use existing save points. Event sign-in, visit attempts, MAA callbacks and `/stop` save; report, Skland, mail and successful native visits can wait for a later save. `_stop_mower` alone and abrupt termination do not save. A saved view can therefore omit recently completed work, which an ordinary restart can repeat.
- A visible running wide-desktop checklist adds one request every 30 seconds; stacked layouts request it only in 今日任务. Stopped users no longer see checklist progress, although the API retains saved facts. Incompatible saved data returns `none` without disrupting Start and Stop.
