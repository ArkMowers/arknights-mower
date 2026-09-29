---
title: Configuration backup includes persistent tmp data
status: implemented
category: feature
date: 2026-09-30
---

# Configuration backup includes persistent tmp data

## Contract

[INV-CFG-01] binds configuration and included persistent tmp data to a single
validated import and recovery snapshot. The
[subsystem contract](../../../../docs/subsystems/config-backup.md) owns the
interface and failure guarantees.

## Implementation

Export includes SQLite tables, inventory, depot histories, reports, Skland records
and workshop presets. Import restores only included tmp files and preserves
missing local data for compatibility with existing config-only backups. It clears
saved scheduling state and retains local access settings. SQLite snapshots and
restores use bounded backup operations, including committed WAL contents.

Pre-flight simplification finds one exporter and two archive readers, including
plan-only import. The existing reader remains authoritative for path validation;
the plan-only reader ignores validated tmp data. The file rollback loop covers
both directories instead of introducing another persistence subsystem.

No scheduling mechanics, configuration schema or glossary definition changes.
The glossary remains unchanged and requires separate approval for any edit.

## Verification

Focused offline tests cover table round trips, WAL snapshots, legacy archives,
preserved access settings, malformed databases, excluded tmp files and rollback.
Governance and formatting checks cover this decision triplet and its direct links.
