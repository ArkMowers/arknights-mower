# Configuration Backup Contract

## 1. Scope

The configuration ZIP contains the current instance's `config/` originals except
`state.json`, together with the persistent data files listed in `TMP_DATA_FILES`
in [config_backup.py](../../arknights_mower/utils/config_backup.py).
SQLite snapshots contain committed database tables, including data in WAL files.
Resource overlays, downloaded updates, logs and unrelated tmp files stay outside
the archive. No configuration model or domain term changes.

## 2. Import Boundary

Import validates bounded archive paths and the SQLite database before creating
the recovery ZIP or replacing files. SQLite restores use the backup API rather
than replacing an open database file. Configuration and included tmp data share
one recovery snapshot. Missing tmp files retain local data, so config-only legacy
ZIP files remain valid. Import clears `saved_state` in the restored database and
retains the current process's access settings and protected configuration files.
Database backup operations have a ten-second deadline. Archive byte and entry
limits cover configuration and tmp data together.

## 3. Subsystem Invariants

- **[INV-CFG-01] Configuration Data Cohesion**: Configuration imports validate all archive members before writing, restore included persistent tmp data with configuration, preserve local access settings, clear saved scheduling state, and roll back file changes if any write or database restore fails.

Malformed data produces a validation error without a recovery ZIP or file writes.
Local path failures retain the existing files. Write failures retain the recovery
ZIP and roll back modified files without replacing runtime configuration.

The [decision record](../../.agents/notes/implemented/feature/2026-09-30-config-backup-tmp-data.md)
states implementation scope and regression coverage. The
[user guide](../../doc/config-backup.md) describes export, import and recovery.
