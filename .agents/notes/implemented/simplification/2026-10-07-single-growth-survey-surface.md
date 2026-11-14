---
title: Single growth survey surface
status: implemented
category: simplification
date: 2026-10-07
---

# Single growth survey surface

The mastery recommendation page is the single consumer of the overview and general operator filters. The requested community-statistics view replaces that surface while retaining the same operator-card and growth-plan state. A second planning route, duplicate goal store or parallel material calculator provides no distinct behavior.

The new operator-statistics component receives locally computed personal aggregates. A focused survey-filter component and pure filtering utility consume public observations and the same owned-operator list. They replace the old filter bindings; they do not fork plan mutations, task insertion or material preparation. Existing historical data remains available to its established backend consumers rather than being relabeled as community observations.

[INV-GROWTH-02] preserves the distinction between absent public observations and measured zero rates, and makes every survey-only interaction read-only with respect to local growth goals. Focused helper and component tests verify replacement behavior without duplicating the full planning workflow.
