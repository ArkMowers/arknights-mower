# Resource Update Contract

## 1. Resource OTA

MowerResource publishes `resource-update.json` with a complete-package size and SHA-256, and direct OTA assets from up to four retained starting versions. OTA assets contain `resource-ota.json`, all target file sizes and SHA-256 values, and only changed files under `payload/`. Files absent from the target list are excluded from the reconstructed generation. OTA assets at least 85 percent of the complete ZIP size are omitted. The complete `resource.zip` remains available to older clients.

The client selects an OTA only for its exact current resource version and only when smaller than the complete package. All download URLs derive from fixed MowerResource release paths. It verifies asset size and SHA-256, reconstructs registered files in staging, verifies every retained target file and target version, then retains existing compatibility, install-lock, immutable-publication and task-boundary loading rules. Metadata absence falls back to the legacy full-package URL. An online OTA failure falls back to the same target release’s full asset once. A manually uploaded OTA uses no network and rejects an unmatched base. Both external and bundled resources can provide unchanged base files.

Full-package and OTA installation discard files not registered by the running client's `is_package_file`. Unknown files are never written; unchanged unknown OTA files require no local base. All archive entries still undergo path, type, duplicate and size checks, and OTA inventory and payload membership remain validated before filtering. Required registered files, retained-file digests and software compatibility remain mandatory. The producer still rejects unregistered archive files when building an OTA. This behavior requires a client software update; a resource package cannot change an older client's installer.

[Verified resource OTA](../../.agents/notes/implemented/architecture/2026-10-09-resource-ota.md) records scope and verification.

Bundled reconstruction reads the historical skill entry from `arknights_mower/data/building_skill.json`. The WebUI build retains the unchanged bytes of `ui/src/pages/basement_skill/buffer.json` under `ui/dist/pages/basement_skill/buffer.json`, alongside the copied public images. A source checkout can use its UI source files; desktop and Android packages require no `ui/src` directory. Selected external generations use their archive paths exclusively; a missing or corrupt base file never borrows bundled data.

Android application packaging requires the built buffer artifact and rejects missing, empty or whitespace-only input before creating an update archive. Release validation also rejects an empty buffer entry in an existing archive.

Bundled files declared in `RES_PACKAGE_DATA` or `RES_PACKAGE_OPTIONAL_DATA` can contain CRLF from a Windows checkout while sharing the published LF resource version. Reconstruction converts CRLF to LF only when such a base file is larger than the declared target, within the existing input limit and at most twice the target size. The staged result still requires the exact target size and SHA-256. Base files remain unchanged; binary resources, OTA payloads and external generations retain exact byte validation.

## 2. Resource Publication

OTA reconstruction writes only staging files. The resource installer validates the target package against the running Mower version, rejects older resources, publishes an immutable version directory under the process and cross-process install locks, and updates the package index atomically. Cache loading retains task-boundary ownership and restores the previous index and selection on failure. Old generation directories remain available to instances that still use them.

Generation directory names hash the downloaded archive and the sorted retained file paths. Reinstalling the same archive after a client update that registers additional files publishes a separate generation, preserving the filtered generation used by older instances. Among eligible external generations with the same resource version, the last installed generation takes precedence, including after restart.

### Installed Resource Metadata

The authenticated `/resource-version` response includes `current_metadata` from the installed `data/version.json`: `activity` and `gacha` retain their names, opening timestamps (`time`) and ending timestamps (`endTime`), while `last_updated` identifies the upstream source snapshot. Activity and gacha timestamps use Unix seconds; neither the resource build date nor `last_updated` defines an expiry date. Missing activity or gacha metadata returns an empty object, and a missing source snapshot returns an empty string. Local-only reads and every remote-check result, including failures, preserve this installed metadata; remote or cached metadata never substitutes for it.

## 3. Subsystem Invariants

- <a id="operator-avatar-completeness"></a>**Operator Avatar Completeness**: Generation and publication reject missing or unreadable obtainable-operator avatars; section 4 owns conversion and source rules.

- <a id="resource-ota-reconstruction"></a>**Resource OTA Reconstruction**: An OTA package reconstructs a complete compatible generation of the running client's registered resources from an exact starting version, verifies retained target file digests and publishes through the existing immutable installer.

## 4. Resource Generation

### Shared Operator Catalog

<a id="shared-operator-catalog"></a>
`auto_get_res_new.py` generates `arknights_mower/data/riic/operators.json` from the character and building tables. The catalog contains operator IDs, basic profiles, upstream order and complete building-skill slots. It omits the derived maximum-stage `skills` array. The generator retains existing calculator order for known IDs, appends new IDs, and exports the historical `agent.json` and `agent_profession.json` views for existing resource clients. Promotion, mastery and training compilation reuse the same profile conversion.

The bundled catalog records its game-table version in `sourceVersion`; `source`, when present, identifies the upstream repository, immutable revision and input-file SHA-256 digests. Updating the catalog includes reviewing changed skills of existing operators as well as newly added identities.

