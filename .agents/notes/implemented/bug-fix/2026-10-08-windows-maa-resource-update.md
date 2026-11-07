---
title: Windows MAA Resource Updates
status: implemented
category: bug-fix
date: 2026-10-08
---

# Windows MAA Resource Updates

## Contract

[INV-UPD-04] exposes independent resource checks and updates for installed Windows MAA through the existing frontend controls and resource routes. GitHub and Mirror酱 use the same incremental merge, resource backup and active-MAA protection as macOS and Linux.

## Simplification

The resource information, check, start and installer functions share the supported platform set. The obsolete Windows manual-update response is removed. The existing frontend consumes `supported` directly; no new UI state, configuration or installer abstraction is introduced.

## Verification

Focused offline tests cover Windows resource information, both update sources, mandatory successful checks, worker platform propagation, preserved core and Python files, incremental resources, backups and active-MAA rejection. Existing merge and rollback tests remain binding.

## Review

Standards Findings: existing transaction locking, bounded downloads and rollback own installation. Spec Findings: installed Windows MAA receives independent resource controls and completes the same update flow as other desktop platforms.
