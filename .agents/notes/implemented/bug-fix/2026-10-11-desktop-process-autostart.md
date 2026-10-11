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

Focused offline tests exercise the real desktop entry point with foreground/background settings, tray and manager modes on the supported desktop platform branches. They cover resource ordering and failure, an already-owned install, pause and shutdown during installation, explicit restart modes and repeated window/browser actions. Status tests verify persistent process ownership after stopping. Frontend tests exercise repeated App mounts, status-store mapping and the non-desktop fallback, including resource automation during non-desktop update restarts. Restoring the old foreground condition makes the process-start regression fail; restoring the repair passes.

Verification passes 66 focused backend tests and 38 frontend tests. Ruff, Python formatting, Prettier and whitespace checks pass. ESLint passes for App and the changed tests; the mower store retains the existing undefined `sc_uri` error, independently confirmed in the alpha baseline. Governance passes its three structural gates with two existing archived-reference warnings.

## Review

Standards review confirms credentialed route reuse, cancellation, existing maintenance admission, host compatibility and unchanged domain concepts. Specification review confirms process-only desktop startup, stopped-state preservation through browser mounts, resource-before-task ordering and explicit restart overrides. No new actionable findings remain. Verification uses mocked platform boundaries; live desktop windows, emulators and the separate Android launcher are not exercised.
