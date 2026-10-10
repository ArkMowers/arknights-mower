---
title: ADB Lock Byte Test Portability
status: implemented
category: testing
date: 2026-10-01
---

# ADB Lock Byte Test Portability

## Contract

[INV-DEV-19] preserves the shared-server generation before a restart attempt, including failed stops and observation by another coordinator. The [shared ADB recovery decision](../../implemented/simplification/2026-10-01-shared-adb-recovery.md) defines the unchanged production boundary.

The failed-stop test reads persisted JSON from byte one through a separate read handle while the coordinator holds its lease. Windows byte-range locking protects byte zero; inspecting the JSON body does not require reading that locked byte. The test retains its generation-before-stop assertion, structured stop-failure assertion and peer-generation observation.

## Simplification

The test seeks past the lock byte instead of reading the whole file and slicing afterward. No production branch, helper abstraction, test skip, platform exclusion or lock relaxation is introduced. Existing invariant registration and glossary definitions remain unchanged.

## Verification

The parameterized test runs with ordinary file reads and an injected denial of whole-file reads. Both paths assert the same failed-stop and peer-generation contract. Focused shared-server tests and repository governance validate the correction; the existing desktop CI matrix retains native Windows execution.
