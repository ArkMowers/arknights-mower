---
title: MuMu 12 Runtime Layout Manager Resolution
status: implemented
category: bug-fix
date: 2026-10-07
---

# MuMu 12 Runtime Layout Manager Resolution

## Contract

The MuMu 12 vendor adapter resolves a manager at `shell/`, `nx_main/`, `temp/main`, `temp/shell` and the installation root. `temp/<pair>` and `.backup/<pair>` are runtime directory pairs, so the Installation Root is two levels above them. A saved Installation Profile holding a runtime directory as `installation_path`, or a registered category path holding one as `manager_path`, resolves to that same root and its `MuMuManager.exe`.

## Defect

Detection resolved manager candidates only in `shell/`, `nx_main/` and the installation root. Builds that keep `MuMuManager.exe` below `temp/main` had no candidate there, so detection reported `missing_installation` with an empty candidate list while the emulator ran. The installation root is the value that later reaches ADB resolution and temporary device recovery, so a runtime directory must never be stored as that root.

The registration path supplies only `UninstallString` in this layout: `InstallLocation` is empty and the registered root comes from the parent of the uninstall executable. Manager execution is not evidence of an installation path, so the vendor adapter keeps its read-only location list and never queries the manager to locate itself.

## Implementation

`arknights_mower/utils/device/mumu_layout.py` owns the installation layout: the root-level layouts (`shell`, `nx_main`), the runtime directory pairs (`temp`, `.backup`), the manager locations and the root above a runtime pair. The Windows discovery adapter and the MuMu IPC path resolver both read that one table, so verified capture, the running IPC adapter and endpoint resolution cannot drift apart.

## Verification

`arknights_mower/tests/device_mumu_io_tests.py` resolves the manager and the root from a registered root directory, from an uninstall executable whose parent is the root, and from a runtime directory candidate. `arknights_mower/tests/device_mumu_capture_tests.py` resolves a saved manager path without an installation directory and rejects a runtime directory as its own root. A live MuMu 12 installation whose manager sits at `temp/main/MuMuManager.exe` reports one `discovered` candidate with its running instance and current ADB endpoint.
