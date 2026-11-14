---
title: Paused Trade Order Admission
status: implemented
category: bug-fix
date: 2026-10-10
---

# Paused Trade Order Admission

[中文](2026-10-10-paused-trade-order-admission.zh.md)

## Ownership and Rationale

The [roster compensation decision](2026-10-08-run-order-roster-compensation.md) owns observed original staffing and restoration after temporary insertion. This decision owns countdown admission before insertion: a valid paused order page must remain distinguishable from failed navigation or unreadable timing. It remains useful independently of restoration failures. The [scheduler contract](../../../../docs/subsystems/base-scheduler.md#252-trade-order-countdown-admission) owns the complete operational rules.

The previous `get_run_order_time` call requires an acceleration button to confirm page entry. Order acquisition pause can remove that button while leaving a valid order page, causing repeated navigation errors. Accepting the page marker addresses entry; it does not by itself establish a countdown. The previous `double_read_time` fallback supplies the current time on recognition failure, which cannot distinguish a paused acquisition from a genuinely due order. A confirmed pause therefore has an explicit empty result, while unconfirmed recognition failure retains its exception.

Recent mood timestamps can also hide a staffing vacancy from ordinary inspection. Reading actual occupants on the confirmed paused path makes the vacancy available to the existing correction planner. Returning to room details first preserves the room reader's page requirement. Reusing ordinary correction avoids a separate replacement policy or bypass of scheduling priority.

The existing occupancy-change callback refreshes appointments that already exist. A paused room has no order appointment to refresh. Successful non-order staffing therefore requests a countdown refresh when neither appointment exists, completing the correction-to-order path without changing insertion or restoration.

This repair reuses [INV-SCHED-04] for admission with valid staffing and preserved compensation, [INV-SCHED-05] for ordinary correction through the existing projection boundary, and [INV-SCHED-27] for product-dependent eligibility. Concept-impact review under [INV-06] preserves Scheduling Plan, Actual and Projected Occupancy, Operator Mood and Dynamic Shift Transition meanings and relationships. No glossary edit, new invariant identifier or persistent pause setting is introduced.

## Verification

The offline [run-order product suite](../../../../arknights_mower/tests/run_order_product_tests.py) passes 28 tests. It exercises real countdown admission and scheduler entry with simulated page and room I/O. Cases cover paused pages without acceleration buttons, valid and zero countdowns, unconfirmed failures, failed room reads, recent stale occupancy, cleared-cache startup, and both planning and refresh entry paths through correction confirmation and resumed order creation. The page simulation rejects mood reads while order details remain open.

At the reviewed implementation, twelve related offline suites pass 531 tests and 85 subtests. They include [restoration](../../../../arknights_mower/tests/run_order_restoration_tests.py), [maintenance](../../../../arknights_mower/tests/maintenance_run_order_tests.py), [planning wakeup](../../../../arknights_mower/tests/run_order_planning_wakeup_tests.py) and [priority admission](../../../../arknights_mower/tests/priority_admission_tests.py). The 28-test product suite passes again after the assertion-format repair. Ruff lint, formatting and whitespace checks pass. These checks do not validate OCR against a real device's paused-page capture.

Scoped governance checks against baseline `7974d9d1bae2f8610ecda0a6ecce560c0a4a0d70` pass triplet, relative-link and terminology validation, with two existing warnings for archived test references.

## Review

Standards review preserves ordinary correction, compensation and product eligibility, and places interface rules in the subsystem contract. Requirement review confirms that paused acquisition does not create an immediate order or lose room eligibility, while verified staffing permits countdown observation again. The test-format failure is repaired without changing runtime behavior. The independent countdown decision has no remaining code or requirement finding.
