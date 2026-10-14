# Scheduling Plan Editor

## 1. Facility Display

`PlanEditor` displays office, training and recycling cards in the local `right_side_room_order`. Dragging any of these cards onto another swaps their positions. The default order is office, training, recycling; the legacy office/training switch migrates to the equivalent three-room order. Main, backup and rescue editors share this setting and retain their facility identities and assignments. The running-plan edit lock also prevents dragging. Recycling provides two operator rows.

## 2. Plan Transfer

The order lives in local configuration and controls backend map navigation. It is absent from Scheduling Plan exports and advanced settings. Importing or switching a Scheduling Plan preserves the local order. Dragging these cards changes neither staffing, backup conditions nor explicit tasks; users match the order to their game layout.

Image export splits the complete compressed Scheduling Plan into fourteen QR codes, with seven in each existing left-side row. The right-side facility cards remain unobstructed and ordinary editor captures retain their dimensions. Normal and rescue images preserve recycling staffing, backup plans, explicit tasks and group bindings; normal exports also retain their advanced settings. JSON export retains the same plan fields. Images smaller than the QR-code area receive enough canvas space to prevent clipping. Import scans only QR symbols, excluding other barcode types from the compressed payload. It accepts both fourteen-code images and legacy sixteen-code images, retrying incomplete scans within the existing scale limit before reporting invalid data.

## 3. Subsystem Invariants

- <a id="operator-replacement-coverage"></a>**Operator Replacement Coverage**: One-click replacement candidates and existing-target warnings include primary operators and replacements from every main and backup plan binding, without duplicate names or mutations during collection.

- <a id="backup-operator-list-removal"></a>**Backup Operator List Removal**: Active backups apply operator additions followed by per-field removals in backup order; deactivation rebuilds effective lists from the main Scheduling Plan and remaining active backups without mutating source lists, and legacy backups retain additive behavior.

- <a id="backup-facility-import-isolation"></a>**Backup Facility Import Isolation**: Importing a main-plan facility replaces only the selected backup facility with a deep copy of its type, product and operator bindings; subsequent edits preserve the source main plan, other facilities, backup conditions and explicit staffing tasks, and the edit lock prevents import.
- <a id="facility-display-order-isolation"></a>**Facility Display Order Isolation**: The local `right_side_room_order` permutes office, training and recycling positions for display and map navigation; dragging preserves every Scheduling Plan facility identity, assignment, condition and task, and the order remains absent from plan exports.

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

<a id="income-export"></a>
## 7. Income Image Export

The normal editor's green income button, alongside advanced settings below the schedule image, opens `PlanIncomeDialog` for a detached copy of the current complete plan and advanced settings. The original export menu retains its existing actions. Default simulation duration is three warmup days and twenty-eight measured days, totaling thirty-one days. Both windows are independently editable; warmup output and initial stock are excluded from measured income.

The dialog reads owned operators, elite phases and levels from Mower's shared Skland cache through the authenticated read-only `/riic/income-cache` endpoint. Manual roster input and an explicit maximum-development assumption remain available. Inventory can use cached quantities, with editable additions, or manual quantities. Missing cached basic resources remain unknown and must be filled; unavailable growth never becomes maximum development. Only simulation fields are returned, without account identities or credentials; opening the dialog performs no remote sync or cache write.

Finite inventory runs continuously through warmup and measurement, without outside income. Inventory-conditioned backups always use this ledger. Gold debt is enabled by default: order delivery can make gold negative, representing a modeled shortfall. Disabling debt blocks unfunded deliveries; all other materials remain constrained. The result window separates gold production, consumption, net change and initial, sample-opening and closing balances. LMD net change subtracts manufacturing costs from income within the measured window; potential-output mode records those costs without changing its unlimited ledger. Recycling contributes only daily and sample-total production counts, without random material identities, inventory inflows or material value.

Weights default to the shared Mower income algorithm, read again before each run. Choosing a named algorithm in the dialog saves its coefficients through `/report/recycling_settings`, preserving the current recycling efficiency; opening and calculating only read settings. Saved custom coefficients are supported. An independent per-run custom weight option is temporary. Reports identify the actual algorithm used, even after later parameter edits.

The Worker runs the fixed calculator dependency closure under `ui/src/riic/vendor/`, with source hashes and local patches recorded in `source.json`. The model assumes ideal order runs, inferred facility levels, initial mood 24 subject to personal limits and maximum dormitory ambience for the inferred level. The fixed model is not automatically synchronized with native scheduler changes. Historical slow observations remain visible after completion, cancellation or failure; activity correlation does not establish a cause. Workers and pending reads are released on close; stale results cannot publish into another run.

The existing image-export endpoint accepts an explicit validated plan snapshot and theme without saving it. Calculation completes into the result window without downloading. Tabs provide parameters, income data and searchable event logs, with recent progress limited to 200 entries, sampled events limited to 5,000 and 50 events rendered per page. Detailed resource flows, facility data, assumptions and diagnostics remain in the window. Users may name the exported schedule without changing the saved plan. The name appears in the image title and JPG filename, followed by the completed run's weighted daily income and measured duration. The explicit export button preserves the original schedule and QR layout, then appends only the weighted daily total, measured duration and product icons with daily and sample-total quantities. Gold and LMD each appear once as net changes; absent products are omitted while active products with a zero net change remain visible. Recycling remains a count. Drone-use badges appear at the upper right of facilities that received drones in the completed simulation, using capture-time facility geometry. Export always uses the successful run's frozen inputs and observations. Only complete successful simulations are exported, and failed image rendering retains results for retry. Existing image import restores the complete main/backup plan and advanced settings; it does not restore transient calculation parameters, cached roster/inventory or shared income settings.

The [income-export decision](../../.agents/notes/implemented/feature/2026-10-14-plan-income-export.md) records the Worker and QR-format choices. The [RIIC maintenance skill](../../.agents/skills/mower-riic/SKILL.md) supplies source synchronization and focused verification procedures.

The result window also offers morale curves over warmup and sampling through the existing `RecordLine` board, with its custom observation editor, group cards, rate legends, visibility controls, width expansion and fullscreen view. Main/backup bindings determine group membership, including every binding of a shared operator; all simulated operators remain available to custom views. Simulation views and order remain local to the dialog and never read or write real history or its saved preferences. The chart marks the sampling boundary on an elapsed-time axis. Curves use simulation observations, retain instantaneous charge jumps, and never change scheduling or production. Collinear points are collapsed; each operator retains at most 6000 turn points plus a gap marker and final observation if truncated. The window states this limit. These curves are not included in the compact JPG.
