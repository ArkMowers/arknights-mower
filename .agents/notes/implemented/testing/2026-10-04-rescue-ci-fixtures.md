---
title: Rescue CI Fixture Contracts
status: implemented
category: testing
date: 2026-10-04
---

# Rescue CI Fixture Contracts

## Contract

Existing [INV-SCHED-09] requires completed rescue staffing before exit and permits early handoff when normal replacements cover unfinished groups. Recovery targets use measured mood. Free beds serve recovery primaries before spare-bed candidates. [INV-SCHED-08] keeps unavailable training slots out of ordinary corrections.

## Simplification

Tests supply the existing episode completion flag and operator name. No production fallback or compatibility layer is added. Prediction tests exhaust the configured replacement to isolate target completion from feasible early handoff.

## Verification

Focused suites cover missing and false staffing completion, measured versus predicted mood, replacement exhaustion, completed-manager release, primary-first bed admission and spare-bed filling. Existing early-handoff tests exercise available normal replacements.

## Standards Findings

Existing invariants remain unchanged. Fixtures use real operator updates and existing scheduling paths. No glossary or runtime behavior changes.

## Spec Findings

The assertions preserve staffing completion, measured recovery and ordinary training protection. They match the current independent rescue schedule contract.
