---
title: Start Selected Instances During Detection
status: implemented
category: feature
date: 2026-09-29
---

# Start Selected Instances During Detection

[English](2026-09-29-instance-detection-start.md) | [中文](2026-09-29-instance-detection-start.zh.md)

## Contract

- **[INV-DEV-13] Detection Startup Target**: Detection starts only a selected target whose read-only check reports a stopped instance and whose preset provides startup control; ambiguous targets and other failures never trigger startup.
- MuMu Pro start and stop query the selected index and verify the saved VM path fingerprint before sending a single-index `open` or `close` command. One deadline covers validation and command execution. Failed or uncertain commands are not replayed.
- Multiple candidates remain a selection list. Selecting a candidate or detecting a uniquely discovered instance allows that immediate startup check. The read-only connection test performs no lifecycle action.
- AVD, redroid and Genymotion startup requests carry the current selected identity as immediate confirmation; that permission is not saved for later scheduled runs. Presets without startup control and manual serial profiles keep manual startup guidance.

MuMu Pro detection explicitly prepares the manager application when its official port is absent; that action sends no VM launch command. Read-only tests never prepare the manager. Selected session startup shares its Recovery Budget with manager preparation.

Normal VM shutdown only closes the selected instance and keeps the manager running. Manager preparation opens the application only when `mumutool port` reports `invalidPort`; available manager calls never trigger a restart. Cold startup waits for the inventory and the selected ADB listener. A manager-reported instance error requires the user to handle that instance in the manager.

## Verification

Offline coverage checks MuMu Pro target validation, command outcomes and session startup, and each settings preset's startup request, detection behavior, failure isolation and read-only action. The permanent interface belongs in the [device contract](../../../../docs/subsystems/device-control.md).
