---
title: OTA release target scope
status: implemented
category: simplification
date: 2026-10-09
---

# OTA release target scope

[INV-UPD-05] Release Artifact Scope excludes macOS x64 from future release builds and limits generated OTA packages to Windows x64 and Android ARM64, including Nightly. Android runtime paths retain canonical relative POSIX names, including Debian multiarch colons, and reject traversal, drive prefixes, duplicate entries and host data files. Invalid target packages stop publication before channel index updates.

The release workflow removes the Intel macOS matrix entry and retains Linux full packages and macOS ARM64. MowerRelease separates full-package targets from OTA targets, publishes each completed delta immediately and logs download/build durations with bounded GitHub commands. Nightly uses the same OTA publisher for both supported platforms. The Android reconstructor accepts the same runtime paths as the publisher.

The simplification removes Linux differential generation from the release path; it does not add a replacement archive abstraction. Focused workflow tests cover the retained build matrix. MowerRelease and Android repository tests cover runtime path compatibility, safe rejection and resumed incremental publication.

[Software update contract](../../../../docs/subsystems/software-update.md) defines the invariant.
