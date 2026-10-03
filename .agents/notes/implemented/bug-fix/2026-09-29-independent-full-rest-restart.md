---
title: Independent full rest after restart
status: implemented
category: bug-fix
date: 2026-09-29
---

# Independent full rest after restart

With experimental dormitory logic enabled, an ungrouped operator configured for both exhaustion and full rest continues an unfinished dormitory recovery cycle when correction cannot find an available replacement. Losing the return task does not end that recovery cycle.

Correction reuses the existing resting-member detection and replacement selection. Normal planning rebuilds the return task from the dormitory deadline through `plan_metadata`; no additional persisted state or timer implementation is introduced. Completed recovery, available replacements, grouped correction, and legacy dormitory behavior retain their existing rules.

Offline tests cover task loss, operator-cache restoration, missing and retained deadlines, repeated planning, effective upper limits of 12/20/24, and completed recovery.
