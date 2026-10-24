---
title: MuMu 12 Runtime Layout Manager Resolution
status: implemented
category: bug-fix
date: 2026-10-07
---

# MuMu 12 Runtime Layout Manager Resolution

## Contract

MuMu 12 discovery and IPC share manager locations and installation root resolution. Root-level `shell` and `nx_main` directories belong to their parent; `temp/<pair>` and `.backup/<pair>` belong to their grandparent, with runtime pairs taking precedence. Explicit manager paths retain the selected executable. Registry and process sources for one installation produce one candidate.

## Defect

Builds with managers below `temp/main` or `temp/shell` need those search locations. Duplicate root inference can retain a runtime directory in a binding, creating duplicate candidates and incorrect paths for ADB or IPC.

## Implementation

`mumu_layout.py` contains one manager location list and `installation_root()`. Discovery and IPC call that function for directories and manager parents. Runtime parent names match exactly `temp` or `.backup`. Location resolution executes no manager commands; callers retain their file checks and missing-manager behavior.

## Verification

`device_mumu_io_tests.py` covers root, uninstall executable, runtime directory, player and manager sources, deduplication and explicit manager priority. `device_mumu_capture_tests.py` covers root-level and runtime layouts, backup directory pairs and rejection of lookalike runtime names. All cases use temporary files and mocked manager output.
