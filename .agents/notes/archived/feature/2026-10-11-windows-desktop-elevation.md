---
title: Windows Desktop Elevation
status: archived
category: feature
date: 2026-10-11
---

# Windows Desktop Elevation

[中文](2026-10-11-windows-desktop-elevation.zh.md)

This historical decision is superseded by [Windows desktop launcher permissions](../../implemented/feature/2026-10-16-windows-desktop-launcher-permissions.md): mandatory elevation prevents users without administrator credentials from starting Mower. The rationale and verification below describe the earlier implementation.

The simplification audit finds two Windows PyInstaller executables and an existing direct process launch in `Api.start`. Native executable manifests provide the required startup consent without another relaunch helper, per-instance shell elevation or persisted permission setting. No existing decision covers this elevation policy. The domain concepts retain their existing meanings and need no glossary changes.

[INV-UPD-08] requires administrator elevation before either packaged desktop application starts. An elevated manager launches each instance through the existing `Popen` path, which inherits its process token. UAC cancellation prevents startup; elevation does not bypass file ACLs or repair missing or damaged resources. Source deployments retain the permissions of their Python process.

An older updater cannot create the new administrator-required process from a non-elevated token. The first upgrade therefore starts from an elevated old application or a manually installed full package; this migration limit is explicit in the contract and packaging procedure.

The [software update contract](../../../../docs/subsystems/software-update.md#14-windows-desktop-elevation) owns the launch behavior. Offline tests inspect both executable declarations and manager launch arguments. The Windows release workflow inspects the built manifests before packaging; interactive UAC and native token inheritance require Windows validation.

Standards and requirements review confirms both Windows entry points share the native elevation policy and the existing manager launch retains arguments, working directory and managed-instance environment. Focused release-workflow and manager suites pass. The manifest gate accepts administrator manifests and rejects missing manifests, absent execution levels and either executable requesting ordinary permissions. Structural governance passes; native build and interactive Windows evidence remain unavailable on the macOS development host.
