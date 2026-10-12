# Local Operation Subsystem

## 1. Scope

`OperationSolver` executes Mower native battles using the existing device and recognizer. It shares stage selection, inventory limits and local stock with MAA planning, but never starts MAA to recognize or execute a battle. The initial sanity snapshot remains separate from material inventory reads.

## 2. Inventory Contract

The reader accepts standard 1920×1080 RGB frames and the ordinary settlement bottom row. It matches bundled depot icons, checks every visible slot, and accepts only complete integer quantities. Unknown icons, clipped rows, abbreviated quantities and ambiguous readings return an unconfirmed result. Successful settlements contribute recognized quantities after two consecutive matching observations within three attempts. The displayed quantity is the batch total and is never multiplied by repeat count. A receipt is committed before dismissing settlement; repeated settlement handling in the same batch does not add it again. A fresh batch resets receipt ownership only after its previous settlement is dismissed. Unknown stock remains unknown. Uncertain recognition leaves inventory unchanged and ends the current grinding dispatch so other tasks can continue.

Active native and MAA battles hold cloud rebases until confirmed receipts are consumed. Local deltas retain stale-cloud protection after the hold ends. Before each batch, the shared stage-limit evaluator checks enabled AND/OR limits. A reached cap ends that stage; the scheduler reselects pending stages using updated stock and continues daily tasks when all selected stages are capped. Completed batches may exceed a cap.

## 3. Subsystem Invariants

- **[INV-STOCK-02] Confirmed Local Battle Drops**: Local operation adds only stable, identified settlement quantities once per completed batch, never multiplies displayed totals by repeat count, holds cloud rebases while running, and stops the current stage at its configured inventory cap without cancelling other tasks.

## 4. Verification

Anonymized recorded item strips exercise actual icon matching and OCR; controlled geometry covers multi-digit and clipped-edge rejection. Live device execution is not part of these regressions. Offline regressions cover receipt idempotency, ambiguous recognition, unknown baselines, repeated batches with identical drops, cloud holds, cap stopping and daily-task continuation. The [decision](../../.agents/notes/implemented/feature/2026-10-08-local-operation-inventory.md) records reuse of existing inventory mechanisms.
