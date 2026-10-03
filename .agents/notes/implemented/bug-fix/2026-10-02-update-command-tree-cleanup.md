---
title: Update Command Tree Cleanup
status: implemented
category: bug-fix
date: 2026-10-02
---

# Update Command Tree Cleanup

## Contract

[INV-UPD-01] owns each Windows update command and its descendants before execution. Cancellation, timeout and completion verify that the owned command tree exits within a finite budget before the temporary checkout is released. Other application instances retain their processes and files during cancelled preparation.

## Simplification

The standard-library installer owns one Windows Job per command. This replaces taskkill tree enumeration and shares termination and completion verification. No configuration, external dependency or compatibility alias is added. Existing cancellation and transaction assertions remain mandatory.

## Verification

Focused command-progress and source-transaction tests cover cancellation, timeout, normal completion, descendants and original-instance preservation. Device integrations are excluded. Windows CI verifies the native process boundary.

## Review

Standards Findings: command containment uses only the standard library, retains fixed argument lists and bounded cleanup, and leaves unrelated instances untouched.

Spec Findings: five new regressions cover containment before execution, cancellation and timeout ordering, failed assignment, descendant completion and cleanup deadlines. Focused command and transaction suites pass 112 tests and 152 subtests; two existing platform skips stay unchanged. Ruff and governance pass. Native Windows execution remains subject to CI.

The proxy-environment test mocks command containment together with Popen, preserving environment assertions without passing a simulated handle to native Windows APIs.
