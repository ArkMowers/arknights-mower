# Resource Update Contract

## 1. Resource OTA

MowerResource publishes `resource-update.json` with a complete-package size and SHA-256, and direct OTA assets from up to four retained starting versions. OTA assets contain `resource-ota.json`, all target file sizes and SHA-256 values, and only changed files under `payload/`. Files absent from the target list are excluded from the reconstructed generation. OTA assets at least 85 percent of the complete ZIP size are omitted. The complete `resource.zip` remains available to older clients.

The client selects an OTA only for its exact current resource version and only when smaller than the complete package. All download URLs derive from fixed MowerResource release paths. It verifies asset size and SHA-256, reconstructs in staging, verifies every target file and target version, then retains existing compatibility, install-lock, immutable-publication and task-boundary loading rules. Metadata absence falls back to the legacy full-package URL. An online OTA failure falls back to the same target release’s full asset once. A manually uploaded OTA uses no network and rejects an unmatched base. Both external and bundled resources can provide unchanged base files.

[Verified resource OTA](../../.agents/notes/implemented/architecture/2026-10-09-resource-ota.md) records scope and verification.

Bundled reconstruction reads the historical skill entry from `arknights_mower/data/building_skill.json`. The WebUI build retains the unchanged bytes of `ui/src/pages/basement_skill/buffer.json` under `ui/dist/pages/basement_skill/buffer.json`, alongside the copied public images. A source checkout can use its UI source files; desktop and Android packages require no `ui/src` directory. Selected external generations use their archive paths exclusively; a missing or corrupt base file never borrows bundled data.

Bundled files declared in `RES_PACKAGE_DATA` can contain CRLF from a Windows checkout while sharing the published LF resource version. Reconstruction converts CRLF to LF only when such a base file is larger than the declared target, within the existing input limit and at most twice the target size. The staged result still requires the exact target size and SHA-256. Base files remain unchanged; binary resources, OTA payloads and external generations retain exact byte validation.

## 2. Resource Publication

OTA reconstruction writes only staging files. The resource installer validates the target package against the running Mower version, rejects older resources, publishes an immutable version directory under the process and cross-process install locks, and updates the package index atomically. Cache loading retains task-boundary ownership and restores the previous index and selection on failure. Old generation directories remain available to instances that still use them.

## 3. Subsystem Invariants

- **[INV-RES-04] Operator Avatar Completeness**: Generation and publication reject missing or unreadable obtainable-operator avatars; section 4 owns conversion and source rules.

- **[INV-RES-02] Resource OTA Reconstruction**: An OTA package reconstructs a complete compatible resource generation from an exact starting version, verifies target file digests and publishes through the existing immutable installer.

## 4. Resource Generation

`Arknights数据处理器.获得干员基建描述` retains every upstream building skill. Known room codes use their display labels, including `RECYCLE` as 回收站; unknown room codes remain unchanged in `roomType` and do not abort generation. Skill descriptions, icons and phase conditions retain their upstream values. The frontend derives facility filters from the generated data.

**[INV-RES-03] Building Skill Facility Preservation** governs this behavior. [Building skill facility preservation](../../.agents/notes/implemented/bug-fix/2026-10-09-resource-facility-preservation.md) records the repair and verification.


`Arknights数据处理器.添加干员` converts every obtainable operator avatar into a decoded 96×96 WEBP before writing the operator directory. Missing or unreadable source images fail generation with the operator name and code. MowerResource fills missing images from a fixed `ArknightsAssets/ArknightsAssets2` `cn` commit and validates all directory avatars before publication.

**[INV-RES-04] Operator Avatar Completeness** governs this behavior. [Complete operator avatars](../../.agents/notes/implemented/bug-fix/2026-10-09-resource-avatar-completeness.md) records the source repair and verification.
