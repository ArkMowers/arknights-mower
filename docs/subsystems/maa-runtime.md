# MAA Runtime Core Contract

## 1. Initialization

`load_verified_maa` serializes desktop core validation and instance construction with the existing update transaction. It checks the configured core file, loads base and incremental resources, and verifies the instance's core version against `read_installed_version(fresh=True)` before acquiring a device connection. An unchanged SDK class and core file identity reuse the verified disk version; resource and cache changes still reload resources.

The fresh disk probe runs in the existing MAA check child process with a thirty-second timeout. Its version-only mode loads no SDK resources and acquires no device connection. Source and packaged launchers use the same version-result protocol; native images and Objective-C registrations stay outside the parent process.

## 2. Reload and Failure Boundary

A changed validated core identity triggers at most one call to `clear_loaded_maa_cache` before resource loading. Windows and Linux release the idle scheduler reference, collect unreachable instances, and reject unloading while any verified or raw SDK instance remains reachable. `stop()` alone does not release a native instance. The SDK destructor releases the instance and joins its native workers before its library is closed.

The loader tracks the current library object and the number of native opens obtained through SDK loading. Cleanup rejects untracked SDK loads, closes every tracked open, removes the old SDK modules and import paths, and imports a new `Asst` class from the configured installation. The scheduler imports instance-option definitions again after reload. The replacement passes an independent disk-version probe and a second file-identity check before connection, including replacements with unchanged version strings.

macOS retains the restart fallback because MAA registers Objective-C classes that remain registered after closing its dynamic library. Cleanup does not close that core. A failed native close invalidates the old SDK class, and later initialization cannot reuse it. Any unsafe cleanup, failed SDK import, failed resource load or failed replacement validation during recovery raises `MaaCoreRestartRequired` with code `maa_core_restart_required`; stopping and starting automation does not replace a process restart.

Android retains its host-managed core lifecycle. Configuration schemas, Scheduling Plans and device transport retain their existing contracts.

## 3. Subsystem Invariants

[INV-MAA-11] is registered in [Coding Standards](../../CODING_STANDARDS.md#28-maa-integration). [Core generation validation](../../.agents/notes/implemented/bug-fix/2026-10-05-maa-core-generation.md) records the decision and focused verification.
