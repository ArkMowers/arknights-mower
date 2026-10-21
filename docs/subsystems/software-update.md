# Software Update Contract

## 1. Command Execution

`Worker.run_command` executes fixed argument lists without a shell. Each command has a monotonic deadline and respects preparation cancellation. POSIX commands own a process group; Windows commands enter a dedicated Job before execution and keep their descendants inside that Job. The installer uses the standard library.

<a id="managed-update-authorization"></a>
### Managed Update Authorization

Each instance stores `updates_enabled` as a strict boolean in `config/conf.yml`. Standalone launches retain update access regardless of this saved manager choice. Managed launches (`MOWER_MANAGED=1`) allow updates by default when the choice is missing, without persisting a choice; saved true and false choices remain effective. AI assistant chat authorization is independent and still defaults to disabled for managed launches. Effective update permission is captured once at startup and exposed through `/status`, independently of later configuration reloads or manager termination.

The manager edits this choice only after the instance process exits. Individual settings and the batch table use the existing stopped-instance checks, captured targets, changed-cell submission and atomic YAML writes. Update All On and All Off affect only editable rows' drafts, without changing AI authorization or starting an update; Save commits the choices. No AI risk-reading notice applies to this independent permission.

Disabled instances hide software, resource and MAA update controls and the global update-package drop interface. Their backend rejects software-update, MAA core/resource-update and manual/online resource-install requests with HTTP 403 and `updates_disabled`, before reading uploads or starting workers. Remote resource-version checks are denied; local version reads remain available. Desktop and page-start automatic update checks and installations are suppressed without changing the user's saved automatic-update preferences. Ordinary configuration saves cannot change manager authorization, and configuration backup imports preserve the current instance's authorization instead of adopting the archive's choice.

During a shared software update, the temporary progress service preserves each instance's permission: unauthorized instances can read progress but cannot cancel the update, and their cancellation control is hidden. Authorization controls who can initiate or cancel maintenance, not which version an instance uses. Authorized updates can still replace a shared installation or shared resources used by unauthorized instances. This boundary does not restrict users who can directly edit host files or launch a separate standalone process.

## 2. Global Update Drop

`GlobalUpdateDrop` excludes local upload targets, editable controls, draggable elements and elements marked `data-no-update-drop`, including their descendants. The Scheduling Plan facility layout carries one marker covering every card, background and gap, including fixed facilities and cards locked during import. The marker does not cover the surrounding page or the editing section below the layout. Entering or hovering over an excluded target clears the update drag hint, including when a local handler consumes the event. Other page regions accept update packages through the existing confirmation flow.

[Facility layout drop boundary](../../.agents/notes/implemented/simplification/2026-10-06-facility-layout-drop-boundary.md) records the decision and focused verification.

## 3. Subsystem Invariants