The backend derives bundled operator names and professions from the catalog. Selected external resource generations use their own historical exports; no individual file is borrowed from the bundled data. Resource changes refresh the existing imported containers in place at the task boundary. A malformed present bundled catalog fails loading rather than silently substituting its exports.

The shared catalog is a software asset outside `RES_PACKAGE_DATA` and `RES_PACKAGE_OPTIONAL_DATA`. Clients predating unknown-file filtering reject it in resource archives; current clients discard it as unregistered. Resource publication retains the historical exports and content-hash identity. The calculator and native mood engine use their software-bundled catalog together with their matching rules. Resource OTA does not replace that calculation input. The native runtime verifies the code and catalog digests, and its saved-state identity covers both. Desktop and Android packages include the catalog independently of frontend sources; Android packaging rejects missing or blank catalog input.

The frontend calculator derives maximum-stage skills as separate objects from the final stage of each slot. Personal ownership, progression and inventory remain in the existing account snapshot and inventory services. The display catalog and its historical `skill.json` archive identity keep their existing owner below. The [shared catalog decision](../../.agents/notes/implemented/simplification/2026-10-30-shared-operator-catalog.md) records the compatibility and packaging choices.

### Building Skill Display Data

`Arknights数据处理器.获得干员基建描述` retains every upstream building skill. Known room codes use their display labels, including `RECYCLE` as 回收站; unknown room codes remain unchanged in `roomType` and do not abort generation. Skill descriptions, icons and phase conditions retain their upstream values. The frontend derives facility filters from the generated data.

<a id="building-skill-facility-preservation"></a>**Building Skill Facility Preservation** governs this behavior. [Building skill facility preservation](../../.agents/notes/implemented/bug-fix/2026-10-09-resource-facility-preservation.md) records the repair and verification.


`Arknights数据处理器.添加干员` converts every obtainable operator avatar into a decoded 96×96 WEBP before writing the operator directory. Missing or unreadable source images fail generation with the operator name and code. MowerResource fills missing images from a fixed `ArknightsAssets/ArknightsAssets2` `cn` commit and validates all directory avatars before publication.

**Operator Avatar Completeness** governs this behavior. [Complete operator avatars](../../.agents/notes/implemented/bug-fix/2026-10-09-resource-avatar-completeness.md) records the source repair and verification.

Every bundled catalog entry has a decoded 96×96 WEBP avatar, and every referenced building-skill icon has a decoded WEBP resource. Room, selection and training name models cover all bundled operator names. The [bundled operator resource tests](../../arknights_mower/tests/bundled_operator_resources_tests.py) check these files independently of the resource-version digest; a matching digest alone does not establish coverage.

### Activity Shop Resources

<a id="activity-shop-resources"></a>
`arknights_mower/data/event_shop.json` is optional data in the selected resource generation. Its absence in an older package yields no shop adaptation and never borrows the bundled file. Collection and resource hashing include it when present; bundled OTA reconstruction normalizes its text line endings under the existing data-file rule. It remains outside mandatory `RES_PACKAGE_DATA` so older complete packages still install.

The file contains at most 128 currently open SS objects. `activity_id` identifies a stage-bearing SS or SS rerun (`act` plus digits and `side` or `sre`), and `activity` matches the activity navigation name. Integer `start_ts` and `end_ts` define the SS battle window; `reward_end_ts` records the later shop reward deadline without extending automatic redemption admission. `entry_names` contains at most 16 nonempty chapter names, each at most 256 characters. `chapters` maps `normal`, `ex` and `s` to their chapter names. `token_ids` contains the activity currency item identifiers. Start precedes end, reward end does not precede battle end, and overlapping entries for the same activity are rejected.

`auto_get_res_new.py` passes `activity_table.json`, `zone_table.json` and `stage_table.json` to [`event_shop_data.py`](../../arknights_mower/utils/event_shop_data.py). Generation uses activity identity, stage and shop availability, `zoneToActivity`, chapter names and `ACTIVITY_ITEM` drops. Standard three-zone SS metadata retains later `zone2` and `zone3` titles even when their EX or S stage rows are not yet published. Missing active-SS inputs fail generation; verified absence of an open SS generates `[]`. Runtime loads this file from the selected immutable resource generation and does not borrow another generation's metadata.

Entrance coordinates and per-activity shop confirmation text are no longer generated or used. Currency images from the MAA installation locate both the activity and shop entrances; common shop-page observations confirm entry. Older shop entries without `activity_id` are accepted only when that selected generation's own stage data establishes a unique SS identity and battle window for the same activity. Unclassifiable legacy entries are ignored. There is no user activity selector or manual coordinate/title override. [Activity Shop Redemption](maa-integration.md#12-activity-shop-redemption) owns admission, navigation and plan-switch behavior; the [current SS update guide](../../.agents/skills/mower-version-update/references/event-shop.md) owns source collection and focused verification.
