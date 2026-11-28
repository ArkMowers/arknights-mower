---
title: LD Screenshot Enhancement
status: implemented
category: feature
date: 2026-09-29
---

# LD Screenshot Enhancement

[中文](2026-09-29-ld-capture.zh.md)

`ld_native` selects LD screenshot enhancement for Windows LDPlayer 9 and 14. The installed `ldopengl64.dll` supplies capture only; scrcpy and MaaTouch remain independent touch choices.

**[INV-DEV-05] Capture Preset Compatibility**: Configuration updates reject incompatible vendor capture presets; capture entry points also verify the host, and UI preset changes clear incompatible capture and coupled touch selections in the draft.

**[INV-DEV-06] LD Capture Binding**: LD screenshot enhancement verifies the selected ADB endpoint against the selected instance and accepts frames only while its process identity and 1920×1080 dimensions remain unchanged.

An owned process isolates the DLL, reuses its capture object, converts bottom-up BGR to RGB, and releases the object on normal exit. The caller bounds requests and terminates only its worker on cleanup. Native failure remains visible through the existing screenshot failure boundary; it never selects another instance or capture backend.

The UI defers backend persistence while a different preset is unconfirmed. Legacy configurations remain readable; incompatible selections require repair before save or capture. Shared ADB Guard remains unchanged.

The Windows MuMu preset is labeled **MuMu 12** and keeps the identifier `windows.mumu12`.

Interface evidence: [MAA LD capture](https://github.com/MaaAssistantArknights/MaaAssistantArknights/blob/dev-v2/src/MaaCore/Controller/LDExtras.cpp) and [vendor interface declarations](https://github.com/MaaXYZ/EmulatorExtras/blob/54d3a3ad448f0541df3759ae91b571a6762daaf1/LD/dnopengl/dnopengl.h).

Offline tests cover configuration rejection, UI selection, RGB orientation, instance identity, deadlines and cleanup. Live emulator verification is outside these tests.

## Targeted Live Verification

User-authorized read-only capture on Windows LDPlayer 9.5.30.1 Arknights edition succeeds for instance 1000 at 1920×1080. A six-frame sample measures a 3.20 s first call and a 131 ms median across five subsequent calls; three ADB captures have a 454 ms median. The captured static screen matches the ADB image, and closing the session leaves no owned worker process. This sample verifies the installed DLL and capture path for that version.

The same user-authorized check succeeds on Windows LDPlayer 14.0.29.0, instance 0, using the existing `windows.ldplayer14` capture path without production code changes. Six enhanced captures yield 1920×1080 RGB frames: the first call takes 2.97 s, and the five subsequent calls have a 114 ms median. Three ADB captures have a 244 ms median. The saved static game-screen images are pixel-identical. Session cleanup takes 84 ms and leaves no owned worker process. The check only reads frames; it sends no game input and changes no persistent configuration. These timings describe the measured samples.

## Standards Findings

Pass: native calls remain in owned workers, identity observations remain transient, manager calls share the capture deadline, and cleanup targets only owned resources. Shared ADB Guard and paired MuMu input remain enforced. The approved Capture Frame glossary update includes LD screenshot enhancement.

## Spec Findings

Pass: LD screenshot enhancement connects to preflight and runtime; incompatible UI and API selections are rejected. Preset changes clear incompatible drafts, including mixed-product discovery. Backend edits for an unconfirmed preset remain in the draft. Offline tests cover these boundaries; the targeted live checks above verify capture and cleanup on the installed LDPlayer 9 Arknights edition and LDPlayer 14.
