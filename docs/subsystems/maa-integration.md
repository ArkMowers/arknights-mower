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

### 2.6 Local Inventory and Fight Caps

Workshop execution and inventory selection do not fetch Skland. Selection reads the shared persisted inventory, including confirmed recipe outputs, ingredients and LMD costs. A successful manual sync or warehouse scan supplies the baseline; unknown or invalidated quantities remain unknown rather than becoming the size of the next drop.

Each assistant instance owns a `MaaDropInventory`. `SubTaskExtraInfo` (20003) with `what=StageDrops` contributes only increases in `details.stats[].quantity`, keyed by `taskid` and canonical item ID. `drops` and `addQuantity` are not added again. Repeated or older totals do not change inventory. Failed transactions do not advance receipts. Receipt storage is bounded to 256 tasks per instance; exceeding the bound emits a diagnostic without dropping existing receipts. Active MAA runs hold cloud inventory rebases because a cloud response can already include a drop whose callback is queued. Completion, stop and failure release the hold. Confirmed pending deltas retain existing stale-cloud protection after release.

Inventory-bound Fight tasks receive `drops` targets equal to task cumulative drops plus the current stock deficit. OR rules can use all remaining native targets. AND rules use a native target only when one known deficit remains; each callback reevaluates all pending bound tasks. Reaching a rule sets that task's `times` and medicine/stone allowances to zero, preserving other parameters and subsequent tasks. `series=0` retains MAA automatic consecutive battles. Drops settle per batch, so a completed batch can exceed the configured cap. Ratio-only tasks do not gain a quantity cap. If all selected stages are capped and no fallback remains, no Fight task is submitted.

The decision is recorded in [Local Inventory Execution](../../.agents/notes/implemented/simplification/2026-10-08-local-inventory-execution.md).

### 2.7 Resource and Task Admission

Desktop and Android initialization download the official activity navigation before task submission. Both validate it as a nonempty JSON object and atomically replace the cached file through `write_json`. Download or validation failure preserves the existing cache. A download-complete line reports file installation only. On desktop, a separate resource-loaded line follows a successful `Asst.load` and records the loaded core version, installed resource timestamp, resource directory and incremental directory. A false load result prevents handle construction and connection. Android sends the validated navigation, or the intact previous local cache after a download failure, through `maa_navigation`. The host atomically installs it in the active component cache and checks `AsstLoadResource` while no MAA task is running. Host loading completes before connection verification and task submission. Older hosts without this RPC use the existing component packer. Matching navigation already present in the loaded component is accepted; changed navigation is packed for the next service start and blocks task submission until the loaded component hash matches. This compatibility path requests a service restart and explains that an APK update enables direct navigation loading; the update is optional for this path.

`VerifiedAsst.append_task` requires a positive integer task identifier. `VerifiedAsst.start` requires a successful native result. Rejection raises `MaaCallError` with `operation`, optional `task_type` and optional `stage`; its message names the phase and target and points to the native MAA log without including reporting identifiers or complete task parameters. Native exceptions preserve their original type.

The scheduler records a stage only after its submission succeeds. An ordinary call failure stops queued work, preserves the original diagnostic if ordinary stop cleanup also fails, and leaves the last execution time unchanged. Cancellation and classified device failures propagate. Rejected calls cannot verify a run for rollback backup retirement. The [call verification decision](../../.agents/notes/implemented/simplification/2026-10-11-maa-call-verification.md) records the shared boundary and offline regression coverage.

<a id="independent-credit-task-admission"></a>**Independent Credit Task Admission**: Enabling credit fighting admits a MAA daily run and its `Mall` task even when shopping and friend visits both use Mower or are disabled. The `shopping` and `visit_friends` parameters follow their own enabled settings and runner choices, so a credit-only task does not repeat Mower shopping or visits. A recorded daily credit fight or a submitted last-operation stage still suppresses the `credit_fight` parameter. [Scheduler tests](../../arknights_mower/tests/stage_plan_scheduler_tests.py) cover configuration properties, legacy configuration adapters, task submission and these execution guards.

### 2.8 Android Resource Update Sources

Android resource updates use either GitHub or the existing MirrorChyan `MaaResource` service. Resource source selection is independent of the Android core source. The same download, archive validation, resource merge, backup and update-check receipt flow applies to both resource sources. Android repacks the installed resources for its host and requires a service restart after a full resource update. Per-run activity navigation refresh uses the idle host RPC instead.

