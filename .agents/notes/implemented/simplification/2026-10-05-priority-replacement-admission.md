---
title: Independent Dormitory Recovery
status: implemented
category: simplification
date: 2026-10-05
---

# Independent Dormitory Recovery

## Contract

[INV-SCHED-21] limits the idle-release switch to ordinary full-mood release task creation. Candidate observation, vacant-bed filling, occupied-bed recovery admission, shift projection, selection and recovery timing share one policy in both switch states. Reservations, exclusions, full-occupancy fallback, candidate eligibility and actual occupancy remain binding. Personal mood-limit release remains mandatory.

Vacancies precede takeover. Unfinished residents retain strict tier protection; completed residents can make room for eligible recovery candidates. Projection-style vacant-bed filling also admits priority recovery candidates into strictly lower-tier occupied beds, including completed residents. Measured and registered priority selection-card candidates share tier and recovery-gap ordering; estimates never change measured mood, timestamps or recovery deadlines. Ordinary estimated candidates retain selection-page confirmation.

## Simplification

`try_add_release_dorm` serves vacant-bed filling, ordinary recovery planning and complete shift projection without a switch-dependent admission branch. Ordinary release creation checks the switch in `plan_metadata`, `generate_plan_by_drom` and `add_release_dorm`. Candidate scans, departure observation, changed-position reads, recovery countdown indices and stale release cancellation share the enabled policy. Selection preserves explicit full-mood names; ordinary release tasks provide their own Free placeholders, and mandatory personal-limit completion still prevents re-entry.

## Verification

`priority_replacement_admission_tests.py` pairs both switch states for priority takeover, ordinary admission near pending work, dynamic and auto-Free recovery timing, explicit roster selection and each ordinary release creation entry. Focused candidate, mood observation, dormitory recovery, group convergence, exclusions and personal-limit suites preserve reservations, actual occupancy, compensation and measured-mood isolation without device or network I/O.
