---
title: Preserve Command Output During Inherited Writes
status: implemented
category: bug-fix
date: 2026-10-03
---

# Preserve Command Output During Inherited Writes

[English](2026-10-03-command-output-review-repairs.md) | [中文](2026-10-03-command-output-review-repairs.zh.md)

## Contract

[INV-DEV-20] preserves captured output while a descendant retains and writes its inherited handles. Collection leaves the writer's file position unchanged, preserves existing bytes and returns within the command's existing deadline and cleanup allowance. [Device Control](../../../../docs/subsystems/device-control.md) owns the interface contract.

## Implementation

`run_command` uses independently opened readers for named temporary output files. `_capture_stream` owns their creation as one stream pair, so both channels share the temporary-file, independent-reader and Windows delete-sharing policy instead of duplicating it. Windows reader handles share delete access with the temporary writer. Only the owned command is terminated; descendants and shared services retain their existing lifecycles. No new thread, retry, configuration field or external dependency is introduced.

BlueStacks Air, I/O-budget and session-caller tests mock the execution function at its consuming module. The budget fixture returns a `CompletedProcess`; incompatible Shared ADB Guard tests reject capture and MaaTouch startup before process creation.

The review round tightens the shared contract. An over-budget capture reports `CommandOutputLimit`, which is both a `ValueError` and a `subprocess.SubprocessError`, so the session classifies it as a device verdict instead of an application fault. `universal_newlines` selects text output exactly like `text`, `stdin=PIPE` receives immediate EOF like the `communicate()` close with no input to write, and `input` is rejected before process creation. The inherited-handle fixture keeps its command deadline above the synthetic command's startup so coverage does not depend on machine load.

The last review round closes the remaining items. A manager budget overrun keeps the shared exception type and states the repair step its caller needs. `run_manager_command` accepts the part of the command call shape it already satisfies and rejects every other option instead of dropping it. Timeout partial output follows the caller's binary/text selection; a fragment that cannot be decoded stays raw, because a decoding failure of partial output must not replace the timeout the command reported. The MuMu input version query reads its answer with replacement so a stray vendor byte cannot fail a version read. `ProductionSimulator` picks each lifecycle runner from the manager class and uses an injected runner verbatim instead of comparing a function object with the default. A capture failure caused by a timed-out device command names the command rather than the selected backend.

## Verification

An offline fixture writes initial stdout/stderr, retains both in a descendant and synchronizes further writes between the reader's seek and read. Assertions cover successful completion, checked failure, timeout partial output, separate and merged channels, owned-process cleanup and temporary-file deletion after descendant exit. Focused caller tests cover the updated execution seams.

Targeted offline verification passes 529 tests and 163 subtests. All six inherited-write scenarios fail before the repair and pass after it. Ruff lint and format checks, repository governance and diff whitespace checks pass. The review round extends `device_command_tests.py` to 36 tests, covering the budget verdict classification, `stdin` EOF, rejected `input` and `universal_newlines` text output; repeated runs of the inherited-handle fixture complete without deadline flakes.

The last round raises `device_command_tests.py` to 43 tests and the targeted suites to 388 tests and 135 subtests. New coverage: the manager repair step and its rejected options, the shared command call shape, text-mode and undecodable timeout output, the lifecycle runner each manager class selects, and the wording of a timed-out capture. `device_screenshot_backend_tests.py` and `device_session_io_tests.py` carry the last two.

## Standards Findings

PASS: Independent readers preserve inherited writer positions. The existing cleanup stack closes both handles on success, launch failure, reader-open failure and command failure. Caller fixtures replace the execution functions they consume and reject unexpected process creation. The manager runner declares the options its own merged, checked contract satisfies and rejects the rest instead of dropping them, and every over-budget or timed-out command stays a device verdict.

## Spec Findings

PASS: Success results, checked-exit errors and timeout partial output retain existing bytes during descendant writes in separate and merged channels. Command deadlines, output limits, text decoding, Shared ADB Guard and Instance Binding retain their contracts. A manager budget overrun keeps its repair step, a timed-out capture names the command rather than the selected backend, and an injected lifecycle runner still replaces the default verbatim.
