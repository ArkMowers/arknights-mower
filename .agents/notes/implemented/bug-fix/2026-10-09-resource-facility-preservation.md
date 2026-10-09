---
title: Building Skill Facility Preservation
status: implemented
category: bug-fix
date: 2026-10-09
---

Resource generation previously indexed a fixed room-code map and failed when upstream building data added `RECYCLE`. [INV-RES-03] Building Skill Facility Preservation maps this existing facility to 回收站 and retains unknown room codes, allowing new skill records to reach the frontend without changing their descriptions, icons or phase conditions.

The pre-flight audit finds one failing lookup; the repair extends it without another conversion layer. The generator entry point is guarded so offline tests call the actual skill writer without fetching data or running model generation. Existing facility concepts and scheduling boundaries remain unchanged; no glossary edit is required. This repair owns a separate failure from font expansion and OTA installation.

Standards and specification review confirm complete skill retention, unchanged known labels and offline test isolation. Six focused cases pass for RECYCLE, TRAINING and an unknown code with numeric and string phase representations. A latest-upstream-data replay produces 432 operators and 929 skills, including two recycle skills. Font migration regressions also pass; repository structural governance verifies references and terminology separately. Production publication is verified independently by the resource build workflow.
