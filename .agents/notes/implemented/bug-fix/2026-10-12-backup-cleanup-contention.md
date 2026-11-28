---
title: Backup Cleanup Contention
status: implemented
category: bug-fix
date: 2026-10-12
---

# Backup Cleanup Contention

## Decision

Startup cleanup shares a nonblocking installation lock. Competing maintenance is a normal skipped attempt; update submission still reports contention to its caller. [INV-UPD-10] registers this distinction in the [software update contract](../../../../docs/subsystems/software-update.md#16-backup-cleanup-contention).

`LockBusyError` preserves `ValueError` compatibility for update callers while distinguishing native lock contention from other acquisition errors. Cleanup catches it only while acquiring the lock. Pending records remain available for later startup attempts.

## Simplification and Concept Impact

Caller review covers runtime startup, verified worker cleanup and update submission. The existing lock and cleanup loop remain authoritative; no additional coordinator, retry loop, dependency or persistent field is introduced. No prior decision triplet covers maintenance lock contention. Scheduling, device and configuration concepts remain unchanged, so the glossary requires no edit.

## Verification

`pytest -q arknights_mower/tests/update_runtime_tests.py arknights_mower/tests/update_backup_tests.py arknights_mower/tests/software_update_tests.py arknights_mower/tests/verify_governance_tests.py` passes with 143 passed and 3 platform-specific skips on macOS. Tests exercise a real competing process with application diagnostics and a copied standalone updater, unchanged pending records, cleanup after lock release, simulated POSIX and Windows lock errors, and release after body failure. Existing tests cover verified backups, denied deletion, replaced files, unrelated data and update submission compatibility. Windows native execution remains unverified locally.

Ruff checks and `python scripts/verify_governance.py` pass. Governance reports two unchanged archived-reference compatibility warnings.

## Standards Findings

PASS: the existing nonblocking lock and guaranteed release remain in place. Cleanup preserves original filesystem failures and existing application logger injection or detached output. Domain concepts and persistent formats remain unchanged.

## Spec Findings

PASS: only acquisition contention ends quietly; the skipped process leaves backups and records intact, and a later process cleans them after release. Existing verified-restart, path and identity protections remain enforced.
