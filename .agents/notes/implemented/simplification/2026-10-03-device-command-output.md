---
title: Share Device Command Output Ownership
status: implemented
category: simplification
date: 2026-10-03
---

# Share Device Command Output Ownership

[English](2026-10-03-device-command-output.md) | [中文](2026-10-03-device-command-output.zh.md)

## Contract

Device commands share the temporary-file execution mechanism in [manager_io.py](../../../../arknights_mower/utils/device/manager_io.py). [INV-DEV-20] defines finite command waiting and output ownership in the [Device Control contract](../../../../docs/subsystems/device-control.md).

## Caller Evidence

Vendor discovery and instance readiness already used `run_manager_command`; preflight, ADB version checks, resolution queries and MuMu input initialization ran through separate pipe-based calls before this decision. Reusing the manager mechanism removed that execution-policy split. `run_command` preserves separate stdout/stderr, merged output, binary output, text decoding and optional return-code checking. The manager adapter retains its existing merged binary output and 1 MiB limit. General device commands accept at most 32 MiB across captured streams, including custom Capture Frame bytes.

## Verification

Synthetic executable fixtures retain inherited output handles independently of the command. Focused tests check command completion, timeout, output limits and owned-process cleanup without devices or network services.

## Standards Findings

PASS: One shared execution mechanism retains existing manager imports, explicit output policy, finite memory and owned cleanup. Governance links and existing domain terms remain valid.

## Spec Findings

PASS: Startup callers share the file-based mechanism while retaining their command arguments, output parsing and failure classification. Offline fixtures verify inherited-handle behavior and output compatibility.
