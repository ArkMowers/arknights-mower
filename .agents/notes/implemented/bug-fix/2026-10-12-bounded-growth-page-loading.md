---
format: decision
title: Bounded growth page loading
status: implemented
category: bug-fix
date: 2026-10-12
---

# Bounded growth page loading

## Problem

The growth page loads every operator's full material graph and deeply watches the response. A synthetic roster of 432 unpromoted operators from the bundled catalog produces 84.03 MiB of JSON and 705414 nested objects. Opening several instances multiplies parsing, observation and rendering costs. These measurements establish excess load; no captured WebView crash establishes the reported blank window's exact cause. Existing growth decisions own material accounting, but none owns this display-resource boundary.

## Decision

The [bounded loading rule](../../../../docs/subsystems/growth-planning.md#bounded-page-loading) separates a material-free overview from selected-operator details. Existing consumers retain the complete default response. The UI renders thirty overview cards per page and retains one detail snapshot. Replacing that snapshot cancels the previous request; late responses cannot overwrite the selected operator. Details have a finite timeout and local retry. Plan drafts retain deep observation, while server snapshots use replacement observation.

## Alternatives considered

Request serialization leaves the 84 MiB response and retained graph in each renderer. Shallow observation alone avoids proxies but retains the entire payload. Reusing the existing calculator behind an optional material flag preserves one accounting implementation without a second preview calculator or a shared cross-instance cache. The pre-flight simplification finds the combined deep watch as the redundant traversal; its plan-draft observation remains necessary.

## Verification

The same 432-operator fixture produces 0.64 MiB and 6700 nested objects in overview mode, compared with 84.03 MiB and 705414 objects before the change. Measured generation falls from about 2.1 seconds to 0.07 seconds on the local development host; these are synthetic measurements, not user-process memory readings.

`python -m pytest arknights_mower/tests/growth_page_loading_tests.py arknights_mower/tests/growth_planning_tests.py arknights_mower/tests/web_routing_tests.py -q` passes 39 tests. The new [loading suite](../../../../arknights_mower/tests/growth_page_loading_tests.py) verifies suppressed material calculation, an overview below one MiB, preserved single-operator costs, real HTTP routing and concurrent reads without catalog mutation.

The focused Vitest run covering the page, mastery store, crafting-order editor, level control and growth/survey utilities passes 49 tests. The [page tests](../../../../ui/src/pages/MasteryRecommendation.test.js) cover pagination, global filtering, cancellation, delayed responses, retry and unmount cleanup; [store tests](../../../../ui/src/stores/mastery.test.js) cover lightweight requests, shallow snapshots and separate frontend-instance state. The production Vite build, focused Ruff/ESLint and whitespace checks pass.

`python scripts/verify_governance.py --base origin/alpha` passes structural checks with two pre-existing archived-reference warnings. Standards review confirms preserved material accounting, independent transient state and bounded detail ownership. Requirements review confirms the real page requests the overview, retains complete-list filtering and reads materials only for the expanded operator. No domain meaning or configuration change requires glossary editing.

## Consequences

Expanding an operator requires an additional local request. The complete default API remains available for automation and older clients. Packaged multi-instance WebView behavior requires manual verification; payload measurements do not establish a crash diagnosis. Domain concepts, scheduling and configuration remain unchanged, so no glossary edit is required.
