---
format: decision
title: On-demand shared OCR independent of the launcher
status: implemented
category: architecture
date: 2026-10-16
---

# On-demand shared OCR independent of the launcher

## Problem

Before this change, each Mower instance constructed its own OCR sessions. Eighteen instances can retain eighteen model copies even when only a few need recognition. The prior detector-input limit reduced per-call allocation without sharing models. Users want the multi-instance manager to remain a launcher that can exit independently.

## Decision

Instances use an independent on-demand OCR service, leaving the manager as a launcher. The [recognition subsystem description](../../../../docs/subsystems/recognition.md#independent-shared-ocr) owns admission, request budgets, model recycling and failure behavior. A lightweight coordinator owns one model worker; account, device and task state stays in each caller. Waiting clients send headers and upload their images only after admission. A shared model with bounded inference parallelism avoids loading one model per instance.

The service exits after idle time and replaces its worker between completed requests to release native allocations even under sustained load. Service and model locks preserve exclusive ownership across failures. The endpoint remains in the writable data root outside update cache storage. [Software-update shutdown](../../../../docs/subsystems/software-update.md#shared-ocr-update-lifecycle) waits for the service and its model lock; updates do not eagerly restart it. A sent request is not replayed and failure does not construct per-instance fallback engines.

## Alternatives considered

Hosting OCR in the manager would stop or duplicate recognition after closing the launcher. Giving each instance a child process preserves repeated model allocation. A many-worker pool improves peak throughput but multiplies model memory; first validate one shared worker with bounded admission before increasing that count. A thread-only service cannot isolate a native crash or enforce a native execution deadline externally.

## Verification

The [shared OCR tests](../../../../arknights_mower/tests/shared_ocr_tests.py) passed 19 focused offline cases across a full service run and a separate endpoint-scope check, including installation and network-namespace separation, eighteen concurrent clients sharing one model, startup races, image admission, option isolation, raw transport bounds, failure and timeout cleanup, idle exit, worker replacement with pending requests, update shutdown and a source service surviving its first client. The frozen entry is executed with a stub service and rejects GUI imports. The [furniture regression](../../../../arknights_mower/tests/furniture_ocr_tests.py) passed 36 cases across local and shared execution. Related runtime registration, updater, manager and memory checks passed 59 cases with one platform-specific skip; recognition regressions passed 169, and desktop/preparation lifecycle checks passed 21. These groups overlap and are not an additive unique-test count.

A local macOS comparison used three independent clients, identical three furniture screenshots and two ONNX intra-operation threads per session in both modes. Once all clients had finished and remained alive, summed RSS was 1252.8 MiB with private models and 822.0 MiB with sharing, including the shared coordinator and worker. All furniture names and counts agreed. The sampled PIDs are the three clients and, in shared mode, the coordinator and model worker; the common measurement harness and multiprocessing resource tracker are excluded. This is a held-state RSS measurement, not a peak, an eighteen-emulator measurement or a long-running stability result.

## Consequences

Serial inference increases wait time under simultaneous load; finite admission and request budgets can reject work. Cold startup returns after idle exit or worker recycling. Sharing is limited to one installation and data root in one network namespace, and does not reduce emulator or other instance-state memory. Loopback authentication is not a cross-host service. After abrupt coordinator death, the portable EOF watcher requires the GIL; a surviving native worker's model lock prevents overlapping replacements until it exits. Packaged Windows/macOS execution and long device runs remain unverified.

Account, device and scheduling concepts retain their meanings and ownership. The change relocates stateless recognition execution and its process lifetime, so no glossary changes are needed.
