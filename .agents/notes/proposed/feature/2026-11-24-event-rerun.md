---
format: decision
title: Resume a rerun activity between stages
status: proposed
category: feature
date: 2026-11-24
---

# Resume a rerun activity between stages

## Problem

Base work can interrupt a rerun before all selected stages have settled. Restarting from the first stage can spend sanity on stages already cleared.

## Proposal

Offer an opt-in stage-plan setting that runs all ordinary battles once per active SS rerun through local operation. EX-8 raids use the existing Copilot workflow. Save each attempt by instance, activity opening and stage. Reserve four minutes before starting a stage. Apply the scheduling deadline again after that stage settles.

## Alternatives considered

MAA's whole-activity Fight entry always starts at the first stage. The weekly plan selects repeatable material stages and would omit some rerun battles. Deriving the ordinary battles from the rerun chapter lets the stage plan resume between stages.

## Acceptance criteria

Check selection, authenticated reads, durable stage admission, single-battle completion and the four-minute boundary offline. Verify ordinary-stage navigation on a device.

## Risks

A battle that exceeds its estimate can delay the next task. A process interruption can leave an attempt without a confirmed result for the user to review.
