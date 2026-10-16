---
format: decision
title: MAA process isolation on desktop
status: implemented
category: architecture
date: 2026-10-17
---

# MAA process isolation on desktop

## Problem

On the inspected macOS host, a completed update installs v6.20.0-beta.1 while four Mower processes retain the v6.19.0 core in the renamed backup directory. The connectivity check uses a fresh child process and therefore reports the installed version. The existing [core generation decision](../../implemented/bug-fix/2026-10-05-maa-core-generation.md) prevents unsafe native reloads but requires restarting Mower on macOS.

## Decision

Each desktop MAA instance runs in a fresh subprocess owned by [`maa_process.py`](../../../../arknights_mower/utils/maa_process.py), using the shared worker entry point in source and frozen applications. Scheduling, inventory accounting and callback interpretation stay in Mower. Existing instance operations and ordered callbacks cross a bounded local channel. The loader confirms the worker's version and the installation's identity before connection. Workers close on completion, update, failure and parent exit; an unavailable worker fails the current call without silently replaying tasks. Shared installation leases coordinate participating Mower instances; exclusive installation and backup retirement require native workers to release their leases. Windows releases native file locks before installation. Android retains its existing native bridge and service-restart requirement, as requested.

This partially supersedes the old decision's desktop activation mechanism; core verification, task admission and backup ownership remain applicable. Domain concepts and persisted configuration retain their existing meanings, so no glossary change is needed. The [MAA runtime description](../../../../docs/subsystems/maa-runtime.md) remains the authoritative behavior owner.

The same boundary protects shared-client files: Windows uses the official installation mutex protocol, while macOS checks mapped core files before writes and backup retirement. The [software update description](../../../../docs/subsystems/software-update.md#17-maa-package-validation-and-backups) owns package-list validation, full-package repair and installation-local `.old` backups. Activity navigation restores its prior bytes when a fresh worker rejects loading, with layout selection and rollback owned by the [MAA integration description](../../../../docs/subsystems/maa-integration.md#6-desktop-activity-navigation).

## Alternatives considered

Removing the macOS guard restores the former attempt to close and reopen the library, but does not establish that native images or Objective-C registrations were released. Restarting Mower provides isolation but interrupts unrelated scheduling and the web interface. Isolating only connectivity checks already works and does not replace the core used by actual automation.

## Verification

Focused offline MAA suites pass. The [worker tests](../../../../arknights_mower/tests/maa_process_tests.py) exercise actual worker launches, ordered callbacks and callback-triggered parameter updates, bounded parent and worker callback queues, task admission, startup failure, timeout, parent-pipe EOF, process exit, cleanup, shared leases and core replacement with unchanged version strings. Scheduler tests cover the production desktop entry and unchanged Android bridge; an update-job test verifies successful activation without restart guidance. Source launcher dispatch and the frozen launch command are checked separately. A no-device smoke check with the official macOS v6.17.0 core replaces the core file and initializes two workers under the same parent. Structural governance checks pass independently of these behavior results.

## Consequences

Desktop updates activate through new workers without restarting Mower or unloading native images in its process. Process startup adds work per MAA run. Communication failure terminates the current operation instead of replaying an accepted task. Windows client mutexes prevent a client from starting during shared-file writes; macOS mapping checks observe occupancy but cannot prevent a later uncoordinated startup. Legacy sibling backups remain untouched. Already-running versions that loaded the core in Mower still require one restart to enter the isolated implementation. Native Windows cores, frozen packages and Android devices have not been run locally; the offline checks do not establish those platform outcomes or live automation behavior.
