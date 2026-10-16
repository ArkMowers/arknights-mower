# Depot Recognition Subsystem

## 1. Scope

`depotREC` reads visible consumable and basic items from standard Capture Frames. Existing item models determine identity before quantity-reader selection. Each warehouse recognition task first calibrates shared materials from a new Skland snapshot under [Inventory synchronization and mastery payments](growth-planning.md#inventory-synchronization-and-mastery-payments); failed synchronization skips scanning and material admission.

## 2. Quantity Contract

LMD uses the shared OCR engine on the complete quantity band. A single result with confidence at least 0.90 accepts ASCII digits, an optional decimal fraction and an optional 万 or 亿 suffix after Unicode width and whitespace normalization. Decimal arithmetic applies multipliers of 10,000 and 100,000,000 and accepts only integral results. Missing, malformed, low-confidence or failed OCR returns `None`; the scan skips that item without template fallback. Other items retain template matching. Cloud inventory reads complete integer counts directly and do not strip display units.

## 3. Subsystem Invariants

- **[INV-REC-07] Complete LMD Amount**: Depot LMD quantities retain the complete recognized amount and its 万 or 亿 multiplier; malformed or low-confidence OCR returns an unconfirmed count without digit-template fallback.

<a id="confirmed-depot-scan"></a>
### Confirmed Depot Scan

A scan confirms the depot scene and a stable Capture Frame before selecting a category and again before reading that category. Recognition uses the same frame that passed those checks. A game restart during scene waiting, a scene mismatch or a stability timeout ends the current scan with failure. Each invocation starts with an empty result and runs once; failure does not restart the complete scan in the solver loop.

Scene checks, frame stability checks and the check for a nonempty scan with no confirmed quantities all precede result writes. Failures at these checks leave the previous scan CSV, scan timestamp and merged history unchanged and skip the post-scan mastery dispatch. A nonempty category with no confirmed quantities cannot produce an empty successful scan; an empty result is accepted only when both categories are explicitly recognized as empty.

After successful confirmation, the scan CSV, database and merged history are written separately; a later persistence error can leave earlier writes in place. Skland synchronization remains a separate observation and retains its existing inventory updates. Existing manual and periodic scan entry points keep their scheduling behavior; scan failure creates no additional retry task or timer.

## 4. Verification

`pytest arknights_mower/tests/depot_quantity_tests.py arknights_mower/tests/recognition_model_tests.py` covers conversion, rejection and reader selection offline. OCR accuracy on game pixels requires recorded quantity bands. The [decision](../../.agents/notes/implemented/bug-fix/2026-10-13-depot-lmd-units.md) records the template limitation and existing engine reuse.

`pytest arknights_mower/tests/depot_scene_tests.py` exercises the scan and its scheduling caller offline, covering restart interruption, scene and stability failures, preservation of prior snapshots, successful scans and explicitly empty categories.
