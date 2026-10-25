# Configuration Backup Contract

## 1. Scope

The configuration ZIP contains the current instance's `config/` originals except
`state.json` and the local `gui.yml.lock` and `recycling_report/submission.lock`
files, together with the persistent data files listed in `TMP_DATA_FILES`
in [config_backup.py](../../arknights_mower/utils/config_backup.py).
SQLite snapshots contain committed database tables, including data in WAL files.
Resource overlays, downloaded updates, logs and unrelated tmp files stay outside
the archive. No configuration model or domain term changes.

Rescue plans follow [instance rescue-plan storage](base-scheduler.md#rescue-plan-persistence).
Import validates `rescue_plan.json` before writing and restores it with the other
configuration files. Legacy archives migrate `conf.yml`'s `automatic_rescue_plan`
field into that file; if both are present, the independent file takes precedence.
Archives containing neither restore an empty rescue plan. Write failures roll back
both saved files and the in-memory configuration, including the rescue plan.

## 2. Import Boundary

Import validates bounded archive paths and the SQLite database before creating
the recovery ZIP or replacing files. SQLite restores use the backup API rather
than replacing an open database file. Configuration and included tmp data share
one recovery snapshot. Missing tmp files retain local data, so config-only legacy
ZIP files remain valid. Import clears `saved_state` in the restored database and
retains the current process's access settings and protected configuration files.
Database backup operations have a ten-second deadline. Archive byte and entry
limits cover configuration and tmp data together.

Full backup import retains the active saved-profile identifier and name, replaces
its snapshot with the imported content, and advances the configuration generation
within the same file and database transaction. Metadata failure restores the
previous files, database, snapshot and generation. Requests from pages opened
before import are rejected according to the
[saved-configuration request boundary](config-profiles.md#api-and-verification).

The 完整备份与恢复 maintenance card names this restore explicitly; the separate
[档案与运行 import](config-profiles.md#frontend-boundary) creates a new configuration
and lets the user select current content to retain.

Before submission, the frontend pauses and drains configuration, normal-plan and
initialized rescue-plan saves. Success or an uncertain response keeps those
stores paused until the page reloads; an explicit validation or busy rejection
can resume saving when the configuration has not changed.

Legacy ZIP entries `tmp/growth_plan.json` and `tmp/workshop_preset.json`
restore into the current instance's `config/` directory. Canonical config entries
win when both forms exist. Growth goals must decode as a JSON list before any
writes; malformed legacy workshop presets retain their existing recoverable
warning behavior. A ZIP missing both forms preserves the corresponding local
config file. Exports omit obsolete tmp copies once canonical files exist.

Local `gui.yml` is exported but protected during import, including its window
settings, mood curve preferences and log layout. Shared installation settings
outside the current instance directory remain outside the archive.
Import preserves both local lock files, even when an older archive includes
them, so an active OS lock continues to protect the same file.

## 3. Subsystem Invariants

- <a id="configuration-data-cohesion"></a>**Configuration Data Cohesion**: Configuration imports validate all archive members before writing, restore included persistent tmp data with configuration, preserve local access settings, clear saved scheduling state, and roll back file changes if any write or database restore fails.

Malformed data produces a validation error without a recovery ZIP or file writes.
Local path failures retain the existing files. Write failures retain the recovery
ZIP and roll back modified files without replacing runtime configuration.

The [decision record](../../.agents/notes/implemented/feature/2026-09-30-config-backup-tmp-data.md)
states implementation scope and regression coverage. The
[user guide](../../doc/config-backup.md) describes export, import and recovery.
