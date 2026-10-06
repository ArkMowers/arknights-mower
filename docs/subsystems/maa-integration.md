# MAA Integration Subsystem Specification

Authoritative specification of the MAA Integration Subsystem, governing the MAA run boundary, callback consumption, translation, filtering, and the runtime progress lines one MAA run produces.

---

## 1. Scope

A MAA run begins at `initialize_maa`, which binds the scheduler to a verified `Asst` handle and assigns a fresh `MaaCallbackLog`, and ends when `maa_stop` releases that handle. The scheduler hands the device to MAA for the whole run, so MAA core callbacks are the only progress signal the run contributes to the runtime log.

Two run paths exist: the desktop path loading the local MAA Python module, and the `MOWER_ANDROID` path using the `mower_android.maa` engine. Both paths assign the reporter before the handle construction and connect call, so connection callbacks are covered.

The subsystem also serves MAA core's delegated drop-data upload. Core decides whether a drop report is produced and builds the complete HTTP request, then hands it over through `ReportRequest` (30000) instead of uploading itself. `upload_report` sends that request, so the Fight task's selected `report_to_penguin` or `report_to_yituliu` report reaches the statistics site. The channel is generic — core labels every request with its own `subtask` — while this backend requests only the stage-drop report. Both report destinations are opt-in configuration; with neither selected, core emits no request.

## 2. Callback Consumption Contract

MAA reports every task chain, sub task and recognition result through a single C callback carrying an `AsstMsg` code and a JSON detail payload. The scheduler registers `on_maa_callback` with the verified handle.

`on_maa_callback` is an instance method rather than a class-level ctypes callback. It decodes the payload, keeps accumulating `StageDrops` into the module-level `stage_drop` for the `maa_stop` report, hands a `ReportRequest` to `upload_report`, and logs the line returned by `MaaCallbackLog.describe` at its level through the scheduler module's logger, so MAA lines retain the runtime log policy of the module that owns the run. The handover is guarded, so a failure escaping `upload_report` becomes a warning instead of an unraisable exception. `describe` returns `None` for a message that carries no readable line. Both polling loops call `report_maa_progress`, which logs the `heartbeat()` line only when the interval has elapsed.

### 2.1 Payload Decoding

`parse_details` accepts the raw payload of one callback and returns a mapping. A missing, empty or unparsable payload returns an empty mapping, and a decoded value that is not an object returns an empty mapping as well. Translation entries read fields defensively and hold either literal text or a reader over the payload.

### 2.2 Translation Tables

`TASK_CHAIN_TEXT` holds task-chain names, `CONNECTION_TEXT` holds connection and device `what` values with their severity, `SUB_TASK_INFO` holds `SubTaskExtraInfo` `what` values, `PROCESS_TASK_START` and `PROCESS_TASK_COMPLETED` hold `ProcessTask` node names with completion keys pairing the task chain and the node, `SUB_TASK_ERROR` holds `SubTaskError` subtask values, and `REPORT_WHY_TEXT` holds the English upload-failure phrases the core returns.

Wording and severity follow the MAA desktop client's callback handler. The tables cover the task chains this scheduler submits — StartUp, Fight, Mall, Award, Recruit, Roguelike, SSSCopilot, Reclamation and SwitchTheme — and carry other known chains so an unexpected one still reads as a name rather than a code. An ERROR line logged from the scheduler module also archives surrounding screenshots, so every client-level error carries that side effect here.

Two entries depart from the client. `ResolutionInfo` keeps an informational DEBUG line, because the client's error for that `what` is gated on a client type `_maa_client_type` never derives. Several entries cover nodes or subtasks the client leaves silent — `ConnectFailed`, `MedicineConfirm`, `RecruitNowConfirm`, `RecruitError`, `ExceededLimit`, the protocol-document names for rogue nodes, an unlisted `SubTaskError`, and the `ProductOfFacility` / `DepotInfo` / `OperBoxInfo` lines the client routes to a toolbox panel — so this log carries failures the client chooses not to show.

### 2.3 Filtering Policy

`ScreencapCost` carries no readable conclusion and produces no line; its raw payload remains in the debug log. The remaining recurring telemetry (`EmulatorFPS`, `FastestWayToScreencap`, `MuMuExtrasInputStatus`) stays at DEBUG. `ProcessTask` sub-task start and completion lines are emitted only for a node-name whitelist, which is the MAA client's own anti-spam mechanism; every other node produces no translated line, and its raw payload remains at DEBUG. `SubTaskStopped` (20004) produces no line. `TaskChainStopped` (10004) does produce one, because the loops that stop MAA on purpose do not all record the stop themselves. `ProductOfFacility`, `DepotInfo` and `OperBoxInfo` stay at DEBUG because the client sends them to a toolbox panel rather than to its log.

### 2.4 Heartbeat

`heartbeat` returns at most one INFO line per `HEARTBEAT_INTERVAL` (60 s), naming the task chain that is running and the elapsed run time, and appends a stall note when no callback has arrived for `STALL_AFTER` (180 s). The recorded task chain clears when a chain completes (10002), stops (10004) or when all tasks complete (3), so neither a finished nor a stopped chain appears as running. `interval`, `stall_after` and `clock` are injectable; the default clock is `time.monotonic`.

### 2.5 Delegated Report Upload

`upload_report` accepts one `ReportRequest` payload and starts the POST on a daemon thread, because the payload arrives on the MAA callback thread. The callback therefore never blocks on the network and never observes an upload failure. A payload without a usable `url` or `body`, and a `url` that exposes no host, are refused with a warning before any thread starts; a `RuntimeError` from thread creation returns `False` behind the same warning. `_post` guards its whole body, because an exception escaping a worker thread reaches only `threading.excepthook` and leaves no record in the runtime log.

