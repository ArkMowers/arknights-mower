# Depot Recognition Subsystem

## 1. Scope

`depotREC` reads visible consumable and basic items from standard Capture Frames. Existing item models determine identity before quantity-reader selection. Each warehouse recognition task first calibrates shared materials from a new Skland snapshot under [Inventory synchronization and mastery payments](growth-planning.md#inventory-synchronization-and-mastery-payments); failed synchronization skips scanning and material admission.

## 2. Quantity Contract

Cloud inventory, local restoration, current inventory and history preserve operator-specific and generic tokens, including zero counts supplied by the material snapshot. The warehouse page shows owned tokens and hides only tokens whose quantity is zero or unknown; display filtering does not remove them from stored or exported inventory. Current inventory and history APIs require the existing instance token before reading user data.

Game-side quantity recognition excludes the 13 basic items confirmed in Skland inventory. Their IDs are maintained in `SKLAND_BASIC_ITEM_IDS` in `arknights_mower/utils/depot.py`. Icon recognition still identifies these slots, but their quantities are not read. Other basic and consumable items retain digit-template matching. These two categories supplement cloud inventory; they do not cover other game categories.

Cloud inventory reads complete integer counts directly. Historical CSV rows remain available, but these 13 items are excluded from `scanned_counts` when merging current inventory, so their old OCR quantities cannot be submitted again as game observations. Existing protection for confirmed crafting changes and battle settlement remains unchanged.

Current inventory, exported quantities and merged history use the same reconciled counts. Retained scan rows supply each scan-only item's latest valid quantity and its original observation time, including an explicit zero. A later partial scan does not advance an absent item's observation time or erase its confirmed count. Newer local changes and cloud observations retain their existing precedence.

When retained scan observations are available, warehouse reading removes database rows that have no retained source, observation marker or pending local change. Missing or unreadable scan history does not authorize this removal, and active battle settlement defers it. An unsupported legacy row is discarded as unknown rather than converted into a fabricated zero. A source record and timestamp establish provenance, not recognition accuracy. A confirmed recognition error can be invalidated as unknown without claiming an observed zero; older cached observations cannot restore that invalidated quantity. A newer explicit observation supplies its replacement, including zero. Deleting a historical row alone does not revoke an already timestamped observation.

## 3. Subsystem Invariants

- **[INV-REC-07] Complete LMD Amount**: Depot LMD quantities use the complete integer count returned by Skland; game-side quantity OCR is not used for LMD.

<a id="confirmed-depot-scan"></a>

### Confirmed Depot Scan

A scan confirms the depot scene and a stable Capture Frame before selecting a category and again before reading that category. Recognition uses the same frame that passed those checks. Each invocation starts with an empty result. A scene mismatch or stability timeout ends the invocation with failure without repeating the scan. If a nonempty scan has no confirmed quantities, it succeeds only when every visible item is confirmed as a Skland-covered item.

The selected category highlight must agree with the requested category. Each nonempty category first moves to its left boundary, then reads overlapping horizontal pages until a confirmed stable swipe leaves the content unchanged at its right boundary. Matched content determines the actual displacement, including a shorter final movement; each grid column is read once. Each boundary search permits at most 32 swipes, and each category has a 60-second monotonic deadline. An unmatched movement, category mismatch, unstable frame or exhausted bound ends the invocation without persistence.

Only after both category scans succeed does the scan write explicit zeros for absent items in their installed recognition-model classes, excluding Skland-covered items and identities seen anywhere in the scan. A visible item with an unreadable quantity does not become zero; its previous valid inventory remains until a new quantity is confirmed. If one of several visible slots with the same identity has an unreadable quantity, their partial sum is not accepted. Other categories and old partial CSV rows never acquire inferred zeros. An explicitly empty category supplies the same zero evidence for its own model scope.

A game restart during scene waiting or navigation interrupts the current attempt. The scan discards its partial result and uses the existing scene graph to complete login and return to the home screen before entering the depot again. Both categories are scanned again from the beginning; no category input or recognition resumes on a login screen. Each invocation permits one game restart and one complete rescan. Another waiting timeout during login recovery or the rescan ends the invocation without another restart. Home navigation starts a fresh observation and has a monotonic deadline of at most 120 seconds, shortened to the existing same-scene freeze interval when that interval is lower. A recognized login page that does not respond to input therefore cannot keep navigation running indefinitely. Unsuccessful navigation also ends the scan without writing results; cancellation and device failures propagate through the scan and its scheduling caller to their existing owners.

Scene checks, frame stability checks and the check for a nonempty scan with no confirmed quantities all precede result writes. Failures at these checks leave the previous scan CSV, scan timestamp and merged history unchanged and skip the post-scan mastery dispatch. An empty supplementary result is accepted when both categories are explicitly empty or all visible items belong to the Skland-covered set. If any remaining scan-only items are present but none have confirmed quantities, the scan fails.

After successful confirmation, the scan CSV, database and merged history are written separately; a later persistence error can leave earlier writes in place. Skland synchronization remains a separate observation and retains its existing inventory updates. Existing manual and periodic scan entry points keep their scheduling behavior; scan failure creates no additional retry task or timer.

## 4. Verification

`pytest arknights_mower/tests/depot_quantity_tests.py arknights_mower/tests/knn_memory_tests.py` verifies that covered items never invoke quantity recognition while scan-only items retain their reader. `pytest arknights_mower/tests/depot_lmd_pixel_tests.py` replays recorded frames and verifies that LMD has no scanned quantity while scan-only items remain recognized. `pytest arknights_mower/tests/depot_history_tests.py` covers exclusion of the covered items from historical scan sources.

`pytest arknights_mower/tests/depot_scene_tests.py` exercises the scan and its scheduling caller offline, covering login recovery after a restart, complete rescanning without partial-result duplication, restart exhaustion, scene and stability failures, preservation of prior snapshots, successful scans and explicitly empty categories.

`pytest arknights_mower/tests/depot_stock_reconciliation_tests.py` covers orphaned legacy rows, current/export/history consistency, partial scans, original per-item observation times, explicit zero counts and newer local changes.

`pytest arknights_mower/tests/depot_paging_tests.py` verifies bounded boundary searches, measured page movement, overlapping columns and a shorter final page using constructed image content. Recorded frames verify category selection; they do not establish real-device swipe behavior. The successful-scan tests in `depot_scene_tests.py` exercise disappearance-to-zero through CSV persistence, database reconciliation, current quantities, export and history, and reject incomplete coverage before writes.
