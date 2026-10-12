# MAA Runtime Core Contract

## 1. Initialization

`load_verified_maa` serializes desktop core validation and instance construction with the existing update transaction. It checks the configured core file, loads base and incremental resources, and verifies the instance's core version against `read_installed_version(fresh=True)` before acquiring a device connection. Core identity includes the configured path, resolved target path, and target file's device, inode, size and modification time. An unchanged SDK class and core identity reuse the verified disk version; replacing a symlink target invalidates that cache. Resource and cache changes still reload resources.

The fresh disk probe runs in the existing MAA check child process with a thirty-second timeout. Its version-only mode loads no SDK resources and acquires no device connection. Source and packaged launchers use the same version-result protocol; native images and Objective-C registrations stay outside the parent process.

Every tracked native open retains its core file identity independently of the successfully verified version cache. Failed resource loading, SDK exceptions, instance construction and disk probing retain that identity. A retry checks it before loading resources: an unchanged core can retry initialization and fresh version probing, while a replaced core enters the same unload-or-restart recovery even when no initialization has succeeded. A preloaded SDK library without a matching owned load record is rejected before resource loading.

## 2. Reload and Failure Boundary

A changed validated core identity triggers at most one call to `clear_loaded_maa_cache` before resource loading. Windows and Linux release the idle scheduler reference, collect unreachable instances, and reject unloading while any verified or raw SDK instance remains reachable. `stop()` alone does not release a native instance. The SDK destructor releases the instance and joins its native workers before its library is closed.

The loader tracks the current library object and the number of native opens obtained through SDK loading. Cleanup rejects untracked SDK loads and locates the loaded version function's address before closing every tracked open. Linux checks `/proc/self/maps`; Windows queries `GetModuleHandleExW` by address without acquiring a reference. Cleanup removes the old SDK modules and import paths only after confirming that this address is no longer mapped to an image. A resident image or unavailable mapping query requires a process restart before replacement resources can load. Successful close calls alone do not establish unloading: GNU_UNIQUE symbols, NODELETE libraries and extra native opens can retain the image.

After confirmed unloading, the loader imports a new `Asst` class from the configured installation. The scheduler imports instance-option definitions again after reload. The replacement passes an independent disk-version probe and a second resolved-target identity check after loading before connection, including replacements with unchanged version strings. Backup ownership retains its separate `lstat` identity semantics.

macOS retains the restart fallback because MAA registers Objective-C classes that remain registered after closing its dynamic library. Cleanup does not close that core. Beginning native close invalidates the old SDK class; a failed close or unconfirmed unload prevents later initialization from reusing it. Any unsafe cleanup, failed SDK import, failed resource load or failed replacement validation during recovery raises `MaaCoreRestartRequired` with code `maa_core_restart_required`; stopping and starting automation does not replace a process restart.

Android retains its host-managed core lifecycle. Configuration schemas, Scheduling Plans and device transport retain their existing contracts.

## 3. Explicit Update Completion

`server._run_maa_resource_update` retains the loaded core after a resource-only installation. The next initialization reloads resources under the unchanged core identity. Android still packs the managed component and reports its service-restart requirement.

`server._run_maa_update` separates committed installation from runtime activation. A post-install cleanup failure retains a successful job, its installed files and backup, and sets `result.restart_required` with process-restart guidance. A failed post-install disk-version probe retains the installation result, reports an unknown `installed_version` and asks the user to check the installation. Initialization still enforces core validation before connection. Installation failures remain errors; Windows pre-install cleanup must succeed before directory replacement to release native file locks.

## 4. Subsystem Invariants

[INV-MAA-11] is registered in [Coding Standards](../../CODING_STANDARDS.md#28-maa-integration). [Core generation validation](../../.agents/notes/implemented/bug-fix/2026-10-05-maa-core-generation.md) records the decision and focused verification.
