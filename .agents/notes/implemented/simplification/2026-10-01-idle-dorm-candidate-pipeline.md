---
title: Shared Idle Dormitory Candidate Pipeline
status: implemented
category: simplification
date: 2026-10-01
---

# Shared Idle Dormitory Candidate Pipeline

[English](2026-10-01-idle-dorm-candidate-pipeline.md) | [中文](2026-10-01-idle-dorm-candidate-pipeline.zh.md)

## Contract

Idle Dormitory Recovery task creation and operator selection consume one candidate snapshot and one reservation policy. The snapshot distinguishes valid readings below recovery limits, verified full readings, and unknown readings. Unknown readings use the game's ascending-mood selection before a full resident is retained.

The simplification audit identifies duplicated reservation collection in `try_add_release_dorm` and `get_dorm_candidates`, default-full classification for unknown readings, and a separate resident fallback branch. `dorm_task_reservations` serves both callers, `DormCandidates` owns the three states, and the existing selection/readback cycle owns confirmation and search throttling. The unified dormitory policy has no legacy mode branch or additional configuration.

Vacant beds receive eligible recovery candidates before verified full occupants. Rescue admits primary operators first and fills only remaining unreserved vacancies. Formal unfinished recovery residents retain their beds; temporary fillers can yield them. Crafting uses an independent task and shares material readiness checks between enqueueing and stationing. Successful restoration and normal planning share one recovery entry point; single and merged releases share one dispatch-time deadline check. Each resident's measured completion time drives release, while primary admission retains its bed-priority rules.
