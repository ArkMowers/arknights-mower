# Configuration Backup Contract

## 1. Scope

The configuration ZIP contains the current instance's `config/` originals except
`state.json` and the local `gui.yml.lock` and `recycling_report/submission.lock`
files, together with the persistent data files listed in `TMP_DATA_FILES`
in [config_backup.py](../../arknights_mower/utils/config_backup.py).
SQLite snapshots contain committed database tables, including data in WAL files.
Resource overlays, downloaded updates, logs and unrelated tmp files stay outside
the archive. [Configuration credential storage](#configuration-credential-storage)
also applies to profile exports and recovery ZIPs.

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

Local `gui.yml` and the [running log background](web-access.md#running-log-background)
at `config/log-background.webp` are exported but protected during import, including
the GUI file's window settings, mood curve preferences and log layout. Shared
installation settings outside the current instance directory remain outside the archive.
Import preserves both local lock files, even when an older archive includes
them, so an active OS lock continues to protect the same file.

## Configuration Credential Storage

The current instance saves the Web UI token, mail account and recipients,
Skland accounts, AI keys and custom endpoint, and MAA download and reporting
credentials in encrypted `mower.secrets.json` at the instance data root. The
shared GitHub token and legacy DeepSeek fallback key use `network.secrets.json`
and `ai.secrets.json` at the installation data root. Yituliu OAuth authorization
uses `yituliu.secrets.json` at the instance data root. Saved profiles use a
matching `<id>.secrets.json` beside their ZIP. These JSON files contain a
versioned encryption envelope, not readable credential values. A launch
environment variable can supply a default where no value has been saved. An
explicitly empty value takes precedence over that default. An explicit
`MOWER_DATA_DIR` limits migration of `token.txt` to that directory.

This feature first introduces encrypted credential storage for existing
plaintext configurations. It supports one envelope format, version 1. The native
HPKE implementation in `cryptography==50.0.2` encrypts the credential JSON with
X-Wing (`MLKEM768_X25519`), `HKDF_SHA256` and `AES_256_GCM`. A fixed recipient
private key contains a 64-byte ML-KEM-768 seed and a 32-byte X25519 private key.
Normal saves reuse that private key; HPKE produces a fresh encapsulation and
ciphertext for each encryption.

The credential envelope contains only `version`, `suite`, `provider`, `key_id`
and `ciphertext`. Its suite is `HPKE-X-Wing-HKDF-SHA256-AES-256-GCM`, `key_id`
is the lowercase hexadecimal SHA-256 digest of the concatenated 1184-byte
ML-KEM-768 and 32-byte X25519 public keys, and `ciphertext` is the
base64-encoded HPKE output including its encapsulation. The canonical header
enters HPKE `info`, binding the version, suite, provider and key identifier to
the ciphertext. The private key is stored separately and does not appear in
the credential envelope.

Windows defaults to protecting the fixed private key with the current user's
DPAPI and saving the protected bytes in
`%LOCALAPPDATA%/arknights-mower/credentials/private.dpapi`, using
`~/AppData/Local` when `LOCALAPPDATA` is unset. An explicitly set
`XDG_DATA_HOME` takes precedence for the data root. macOS stores the base64-encoded
private key directly in Keychain, and Linux uses Secret Service through
`secret-tool` when available in a D-Bus session. Without that tool or session,
headless Linux and Android save the base64-encoded private key in
`$XDG_DATA_HOME/arknights-mower/credentials/private.key`, or
`~/.local/share/arknights-mower/credentials/private.key` when `XDG_DATA_HOME` is
unset. The private directory has mode `0700` and its key file has mode `0600`
on POSIX systems. This file provider relies on filesystem permissions.
On any platform, `MOWER_CREDENTIAL_KEY_FILE` can select an existing file
containing the base64-encoded 96-byte private key; reading also accepts URL-safe
base64. A missing explicitly selected file is not created automatically.

The default private key is shared by Mower instances running as the same system
user with the same key-storage settings: they use the same Keychain entry,
Secret Service attributes or private-key directory. It is not an independent
key per instance or manager. Selecting distinct private keys through
`MOWER_CREDENTIAL_KEY_FILE` can isolate deployments.

System-service initialization and explicit recovery serialize through the fixed
user directory `~/.local/share/arknights-mower/credential-service-lock`, independent
of `XDG_DATA_HOME`, because the Keychain and Secret Service entries are shared by
that user. Ordinary reads do not create this coordination directory.

Without an explicit key-file setting, reads use the recorded provider and
require a matching key identifier. With `MOWER_CREDENTIAL_KEY_FILE` explicitly
set, reads use that private key for any recorded provider, require the same
key identifier and authenticate the original header without rewriting the
ciphertext. This permits manual recovery across platforms with the original
raw private key. Copying `private.dpapi` alone does not remove its Windows
account protection. Normal migration does not require users to export a private
key: they re-enter credentials or use the optional password-protected backup below.

Reading never silently switches providers or creates a replacement for a
missing key. Provider-specific initialization records prevent creating a new private key after
the original is lost, including when saving another credential file. An
unavailable provider, missing private key or damaged ciphertext fails the
operation without treating credentials as empty or changing access control.
Credential files, private keys and initialization records are persistent user
data, outside cache cleanup.

Writes are atomic and verified by reading back the saved values. A failed write
or readback restores the prior file bytes. Saving unrelated settings can leave
the credential file unchanged. Unsupported formats or missing hybrid runtime
support produce an error; there is no fallback encryption format. X-Wing
combines X25519 and ML-KEM-768 and is distinct from the similarly named TLS
key-exchange group. Local credential encryption does not configure HTTPS or
prevent access by a process that can obtain the private key or use its system
credential service.
The [hybrid encryption decision](../../.agents/notes/implemented/architecture/2026-11-16-hybrid-credential-encryption.md)
records the rationale and accepted storage costs. Implementation and
focused verification live in
[`credential_store.py`](../../arknights_mower/utils/credential_store.py) and
[`credential_store_hybrid_tests.py`](../../arknights_mower/tests/credential_store_hybrid_tests.py).
Dependency installation and backend capability checks follow the
[credential encryption runtime guide](../cookbook/packaging.md#credential-encryption-runtime).

The configuration loader migrates credentials directly from existing
`conf.yml`, `network.json`, `yituliu_sync.json`, saved-profile ZIPs and `token.txt`.
It removes a plaintext source only after writing and reading back the encrypted
destination. New saves do not create plaintext credential files. If both `config/conf.yml`
and the former root-level `conf.yml` exist, the former root-level file's
credentials move to `legacy-mower.secrets.json` without entering the active
configuration. Authenticated settings requests continue to read, edit and clear
the same values. Settings responses that carry credentials use
`Cache-Control: no-store`. AI clients receive their configured key for
authentication; storing that key does not add it to model messages.

Exported ZIPs and recovery ZIPs omit credential values, encryption keys and
credential files, including sensitive environment files. Imports protect the actual
configured deployment-key path even when it lies inside configuration or
persistent tmp data; file or directory collisions with that key path reject the
import. A restore from a redacted backup retains local credentials and the
synchronization record for the local
Yituliu token. Import from an older backup can still read credentials included
in that backup and move them into the destination encrypted files, subject to
the existing protection for local access and network settings. Earlier ZIP
exports can still contain credentials. A normal backup cannot recover a lost
encryption key or transfer credentials to another machine.

<a id="credential-recovery"></a>
## Recovery After Credential Key Loss

The desktop launcher catches credential-storage failures before normal server
startup and opens a separate recovery service without importing configuration.
The same service is available through `--credential-recovery` in the desktop
launcher and `python -m arknights_mower.utils.credential_recovery` in Python
deployments. Its [authorization boundary](web-access.md#credential-recovery-access)
does not depend on the unreadable saved Web UI token.
The desktop launcher opens a recovery window when a desktop backend is available;
the Python module defaults to printing the temporary URL. `--headless` explicitly
selects terminal output. This one-time URL contains the session credential;
HTTP access and protocol logs omit it.

Recovery lists unreadable credential files in the selected instance and shared
credential files, together with a confirmation snapshot. A reset requires an
explicit confirmation and an unchanged snapshot. It preserves readable
credentials, configuration files, scheduling plans, profile ZIPs and databases.
Unreadable ciphertext is retained in a separate `credential-recovery` directory;
ordinary configuration ZIPs exclude that directory, password-protected credential
backup files and quarantined private keys. Retained ciphertext still requires its
original private key to decrypt.

Only this explicit operation may create a replacement for a previously
initialized default key. A usable key is always retained. Missing system-service
entries may be recreated; locked services, invalid entries, unsafe filesystem
objects and permissions errors remain errors. An externally selected
`MOWER_CREDENTIAL_KEY_FILE` is never replaced. Damaged default file keys are
quarantined before replacement, with readback verification and compensation on
failure. Other instances that used a lost shared key still need their own
credential reset or restoration; recovery does not discard their configuration.

After successful recovery the user closes the recovery service and restarts
Mower, then re-enters credentials or imports a previously exported password
backup. Desktop startup with no saved access token remains loopback-only. Docker
retains its nonempty-token startup requirement. Recovery never silently resumes
automation or retries normal configuration import in a partially initialized
process.

<a id="password-credential-backup"></a>
## Password-Protected Credential Backup

The optional 凭据备份与迁移 controls in 完整备份与恢复 export a separate
`.mower-credentials` file. The file contains saved business credential fields
from the current instance and its current profile, plus shared GitHub and AI
fallback credentials. It excludes the Web UI access token, other saved profiles,
environment-only defaults, private keys, scheduling plans and ordinary settings.
For several profiles, users export each profile's credentials separately.

Version 1 uses scrypt with fixed `N=131072`, `r=8`, `p=1`, a random 16-byte salt,
and a 32-byte output for AES-256-GCM with a random 12-byte nonce. The authenticated
context binds the fixed format and algorithms. Files cannot supply arbitrary KDF
cost parameters. Passwords require at least 12 Unicode characters and at most
1024 UTF-8 bytes. Input files are limited to 4 MiB and plaintext to 2 MiB;
duplicate JSON keys, unknown fields, invalid types and unsupported versions are
rejected. The KDF is serialized with a bounded admission wait. No password is
persisted or intentionally logged. Password strength limits backup protection;
there is no password recovery service.

Authenticated POST routes export, preview and import through the existing Web UI
token guard and settings-confirmation header. Preview returns only fixed category
labels and field counts, including empty values. Import requires confirmation,
the current configuration generation and an idle instance under the existing
configuration-maintenance locks. Uploaded paths are never used as destination
paths. Only known credential fields are merged; absent fields and the destination
access token are retained, while explicitly empty fields clear their values.
Shared credential changes apply to other instances using those shared files.

Import encrypts values with the destination's automatically managed hybrid key;
it does not copy or replace a source private key. It validates writes and restores
the previous ciphertext bytes on failure. The in-memory configuration is replaced
only after successful model validation, preserving unset defaults and unrelated
nested configuration objects. Successful imports advance the configuration
generation in the same transaction, so other open pages cannot save stale
credential drafts. A changed Yituliu token invalidates its
old synchronization metadata in the same transaction; unrelated settings remain
unchanged. Incomplete rollback is reported as an uncertain failure, so the page
keeps automatic saving paused. Successful import reloads the page without
automatically starting tasks. An unreadable destination credential store must be
recovered through the separate recovery entry before importing.

Implementation and focused verification live in
[`credential_backup.py`](../../arknights_mower/utils/credential_backup.py),
[`credential_recovery.py`](../../arknights_mower/utils/credential_recovery.py),
[`credential_backup_route_tests.py`](../../arknights_mower/tests/credential_backup_route_tests.py)
and [`CredentialBackup.test.js`](../../ui/src/components/CredentialBackup.test.js).

<a id="database-maintenance"></a>
## Database Maintenance and Backup Limits

The running log's 数据库管理 dialog displays the database's allocated size
and free-page space. Deleting records leaves reusable pages in SQLite; 整理数据库
checks database integrity, runs `VACUUM` and truncates the WAL through a checkpoint.
It preserves retained records and table definitions and returns the allocated
size before and after compaction. A failed integrity check prevents `VACUUM`.
SQLite execution has a sixty-second progress deadline and a five-second lock wait;
an error or timeout releases the connection and maintenance locks for a later
explicit retry. External readers can prevent WAL truncation after compaction;
that incomplete reclamation returns an error rather than a success message.

The dialog saves an integer backup limit from 1 to 1024 MiB, defaulting to 16 MiB.
The limit covers compressed ZIP bytes, total expanded configuration and persistent
data, SQLite snapshots, profile combination and pre-import recovery snapshots.
The existing entry-count and ten-second SQLite backup bounds remain independent.
Increasing the limit permits larger in-memory snapshots. Reducing it does not
invalidate the saved-profile registry; operating on an oversized snapshot requires
raising the limit again. Plan-only upload requests retain their separate bound.

`backup_limit_mib` is stored in the current instance's protected `config/gui.yml`.
Restoring configuration and activating a saved profile preserve the local setting.
Frontend file selection leaves size validation to the backend's current limit.

`GET /db-admin/maintenance` returns allocated and free-page bytes, the selected
limit, its maximum and busy status. `POST /db-admin/compact` performs compaction;
`PUT /db-admin/backup-limit` accepts `{backup_limit_mib: integer}`. All three
interfaces require the existing instance token. Both writes require
`X-Mower-Settings: 1` and the existing permitted-origin boundary. They share the
configuration backup and profile-maintenance locks and refuse changes while
scheduling, device operations, update work, AI requests, recycling reports or
shutdown prevent configuration maintenance. Invalid limits return 400 without
writing preferences; busy operations return 409, and storage or SQLite failures
return 503. Successful writes return refreshed maintenance status.

Focused offline checks are in
[`db_maintenance_tests.py`](../../arknights_mower/tests/db_maintenance_tests.py),
alongside the existing backup and profile suites. They cover reclamation followed
by export, retained rows, WAL databases, authentication, busy refusal, configured
ZIP and expanded-data limits and local-setting preservation.

## 3. Subsystem Invariants

- <a id="configuration-data-cohesion"></a>**Configuration Data Cohesion**: Configuration imports validate all archive members before writing, restore included persistent tmp data with configuration, preserve local access settings, clear saved scheduling state, and roll back file changes if any write or database restore fails.

Malformed data produces a validation error without a recovery ZIP or file writes.
Local path failures retain the existing files. Write failures retain the recovery
ZIP and roll back modified files without replacing runtime configuration.

The [decision record](../../.agents/notes/implemented/feature/2026-09-30-config-backup-tmp-data.md)
states implementation scope and regression coverage. The
[user guide](../../doc/config-backup.md) describes export, import and recovery.
