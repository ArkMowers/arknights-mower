---
title: MAA navigation and verified battle dispatch
status: implemented
category: bug-fix
date: 2026-10-12
---

# MAA navigation and verified battle dispatch

Desktop activity navigation occupies `cache/resource/tasks/tasks.json`. MAA recursively loads task directories and ignores the legacy sibling `resource/tasks.json` when `resource/tasks/` exists. MaaResource's OCR hotfix directory activates this precedence, so navigation written outside the directory never reaches the core. The navigation file coexists with hotfix definitions without copying installed tasks or rewriting unrelated cached resources.

The simplification review reuses `update_maa_navigation`, its atomic JSON writer and the existing verified admission boundary. Downloaded navigation must be a nonempty mapping whose task definitions are objects; download, validation and write failures preserve the previous file. Android retains its existing navigation path for component packaging and bridge loading. No updater class, resource layer or persistent configuration is added. [INV-MAA-08] governs resource and dispatch admission.

Offline tests reproduce directory precedence and duplicate-name rejection with an existing OCR hotfix directory. Existing admission tests cover invalid downloads, failed writes, Android loading and rejected resource loads, tasks and starts. The [MAA integration contract](../../../../docs/subsystems/maa-integration.md) owns runtime behavior.
