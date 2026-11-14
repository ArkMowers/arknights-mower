---
title: MAA Core Generation Validation
status: implemented
category: bug-fix
date: 2026-10-05
---

# MAA Core Generation Validation

The [desktop process isolation decision](../architecture/2026-10-17-maa-process-isolation.md) replaces this record's desktop activation mechanism. Core identity/version validation and backup ownership remain applicable; the native-unload rationale below governs the compatibility loader and already-loaded in-process cores.

## Contract

[INV-MAA-11] validates desktop core identity and version before connection. The [MAA runtime contract](../../../../docs/subsystems/maa-runtime.md) owns initialization, safe idle reloading and process-restart fallback. The identifier uses the MAA namespace because the software-update namespace already assigns its second identifier to registration scans.

## Rationale and Simplification

External updates replace files without replacing the running native image. The existing cache cleanup provides one recovery path for Windows and Linux once instance destruction, library ownership and actual image unloading are verified. Tracking repeated SDK opens alone is insufficient: GNU_UNIQUE symbols, NODELETE libraries and external opens can keep an image resident after every tracked close succeeds. Recovery confirms removal of the loaded function's mapping before reimporting the SDK. macOS MAA registers Objective-C classes that survive closing the library, so its recovery retains process restart. A bounded child-process version probe avoids registering duplicate native classes in the parent.

Core generation records the resolved target file rather than the symlink entry, so replacing a target invalidates the cached version and its identity is checked again after probing and loading. Backup ownership retains the existing `lstat` helper; its semantics serve a different lifecycle and remain unchanged. Both review defects extend the existing [INV-MAA-11] guarantee rather than introduce a new identifier.

Native-open tracking also retains file identity when initialization fails before version validation. Keeping this identity in the existing load record closes the failed-first-initialization gap without treating a failed probe as a verified version or adding another cache. Retrying an unchanged core remains possible; replacing it triggers recovery before new resources reach the old image. Untracked preloaded libraries cannot establish identity through version equality alone. This repair reuses [INV-MAA-11] and the same record owner.

The scheduler delegates construction to the tested runtime loader and retains resource diagnostics and callback initialization. No configuration flags, recovery workers or scheduling state are added. Existing domain concepts retain their names, meanings and boundaries, so glossary edits are unnecessary. This review repair updates the owning triplet in place and retains its implemented lifecycle.

Explicit update workers apply the same lifecycle boundary: resource-only updates retain the core, while a completed core installation retains its result when post-install activation requires restart. Treating cleanup as installation failure loses the committed result and its backup reference. Windows cleanup before replacement remains an installation prerequisite. This repair also follows [INV-UPD-04] without introducing another invariant or decision.

## Verification

Focused offline suites cover core validation, same-version and symlink-target replacement, target changes during probing, retained idle and raw SDK instances, untracked loads, repeated native opens, failed or unconfirmed unloading, SDK reimport, fresh instance options, resource diagnostics, callback routing, navigation, shared ADB transport and source/packaged version-probe dispatch. Compiler-built native fixtures exercise actual dynamic-library unloading and confirm the replacement build despite an unchanged version string. Linux NODELETE and extra-open fixtures require restart without loading replacement resources into the resident image, including a later retry. They run in isolated child processes; mapping-sensitive cases require Linux and native fixtures require a POSIX C compiler.

Additional native cases fail resource loading, SDK loading after an open, instance construction or disk probing twice before same-version replacement. Linux then admits build 2 after one cleanup; macOS requires restart without a third resource load. Unchanged-core retries after resource or probe failure recover build 1 without cleanup. All four replacement cases fail on the preceding implementation and pass after retaining native-open identity.

A device-free check with the local official macOS MAA v6.17.0 core confirms repeated initialization and the restart fallback after replacing the core file. An offline Linux container with official MAA v5.24.2 confirms restart after same-version replacement and replacement of a symlink target whose fresh disk version is v5.24.3; neither case reloads resources into the resident core or reuses the invalidated SDK. These checks connect no device and start no automation. Actual Windows MAA binaries and packaged launchers remain untested locally; cross-platform CI remains separate evidence.

Worker tests exercise the status endpoints for resource updates and completed core updates across all three desktop platforms. Unsafe cleanup preserves successful installation results and restart guidance; successful cleanup, failed post-install version probing, actual installation failure and Android resource packing retain their respective outcomes. The two unsafe-cleanup cases fail before the worker repair and pass afterward.

## Standards Findings

Pass: cleanup rejects reachable instances and unknown ownership, preserves busy admission, and keeps native version probing outside the parent. Domain concepts and Scheduling Plans retain their contracts. Governance checks provide structural evidence separately from behavior tests.

## Spec Findings

Pass: Windows/Linux attempt at most one idle reload after actual image unloading is confirmed, obtain a new SDK class and option definitions, and compare the replacement with a fresh disk probe and resolved target identity before connection. Unsafe or failed recovery retains explicit process-restart guidance; macOS follows that boundary without closing its native image.
