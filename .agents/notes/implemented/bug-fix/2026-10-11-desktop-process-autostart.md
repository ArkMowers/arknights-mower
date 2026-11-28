---
title: Process-owned desktop autostart
status: implemented
category: bug-fix
date: 2026-10-11
---

# Process-owned desktop autostart

Commit `8a4d1d7f20e0755d28a74d79b20d6b193481daa2` on 2023-06-08 adds task startup to the frontend mount callback. Normal desktop processes report startup as unhandled, so every browser mount can restart a stopped task. Later update and configuration-import protections cover specific reloads rather than the process lifetime.

The [Web Access contract](../../../../docs/subsystems/web-access.md#5-desktop-startup) owns [INV-WEB-03] and the complete startup policy. The existing desktop worker takes foreground startup and automatic resource installation together, preserving resource-before-task ordering without requiring a page. Its ownership flag also suppresses cached frontend task-start code. The existing host fallback remains for the separate Android launcher.

The complexity audit reuses the desktop resume worker, tracked resource installer and compatibility status flag, with an explicit desktop flag distinguishing resource ownership from non-desktop restart suppression. No persistent consumed flag, polling-based task admission or additional startup service is introduced. Prior-work searches locate update restart protections and owned-resource shutdown, but no record owns automatic task admission across browser mounts; this decision records that independent boundary. Domain concepts and configuration meanings remain unchanged, so [INV-06] requires no glossary changes.

## Verification

The startup worker originally reused the resource installer's POST context for `server.start`. That route requires an explicit temporary-preparation payload on POST and returns HTTP 400 before task admission when the payload is absent. The worker now uses a separate credentialed GET context for ordinary starts and update resumes, while resource installation retains POST. [INV-WEB-03] and the existing temporary-preparation consent contract retain their meanings.

The desktop fixture executes the real `server.start` route and isolates `_start_mower` at the task-execution boundary. Four existing startup and resume cases fail before the context correction because task admission is absent; they pass after it. Coverage includes normal startup without resource automation, resource-first ordering, failures, cancellation and explicit restart policies. The fixture also verifies that resource installation retains POST.

The context correction passes 43 tests across desktop lifecycle, process control, server status and application shutdown, plus two selected device-settings route tests verifying one-start preparation consent and rejection of missing or mismatched consent. Ruff, formatting, whitespace and structural governance checks pass, with two existing archived-reference warnings.

Focused offline tests exercise the real desktop entry point with foreground/background settings, tray and manager modes on the supported desktop platform branches. They cover resource ordering and failure, an already-owned install, pause and shutdown during installation, explicit restart modes and repeated window/browser actions. Status tests verify persistent process ownership after stopping. Frontend tests exercise repeated App mounts, status-store mapping and the non-desktop fallback, including resource automation during non-desktop update restarts. Restoring the old foreground condition makes the process-start regression fail; restoring the repair passes.

Verification passes 66 focused backend tests and 38 frontend tests. Ruff, Python formatting, Prettier and whitespace checks pass. ESLint passes for App and the changed tests; the mower store retains the existing undefined `sc_uri` error, independently confirmed in the alpha baseline. Governance passes its three structural gates with two existing archived-reference warnings.

## Review

Standards review confirms credentialed route reuse, cancellation, existing maintenance admission, host compatibility and unchanged domain concepts. Specification review confirms process-only desktop startup, stopped-state preservation through browser mounts, resource-before-task ordering and explicit restart overrides. The context correction adds real route validation to the desktop fixture; platform and task-execution boundaries remain isolated. Live desktop windows, emulators and the separate Android launcher are not exercised.
