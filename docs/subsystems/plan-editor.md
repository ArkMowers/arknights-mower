# Scheduling Plan Editor

## 1. Facility Display

`PlanEditor` displays office and training cards in the order selected by the existing local configuration field `swap_contact_train`. The default places the office above training; enabling the setting places training above the office. Main and backup plans share the same display preference. Card selection, operator avatars and editing remain bound to the original `contact` and `train` facility identities.

## 2. Plan Transfer

The setting remains in local configuration and is absent from Scheduling Plan data and its exported advanced settings. Importing or sharing a Scheduling Plan does not carry the displayed office/training order. The existing backend facility-location setting retains its behavior.

## 3. Subsystem Invariants

- **[INV-SCHED-26] Backup Operator List Removal**: Active backups apply operator additions followed by per-field removals in backup order; deactivation rebuilds effective lists from the main Scheduling Plan and remaining active backups without mutating source lists, and legacy backups retain additive behavior.

- **[INV-UI-08] Facility Display Order Isolation**: The local `swap_contact_train` setting changes only the office and training card display order in every Scheduling Plan; facility identities, assignments and exported plan data remain unchanged.

The [display order decision](../../.agents/notes/implemented/simplification/2026-10-06-plan-facility-display-order.md) records shared rendering and verification.

Facility cards retain the [global update drop exclusion](software-update.md#2-global-update-drop).

## 4. Backup Operator Lists

Normal backup lists contain additions. `BackupPlanConf.removed_operators` maps the same operator-list field names to comma-separated removal lists. Each active backup adds entries, then removes named entries from the effective list. Later backups can re-add entries. Empty lists inherit earlier results, and removing every inherited entry produces an empty effective list. Unsupported removal fields fail schema validation. Main-plan lists remain direct selections. Backup controls divide each original selection area horizontally into 增 and 减 columns; row height and vertical spacing retain the existing form styles. Rescue plans retain their existing single-list controls.

The editor displays separate 增 and 减 selections for each backup operator option, including 宿舍保留干员 directly below the dormitory blacklist on the plan page. Import, export, autosave and operator replacement retain both lists. Refresh-trading removals match complete operator names, including entries with room qualifiers. Dormitory room order and mood limits retain their own override contracts.

The [operator-list decision](../../.agents/notes/implemented/feature/2026-10-06-backup-operator-list-removal.md) records the merge boundary and verification.

The [shared field decision](../../.agents/notes/implemented/simplification/2026-10-06-shared-plan-operator-fields.md) defines operator-list conversion reuse.

## 5. Operator Group Columns

The plus button beside an operator's group field adds an independent group/replacement column beneath the first column. Deleting any column preserves the others; deleting the first promotes the next column into the legacy fields. Empty operators, `Free`, `Current` and Fiammetta cannot add bindings. Running-plan edit locks cover addition, deletion and every field. Facility clearing removes all bindings with the operator.

Every avatar uses one equal-width color segment per configured column in a 5-pixel bottom strip, with its neutral background preserved in the editor and exported images. Unfinished empty columns retain a transparent segment. The main plan and all backup plans share a color map, so selecting another table preserves the colors of identically named groups. Plan saving, import, export and facility movement retain nested bindings.

The [scheduling contract](base-scheduler.md#211-multiple-group-bindings) defines persisted fields, validation and shift behavior. The [shared rendering decision](../../.agents/notes/implemented/simplification/2026-10-06-shared-group-shift-selection.md) records the simplification.

The [shared color decision](../../.agents/notes/implemented/simplification/2026-10-06-shared-plan-group-colors.md) defines color assignment and rendering.
