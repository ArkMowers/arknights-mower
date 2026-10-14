# Depot Recognition Subsystem

## 1. Scope

`depotREC` reads visible consumable and basic items from standard Capture Frames. Existing item models determine identity before quantity-reader selection. Each warehouse recognition task first calibrates shared materials from a new Skland snapshot under [Inventory synchronization and mastery payments](growth-planning.md#inventory-synchronization-and-mastery-payments); failed synchronization skips scanning and material admission.

## 2. Quantity Contract

LMD uses the shared OCR engine on the complete quantity band. A single result with confidence at least 0.90 accepts ASCII digits, an optional decimal fraction and an optional 万 or 亿 suffix after Unicode width and whitespace normalization. Decimal arithmetic applies multipliers of 10,000 and 100,000,000 and accepts only integral results. Missing, malformed, low-confidence or failed OCR returns `None`; the scan skips that item without template fallback. Other items retain template matching. Cloud inventory reads complete integer counts directly and do not strip display units.

## 3. Subsystem Invariants

- **[INV-REC-07] Complete LMD Amount**: Depot LMD quantities retain the complete recognized amount and its 万 or 亿 multiplier; malformed or low-confidence OCR returns an unconfirmed count without digit-template fallback.

## 4. Verification

`pytest arknights_mower/tests/depot_quantity_tests.py arknights_mower/tests/recognition_model_tests.py` covers conversion, rejection and reader selection offline. OCR accuracy on game pixels requires recorded quantity bands. The [decision](../../.agents/notes/implemented/bug-fix/2026-10-13-depot-lmd-units.md) records the template limitation and existing engine reuse.