- <a id="cleanup-contention-isolation"></a>**Cleanup Contention Isolation**: The [backup cleanup boundary](#16-backup-cleanup-contention) distinguishes routine lock contention from failed maintenance and preserves pending records.
- <a id="local-update-cache"></a>**Local Update Cache**: Software update coordination, uploads, downloaded packages and job workspaces reside under shared `@app/tmp/updates/`, with installation identity isolation; package-inspection temporary directories use the same tree instead of system cache or temporary directories.

- <a id="elevated-windows-desktop-launch"></a><a id="windows-desktop-launch-permissions"></a>**Windows Desktop Launch Permissions**: Both packaged Windows desktop executables inherit the launcher's permissions without requesting elevation; manager-launched instances inherit the manager's token through ordinary process creation.

- <a id="cross-channel-upgrade-selection"></a>**Cross-Channel Upgrade Selection**: Installed development and beta channels admit newer installable releases from more stable channels, preserve the selected channel and use only a verified OTA from the exact installed version to the selected target.

- <a id="template-glyph-coverage"></a>**Template Glyph Coverage**: Resource generation requires a real glyph for each rendered character and preserves the calibrated glyphs already present in its subsets. Missing source coverage stops generation before either subset file changes. Expansion verifies actual character maps, uses only the matching game font, and preserves existing glyphs and metrics.

- <a id="maa-resource-platform-parity"></a>**MAA Resource Platform Parity**: Installed MAA on Windows, macOS and Linux exposes independent resource checks and updates; installation preserves core and Python files, rejects active MAA use, and retains resource rollback copies.
- <a id="release-artifact-scope"></a>**Release Artifact Scope**: Future release builds exclude macOS x64; OTA publication targets only Windows x64 and Android ARM64, including Nightly, and rejects unsafe Android runtime paths without publishing a new channel index.

- <a id="shared-skill-data-packaging"></a>**Shared Skill Data Packaging**: Application archives contain the backend-owned building-skill catalog independently of frontend sources or build output; both backend consumers and the frontend share that catalog, while resource packages retain their historical entry path for existing clients.
- <a id="nightly-direction-evidence"></a>**Nightly Direction Evidence**: Same-alpha Nightly updates use valid publication times or verified upstream commit ancestry to determine direction; missing index history alone never establishes a downgrade, and unverified direction retains manual confirmation.
- <a id="owned-command-completion"></a>**Owned Command Completion**: Windows update commands own their descendants before execution and verify tree completion within a finite budget before releasing the temporary checkout; cancellation preserves other application instances.
- <a id="complete-registration-scan"></a>**Complete Registration Scan**: Strict registration scans retry unreadable files within one shared monotonic budget, preserve unverified registrations and raise `InstanceScanError` when that budget expires instead of returning an incomplete snapshot.
- <a id="facility-update-drop-isolation"></a>**Facility Update Drop Isolation**: The Scheduling Plan facility layout, including every card, background and gap, suppresses and clears global update drag hints without intercepting facility sorting; other page regions retain update-package drops.

## 4. Registration Scan Boundary

`update_runtime.instances` returns a complete live-registration snapshot in strict mode. Its default five-second retry budget covers the entire scan. A zero timeout performs one attempt and reports unreadable registrations immediately. `strict=False` explicitly permits best-effort results. Read failures never establish process termination or authorize deletion of an unverified registration.

`RuntimeRegistration` publishes a snapshot of its in-memory record under a per-instance lock. Registration writes flush and sync the temporary file before atomic replacement; POSIX also syncs the containing directory. Failed heartbeat publication emits an error through the application logger and retries on the next heartbeat. Configured file and interface handlers receive the error even without console output. Atomic publication preserves a complete previous record when preparation or replacement fails. Closing marks the registration closed, waits up to six seconds for in-flight publication and removes the registration while further publication is excluded. A close timeout preserves the registration for another cleanup attempt. A closed registration never starts another publication.

[Restart readiness scan budget](../../.agents/notes/implemented/testing/2026-10-06-restart-readiness-scan-budget.md) records the focused test correction.

## 5. Failure Boundary

Cancellation and timeout terminate only the owned command tree. Successful root-process completion also requires the Job to become empty. Cleanup failure remains an error; it never establishes successful installation or permits stopping unrelated instances.

[Command tree cleanup](../../.agents/notes/implemented/bug-fix/2026-10-02-update-command-tree-cleanup.md) records implementation and focused verification.

## 6. Nightly Version Direction

`release_is_downgrade` compares semantic version components before resolving same-alpha Nightly builds. Valid, timezone-aware publication dates in the channel index determine direction without another request. Missing history or invalid dates trigger one upstream GitHub commit comparison from the installed SHA to the target SHA, using the selected HTTP proxy and existing finite request timeout. `ahead` and `identical` permit updating; `behind`, `diverged`, malformed responses and request failures retain manual confirmation. Identical version names need no comparison. Offline package inspection remains network-free and retains confirmation when SHA ordering is unknown.

[Nightly direction evidence](../../.agents/notes/implemented/bug-fix/2026-10-07-nightly-direction-evidence.md) records the contract and focused verification.

## 7. MAA Resource Updates

`/maa-resource-update/info` reports support for installed MAA on Windows, macOS and Linux. `MaaBasic` displays its independent resource controls from that response. `/maa-resource-update/check` uses the selected GitHub or Mirror酱 source; `/maa-resource-update/start` follows the [MAA update admission policy](maa-integration.md#29-independent-update-policies), including unknown local versions. Both resource and core updates share the maintenance lock and reject active MAA use.

`install_maa_resource_update` stages an incremental resource merge, preserves core and Python files, and replaces only `resource`. The previous resource tree remains in the installation's `.old/resource`; failed replacement or version verification restores the original tree and previous backup. A merged resource tree must satisfy the installed package's file list before replacement. Core updates follow the [MAA package validation and backup boundary](#17-maa-package-validation-and-backups).

The update worker follows the [MAA runtime activation boundary](maa-runtime.md#3-explicit-update-completion) after installation.

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

For content hashing, `package_file_paths` collects the shared source when the compatibility export is absent. `content_hash` uses the historical archive name for that catalog's ordering, path digest and text normalization. Clean checkouts and generated resource packages with identical data therefore share the same resource version on LF and CRLF checkouts, without writing a compatibility file during validation.

[Shared building-skill data](../../.agents/notes/implemented/simplification/2026-10-09-shared-building-skill-data.md) records the boundary and verification.

OTA starting-file reads follow the [bundled reconstruction contract](resource-update.md#1-resource-ota).

## 13. Temporary Update Progress Service

`ProgressServers` reuses registered instance ports and credentials while the application is replaced. Its POST handler reads supported request bodies within the existing 1024-byte limit and five-second socket timeout before returning a rejection, preventing unread POST data from aborting the response on Windows. Invalid credentials, update headers or origins retain HTTP 403 precedence; an authenticated unknown path returns HTTP 404. Only an authorized cancellation request with a valid body reaches `cancel_update`; body-reading failures retain the applicable rejection or return HTTP 400. Closing the service releases its registered ports for the restarted application.

<a id="14-windows-desktop-elevation"></a>
## 14. Windows Desktop Launch Permissions

The Windows package embeds `asInvoker` with `uiAccess=false` in both `mower.exe` and `多开管理器.exe`. A standard Windows account can launch either executable without administrator credentials or a UAC elevation request. The manager starts instances through ordinary `Popen`, so they inherit its token. Desktop children, maintenance workers and restarts retain their parent's permissions. A user can explicitly choose Run as administrator when needed and authorized; Mower does not automatically request elevation on failure.

Desktop startup does not generate launch shortcuts or batch scripts. Users who need elevated permissions can right-click the installed EXE and choose Run as administrator; only that explicit action requests elevation. Existing user-side shortcuts are left untouched and are no longer refreshed after moving the installation.

The existing single-manager reuse rule still applies. To replace an already running standard-permission manager with an elevated one, exit that manager before launching the manager EXE with Run as administrator.

The release workflow verifies both built executable manifests before creating the archive. Source deployments inherit the Python process permissions. Windows retains the portable installation and data layout: standard accounts require write access to the installation for software updates and to the configured data and MAA directories for their writes. `MOWER_DATA_DIR` redirects application data but does not make a protected installation writable. Permission failures remain subject to Windows file ACLs and emulator access restrictions.

An already elevated old package and its updater remain elevated until they exit. Users without administrator credentials can install the new full package in a writable directory and launch it directly; changing Python sources alone does not replace the manifest in an old executable.

[Windows desktop launcher permissions](../../.agents/notes/implemented/feature/2026-10-16-windows-desktop-launcher-permissions.md) records the startup decision and verification limits.

## 15. Update Cache Storage

`update_runtime.state_dir` resolves `@app/tmp/updates/<installation-hash>/` with `space=""`. All instances using the same installation and data root share update coordination; separate installations retain separate directories. Uploaded previews, downloaded packages, detached runners, source preparation and update logs inherit this directory through the existing job workspace. DMG package inspection creates and removes its temporary mount workspace directly under `@app/tmp/updates/`.

Persistent update preferences use the shared data root's
`config/software-update/<namespace>.json` with `space=""`. The namespace is a
SHA-256-derived key of the resolved update state directory, retaining installation
and data-root separation while all its instances share the settings. This file
stores channel, background mode, automatic checks and updates, source branch,
source remote and remote history. On first read, an absent destination receives
the former update-cache `settings.json` under a migration lock. An existing
destination wins; migration errors propagate without overwriting the source.
Update coordination, downloads and temporary workspaces remain in the cache.

`tmp/` sits beside `config/` and `logs/` in the Mower data root. `MOWER_DATA_DIR` redirects this root; macOS frozen applications use their writable application data root rather than the signed `.app` bundle. Resource packages and MAA storage retain their existing contracts. Update rollback backups retain their existing locations and verification lifecycle.

[Local software update cache](../../.agents/notes/implemented/simplification/2026-10-12-local-software-update-cache.md) records the simplification and focused verification.

## 16. Backup Cleanup Contention

Startup instances and verified update workers share the existing nonblocking `backup-cleanup/submission.lock`. `submission_lock` raises `LockBusyError`, a `ValueError` subtype, only for native lock-contention errors. Other acquisition failures retain their original `OSError`; update submission preserves its existing busy message and exception compatibility.

`retry_backup_cleanup` treats a busy lock during acquisition as a completed skipped attempt, without warnings, tracebacks, waiting or record mutation. The lock owner continues cleanup; pending `cleanup.json` records remain available for subsequent startup attempts. Other acquisition failures and cleanup failures retain application logger or detached updater diagnostics. Successful acquisition retains verified-restart, permitted-path and recorded-file-identity checks, with lock release on completion or error. The lock file remains in place.

[Backup cleanup contention](../../.agents/notes/implemented/bug-fix/2026-10-12-backup-cleanup-contention.md) records the decision and focused verification.

## 17. MAA Package Validation and Backups

Windows MAA installations use the client's `filelist.txt` resource-presence check when that file exists. Each listed non-DLL, non-EXE and non-Python file must exist; old packages without a list retain compatibility. Unreadable, malformed or oversized lists fail validation. A damaged Windows installation or `pending-update-failure.txt` requests a full package without submitting an installed version, permitting repair at the same version through GitHub or Mirror酱. An OTA response cannot repair that installation. Full extraction, OTA merging and resource merging validate their resulting files before switching the installation. OTA processing retains both `removelist.txt` and `changes.json.deleted` semantics.

Desktop core replacement stages the complete installation and retains its predecessor in `<MAA>/.old`. Desktop resource replacement uses `<MAA>/.old/resource`. OTA preparation excludes the top-level `.old` tree. Failed switching restores the prior installation and prior backup; successful tasks retire backups only through the [runtime ownership and occupancy checks](maa-runtime.md#2-reload-and-failure-boundary). Legacy desktop sibling `maa.old` and `resource.old` directories are preserved and receive no new automatic cleanup. Android retains the host's existing component backup and `resource.old` layout, cleanup hook and service restart.

Mower keeps its staged directory replacement rather than launching `MAA.Updater.exe`. It shares the Windows client's installation mutex protocol, resource validation and repair selection, and `.old` backup location. The [parity tests](../../arknights_mower/tests/maa_update_parity_tests.py) cover damaged installations, same-version repairs, backup restoration and occupied-client admission.

## Shared OCR Update Lifecycle

Update shutdown waits for the coordinator and model worker registrations described by [Independent Shared OCR](recognition.md#independent-shared-ocr), as it does for the other registered processes, and verifies release of the model lifetime lock before replacing files. The worker registers before it acquires that lock or constructs the model and keeps the registration until process exit, so update shutdown still sees a surviving model if its coordinator exits before the shutdown snapshot. A model blocked in a native call keeps the update pending within its existing shutdown budget; an exhausted budget rejects installation.

Restart and rollback relaunch only the saved applications; the OCR registrations described by [Independent Shared OCR](recognition.md#independent-shared-ocr) are not relaunched. Coordinator and worker registrations each participate in the existing submission lock and are refused while an update or process-control job is active unless their inherited restart-job identity matches that owner. This prevents a late worker from constructing a model after update admission. A coordinator cold start that cannot obtain admission, including while an update is still preparing, retries within the request's remaining time budget instead of failing immediately; the retry cannot register after the shutdown snapshot, because registration still requires the submission lock and an inactive job. If the budget expires first, that OCR request fails and a sent request is not replayed.

OCR registrations disable optional backup cleanup so these processes do not load application image or logging dependencies for maintenance.
