# Scheduling Plan Editor

## 1. Facility Display

`PlanEditor` displays office, training and recycling cards in the local `right_side_room_order`. Dragging swaps positions only when the resulting order is legal; a rejected swap retains the current order and sends no configuration patch. The default order is office, training, recycling; the legacy office/training switch migrates to the equivalent three-room order. Main, backup and rescue editors share this setting and retain their facility identities and assignments. The running-plan edit lock also prevents dragging. Recycling provides two operator rows.

Top to bottom, the legal orders are office/training/recycling, training/office/recycling and training/recycling/office. Recycling swaps only with the office after the office and training have exchanged positions; it never occupies the uppermost of these three positions or sits above training. Both configuration updates and map navigation reject other orders. Reading an older saved configuration moves recycling to the bottom of an impossible complete permutation, preserving the relative office/training order and all unrelated settings. Reading does not write the file; the next ordinary save persists the corrected order. Malformed lists still fail validation.

## 2. Plan Transfer

The order lives in local configuration and controls backend map navigation. It is absent from Scheduling Plan exports and advanced settings. Importing or switching a Scheduling Plan preserves the local order. Dragging these cards changes neither staffing, backup conditions nor explicit tasks; users match the order to their game layout.

## 3. Subsystem Invariants

- **[INV-UI-10] Operator Replacement Coverage**: One-click replacement candidates and existing-target warnings include primary operators and replacements from every main and backup plan binding, without duplicate names or mutations during collection.

- **[INV-SCHED-26] Backup Operator List Removal**: Active backups apply operator additions followed by per-field removals in backup order; deactivation rebuilds effective lists from the main Scheduling Plan and remaining active backups without mutating source lists, and legacy backups retain additive behavior.

- **[INV-UI-09] Backup Facility Import Isolation**: Importing a main-plan facility replaces only the selected backup facility with a deep copy of its type, product and operator bindings; subsequent edits preserve the source main plan, other facilities, backup conditions and explicit staffing tasks, and the edit lock prevents import.
- **[INV-UI-08] Facility Display Order Isolation**: The local `right_side_room_order` admits only office/training/recycling, training/office/recycling and training/recycling/office for display and map navigation; dragging preserves every Scheduling Plan facility identity, assignment, condition and task, and the order remains absent from plan exports.

The [recycling and local layout decision](../../.agents/notes/implemented/feature/2026-10-08-recycle-station-selection.md) records shared rendering, legacy migration and verification.

Facility cards retain the [global update drop exclusion](software-update.md#2-global-update-drop).

## 4. Backup Operator Lists

Normal backup lists contain additions. `BackupPlanConf.removed_operators` maps the same operator-list field names to comma-separated removal lists. Each active backup adds entries, then removes named entries from the effective list. Later backups can re-add entries. Empty lists inherit earlier results, and removing every inherited entry produces an empty effective list. Unsupported removal fields fail schema validation. Main-plan lists remain direct selections. Backup controls divide each original selection area horizontally into 增 and 减 columns; row height and vertical spacing retain the existing form styles. Rescue plans retain their existing single-list controls.

The editor displays separate 增 and 减 selections for each backup operator option, including 宿舍保留干员 directly below the dormitory blacklist on the plan page. Import, export, autosave and operator replacement retain both lists. Refresh-trading removals match complete operator names, including entries with room qualifiers. Dormitory room order and mood limits retain their own override contracts.

The [operator-list decision](../../.agents/notes/implemented/feature/2026-10-06-backup-operator-list-removal.md) records the merge boundary and verification.

The [shared field decision](../../.agents/notes/implemented/simplification/2026-10-06-shared-plan-operator-fields.md) defines operator-list conversion reuse.

## 5. Operator Group Columns

The plus button beside an operator's group field adds an independent group/replacement column beneath the first column. The first row displays only the add button; subsequent rows display only the remove button and retain the other bindings when removed. Empty operators, `Free`, `Current` and Fiammetta cannot add bindings. Running-plan edit locks cover addition, deletion and every field. Facility clearing removes all bindings with the operator.

Every avatar uses one equal-width color segment per configured column in a 5-pixel bottom strip, with its neutral background preserved in the editor and exported images. Unfinished empty columns retain a transparent segment. The main plan and all backup plans share a color map, so selecting another table preserves the colors of identically named groups. Plan saving, import, export and facility movement retain nested bindings.

The one-click operator replacement source menu and existing-target warning use a shared collection of primary operators, first-column replacements and all `group_bindings[].replacement` entries across the main and backup plans. Collection deduplicates names without changing plan data. Selecting a source replaces its entries in every corresponding column while preserving group names and other operators.

The [replacement coverage decision](../../.agents/notes/implemented/bug-fix/2026-10-07-group-binding-replacement-candidates.md) records the regression verification.

The [scheduling contract](base-scheduler.md#211-multiple-group-bindings) defines persisted fields, validation and shift behavior. The [shared rendering decision](../../.agents/notes/implemented/simplification/2026-10-06-shared-group-shift-selection.md) records the simplification.

The [shared color decision](../../.agents/notes/implemented/simplification/2026-10-06-shared-plan-group-colors.md) defines color assignment and rendering.

## 6. Backup Facility Import

The backup facility toolbar copies the selected main-plan facility, including its type, product, primary operators and all group/replacement bindings. The copy replaces only that facility in the selected backup and shares no mutable rows or replacement lists with the main plan. Backup conditions, explicit staffing tasks, other facilities and other backups remain unchanged. The button is hidden on the main plan and disabled by the edit lock.
