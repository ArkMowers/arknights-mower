---
format: decision
title: Building Skills and Groups
status: implemented
category: feature
date: 2026-10-13
---

# Building Skills and Groups

[English](2026-10-13-base-skill-groups.md) | [中文](2026-10-13-base-skill-groups.zh.md)

## Problem

The skill catalog previously had no group browsing. Curated groups include cross-facility references, alternatives and accessories; the page must preserve those roles without treating ownership as operational readiness.

## Decision

Pre-flight simplification identifies one group-page consumer of the edit, import, export and storage helpers. Read-only browsing removes those helpers, the editor and import dialogs, and the legacy member-ID mapping. Twenty curated presets retain separate core, alternative and accessory roles with group notes and per-member conditions. The first preset lists the four supported run-order operators, with Proviso and Tequila first. The collection, group objects, role arrays and condition maps are frozen. Existing browser-stored definitions remain untouched and do not affect displayed presets.

The existing skill page contains skill and group tabs sharing the skill catalog and local ownership snapshot. Searches support Chinese and pinyin; group filters expose only categories present in the presets. All matching combinations appear in one vertical list without selecting a combination. Compact member buttons use 32-pixel portraits. Empty role sections are omitted. Core, alternative and accessory sections retain their authored order; conditions remain separate from operator names so portrait resources and skill links use catalog names. Search includes accessory names and condition text. Known missing members have dimmed avatars; missing roster data stays unknown. Only hovering member skill labels opens descriptions; the labels perform no navigation. The [estimation extension](2026-10-13-base-group-estimates.md) owns ephemeral member selection and efficiency rules. Ownership alone does not assert operational readiness because presets include cross-facility references and single-operator entries.

The skill table retains its seven desktop columns and wraps into compact rows on narrow screens. Operator portraits use base-relative resource URLs with text fallbacks only on image failure; skill icons remain small circular images inside colored tags. Special-effect traversal collects every branch once and stops cycles; its dialog fits the viewport. No glossary change is required.

The [subsystem specification](../../../../docs/subsystems/base-scheduler.md) owns the public boundary. The [preset data](../../../../ui/src/data/baseGroups.js) owns immutable definitions; [group utilities](../../../../ui/src/utils/baseGroups.js) own filtering and member annotation. The [group component](../../../../ui/src/components/BaseGroups.vue) owns browsing and member selection.

## Verification

[Group utility tests](../../../../ui/src/utils/baseGroups.test.js) verify preset order and categories, member resolution, per-member conditions, immutability, all three roles, alternative priority, accessory searches and unknown ownership. [Component tests](../../../../ui/src/components/BaseGroups.test.js) verify that old custom data is ignored, storage remains untouched and every filtered result remains visible. [Page tests](../../../../ui/src/pages/BasementSkill.test.js) retain shared-snapshot and explicit-sync guarantees.

## Alternatives considered

Retaining editing, import and browser storage would expand the reference page and require definition migration, so bundled immutable data owns the groups. Reusing the skill page avoids introducing another account service.

## Consequences

Focused frontend tests, changed-file ESLint and the production build pass. Browser verification confirms twenty presets, loaded member portraits, all combinations in a scrollable page, compact role rows, no modification controls, filtering and skill-label-only hover. The existing CommonJS and chunk-size build warnings remain.
