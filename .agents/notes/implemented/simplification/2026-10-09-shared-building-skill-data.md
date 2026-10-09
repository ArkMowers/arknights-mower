---
title: Shared building-skill data
status: implemented
category: simplification
date: 2026-10-09
---

# Shared building-skill data

## Contract

[INV-UPD-07] Shared Skill Data Packaging places the committed catalog in `arknights_mower/data/building_skill.json`. Backend consumers and frontend imports share that source. Backend reads require neither frontend sources nor a WebUI build. Application packaging includes the catalog with backend data and rejects absent or empty required data before publication.

## Boundary and simplification

`dorm_skills._skill_index` and `building_skills.skill_index` use `resource_pkg_path` instead of reconstructing paths inside frontend sources. The frontend imports the shared source, and the HTTP route retains its existing filename. Desktop packaging removes its separate frontend-source inclusion because normal backend data collection includes the catalog. Android collection uses the same directory.

Resource packages retain their historical catalog entry for existing clients and the current publisher. `write_building_skill_data` serializes once and writes identical bytes to the canonical source and an ignored compatibility export. The compatibility export is a generated publication input, not a second committed source or an application packaging input. `resource_pkg_path` translates canonical requests only for the selected resource package, preserving complete-generation isolation and cache invalidation.

The [software update contract](../../../../docs/subsystems/software-update.md#7-shared-building-skill-data) defines authoritative behavior. Scheduling rules, configuration schemas and domain terminology remain unchanged.

## Verification

Focused offline tests cover identical generation output, resource content hashing, both backend consumers without any frontend files, desktop and Android package contents, missing or empty catalog rejection, existing HTTP filenames, selected legacy resource-package priority and cache invalidation. Frontend production compilation checks the shared import.
