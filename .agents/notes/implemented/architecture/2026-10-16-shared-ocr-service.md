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

When more than one Mower instance needs OCR, the instances use an independent on-demand OCR service and the manager remains a launcher. The [recognition subsystem description](../../../../docs/subsystems/recognition.md#independent-shared-ocr) owns admission, request budgets, model recycling, failure behavior, the service protocol and the selection rule. A lightweight coordinator owns one model worker; account, device and task state stays in each caller. One shared model with bounded inference parallelism then replaces one model per instance.

The service lifetime belongs to the installation rather than to the caller that started it. It exits after idle time and replaces its worker between completed requests, so native allocations return without relying on garbage collection. The service lock admits one coordinator; a surviving model worker's lock prevents a replacement model after coordinator death. The model worker registers independently before constructing a model, so an update still sees an orphaned model after its coordinator exits. [Software-update shutdown](../../../../docs/subsystems/software-update.md#shared-ocr-update-lifecycle) waits for the service; update recovery does not relaunch it, and a later caller that needs sharing creates a new service on demand. Endpoint metadata stays in the writable data root outside update cache storage, keeping update cache replacement separate from live service state.

Sharing is gated by the number of live consumers. `initialize_ocr` counts live `instance` registrations under the same installation and data root and keeps a single instance on an in-process engine, using the shared service only at two or more instances. `MOWER_OCR_MODE` forces `auto`, `local` or `shared`; an invalid value fails instead of falling back. The gate follows MAA's asymmetry: MaaCore shares OCR as a process-level singleton, so sharing costs no separate process, and a process that consumes OCR alone keeps the model in that process. Only a second Mower process justifies the coordinator and worker. A process without an instance registration, such as a directly started web server or the Android host, is treated as a single local consumer; a multi-instance deployment in that mode must select the shared mode explicitly.

## Alternatives considered

Hosting OCR in the manager would either stop recognition when the launcher closes or duplicate it. Giving each instance a child process preserves repeated model allocation. A many-worker pool improves peak throughput but multiplies model memory; first validate one shared worker with bounded admission before increasing that count. A thread-only service cannot isolate a native crash or enforce a native execution deadline externally. No existing background process provides the required lifetime: JPEG encode workers are job-scoped, the update worker is a one-shot task, and the Windows supervisor belongs to one instance and one platform. Reusing one would tie OCR to a job, an update or a single instance instead of the installation.

A pipe or a file-based request queue needs an owner process to accept requests, which reintroduces the caller-lifetime coupling; loopback sockets let any instance connect to a service that outlives its creator. A general HTTP server would add a request framework and a wider interface for one binary request/response. Unix-domain sockets and Windows named pipes would each need a platform-specific endpoint path and access policy; one loopback socket, its endpoint file and the existing filesystem locks provide discovery, authentication and single-instance arbitration with one implementation.

## Verification

In the final verification run, the [shared OCR tests](../../../../arknights_mower/tests/shared_ocr_tests.py) passed 45 focused offline cases and the [shared OCR update lifecycle tests](../../../../arknights_mower/tests/shared_ocr_update_lifecycle_tests.py) passed 10, in 119.42 seconds combined; the same run also included 26 cases from the [OCR gate tests](../../../../arknights_mower/tests/ocr_gate_tests.py) and 32 from the [runtime memory tests](../../../../arknights_mower/tests/runtime_memory_tests.py). Shared OCR coverage includes installation and network-namespace separation, eighteen concurrent clients sharing one model, startup races, image admission, option isolation, raw transport bounds, failure and timeout cleanup, idle exit, worker replacement with pending requests, twelve parameterized worker-recycling pipe-close regressions, update shutdown and a source service surviving its first client. The frozen entry is executed with a stub service and rejects GUI imports.

The lifecycle cases cover the orphaned worker remaining in the update shutdown snapshot, restart exclusion for both registration kinds and rejection of a worker start after update admission. The gate cases cover single-instance local and two-instance shared selection, mode overrides and invalid values, per-call re-evaluation and switching, failure fallback, data-root filtering, concurrent initialization and local-engine option parity. The runtime memory cases cover detector tensor bounds, concurrent client initialization and the log and screenshot memory bounds.

The [furniture regression](../../../../arknights_mower/tests/furniture_ocr_tests.py) passed 36 cases across local and shared execution. Related runtime registration, updater, manager and memory checks passed 59 cases with one platform-specific skip; recognition regressions passed 169, and desktop/preparation lifecycle checks passed 21. These groups overlap and are not an additive unique-test count.

A local macOS comparison used three independent clients, three identical furniture screenshots and two ONNX intra-operation threads per session in both modes. Once all clients had finished and remained alive, summed RSS was 1252.8 MiB with private models and 822.0 MiB with sharing, including the shared coordinator and worker. All furniture names and counts agreed. The sampled PIDs are the three clients and, in shared mode, the coordinator and model worker; the common measurement harness and multiprocessing resource tracker are excluded. This is a held-state RSS measurement, not a peak, an eighteen-emulator measurement or a long-running stability result.

The request budget, idle exit and recycle threshold keep their values of 60 seconds, 60 seconds and 256 requests, supported by local measurements. A read-only probe on a 16-logical-core Windows host used two OpenCV threads and two ONNX intra-operation threads per session: full-frame inference had a 1.07 s median and a 2.8 s first call, and model construction took 1.66 s cold and 0.54 s with a warm page cache. Eighteen-way bursts completed in 13.5–17.2 s, leaving 71–77% of the request budget; a host slow enough to need 2.8 s per call takes about 54 s and leaves about 10%. Cold start after idle exit adds 2.1–3.5 s. Replacing the worker after 256 requests costs about 4 s, or 16 ms per request amortized. A slower or loaded host, or a worker replacement inside a burst, reduces these margins. These are source-launch measurements on one host, not an end-to-end service guarantee.

## Consequences

Serial inference increases wait time under simultaneous load; finite admission and request budgets can reject work. Cold startup recurs after idle exit or worker recycling. Sharing is limited to one installation and data root in one network namespace, and does not reduce emulator or other instance-state memory. Loopback authentication is not a cross-host service. A failed shared request is not replayed and does not fall back to an in-process model. After abrupt coordinator death, the portable parent-channel EOF watcher requires the GIL; a surviving native worker's model lock prevents overlapping replacements until it exits, and the worker's own registration keeps that orphan within [update shutdown](../../../../docs/subsystems/software-update.md#shared-ocr-update-lifecycle).

The single-instance case no longer pays for the shared coordinator and worker. Whether sharing saves memory from two instances upward depends on the measurement caliber on the Windows host: under peak WorkingSet, a single shared instance used about 10–52% more than a local one with a break-even near 1.1–1.6 instances, and two instances already saved; under retained WorkingSet, a single shared instance used about 71–77% more with a break-even near 2.8–3.1, and two instances still used about 14% more while about three broke even. The gate removes the single-instance case that loses under every measured caliber; above it, the benefit depends on which memory figure constrains the deployment. The PR's macOS retained-RSS comparison is a different caliber and is not directly comparable.

Mode changes converge at the next `initialize_ocr` call: registrations are read once without retries, so instances that start close together can briefly select different modes, and a failed scan falls back to local without a watcher or background polling. A switch constructs the new engine before publishing it and keeps the previous engine when construction fails; in-flight requests keep their own engine. Releasing an in-process model drops only this module's reference, so ONNX Runtime and allocator memory can remain allocated until process exit; switching back to local does not promise an immediate resident-memory reduction.

## Limitations

Android host execution, packaged Windows/macOS artifacts and long device runs remain unmeasured.

Account, device and scheduling concepts retain their meanings and ownership. The change relocates stateless recognition execution and its process lifetime, so no glossary changes are needed.
