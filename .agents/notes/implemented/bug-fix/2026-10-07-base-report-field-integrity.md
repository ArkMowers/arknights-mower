---
title: Base Report Field Integrity
status: implemented
category: bug-fix
date: 2026-10-07
---

# Base Report Field Integrity

## Contract

[INV-REC-07] preserves each independently read base report field. Unavailable fields remain unread rather than becoming zero, including when the corresponding order total or count is available. Reports with no readings or failed storage remain unclaimed and retryable. Cancellation and Device Control recovery propagate under [INV-REC-03] and [INV-DEV-18] without consuming reading attempts or replaying uncertain input.

## Reading and storage

`ReportSolver.get_number` rescales a field by `29 / 19` and pads each contour with a 10 px border before matching the ten shipped `noto_sans` templates. Template heights range from 29 to 31 px and widths from 18 to 22 px. OpenCV accepts matching when one image contains the other on both axes, including a reversed comparison when the stamp is smaller than the template; crossed dimensions raise `cv2.error`. A 4x4 grey mark in the order-count region produces a stamp with crossed dimensions and no usable digit score.

`match_digit` requires the stamp to contain its candidate template on both axes, returning `None` for incompatible geometry or an OpenCV matching error. `get_number` keeps all usable candidate scores and returns `None` for the complete field when any digit has no score. An available blank crop still reads as zero; absent anchors and empty crops remain unread. Both color masks use the same cached Capture Frame, and unavailable anchors affect only their dependent fields.

`record_report` stores every independent reading and serializes unread fields as empty cells. `parse_cell_num` treats those cells as absent. It returns failure before claiming or notifying when there are no readings or the CSV append fails. A successful append sets `_stored` before panel input; later ordinary notification or panel errors preserve the confirmed result. `read_report` ends after confirmed storage instead of repeating an append following a panel error.

`read_report` permits at most three reads per run; `ReportSolver.run` permits at most three failed runs per process and date. Failed runs leave scheduler `daily_report` unset. A new date resets the outer budget, and successful storage clears accumulated attempts. Cancellation and Device Control recovery propagate through every handler without consuming either budget or replaying uncertain input.

## Simplification evidence

Unused `remove_blank`, `crop_report_backup` and the `ReportSolver` instance of `DigitReader` are removed. `order_claim_inconsistent` and `claimed_orders_unread` have no production callers under `arknights_mower/` or `ui/src/`, and neither belongs to an existing public interface. Their tests assert a duplicate pair policy instead of exercising storage. Removing the helpers and the total/count clearing loop gives independent fields one storage rule.

`digit_stamp_floor` serves only `match_digit`. The per-template dimension check replaces its cached global minimum, keeping template compatibility in one place and preventing OpenCV's reversed comparison of smaller stamps without a second size policy.

## Verification

`arknights_mower/tests/base_report_read_tests.py` drives real report cropping against a synthetic 1920x1080 Capture Frame carrying the report anchors. It verifies all ten shipped digits, compatible candidates despite another incompatible template, complete-field failure for an unscorable digit, missing anchors, empty crops and the zero-versus-unread distinction. Temporary CSV files verify independent order fields, empty cells, failed writes followed by successful retry and preserved post-write success. Mocked device input and email verify propagation of cancellation, Device Control recovery and uncertain touch delivery at run, claim and notification boundaries, together with both retry budgets.
