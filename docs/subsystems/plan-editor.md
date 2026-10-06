# Scheduling Plan Editor

## 1. Facility Display

`PlanEditor` displays office and training cards in the order selected by the existing local configuration field `swap_contact_train`. The default places the office above training; enabling the setting places training above the office. Main and backup plans share the same display preference. Card selection, operator avatars and editing remain bound to the original `contact` and `train` facility identities.

## 2. Plan Transfer

The setting remains in local configuration and is absent from Scheduling Plan data and its exported advanced settings. Importing or sharing a Scheduling Plan does not carry the displayed office/training order. The existing backend facility-location setting retains its behavior.

## 3. Subsystem Invariants

- **[INV-UI-08] Facility Display Order Isolation**: The local `swap_contact_train` setting changes only the office and training card display order in every Scheduling Plan; facility identities, assignments and exported plan data remain unchanged.

The [display order decision](../../.agents/notes/implemented/simplification/2026-10-06-plan-facility-display-order.md) records shared rendering and verification.

Facility cards retain the [global update drop exclusion](software-update.md#2-global-update-drop).
