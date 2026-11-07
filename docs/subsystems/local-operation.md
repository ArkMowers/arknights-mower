# Local Operation Subsystem

## 1. Scope

`OperationSolver` executes Mower native battles using the existing device and recognizer. It shares stage selection, inventory limits and local stock with MAA planning, but never starts MAA to recognize or execute a battle. The initial sanity snapshot remains separate from material inventory reads.

## 2. Inventory Contract

The reader accepts standard 1920×1080 RGB frames and the ordinary settlement bottom row. It matches bundled depot icons, checks every visible slot, and accepts only complete integer quantities. Unknown icons, clipped rows, abbreviated quantities and ambiguous readings return an unconfirmed result. Successful settlements contribute recognized quantities after two consecutive matching observations within three attempts. The displayed quantity is the batch total and is never multiplied by repeat count. A receipt is committed before dismissing settlement; repeated settlement handling in the same batch does not add it again. A fresh batch resets receipt ownership only after its previous settlement is dismissed. Unknown stock remains unknown. Uncertain recognition leaves inventory unchanged and ends the current grinding dispatch so other tasks can continue.

Active native and MAA battles hold cloud rebases until confirmed receipts are consumed. Local deltas retain stale-cloud protection after the hold ends. Before each batch, the shared stage-limit evaluator checks enabled AND/OR limits. A reached cap ends that stage; the scheduler reselects pending stages using updated stock and continues daily tasks when all selected stages are capped. Completed batches may exceed a cap.

## 3. Subsystem Invariants

- <a id="confirmed-local-battle-drops"></a>**Confirmed Local Battle Drops**: Local operation adds only stable, identified settlement quantities once per completed batch, never multiplies displayed totals by repeat count, holds cloud rebases while running, and stops the current stage at its configured inventory cap without cancelling other tasks.
- <a id="full-annihilation-reward"></a>**Full Annihilation Reward**: Local operation treats the weekly Annihilation reward as full only when its large figure reads 1800. A full reward ends the Annihilation stage before any battle, so later stages in the same dispatch still run. That dispatch counts as a local run for the `maa_gap` interval and schedules no follow-up for Annihilation; each later dispatch checks the page again.
- <a id="locked-annihilation-proxy"></a>**Locked Annihilation Proxy**: When the Annihilation page shows Proxy Command locked, local operation ends the Annihilation stage the same way as a [full reward](#full-annihilation-reward). The scheduler logs an ERROR that asks the user to clear the current Annihilation manually, without a support operator, and reach 400 kills. It mails that error and archives screenshots once per game day; later skips on the same day only log.

## 4. Verification

Anonymized recorded item strips exercise actual icon matching and OCR; controlled geometry covers multi-digit and clipped-edge rejection. Live device execution is not part of these regressions. Offline regressions cover receipt idempotency, ambiguous recognition, unknown baselines, repeated batches with identical drops, cloud holds, cap stopping and daily-task continuation. The [decision](../../.agents/notes/implemented/feature/2026-10-08-local-operation-inventory.md) records reuse of existing inventory mechanisms. A user-supplied Annihilation screenshot exercises the [weekly reward reading](../../arknights_mower/tests/eliminate_weekly_reward_tests.py); no locked screenshot exists, so the locked Proxy Command branch replaces only the lock-icon match. [Scheduler regressions](../../arknights_mower/tests/local_operation_annihilation_scheduler_tests.py) cover same-dispatch continuation, the absent follow-up and the `maa_gap` wait for both skips, and one lock email per game day.
