---
format: decision
title: Shared generated operator catalog
status: implemented
category: simplification
date: 2026-10-30
---

# Shared generated operator catalog

## Problem

Previously, operator names, professions and building skills used separate generation and loading paths. The calculator catalog stored maximum-stage skills beside their complete slot histories, and the native mood bundle embedded that catalog again. The existing [shared building-skill decision](2026-10-09-shared-building-skill-data.md) owns the display catalog and its historical archive path; it does not own calculator profiles or native mood packaging.

## Decision

[`operator_data.py`](../../../../arknights_mower/utils/operator_data.py) compiles a compact shared catalog under backend data from the game tables used by `auto_get_res_new.py`. Bundled names, professions and calculator maximum-stage skills derive from that catalog. The generator preserves the historical resource exports, and selected external generations use their own exports without borrowing bundled files. The shared catalog stays outside resource archives because existing clients reject unknown members. Native mood rules load their bundled catalog separately and verify code and data together; their saved-state identity covers both. The calculator and native runtime retain their software-version pairing rather than following resource OTA changes. The [resource generation description](../../../../docs/subsystems/resource-update.md#shared-operator-catalog) owns these loading and publication requirements.

## Alternatives considered

Combining account progression with game definitions would couple independent update sources and is unnecessary. Publishing the new catalog as an optional archive member still makes existing strict resource clients reject the package. Replacing the calculator's data with whichever OTA happens to be installed would lose the verified rules/data pairing. Keeping embedded copies avoids a loader change but retains redundant shipped data and separate maintenance paths.

## Consequences

Historical archive files remain small generated compatibility outputs. The browser page and Worker each retain a compiled copy of the shared compact catalog, while native mood packaging stores its input separately from code. Display-specific building-skill data remains owned by its existing decision. Game data changes still require supported calculator rules; a common catalog does not establish coverage of every skill. Personal synchronization, Scheduling Plan semantics and Operator Mood definitions remain unchanged, so this storage and packaging change requires no glossary edit.

## Verification

The initial compilation matches all 432 existing profiles and 929 skill stages. The focused backend suites pass 204 tests, including [catalog generation and resource isolation](../../../../arknights_mower/tests/operator_data_tests.py), [native packaged execution and data integrity](../../../../arknights_mower/tests/calculated_mood_tests.py), resource installation and OTA, growth, training rules and Android archive checks. The four selected frontend files pass 67 tests for catalog adaptation, native bundle generation, mood preparation and income calculations. The production frontend build, generated-runtime check and calculator-source verification pass. Repository structural checks pass separately from this behavior evidence. Relative to the inspected starting build, the catalog and three affected JavaScript artifacts have a net uncompressed reduction of 578,487 bytes. This measures those files rather than a final installer. Verification is offline; no live device session or complete release archive is claimed.
