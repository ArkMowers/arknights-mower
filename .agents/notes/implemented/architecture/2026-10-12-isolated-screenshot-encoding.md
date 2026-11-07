---
format: decision
authors: [Codex]
title: Isolated Screenshot Encoding
status: implemented
category: architecture
date: 2026-10-12
---

# Isolated Screenshot Encoding

[中文](2026-10-12-isolated-screenshot-encoding.zh.md)

## Problem

Screenshot JPEG encoding previously shared the main instance with device scheduling. A native encoder exit or hang could interrupt automation, while an older history frame must not block newer preview frames. The existing shared-frame behavior remains binding.

## Decision

The existing [shared screenshot encoding](../../implemented/simplification/2026-09-29-shared-screenshot-encoding.md) decision owns per-snapshot reuse. This decision owns the separate process boundary for native JPEG failure. A Python thread cannot contain an access violation or terminate a hung native encoder.

The implementation uses the existing Pillow dependency to remove the JPEG color-conversion allocation. The public `img2bytes` ndarray wrapper preserves attachment compatibility and permits general image dimensions. The [encoding owner](../../../../arknights_mower/utils/screenshot_encoding.py) reuses one primary child for history and immediately available preview work. A busy primary starts at most one auxiliary preview child; thirty idle seconds reclaim that child even when no new frames arrive. The primary remains reusable. A single serial child without this auxiliary would block newer previews behind a hung history frame. Fixed shared mappings avoid image-sized pipe writes and an additional frame backlog. On Windows 10 and later, an encoding slot atomically creates its launcher inside a private kill-on-close Job before resuming it. Kernel ownership covers launcher descendants and parent death during a native call holding the GIL. Delete-on-last-handle mapping files also disappear after abrupt termination. The portable control-channel watcher starts before native Pillow imports, but requires the GIL. Cleanup retains an unreaped Job instead of accumulating replacements.

The [JPEG process boundary](../../../../docs/subsystems/device-control.md#jpeg-process-isolation) owns the complete interface. Existing archive drain, encoded recent cache and shared frame encoding rules remain binding. Capture Frame, Instance Binding and Actual Occupancy keep their existing meanings; no glossary change is needed.

## Alternatives considered

In-process OpenCV 4.11 encoding is faster in the measured environment but leaves native failures in the main instance. Keeping both encoding children after first use preserves preview independence at a higher idle cost. Pebble can manage process task timeouts, but shared frame transport, bounded admission, Windows kernel ownership and frozen entry points still need adaptation and verification. The selected implementation retains Pillow and existing process ownership while reclaiming the auxiliary.

## Consequences

Sequential history and preview work need one encoding process. Contention can still use two, and restarting a reclaimed auxiliary pays process startup again. Shared mappings and codec allocations retain their bounds. Other native recognition calls and direct image attachment encoding remain in the main instance. Frozen installation and long device runs remain outside the current measurements.

## Verification Scope

The initial isolated encoding implementation passed 125 tests and 33 subtests in the focused screenshot encoding, pipeline, integration and storage suites in 23.92 seconds in an isolated environment with OpenCV 4.11.0, NumPy 1.26.4 and Pillow 10.3.0. Real test children exit, hang, emit incomplete or trickled responses, return invalid JPEG data, reject allocation and fail startup. Assertions cover next-frame recovery, one attempt per failed snapshot, bounded capacity, source-array release, independent preview and real Device/Recognizer progress. Windows tests call `ctypes.PyDLL` with infinite native sleep to hold the GIL during encoding and startup, then kill a test parent outside a Job; the actual worker, launcher descendants and shared file disappear. Native timeout also terminates the complete JPEG Job. A launcher that exits before its hung descendants cannot admit a replacement until retained, confirmed Job-member handles signal complete termination. Simulated cleanup refusal retains ownership without launching replacements, and another process cannot close the original owner's children.

Codec tests cover RGB colors, grayscale dimensions, read-only and strided input, general image dimensions and the real email attachment's ndarray compatibility. A focused integration test proves optional diagnostic snapshot `MemoryError` preserves the successful RGB and grayscale observation. Affected Python lint and format checks and structural governance pass. Initial independent review confirmed the process boundary, deadline, ownership and cleanup behavior. No test invokes a live device or exhausts host memory. The source launcher executes the real early worker dispatch and frozen command routing is checked; an installed frozen executable and live-device endurance are outside this evidence.

The earlier worker-wait change was additionally verified by the affected encoding suite: 21 tests and 13 subtests passed in 18.94 seconds. Its concurrent statistics regression uses a real Windows child and a preemption barrier around an unlocked handle wait. Restoring the previous wait method only inside an independent diagnostic process reproduces `WinError 6` with that same test; the current wait uses locked polling and budgeted short sleeps. All diagnostic children are reaped.

The current [encoding tests](../../../../arknights_mower/tests/screenshot_encoding_tests.py) also cover one-child reuse, autonomous auxiliary reclamation, restart after reclamation and retaining an active auxiliary past its idle threshold. The [pipeline](../../../../arknights_mower/tests/screenshot_pipeline_tests.py), [integration](../../../../arknights_mower/tests/screenshot_integration_tests.py) and [storage](../../../../arknights_mower/tests/screenshot_tests.py) tests retain the shared frame and shutdown boundaries.

Following rebase and auxiliary lifecycle changes, the combined focused screenshot, process recovery, device recovery, desktop lifecycle, process control, status and scheduled-start suites pass 285 tests and 88 subtests in 61.43 seconds. Recovery status, App integration and the task state store pass 22 frontend tests. Syntax, Ruff and structural governance are checked separately. Current lifecycle memory measurements belong to the [supervision resource evidence](2026-10-12-owned-instance-supervision.md#resource-measurement).

## Performance Evidence

Offline measurements use one existing 1920×1080 game screenshot as a read-only RGB array, JPEG quality 75 and 81 warm samples per path in randomized order. Both environments use Python 3.12.10, NumPy 1.26.4, Pillow 10.3.0 and OpenCV's default 16 threads. Before auxiliary reclamation, the two dedicated slots gave these median times:

| Encoding path | OpenCV 4.9 environment | OpenCV 4.11 environment |
| --- | ---: | ---: |
| OpenCV RGB→BGR and JPEG | 28.0 ms | 5.1 ms |
| Pillow in the same process | 6.8 ms | 6.3 ms |
| History worker, complete warm round trip | 7.9 ms | 7.6 ms |
| Preview worker, complete warm round trip | 7.5 ms | 8.0 ms |

Five fresh-worker samples give median first-encode times of 0.325 and 0.350 seconds, including process creation and codec imports. Warm worker timings include shared-memory transfers, control IPC and complete returned JPEG bytes; all timings exclude screenshot acquisition, the existing parent snapshot copy, queue delay and file writes. Every path returns identical JPEG bytes for this image and leaves the source unchanged. These are source-environment observations on one host; frozen startup and other image content remain unmeasured.

The earlier roughly 22→7 ms comparison describes OpenCV 4.9 versus Pillow encoding, not the complete IPC path or a speed benefit over OpenCV 4.11. The dedicated workers remain for local native-failure cleanup and independent preview progress. Their process memory, transfers and startup cost buy that failure boundary; they are not a performance optimization.
