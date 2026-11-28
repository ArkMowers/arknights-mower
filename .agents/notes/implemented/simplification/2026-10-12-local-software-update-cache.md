---
title: Local Software Update Cache
status: implemented
category: simplification
date: 2026-10-12
---

# Local Software Update Cache

## Contract

[INV-UPD-09] places software update state and temporary workspaces under shared `@app/tmp/updates/`. Installation hashes preserve isolation; instance spaces do not split coordination. DMG inspection uses the same temporary tree. Resource packages, MAA storage and rollback backup locations retain their existing contracts.

## Simplification

`update_runtime.state_dir` owns the update workspace path for launcher registration, job submission and uploads. One data-root resolution replaces three platform cache branches. Existing job consumers inherit the path without new configuration or storage abstractions. `software_update_package._dmg_version` explicitly places its temporary mount workspace in the same tree.

## Verification

Focused tests verify the redirected data root, shared instance storage, separate installation identities and removal of a failed DMG mount workspace without network or device access.

The update runtime, software update and governance test suites report 134 passed and 3 skipped. Repository governance checks pass.

## Standards Findings

The change preserves installation identity hashing and finite DMG command timeouts. No glossary or configuration schema change is required.

## Spec Findings

Software update state and temporary inspection files use the data-root tmp tree. The change is confined to software update storage.
