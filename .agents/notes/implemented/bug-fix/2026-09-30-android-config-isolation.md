---
title: Android configuration isolation
status: implemented
category: bug-fix
date: 2026-09-30
---

# Android configuration isolation

## Contract

[INV-DEV-12] Android Configuration Ownership requires Android-managed connection, capture, input, native appearance, screenshot history and service endpoint settings to remain authoritative during load, import, partial update and save/reload. Desktop Device Profile values never overwrite those settings. The user's game server and general task settings remain editable.

## Boundary and simplification

`Conf.migrate_legacy_keys` reuses the installed Android adapter's `normalize` contract and removes the incoming desktop Device Profile before profile validation. `Conf.migrate_device_profile` derives the Device Profile from the validated native fields, preserving server-field type conversion. `Conf.updated` routes Android edits through the same constructor instead of applying desktop instance-binding validation first. No second platform settings registry, discovery adapter or recovery loop is introduced. Existing Android adapters require no schema update.

An explicit `package_type` selects the server. A profile-only import retains a supported `game_package` when the legacy server field is absent. General settings are not replaced by a platform-wide default configuration.

`config_backup._validate_configuration` overlays the validated Android configuration on the imported configuration before serialization. Import writes and subsequent exports contain the native settings and canonical Device Profile instead of retaining the desktop values on disk. Main and backup Base Plans, weekly plans and general task settings remain editable and support export/import round trips. Unknown backup fields remain preserved, and desktop backup serialization remains unchanged.

## Verification

Hermetic tests freeze the legacy Android normalization contract and exercise imported desktop profiles, malformed desktop-only fields, partial updates, native settings, game server selection, general task settings, import/export, save/reload and unchanged desktop behavior. Separate compatibility checks combine the current Android adapter with the updated main repository without connecting a device.
