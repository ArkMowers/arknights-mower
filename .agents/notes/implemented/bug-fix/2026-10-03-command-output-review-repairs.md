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

`run_command` uses independently opened readers for named temporary output files. The [stream ownership decision](../simplification/2026-10-03-device-output-reader.md) defines their shared creation and cleanup. Windows reader handles share delete access with the temporary writer. Only the owned command is terminated; descendants and shared services retain their existing lifecycles.

BlueStacks Air, I/O-budget and session-caller tests mock the execution function at its consuming module. The budget fixture returns a `CompletedProcess`; incompatible Shared ADB Guard tests reject capture and MaaTouch startup before process creation.

## Verification

An offline fixture writes initial stdout/stderr, retains both in a descendant and synchronizes further writes between the reader's seek and read. Assertions cover successful completion, checked failure, timeout partial output, separate and merged channels, owned-process cleanup and temporary-file deletion after descendant exit. Focused caller tests cover the updated execution seams.

Targeted offline verification passes 529 tests and 163 subtests. All six inherited-write scenarios fail before the repair and pass after it. Ruff lint and format checks, repository governance and diff whitespace checks pass.

## Standards Findings

PASS: Independent readers preserve inherited writer positions. The existing cleanup stack closes both handles on success, launch failure, reader-open failure and command failure. Caller fixtures replace the execution functions they consume and reject unexpected process creation.

## Spec Findings

PASS: Success results, checked-exit errors and timeout partial output retain existing bytes during descendant writes in separate and merged channels. Command deadlines, output limits, text decoding, Shared ADB Guard and Instance Binding retain their contracts.
