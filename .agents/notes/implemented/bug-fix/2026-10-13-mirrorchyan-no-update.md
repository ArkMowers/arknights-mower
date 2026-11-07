---
format: decision
title: MirrorChyan No Update Result
status: implemented
category: bug-fix
date: 2026-10-13
---

# MirrorChyan No Update Result

[中文](2026-10-13-mirrorchyan-no-update.zh.md)

## Problem

MirrorChyan can return a successful response containing a version without a download URL when the submitted installed version is current. Requiring a URL before comparing versions caused the updater to reject this valid result as incomplete download information. The [MirrorChyan integration guide](https://github.com/MirrorChyan/docs#响应数据结构) defines the response fields.

## Decision

The updater compares versions after service-error and CDK-expiration checks, before requiring a download asset. `MaaRelease.runtime` is optional so the existing metadata path can represent no update. The check route returns no check identifier, the installer returns `updated=false`, and the worker reports that no update is needed while retaining the loaded core. The [MAA integration description](../../../../docs/subsystems/maa-integration.md#mirrorchyan-no-update) defines the behavior and interface results.

## Alternatives considered

A second request is unnecessary because the response already supplies the version needed for comparison. A dummy URL would misrepresent the absence of an asset. A new exception path would turn a successful protocol outcome into error handling; the existing release metadata carries that outcome directly.

## Consequences

No-update execution preserves the installation, backup and loaded core. Newer releases and first installations still require a valid HTTPS download URL, and CDK errors remain failures. Callers must accept a null runtime asset for no-update metadata. This repair does not restore previously damaged resource caches. No glossary definition changes are needed.

## Verification

The focused offline [update tests](../../../../arknights_mower/tests/maa_update_tests.py) and [route tests](../../../../arknights_mower/tests/maa_update_route_tests.py) pass 76 tests, with one Windows module-query test skipped on macOS. They cover same or older versions without URLs, missing URLs for newer releases or first installation, CDK refusal, retained installation and backup, check results and worker behavior. Governance unit tests pass 80 tests; Ruff checks pass. Windows GUI operation and real CDK downloads were not exercised.
