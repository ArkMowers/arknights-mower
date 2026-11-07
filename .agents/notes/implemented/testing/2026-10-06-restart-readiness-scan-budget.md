---
title: Restart Readiness Scan Budget
status: implemented
category: testing
date: 2026-10-06
---

# Restart Readiness Scan Budget

## Contract

[INV-UPD-02] requires strict registration scans to retry unreadable files within one shared monotonic budget, preserve unverified registrations and report exhausted budgets through `InstanceScanError`. Restart-persistence readiness uses complete snapshots within a 30-second deadline.

## Simplification Audit

`ProcessRestartPersistenceTests` has one local readiness poller. Its zero-timeout override disables the scanner's existing retry policy during concurrent registration publication. The poller reuses the five-second scanner budget, capped by its remaining readiness time; no new helper, production retry policy or best-effort fallback is added.

## Verification

The restart-persistence test injects one `PermissionError` while reading the child's registration and verifies a subsequent successful read before asserting configuration, plan-byte and update-acknowledgement persistence through two restarts. `InstanceScanTests` covers transient recovery, one shared retry budget, structured persistent errors and registration preservation.

## Standards Findings

Pass. The change is confined to the test and registration-scan contracts. Child-process cleanup and finite deadlines remain binding. Existing domain definitions require no glossary changes. Ruff and governance checks pass.

## Spec Findings

Pass. Readiness tolerates transient Windows registration-file contention while persistent unreadability remains a structured failure. Production update admission, process control and scanner behavior retain their existing contracts. Focused process-control, runtime-scan and governance suites pass 52 tests and 33 subtests; two native Windows tests are skipped on macOS. Native Windows validation remains subject to CI.
