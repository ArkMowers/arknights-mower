# Software Update Contract

## 1. Command Execution

`Worker.run_command` executes fixed argument lists without a shell. Each command has a monotonic deadline and respects preparation cancellation. POSIX commands own a process group; Windows commands enter a dedicated Job before execution and keep their descendants inside that Job. The installer uses the standard library.

## 2. Global Update Drop

`GlobalUpdateDrop` excludes local upload targets, editable controls, draggable elements and elements marked `data-no-update-drop`, including their descendants. The Scheduling Plan facility layout carries one marker covering every card, background and gap, including fixed facilities and cards locked during import. The marker does not cover the surrounding page or the editing section below the layout. Entering or hovering over an excluded target clears the update drag hint, including when a local handler consumes the event. Other page regions accept update packages through the existing confirmation flow.

[Facility layout drop boundary](../../.agents/notes/implemented/simplification/2026-10-06-facility-layout-drop-boundary.md) records the decision and focused verification.

## 3. Subsystem Invariants

- **[INV-UPD-06] Cross-Channel Upgrade Selection**: Installed development and beta channels admit newer installable releases from more stable channels, preserve the selected channel and use only a verified OTA from the exact installed version to the selected target.

- **[INV-RES-01] Template Glyph Coverage**: Resource generation requires a real glyph for each rendered character and preserves the calibrated glyphs already present in its subsets. Missing source coverage stops generation before either subset file changes.

- **[INV-UPD-04] MAA Resource Platform Parity**: Installed MAA on Windows, macOS and Linux exposes independent resource checks and updates; installation preserves core and Python files, rejects active MAA use, and retains resource rollback copies.
- **[INV-UPD-05] Release Artifact Scope**: Future release builds exclude macOS x64; OTA publication targets only Windows x64 and Android ARM64, including Nightly, and rejects unsafe Android runtime paths without publishing a new channel index.

- **[INV-UPD-07] Shared Skill Data Packaging**: Application archives contain the backend-owned building-skill catalog independently of frontend sources or build output; both backend consumers and the frontend share that catalog, while resource packages retain their historical entry path for existing clients.
- **[INV-UPD-03] Nightly Direction Evidence**: Same-alpha Nightly updates use valid publication times or verified upstream commit ancestry to determine direction; missing index history alone never establishes a downgrade, and unverified direction retains manual confirmation.
- **[INV-UPD-01] Owned Command Completion**: Windows update commands own their descendants before execution and verify tree completion within a finite budget before releasing the temporary checkout; cancellation preserves other application instances.
- **[INV-UPD-02] Complete Registration Scan**: Strict registration scans retry unreadable files within one shared monotonic budget, preserve unverified registrations and raise `InstanceScanError` when that budget expires instead of returning an incomplete snapshot.
- **[INV-UI-07] Facility Update Drop Isolation**: The Scheduling Plan facility layout, including every card, background and gap, suppresses and clears global update drag hints without intercepting facility sorting; other page regions retain update-package drops.

## 4. Registration Scan Boundary

`update_runtime.instances` returns a complete live-registration snapshot in strict mode. Its default five-second retry budget covers the entire scan. A zero timeout performs one attempt and reports unreadable registrations immediately. `strict=False` explicitly permits best-effort results. Read failures never establish process termination or authorize deletion of an unverified registration.

[Restart readiness scan budget](../../.agents/notes/implemented/testing/2026-10-06-restart-readiness-scan-budget.md) records the focused test correction.

## 5. Failure Boundary

Cancellation and timeout terminate only the owned command tree. Successful root-process completion also requires the Job to become empty. Cleanup failure remains an error; it never establishes successful installation or permits stopping unrelated instances.

[Command tree cleanup](../../.agents/notes/implemented/bug-fix/2026-10-02-update-command-tree-cleanup.md) records implementation and focused verification.

## 6. Nightly Version Direction

`release_is_downgrade` compares semantic version components before resolving same-alpha Nightly builds. Valid, timezone-aware publication dates in the channel index determine direction without another request. Missing history or invalid dates trigger one upstream GitHub commit comparison from the installed SHA to the target SHA, using the selected HTTP proxy and existing finite request timeout. `ahead` and `identical` permit updating; `behind`, `diverged`, malformed responses and request failures retain manual confirmation. Identical version names need no comparison. Offline package inspection remains network-free and retains confirmation when SHA ordering is unknown.

[Nightly direction evidence](../../.agents/notes/implemented/bug-fix/2026-10-07-nightly-direction-evidence.md) records the contract and focused verification.

## 7. MAA Resource Updates

`/maa-resource-update/info` reports support for installed MAA on Windows, macOS and Linux. `MaaBasic` displays its independent resource controls from that response. `/maa-resource-update/check` uses the selected GitHub or Mirror酱 source; `/maa-resource-update/start` requires a matching successful check showing a newer resource version. Both resource and core updates share the maintenance lock and reject active MAA use.

