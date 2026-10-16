# Recognition

Recognition consumes standard canvas frames and their crops. [Device Control](device-control.md#4-capture-frame-contract--storage) owns acquisition and screenshot storage; this subsystem owns model input preparation and OCR construction.

## OCR Memory Bounds

[`rapidocr.py`](../../arknights_mower/utils/rapidocr.py) owns OCR construction for runtime and real-image regressions. Detector preprocessing preserves short-edge enlargement toward 736 pixels for small text, caps the resulting long edge at 1920 pixels, and aligns dimensions to the network's 32-pixel units. This prevents narrow crops from expanding into several-thousand-pixel-wide detector tensors. Recognition thresholds and result coordinates retain their existing meaning.

Concurrent initialization publishes one engine per process; failed construction leaves initialization retryable. Separate Mower processes still own separate OCR engines. The manager's existing child-process launches do not share these model sessions. The input limit reduces inference allocations; it does not bound the entire application's resident memory or force an allocator to return freed pages to the operating system.

## Offline Verification

[`runtime_memory_tests.py`](../../arknights_mower/tests/runtime_memory_tests.py) verifies detector tensor bounds and initialization. Furniture, mastery, clue, manufacturing, recycling and operation-drop fixtures construct the production engine and verify their recognition paths. Changes to preprocessing must retain those expected names, counts, timing and rejection results. These offline checks do not establish long-running device memory stability.
