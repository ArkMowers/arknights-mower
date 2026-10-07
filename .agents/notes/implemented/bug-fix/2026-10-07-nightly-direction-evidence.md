---
title: Nightly Direction Evidence
status: implemented
category: bug-fix
date: 2026-10-07
---

# Nightly Direction Evidence

## Contract

[INV-UPD-03] resolves same-alpha Nightly direction from publication dates or verified upstream commit ancestry. An installed build outside retained index history still receives an upgrade verdict when the target descends from it. Unknown direction retains manual confirmation.

## Simplification

The existing release direction function owns the fallback and reuses the bounded GitHub request helper. No additional version abstraction, configuration, dependency or persistent cache is introduced. Publication dates and identical version names avoid the fallback request; offline package inspection remains network-free.

## Verification

Focused software update tests cover the installed `074d15a3` build and target `90a9d91f`, proxy propagation, forward and backward ancestry, divergence, unavailable comparisons, missing or malformed dates, publication ordering and offline confirmation.

## Review

Standards Findings: the fallback reuses a finite request timeout and adds no persistent state. Spec Findings: retained history is an optimization rather than a prerequisite for recognizing older installed builds; verified rollbacks and unknown direction retain confirmation.