The protocol states that the payload `headers` omit `Content-Type`, so the client supplies `application/json; charset=utf-8` and always sends `Accept: application/json`. Header merging is case-insensitive, so a payload `Content-Type` wins under any spelling, HTTP header names being case-insensitive.

The retry parameters, the success criterion and the backup domain are ported from the MAA desktop client. One domain receives up to `REPORT_ATTEMPTS` (3) attempts; only a 5xx response retries, after `REPORT_BACKOFF` (3 s) and then `× 1.5` (4.5 s). Success is strictly status `200`. A network exception ends that domain at once. When the subtask is `ReportToPenguinStats` and the URL host is `penguin-stats.io`, the same sequence repeats against `penguin-stats.cn`, because the primary domain is unreachable on some networks; the host is compared as a host, so a domain appearing in a path or query selects no backup. Any other target is attempted on its own domain only. A `subtask` value that is neither known report still uploads and is labelled with its own name. `REPORT_TIMEOUT` (15 s) bounds the connection and then each read rather than the attempt as a whole, and no bound covers name resolution. A report whose six attempts each reach the connection deadline occupies its worker for about 105 s; a stalled read adds up to another 15 s per attempt, and a peer that keeps the socket alive keeps the worker. Three behaviours therefore depart from the client: its single `HttpClient` deadline covers a whole attempt, its backup-domain test is a substring match on the URL rather than a comparison of the host, and it sleeps once more, after its last 5xx in a domain.

Success logs one INFO line. A penguin failure logs one WARNING line naming the destination and giving up on that report. A failure for any other destination logs the same text at DEBUG, mirroring the client's deliberate silence for 一图流, except that the first such failure of the process is promoted to WARNING so a permanently failing destination leaves at least one line on the WebSocket log page.

## 3. Subsystem Invariants

- **[INV-MAA-04] Inventory Stage Priority**: Inventory selection keeps selected annihilation first and defers unbound stages while any selected inventory-bound stage survives its limits; when all bound stages are skipped, ordinary stages remain eligible even with annihilation present, and backend dispatch and frontend preview agree without changing saved selections.
- **[INV-MAA-01] Total Callback Handling**: Every MAA callback is consumed without raising; a missing, empty, or unrecognized payload field yields at most one diagnostic line at the C callback boundary instead of an exception.
- **[INV-MAA-02] Callback-Derived MAA Progress**: A MAA run's runtime log derives progress from core callbacks — each task-chain transition and each whitelisted milestone produces one line, while the polling loop contributes at most one heartbeat line per interval.
- **[INV-MAA-03] Detached Bounded Upload**: A delegated report upload runs off the MAA callback thread, applies a finite connect and read deadline within a bounded number of attempts, and reports its outcome as a log line rather than an exception.

Failure modes: an exception raised inside the C callback is reported by ctypes as an unraisable exception, so that callback loses its line and any state the branch owned, while later callbacks still arrive; a field the tables index without normalising its type raises before any line is produced; a malformed drop payload reaching the report accumulator corrupts the `maa_stop` summary. A heartbeat emitted per poll floods the runtime log, a task chain retained after completion or stop reports finished work as running, and a milestone absent from the tables removes the progress signal for that step. An upload sent from the callback thread stalls every later callback for the length of the network call, and an upload without a connection or read deadline, or without a bound on attempts, can hold a callback thread indefinitely; an exception escaping the upload worker thread reaches only `threading.excepthook`, so it leaves no line in the runtime log at all.

## 4. Implementation Boundaries

- Callback translation: [`maa_callback.py`](../../arknights_mower/utils/maa_callback.py).
- Delegated upload: [`maa_report.py`](../../arknights_mower/utils/maa_report.py).
- Scheduler consumption: [`BaseSchedulerSolver`](../../arknights_mower/solvers/base_schedule.py).
- Regression coverage: `arknights_mower/tests/maa_callback_tests.py`, `arknights_mower/tests/maa_report_tests.py`.
- Decision records: [MAA Callback Logging](../../.agents/notes/implemented/feature/2026-09-30-maa-callback-logging.md), [Delegated Battle Report Upload](../../.agents/notes/implemented/feature/2026-10-01-maa-report-upload.md).
- Interface evidence: [MAA callback protocol](https://docs.maa.plus/zh-cn/protocol/callback-schema.html), [MAA desktop client callback handler](https://github.com/MaaAssistantArknights/MaaAssistantArknights/blob/dev-v2/src/MaaWpfGui/Main/AsstProxy.cs).

## 5. Inventory Stage Selection

`select_stages_by_inventory` evaluates enabled positive item limits before ratios. A stage with an enabled, identified positive limit or an enabled, identified positive ratio member is inventory-bound. Selected annihilation runs first. Surviving bound stages retain their daily-plan order and exclude unbound stages from this dispatch; ratios then choose among surviving members. When no bound stage survives, unbound selections, including last operation, supply the fallback even if annihilation remains. Disabled rules, empty conditions and zero limits or ratios confer no priority. With only capped stages and no remaining selection, the existing whole-plan fallback remains authoritative. Source plans are never rewritten.

MAA Fight and local operation planning consume this same selection. `previewInventorySelection` mirrors it for the inventory panel. Focused selection and scheduler tests cover partial and complete chip limits, annihilation, inactive rules, ratio bindings and unchanged saved selections. The [inventory priority decision](../../.agents/notes/implemented/feature/2026-10-06-inventory-stage-priority.md) records reuse and verification.
