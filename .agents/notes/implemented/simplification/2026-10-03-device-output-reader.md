---
title: Share Captured Output Stream Ownership
status: implemented
category: simplification
date: 2026-10-03
---

# Share Captured Output Stream Ownership

[English](2026-10-03-device-output-reader.md) | [中文](2026-10-03-device-output-reader.zh.md)

## Contract

The [Device Control contract](../../../../docs/subsystems/device-control.md) owns [INV-DEV-20]. Each captured channel owns one temporary writer and one independently opened reader. Output collection changes only the reader's position. Both handles close through the command's existing `ExitStack`.

## Caller Evidence

`run_command` creates stdout and stderr captures separately. Both call the same stream-pair helper, which encapsulates temporary-file creation, independent reader creation and Windows delete sharing. `run_manager_command` retains its merged-output adapter and limit. This avoids duplicating the platform-specific handle policy across the channels.

## Verification

The [review repair decision](../bug-fix/2026-10-03-command-output-review-repairs.md) records the inherited-writer regression and targeted verification. No new thread, retry, configuration field or external dependency is introduced.
