---
title: Isolated device test fixtures
status: implemented
category: testing
date: 2026-09-30
---

# Isolated device test fixtures

## Contract

Offline tests declare the host required by their device preset, provide the current interface signatures, and release every verified MAA connection they acquire. Platform rejection, target identity, startup deadlines, and resource compensation retain their production behavior.

[INV-DEV-05] requires capture compatibility checks before native capture. Windows MuMu tests select a Windows host at the capture boundary; separate compatibility tests retain unsupported-host rejection. [INV-DEV-03] requires preparation and preflight to share the startup budget. Preparation fixtures provide an explicit physical Device Profile, ADB resolver, and matching one-run authorization before asserting cleanup.

## Simplification and boundaries

The fixture repairs reuse existing mock boundaries and invariants. No production fallback or new fixture framework is introduced. The desktop launcher test supplies the worker/channel tuple and verifies ownership registration without starting a process. The pure launcher test runs on every host; inherited POSIX pipe tests retain their platform restriction. The HTTP worker fixture accepts the current keyword-only preparation argument. Unsupported hosts and missing adapters retain distinct structured errors.

MAA connection tests register `VerifiedAsst.stop` as cleanup immediately after successful initialization. This preserves the resource updater's real busy guard while preventing a retained callback from leaking active state into later tests. Unclassified startup faults still request application shutdown before coordinated cleanup; classified preflight rejection releases resources without exiting the application.

## Verification

Focused tests reproduce the failing CI cases, exercise Linux capture boundaries, and run MAA initialization before resource updates in one process. Existing resource compensation and unsupported-platform assertions remain active. Ruff, the governance gates, and their focused tests verify repository contracts.
