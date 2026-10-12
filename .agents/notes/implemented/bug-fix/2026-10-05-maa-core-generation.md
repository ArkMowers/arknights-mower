---
title: MAA Core Generation Validation
status: implemented
category: bug-fix
date: 2026-10-05
---

# MAA Core Generation Validation

## Contract

[INV-MAA-11] validates desktop core identity and version before connection. The [MAA runtime contract](../../../../docs/subsystems/maa-runtime.md) owns initialization, safe idle reloading and process-restart fallback. The identifier uses the MAA namespace because the software-update namespace already assigns its second identifier to registration scans.

## Rationale and Simplification

External updates replace files without replacing the running native image. The existing cache cleanup provides one recovery path for Windows and Linux once instance destruction and library ownership are verified. Tracking repeated SDK opens prevents a single close from leaving the original image resident. macOS MAA registers Objective-C classes that survive closing the library, so its recovery retains process restart. A bounded child-process version probe avoids registering duplicate native classes in the parent.

The scheduler delegates construction to the tested runtime loader and retains resource diagnostics and callback initialization. No configuration flags, recovery workers or scheduling state are added. Existing domain concepts retain their names, meanings and boundaries, so glossary edits are unnecessary. This review repair updates the owning triplet in place and retains its implemented lifecycle.

## Verification

Focused offline suites cover core validation, same-version replacement, retained idle and raw SDK instances, untracked loads, repeated native opens, failed unloading, SDK reimport, fresh instance options, resource diagnostics, callback routing, navigation, shared ADB transport and source/packaged version-probe dispatch. Compiler-built native fixtures exercise actual dynamic-library unloading and confirm the replacement build despite an unchanged version string; they run in isolated child processes and skip when no POSIX C compiler is available.

A device-free check with the local official macOS MAA v6.17.0 core confirms repeated initialization and the restart fallback after replacing the core file. It connects no device and starts no automation. Actual Windows/Linux MAA binaries and packaged launchers are not exercised locally; cross-platform CI remains separate evidence.

## Standards Findings

Pass: cleanup rejects reachable instances and unknown ownership, preserves busy admission, and keeps native version probing outside the parent. Domain concepts and Scheduling Plans retain their contracts. Governance checks provide structural evidence separately from behavior tests.

## Spec Findings

Pass: Windows/Linux attempt at most one verified idle reload, obtain a new SDK class and option definitions, and compare the replacement with a fresh disk probe before connection. Unsafe or failed recovery retains explicit process-restart guidance; macOS follows that boundary without closing its native image.