Android core updates continue to require the official Android component package. MAA-Meow's MirrorChyan application resource distributes its own APK and is not a Mower core update source. The integration follows MAA-Meow's [resource download resolver](https://github.com/Aliothmoon/MAA-Meow/blob/4e6a4d910d8b5f0b34c9cce2e5cc08a9da4f4f1b/app/src/main/java/com/aliothmoon/maameow/data/datasource/update/MirrorChyanResourceDownloadUrlResolver.kt).

### 2.9 Independent Update Policies

MAA core and resource updates each expose automatic-check and automatic-install switches in their own settings section. Entering the settings page or changing relevant configuration checks only enabled components. Automatic installation also enables its own check and uses the existing update endpoint after a current successful result. Disabling a policy or changing the target, source or core channel invalidates pending automatic installation. The legacy combined check initializes both check policies without enabling installation; explicit resource preferences remain independent.

A missing or invalid local resource timestamp is unknown. A valid published timestamp can update unknown resources after a matching check; known versions require a strictly newer published timestamp. Check receipts remain bound to the target, source and observed local version, are consumed once, and retain the MAA idle-engine and update-job gates. Read-denied resource metadata exposes the file path and remediation guidance. Connection-preset reads and failed resource-loading diagnostics distinguish missing, malformed and read-denied `resource/config.json` files. Merging alters write permissions only on staged replacement files; failures preserve the current installation and rollback copies.

The [independent update decision](../../.agents/notes/implemented/simplification/2026-10-11-maa-independent-updates.md) records the simplification audit and offline coverage.

## 3. Subsystem Invariants

- <a id="mirrorchyan-no-update"></a>**MirrorChyan No Update**: A successful MirrorChyan response whose version is not newer than the submitted installed version requires no download URL and leaves the installation, backup and loaded core untouched.

- <a id="independent-update-admission"></a>**Independent Update Admission**: MAA core and resource automatic checks and installations use independent policies, installations consume a matching check only while MAA is idle, and an unknown local resource version accepts a valid published version without accepting mismatched or reused checks.

- <a id="verified-maa-admission"></a>**Verified MAA Admission**: Desktop activity navigation atomically replaces validated task definitions in `cache/resource/tasks/tasks.json`, preserving other cached resources and the previous navigation on update failure. Resource loading, task submission and task startup require positive MAA results; rejected calls identify their phase and target, clear the pending run without recording successful execution, and preserve rollback backups.

- <a id="normal-long-task-termination"></a>**Normal Long-Task Termination**: Roguelike, SSSCopilot and Reclamation completion or scheduler interruption never creates an error solely because `running()` returns false; core error callbacks and invocation exceptions retain their error reporting.
- Long-task polling returns to the existing idle path after completion or scheduler interruption. Callback lines describe completion and stop; polling adds no generic interruption error or ERROR notification. The [normal termination decision](../../.agents/notes/implemented/simplification/2026-10-09-maa-normal-termination.md) records the removed crash inference.
- <a id="weekday-independent-medicine"></a>**Weekday-Independent Medicine**: MAA Fight passes the configured expiry threshold independently of weekday, local potion use retains positive-threshold and expiring-potion checks, and retired weekend-only keys never alter either rule or persist on save. The [expiry threshold decision](../../.agents/notes/implemented/simplification/2026-10-11-medicine-expiry-threshold.md) records the removed setting and native recognition boundary.

- <a id="local-inventory-execution"></a>**Local Inventory Execution**: Workshop execution and inventory stage selection use persisted local stock without fetching Skland; accepted MAA cumulative drops update that stock once per task, and configured stage caps stop only the reached Fight task while preserving automatic series and subsequent tasks.

- <a id="inventory-stage-priority"></a>**Inventory Stage Priority**: Inventory selection keeps selected annihilation first and defers unbound stages while any selected inventory-bound stage survives its limits; when all bound stages are skipped, ordinary stages remain eligible even with annihilation present, and backend dispatch and frontend preview agree without changing saved selections.
- <a id="total-callback-handling"></a>**Total Callback Handling**: Every MAA callback is consumed without raising; a missing, empty, or unrecognized payload field yields at most one diagnostic line at the C callback boundary instead of an exception.
- <a id="callback-derived-maa-progress"></a>**Callback-Derived MAA Progress**: A MAA run's runtime log derives progress from core callbacks — each task-chain transition and each whitelisted milestone produces one line, while the polling loop contributes at most one heartbeat line per interval.
- <a id="detached-bounded-upload"></a>**Detached Bounded Upload**: A delegated report upload runs off the MAA callback thread, applies a finite connect and read deadline within a bounded number of attempts, and reports its outcome as a log line rather than an exception.

Failure modes: an exception raised inside the C callback is reported by ctypes as an unraisable exception, so that callback loses its line and any state the branch owned, while later callbacks still arrive; a field the tables index without normalising its type raises before any line is produced; a malformed drop payload reaching the report accumulator corrupts the `maa_stop` summary. A heartbeat emitted per poll floods the runtime log, a task chain retained after completion or stop reports finished work as running, and a milestone absent from the tables removes the progress signal for that step. An upload sent from the callback thread stalls every later callback for the length of the network call, and an upload without a connection or read deadline, or without a bound on attempts, can hold a callback thread indefinitely; an exception escaping the upload worker thread reaches only `threading.excepthook`, so it leaves no line in the runtime log at all.

## 4. Implementation Boundaries

- Callback translation: [`maa_callback.py`](../../arknights_mower/utils/maa_callback.py).
- Delegated upload: [`maa_report.py`](../../arknights_mower/utils/maa_report.py).
- Scheduler consumption: [`BaseSchedulerSolver`](../../arknights_mower/solvers/base_schedule.py).
- Regression coverage: `arknights_mower/tests/maa_callback_tests.py`, `arknights_mower/tests/maa_report_tests.py`.
- Decision records: [MAA Callback Logging](../../.agents/notes/implemented/feature/2026-09-30-maa-callback-logging.md), [Delegated Battle Report Upload](../../.agents/notes/implemented/feature/2026-10-01-maa-report-upload.md).
- Interface evidence: [MAA callback protocol](https://docs.maa.plus/zh-cn/protocol/callback-schema.html), [MAA desktop client callback handler](https://github.com/MaaAssistantArknights/MaaAssistantArknights/blob/dev-v2/src/MaaWpfGui/Main/AsstProxy.cs).

## 5. Inventory Stage Selection

`select_stages_by_inventory` evaluates enabled positive item limits before ratios. A stage with an enabled, identified positive limit or an enabled, identified positive ratio member is inventory-bound. Selected annihilation runs first. Surviving bound stages retain their daily-plan order and exclude unbound stages from this dispatch; ratios then choose among surviving members. When no bound stage survives, unbound selections, including last operation, supply the fallback even if annihilation remains. Disabled rules, empty conditions and zero limits or ratios confer no priority. With only capped stages and no remaining selection, no battle is dispatched and other tasks continue. Source plans are never rewritten.

MAA Fight and local operation planning consume this same selection. `previewInventorySelection` mirrors it for the inventory panel. Focused selection and scheduler tests cover partial and complete chip limits, annihilation, inactive rules, ratio bindings and unchanged saved selections. The [inventory priority decision](../../.agents/notes/implemented/feature/2026-10-06-inventory-stage-priority.md) records reuse and verification.

Native settlement accounting and per-batch cap handling follow the [local operation contract](local-operation.md).


## 5. Activity Weekly Plans

<a id="expired-source-plan-cleanup"></a>**Expired Source Plan Cleanup** governs automatic activity fallback. After selecting the destination successfully, the manager removes source-plan selections whose observed or cached stage end times have passed according to the calibrated server clock. The destination, ordinary stages, still-open activity stages, daily row settings and inventory rules remain unchanged. A failed destination selection causes no selection cleanup. Without stage-specific end-time evidence, the manager preserves selections.

Selected activity end times are cached per plan and stage, retained across resource-window removal, refreshed from current data and pruned when selections change. The existing atomic weekly-plan writer persists cleanup and removes obsolete plan-end metadata. Manual plan selection does not perform expiry cleanup.

Frontend activity options, inventory suggestions and plan-end metadata reload on installed resource-version changes. Refreshing plan metadata does not overwrite inventory drafts or selected stages; custom switch times keep precedence.

[Expired source plan cleanup](../../.agents/notes/implemented/bug-fix/2026-10-09-expired-activity-plan-cleanup.md) records the decision and focused verification.


## 6. Desktop Activity Navigation

`update_maa_navigation` validates a nonempty task map whose definitions are objects and atomically replaces `cache/resource/tasks/tasks.json` through the existing JSON writer. Download, validation and write failures retain the previous navigation file. Other cached task files, including `tasks/hotfix/ocr_replace.json`, remain intact.

MAA recursively loads JSON files in `resource/tasks/`, which takes precedence over the legacy sibling `resource/tasks.json`. Desktop activity navigation therefore belongs inside the incremental task directory. Task names may override the installed resource layer; duplicate names within one directory load fail. Android retains `cache/resource/tasks.json` for its component packaging and bridge contract.

The existing verified admission boundary checks resource loading, task IDs and startup before recording execution. The [navigation dispatch decision](../../.agents/notes/implemented/bug-fix/2026-10-12-maa-navigation-dispatch.md) records this path correction. Offline coverage resides in `arknights_mower/tests/maa_navigation_tests.py` and `arknights_mower/tests/maa_admission_tests.py`.

## 7. MirrorChyan Update Results

Windows x64 update requests submit the installed core version to MirrorChyan. `_get_mirrorchyan_asset` checks service errors and CDK expiration, then compares the returned version with the submitted version before requiring a URL. A version at or below the installed version produces release metadata with `runtime=None`. The check route returns `available=false`, no check identifier and a null runtime asset. The installer returns `updated=false` before staging or downloading; the worker reports no update and preserves the loaded core. Newer releases and first installations still require an HTTPS asset. Existing full-package requests on other platforms retain their download behavior.

Failure mode: requiring a URL before comparing versions misclassifies a valid no-update response as incomplete download information.

The [MirrorChyan no-update decision](../../.agents/notes/implemented/bug-fix/2026-10-13-mirrorchyan-no-update.md) records the protocol and offline coverage.
