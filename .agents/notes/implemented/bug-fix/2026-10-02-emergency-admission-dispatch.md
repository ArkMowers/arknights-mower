---
title: Intelligent Rescue Admission and Dispatch
status: implemented
category: bug-fix
date: 2026-10-02
---

# Intelligent Rescue Admission and Dispatch

## Contract

[INV-SCHED-03] prevents completed personal-limit residents from returning to vacant fixed dormitory positions through ordinary correction, backup transitions or rescue handoff. Already present fixed residents remain in place. Generated and cached handoff plans share the correction admission rule.

Staffing scans reserve a 45-second scan budget and a one-second return margin before the earliest strict release operation start. The start includes the existing measured dormitory operation allowance. Completed facility comparisons persist through the existing staffing plan; unfinished facility comparisons survive the yield. The existing rescue check advances to the next observation. Handoff also yields when its operation allowance reaches a strict release start. Failed handoff reopens emergency beds, retaining saved deadlines only when actual bed and occupant identity match.

[INV-SCHED-04] retains started trade order compensation across eligibility filtering and run-order room changes. Required trade operators already in the target facility remain eligible for retries. Snapshot names reserve original temporary workers during other planning. Restoration waits when an original worker occupies another working facility; immediate restoration becomes the existing queued compensation rather than taking that worker. Explicit vacant slots survive retries and compensation.

## Simplification

Correction, backup transitions and handoff use one completed-resident admission function. Dispatch reuses strict-release timing, staffing plans, the existing rescue check and specialized compensation tasks. The change adds no setting or compatibility path. The [base scheduling contract](../../../../docs/subsystems/base-scheduler.md) owns interface guarantees.

## Verification

Offline tests retain real correction, native feasibility, backup task generation, selection, strict-release planning and staffing scheduling. Device, clock and storage boundaries are isolated. Cases cover generated and cached manager returns, existing managers, drone failure, immediate and queued compensation, foreign-facility occupation, reservations, interrupted scans, partial progress and failed handoff.

## Review

Standards Findings: completed-resident admission shares callers; compensation survives errors; scan and handoff allowances respect strict release operation windows.

Spec Findings: normal fixed residents remain stable; completed recovery does not repeat; started specialized responsibilities remain pending without stealing workers from other facilities. Validation results accompany the immutable review snapshot.

Thirteen focused offline suites pass 402 tests and 4 subtests. Scoped Ruff, formatting, whitespace and all governance gates pass. The isolated-context review uses this committed snapshot. No live-device integration tests run.
