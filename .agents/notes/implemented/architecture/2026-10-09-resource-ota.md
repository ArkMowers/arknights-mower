---
title: Verified Resource OTA
status: implemented
category: architecture
date: 2026-10-09
---

Resource OTA stores only added or changed resource files and a complete target file digest manifest. [INV-RES-02] Resource OTA Reconstruction requires an exact resource starting version, validates every reconstructed target file, and publishes only a complete compatible generation through the existing immutable resource installer. Online failures use the same release’s complete package; manual packages remain offline.

Pre-flight assessment reuses download proxy handling, install locking, compatibility checks, immutable generations and task-boundary loading. One standard-library codec serves the producer and installer. MowerResource generates direct updates from up to four retained releases and omits patches at least 85 percent of the complete package. Removed files disappear by omission from the target manifest.

Existing domain concepts, scheduling behavior and configuration schema remain unchanged; no glossary modification is needed. Verification covers immutable generation publication and job fallback, starting-version and digest mismatches, deletions, prohibited paths, download bounds, manual installation and publisher asset ordering.

Standards review confirms finite download budgets, bounded inventories, staging cleanup, unchanged active generations, and reuse of the existing process and file installation locks. Specification review confirms exact-base selection, same-target online fallback, offline manual installation, and backward-compatible complete packages. Historical release discovery or per-base generation failure leaves complete-package publication available.

Verification evidence: the focused OTA, progress, package, manual-update and version suites pass with 94 tests and 15 subtests; publisher tests pass with 17 tests. Ruff, the component ESLint check and repository governance pass. A reconstruction experiment using published resources from `v2026.09.29-5f4591c` to `v2026.10.09-466ab33` verifies every target digest: 1,900 files, 6 changed, 13,495,813-byte full package and 5,519,896-byte OTA (59.1 percent smaller). These checks verify implementation; GitHub merge and resource release publication remain separate actions.

CI proxy regressions cover both the OTA index and fallback complete-package requests through the configured GitHub station, global HTTP proxy and default fallback station. The default-station fixture rejects every non-fixture request, so publication of a real OTA index cannot redirect this test to a live resource asset.
