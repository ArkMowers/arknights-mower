---
format: decision
title: Windows Desktop Launcher Permissions
status: implemented
category: feature
date: 2026-10-16
---

# Windows Desktop Launcher Permissions

[中文](2026-10-16-windows-desktop-launcher-permissions.zh.md)

## Problem

Users with standard Windows accounts and no administrator credentials cannot launch either packaged desktop entry point under the previous mandatory-elevation policy. The [earlier decision](../../archived/feature/2026-10-11-windows-desktop-elevation.md) used native manifests to obtain elevation before startup and propagate it to managed instances, but made administrator authorization a prerequisite for all users.

## Decision

Both executables in [the Windows packaging specification](../../../../webui_zip.spec) use `asInvoker` through `uac_admin=False`. The existing manager launch inherits its caller's permissions. This replaces the earlier mandatory-elevation decision; the [Arknights Mower Software Update Subsystem Description](../../../../docs/subsystems/software-update.md#14-windows-desktop-launch-permissions) owns the startup and directory-access rules. Domain concepts retain their meanings; no glossary changes are needed.

The [shortcut helper](../../../../arknights_mower/utils/windows_shortcuts.py) creates optional elevated launch links at ordinary desktop startup. Generating them in the actual installation directory avoids embedding a build-machine path; refreshing them after relocation keeps the links usable. Their generation has a finite timeout and does not prevent startup on failure.

## Alternatives considered

Keeping mandatory elevation excludes users who cannot supply administrator credentials. Requesting elevation again after an access failure still cannot authorize those users and adds restart behavior without correcting file permissions. Inherited permissions allow ordinary startup and retain Windows' explicit Run as administrator option for authorized users who need it.

## Consequences

Standard users can start the application without an elevation request. They need a writable portable installation and writable data and MAA directories. Access restrictions imposed by an emulator or Windows remain effective. Existing executables retain their embedded manifests until replaced; users unable to start the old package need the rebuilt full package. Updating from an elevated process retains elevation until that process tree exits and the application is launched normally again.

## Verification

The release-workflow, manager and shortcut suites pass 57 focused offline tests; one native Windows Shell test is skipped on macOS. The updated launch-policy checks fail against the old packaging configuration before the repair. Tests inspect both executable declarations, execute the release manifest gate against accepted and rejected manifests, and verify direct manager launches with their arguments, working directory and environment. The gate rejects mandatory or optional elevation, UI access, missing manifests and absent execution-level declarations. Shortcut tests cover both desktop callers, platform isolation, actual executable directory selection, bounded process invocation and failure continuation. The Windows CI test reads both native shortcuts and checks their targets, working directories, elevation flags, repeated startup and relocation; it has not run on the macOS host. Interactive standard-account startup, UAC, emulator access and update restart still require Windows validation.
