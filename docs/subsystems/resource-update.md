# Resource Update Contract

## 1. Resource OTA

MowerResource publishes `resource-update.json` with a complete-package size and SHA-256, and direct OTA assets from up to four retained starting versions. OTA assets contain `resource-ota.json`, all target file sizes and SHA-256 values, and only changed files under `payload/`. Files absent from the target list are excluded from the reconstructed generation. OTA assets at least 85 percent of the complete ZIP size are omitted. The complete `resource.zip` remains available to older clients.

The client selects an OTA only for its exact current resource version and only when smaller than the complete package. All download URLs derive from fixed MowerResource release paths. It verifies asset size and SHA-256, reconstructs in staging, verifies every target file and target version, then retains existing compatibility, install-lock, immutable-publication and task-boundary loading rules. Metadata absence falls back to the legacy full-package URL. An online OTA failure falls back to the same target release’s full asset once. A manually uploaded OTA uses no network and rejects an unmatched base. Both external and bundled resources can provide unchanged base files.

[Verified resource OTA](../../.agents/notes/implemented/architecture/2026-10-09-resource-ota.md) records scope and verification.

## 2. Resource Publication

OTA reconstruction writes only staging files. The resource installer validates the target package against the running Mower version, rejects older resources, publishes an immutable version directory under the process and cross-process install locks, and updates the package index atomically. Cache loading retains task-boundary ownership and restores the previous index and selection on failure. Old generation directories remain available to instances that still use them.

## 3. Subsystem Invariants

- **[INV-RES-02] Resource OTA Reconstruction**: An OTA package reconstructs a complete compatible resource generation from an exact starting version, verifies target file digests and publishes through the existing immutable installer.

## 4. Resource Generation

`Arknights数据处理器.获得干员基建描述` retains every upstream building skill. Known room codes use their display labels, including `RECYCLE` as 回收站; unknown room codes remain unchanged in `roomType` and do not abort generation. Skill descriptions, icons and phase conditions retain their upstream values. The frontend derives facility filters from the generated data.

**[INV-RES-03] Building Skill Facility Preservation** governs this behavior. [Building skill facility preservation](../../.agents/notes/implemented/bug-fix/2026-10-09-resource-facility-preservation.md) records the repair and verification.