`install_maa_resource_update` stages an incremental resource merge, preserves core and Python files, and replaces only `resource`. The previous resource tree remains in `resource.old`; failed replacement or version verification restores the original tree and previous backup.

[Windows MAA resource updates](../../.agents/notes/implemented/bug-fix/2026-10-08-windows-maa-resource-update.md) records the platform correction and focused verification.

## 7. Resource Template Fonts

`auto_get_res_new.py` prepares room-name glyphs before the three operator models load fonts. `build_default_model` prepares mastery name and skill glyphs before rendering. Complete originals and licenses reside in MowerFonts under `fonts/`. Resource builds pass that checkout through `MOWERFONTS_DIR`; local generation without the variable uses `ArknightsGameResource/fonts`. Source fonts remain outside runtime and resource packages. A complete subset needs no source file. Missing source files or glyphs stop generation before font or charset mutation. Full game fonts and fontTools are generation dependencies; runtime continues loading compressed models.

[Automatic resource font expansion](../../.agents/notes/implemented/bug-fix/2026-10-09-resource-font-expansion.md) records the decision and focused verification.

## 9. Shared Resource Revisions

Resource update checks accept a different compatible content hash on the same date when source timestamps are equal, missing or incomparable. Hashes identify content and are never sorted to infer release order. Earlier resource dates and comparable older timestamps remain rejected; identical content reports no update.

The immutable resource installer records `builtin_version` in the shared `index.json` alongside the ordered accepted packages. Same-day revisions follow installation order only while that baseline matches the current builtin resource version. A software update that changes builtin resources clears this precedence implicitly through the version mismatch, so an older same-day cache cannot replace the new builtin set. Legacy indexes without a baseline retain conservative selection until another resource installation records one. Installation failures restore both the prior package list and baseline; running instances switch complete generations only at existing task boundaries.

[Verified Resource OTA](../../.agents/notes/implemented/architecture/2026-10-09-resource-ota.md) records installer reuse and verification for full packages and same-day OTA revisions.

## 10. Published Artifact Scope

Release builds produce Windows x64, Linux x64/ARM64, macOS ARM64 and Android ARM64 full packages. MowerRelease generates OTA packages only for Windows x64 and Android ARM64, for public releases and Nightly. Linux and macOS updates use full packages. Runtime filenames use canonical relative POSIX paths; Debian multiarch colons remain valid, while traversal, drive prefixes, duplicate entries and host data files remain invalid. OTA validation errors prevent channel index publication.

[OTA release target scope](../../.agents/notes/implemented/simplification/2026-10-09-ota-release-target-scope.md) records focused verification.

## 11. Cross-Channel Upgrades

Installed development checks compare the development, beta and stable indexes. Beta checks compare beta and stable; stable checks read only stable. A more stable channel replaces the selected target only when its semantic version is higher and its full package passes platform, official-URL and SHA-256 metadata validation. Missing, unavailable or incompatible optional indexes preserve the primary channel result. The selected channel remains unchanged after installation, so later eligible Nightly builds remain discoverable. Source development deployments continue following their selected Git branch.

Channel indexes retain their schema and channel-specific targets. Full and OTA assets come from the selected target's same index. OTA requires the exact installed source version; absence or reconstruction failure falls back to that target's full package. MowerRelease reserves recent Nightly sources for beta targets, and recent beta and Nightly sources for stable targets, with independent bounded quotas and platform filtering. Same-alpha Nightly direction retains [publication and commit evidence](#6-nightly-version-direction).

[Cross-channel OTA upgrades](../../.agents/notes/implemented/bug-fix/2026-10-09-cross-channel-ota-upgrades.md) records the decision and focused verification.

## 12. Shared Building-Skill Data

`arknights_mower/data/building_skill.json` is the sole committed building-skill catalog. Dormitory classification and building-skill unlocks read it through `resource_pkg_path`; the frontend imports the same catalog for its bundled fallback. The HTTP filename `/basement_skill/skill.json` remains unchanged. Android and desktop packaging collect the catalog with the backend data directory, and Android publication requires a nonempty catalog.

Resource packages retain `ui/src/pages/basement_skill/skill.json` as their historical archive entry. `write_building_skill_data` serializes the catalog once and writes identical bytes to the shared source and an ignored compatibility export used by the existing resource publisher. The compatibility export is not an application packaging input. `resource_pkg_path` maps the shared catalog request to that entry only when a resource package is selected; a missing entry in a selected package never permits mixing in bundled data. Resource validation, content hashing and existing clients retain their archive contract.

[Shared building-skill data](../../.agents/notes/implemented/simplification/2026-10-09-shared-building-skill-data.md) records the boundary and verification.
