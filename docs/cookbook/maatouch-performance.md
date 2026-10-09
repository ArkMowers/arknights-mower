# Measuring MaaTouch Call Overhead

The [Device Control contract](../subsystems/device-control.md#3-subsystem-invariants) owns Shared ADB Guard, uncertain input and resource cleanup behavior. This recipe measures host overhead without connecting to a device.

## Reproduce the comparison

1. Use Python 3.12 with the repository's runtime dependencies. The harness compares baseline and working-tree `session.py` and `adb_client/server.py`. It requires `maatouch/core.py`, `maatouch/command.py`, `manager_io.py` and `io_budget.py` to match the baseline because both sides use those current callers and execution helpers. A mismatch stops the comparison.
2. Run the offline comparison from the repository root:

   ```powershell
   python scripts/benchmark_maatouch.py --baseline 3c3ce4e0 --iterations 40 --pipe-delay-ms 1 --output maatouch-benchmark.json
   ```

3. To measure local ADB version execution as well, add `--adb` with an absolute path to a trusted installed native ADB executable. This runs only `adb version`; the shared-server socket probe is replaced. For the recorded Windows measurement:

   ```powershell
   python scripts/benchmark_maatouch.py --baseline 3c3ce4e0 --iterations 40 --pipe-delay-ms 1 --adb E:/adb/adb.exe --output maatouch-benchmark.json
   ```

4. Compare medians, p95 values and process counts. The output resolves the baseline to a full commit, records hashes of the harness and compared/shared Python sources, and includes the optional ADB executable's name, size, protocol and content hash. Python source hashes use UTF-8 with LF newlines. Both comparisons run before samples followed by after samples, without warmup; each local-version side begins with an empty process-local cache. The pipe cases replace process startup, pipes, installation checks and the ADB guard, retain real gesture waits and disable logging. Each header-line read and command write waits for the configured simulated delay. These samples exclude Android startup, transport latency, scene recognition, screenshots and solver waits. Operating-system scheduling and fixed sample order remain sources of variation.
5. Run the focused regressions below. A faster sample does not establish correct failure classification or cleanup:

   ```powershell
   python -m pytest arknights_mower/tests/adb_version_cache_tests.py arknights_mower/tests/adb_server_tests.py arknights_mower/tests/adb_shared_transport_tests.py arknights_mower/tests/device_maatouch_io_tests.py arknights_mower/tests/device_maatouch_tests.py arknights_mower/tests/device_touch_tests.py arknights_mower/tests/device_owned_resources_tests.py arknights_mower/tests/device_shutdown_tests.py -q
   ```

## Recorded evidence: 2026-10-09

This comparison was collected again after rebasing onto upstream `alpha` at `3c3ce4e0`. That commit is the baseline and includes the MaaTouch termination-before-pipe-closure repair; the after source hashes identify the rebased optimization. The [raw benchmark output](maatouch-benchmark-20261009.json) records Windows, Python 3.12.10 and 40 samples per case. Its local ADB executable metadata records 2,583,552 bytes and protocol 41.

| Case | Before median | After median | Reduction | Before / after p95 |
| :--- | ---: | ---: | ---: | ---: |
| Local version guard after its first sample; socket probe replaced | 61.170 ms | 7.252 ms | 88.1% | 89.206 / 8.152 ms |
| Simulated handshake, send and close | 21.529 ms | 4.614 ms | 78.6% | 22.101 / 4.959 ms |
| Simulated tap including its existing wait | 71.941 ms | 55.223 ms | 23.2% | 73.299 / 56.056 ms |
| Simulated 100 ms swipe including its existing waits | 295.462 ms | 260.182 ms | 11.9% | 297.559 / 261.781 ms |

The local-version section executes 41 version processes before the change and one after it: one first guard plus 40 subsequent guards. Its first sample is 65.056 ms before and 92.441 ms after. The first measured guard follows version calibration and executable-content hashing, so it excludes operating-system cold startup. The after samples include executable-content hashing and file-identity checks. The pipe section creates 120 simulated processes and performs 120 guards on each side; process reuse is not part of this change. The two sections measure separate costs and their reductions cannot be added into an end-to-end claim.

An earlier local analysis of `runtime.log.2026-10-09_16` reported one helper startup per gesture. That log is not checked in, and this review cannot independently reproduce its statistics. Entry-to-handshake observations combine input preparation, Shared ADB Guard, host process startup and the Android handshake, so they do not establish the independent cost of any stage or measured recoverable savings.

## Scope and limits

The measured local-version reduction comes from reusing the protocol version of an unchanged native executable. Every guard still observes the shared server. The bounded cache, content verification, unsupported-file behavior and failure rules belong to the [Device Control contract](../subsystems/device-control.md#3-subsystem-invariants). The completion-wakeup change removes the wait for the next ten-millisecond poll while preserving periodic Recovery Budget checks.

Each gesture still owns and closes its MaaTouch process. Cross-gesture reuse requires additional evidence for remote completion, contact state, recovery and shutdown ownership.

The existing 50 ms wait per publish and all requested `w` waits remain. Batching or removing those waits changes contact timing without current Android validation. Movement commands within a phase are already batched. The existing indexing of unequal swipe segment durations is outside this performance change.

There is no live-device after measurement. Actual gains depend on executable size, cache eligibility, filesystem speed, pipe scheduling, Android startup and solver waits. Hash verification catches same-size in-place updates that restore modification time; it does not lock the executable through the subsequent operating-system process launch. Filesystem and process creation retain their operating-system interruptibility limits.

Concept-impact review reuses the existing Device Profile, Instance Binding, Shared ADB Guard and Recovery Budget meanings and boundaries. No glossary change, new invariant or separate decision record is necessary for these local execution optimizations.
