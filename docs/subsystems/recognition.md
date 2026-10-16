# Recognition

Recognition consumes standard canvas frames and their crops. [Device Control](device-control.md#4-capture-frame-contract--storage) owns acquisition and screenshot storage; this subsystem owns model input preparation and OCR execution.

## OCR Memory Bounds

[`rapidocr.py`](../../arknights_mower/utils/rapidocr.py) owns the production model factory. Detector preprocessing preserves short-edge enlargement toward 736 pixels for small text, caps the resulting long edge at 1920 pixels, and aligns dimensions to the network's 32-pixel units. This prevents narrow crops from expanding into several-thousand-pixel-wide detector tensors. Recognition thresholds and result coordinates retain their existing meaning.

Concurrent initialization publishes one lightweight client per instance; failed construction leaves initialization retryable. The shared service constructs the model through the same factory, with two intra-operation threads and one inter-operation thread per ONNX session, and an OpenCV thread limit of two. This bounds each library's parallel work rather than reserving particular CPU cores. The input limit reduces inference allocations; it does not establish an application-wide resident-memory limit.

## Independent Shared OCR

**Independent Shared OCR**: instances using the same installation and data root share one on-demand OCR model worker. The multi-instance manager remains a launcher; closing it or the first requesting instance does not stop recognition for other instances. Account, task and device state stays in each instance. Separate installations, data roots and network namespaces do not share this service.

[`ocr_shared.py`](../../arknights_mower/utils/ocr_shared.py) implements the callable client used by `initialize_ocr`. [`ocr_service.py`](../../arknights_mower/utils/ocr_service.py) runs an independent coordinator and its sole model worker. Source and frozen launches route to this service before GUI and configuration initialization. A new service starts only when a caller needs OCR; it does not keep the manager or an instance alive.

```text
Instance A ─┐
Instance B ─┼─ small request headers → loopback listener (backlog 32)
Instance N ─┘                              │
                        one admitted image at a time
                                           ↓
                         one OCR model worker → caller's result
                                           ↑
                          independent deadline coordinator
```

Clients upload pixels only after admission. Each instance serializes its own calls; the service holds at most one admitted image, limited to 32 MiB of `uint8` pixels. Grayscale and one-, three- or four-channel arrays are accepted, including non-contiguous crops. Headers are limited to 4096 bytes and JSON responses to 2 MiB. Socket data uses bounded JSON and raw arrays, not executable object serialization. A random secret authenticates the loopback endpoint. The OS listen backlog bounds waiting connections; this is not a throughput guarantee for eighteen simultaneous requests.

The request's 60-second monotonic budget includes client serialization, cold startup, admission, upload, model execution and response. A newly launched service has a ten-second sub-budget to publish its endpoint. Header reception has a five-second budget. Waiting clients receive no implied success, and a sent request is never automatically replayed. Failure does not create a private model in each instance. Each request restores OCR thresholds before inference, preventing one caller's options from changing another caller's results.

The coordinator terminates and joins its own worker on an execution deadline or update shutdown. Model failure closes that service generation; a subsequent new request can start a service. After 256 handled model requests, the coordinator confirms the old worker's exit before replacing it; the listener, secret and waiting connections remain available. This releases native allocations without requiring Python garbage collection to return them. After 60 seconds without an accepted connection, the worker and coordinator exit. The next request starts cold.

Startup, service and model lifetime locks prevent duplicate construction. A model lock left held by a surviving worker prevents a replacement from loading a second model after coordinator death. The portable parent-channel EOF watcher needs the GIL; an abruptly orphaned native call holding it cannot be guaranteed immediate cleanup on every platform. No foreign process is terminated to overcome that lock.

Endpoint metadata and lifetime locks live under `@app/tmp/shared-ocr/<service-hash>/`, with `space=""`; `MOWER_DATA_DIR` and macOS writable-data-root behavior match ordinary application paths. The service hash includes the installation path and host name, plus the Linux network-namespace identity so containers sharing a data volume do not reuse an inaccessible loopback endpoint. These are separate from the software-update cache. The coordinator has an `ocr-service` runtime registration solely so [software updates](software-update.md#shared-ocr-update-lifecycle) can stop it before replacing files. Update recovery excludes it from eager relaunch; resumed instances create it on demand.

The [shared OCR decision](../../.agents/notes/implemented/architecture/2026-10-16-shared-ocr-service.md) records why service lifetime is independent of the launcher and why the first implementation uses one model worker.

## Offline Verification

[`shared_ocr_tests.py`](../../arknights_mower/tests/shared_ocr_tests.py) exercises eighteen concurrent clients, cold-start arbitration, deferred pixel upload, independent thresholds, input validation, real OCR equivalence, model failure, timeouts, worker replacement, idle exit and software-update shutdown. A real source launch remains available after its originating client exits. Frozen entry routing is checked offline; packaged Windows and macOS execution and eighteen real running emulators have not been measured here.

[`runtime_memory_tests.py`](../../arknights_mower/tests/runtime_memory_tests.py) verifies detector tensor bounds and concurrent client initialization. Furniture, mastery, clue, manufacturing, recycling and operation-drop fixtures verify the production model's expected names, counts, timing and rejection results. These offline checks do not establish long-running device memory stability or bound simulator memory.
