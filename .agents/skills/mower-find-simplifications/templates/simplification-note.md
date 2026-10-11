---
format: decision
title: ${TITLE}
status: proposed
category: simplification
date: ${DATE}
---

# ${TITLE}

Use only after [record ownership](../../../notes/README.md#record-ownership) establishes a durable independent decision. Replace prompts with facts; use the [destination body](../../../notes/README.md#body-by-lifecycle) when implementing or rejecting this proposal.

## Problem

Describe the concrete maintenance or user problem and evidence that the abstraction causes it. Identify actual production callers and public or persisted uses; a single caller alone does not establish redundancy. Link to source and the governing behavior contract.

## Proposal

State what is removed or replaced, why the simpler owner is sufficient and how callers use it. Explain the observable behavior preserved or intentionally removed, and any responsibility that moves. Add technical detail only when needed to understand state commitment, failure ownership, compatibility or cleanup.

## Alternatives considered

For each genuine alternative, state its benefit and why it loses under the problem's constraints. Retaining the current code or using a maintained dependency belongs here only when evaluated. Explain why this removal would be undesirable to reverse under present conditions.

## Acceptance criteria

Describe the inputs and observable outcomes through actual production entry points that establish preserved behavior, including relevant failure cases. For intentional removal, account for remaining callers, configuration, persisted data and shipped files where affected. Identify focused offline tests and any device outcomes still requiring observation; distinguish planned checks from evidence already obtained.

## Risks

State accepted costs, lost extension or compatibility options, uncertain callers and failure or recovery concerns. Explain mitigation and evidence needed where known. Relevant Mower cases include persisted selections, Actual Occupancy versus Projected Occupancy, uncertain device input, compensation and released resources; include only cases affected by this simplification.
