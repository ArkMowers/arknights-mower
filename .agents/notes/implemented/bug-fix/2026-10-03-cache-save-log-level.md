---
title: Cache Save Log Visibility
status: implemented
category: bug-fix
date: 2026-10-03
---

# Cache Save Log Visibility

Successful cache persistence emits DEBUG, which the existing INFO-level WebHandler excludes from the user log. Diagnostic file logging retains the record. SQLite failures remain ERROR under [INV-DIAG-06].

Simplification: reuse existing handler levels; no new filter, setting or persistence behavior. Verification and two-axis review: the save result and transaction are unchanged; handler-level inspection, Ruff and governance validate this logging-only change. No additional unit test duplicates the existing logging configuration.
