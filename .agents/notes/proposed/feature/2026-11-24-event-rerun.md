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

Run selected ordinary stages through local operation and the optional EX-8 raid through MAA Copilot with automatic formation. Save each attempt by instance, activity opening and stage. Reserve four minutes before starting a stage. Apply the scheduling deadline again after that stage settles.

## Alternatives considered

MAA's whole-activity Fight entry always starts at the first stage. The weekly plan selects repeatable material stages and would omit some rerun battles. An independent queue can preserve the full selection and resume between stages.

## Acceptance criteria

Check selection, authenticated reads, durable stage admission, single-battle completion and the four-minute boundary offline. Verify live navigation and raid handover on a device.

## Risks

A battle that exceeds its estimate can delay the next task. A process interruption can leave an attempt without a confirmed result for the user to review.
