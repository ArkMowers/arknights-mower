---
title: Shared MuMu Parsing and Settings State
status: implemented
category: simplification
date: 2026-09-29
---

# Shared MuMu Parsing and Settings State

[中文](2026-09-29-review-boundaries.zh.md)

The ADB endpoint query and IPC preflight duplicate three JSON shape branches with different identity rules. A shared parser validates explicit identity, optional saved name, and endpoint format. Discovery reuses the same JSON shape normalization.

Settings derives the idle action from its three persisted flags through one writable computed value. RecoveryPolicy already defines poll_interval, so binding accesses that field directly.

The performance feedback globals have consumers in the performance policy and solver code. io_timeout invokes the active deadline callback. The synchronous configuration traversal collects Vue watchEffect dependencies. These mechanisms remain active.

The [repair contract](../bug-fix/2026-09-29-review-command-isolation.md) defines behavior and verification. Existing glossary definitions remain unchanged.
