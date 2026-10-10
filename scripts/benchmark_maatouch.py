"""Compare MaaTouch pipe overhead offline; optional ADB runs use only version."""

import argparse
import hashlib
import io
import json
import logging
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from threading import Event
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.device.adb_client import server  # noqa: E402
from arknights_mower.utils.device.maatouch import core, session  # noqa: E402

COMPARED_PATHS = (
    "arknights_mower/utils/device/maatouch/session.py",
    "arknights_mower/utils/device/adb_client/server.py",
)
SHARED_PATHS = (
    "arknights_mower/utils/device/maatouch/core.py",
    "arknights_mower/utils/device/maatouch/command.py",
    "arknights_mower/utils/device/manager_io.py",
    "arknights_mower/utils/device/io_budget.py",
)


def git_source(ref, path):
    return subprocess.check_output(
        ["git", "show", f"{ref}:{path}"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


def baseline_module(ref, path, source):
    module = ModuleType(f"baseline_{Path(path).stem}")
    exec(compile(source, f"{ref}:{path}", "exec"), module.__dict__)
    return module


def comparison_sources(ref):
    baseline = {path: git_source(ref, path) for path in COMPARED_PATHS + SHARED_PATHS}
    current = {
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in COMPARED_PATHS + SHARED_PATHS
    }
    changed = [path for path in SHARED_PATHS if baseline[path] != current[path]]
    if changed:
        raise ValueError(
            "Shared benchmark dependencies differ from the baseline: "
            + ", ".join(changed)
        )
    return baseline, current


def source_hashes(sources):
    return {
        path: hashlib.sha256(source.encode("utf-8")).hexdigest()
        for path, source in sources.items()
    }


def summary(samples):
    ordered = sorted(samples)
    return {
        "n": len(samples),
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 3),
        "min_ms": round(min(samples), 3),
        "max_ms": round(max(samples), 3),
    }


def measure(operation, iterations):
    samples = []
    for _ in range(iterations):
        started = time.perf_counter()
        operation()
        samples.append((time.perf_counter() - started) * 1000)
    return summary(samples)


class Pipe(io.StringIO):
    def __init__(self, content="", *, delay):
        super().__init__(content)
        self.delay = delay

    def readline(self, *args):
        Event().wait(self.delay)
        return super().readline(*args)

    def write(self, content):
        Event().wait(self.delay)
        return super().write(content)


class Process:
    def __init__(self, delay):
        self.stdout = Pipe("^ 10 1920 1080 255\n$ 123\n", delay=delay)
        self.stdin = Pipe(delay=delay)
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 1 if os.name == "nt" else -15

    kill = terminate

    def wait(self, timeout):
        if self.returncode is None:
            raise subprocess.TimeoutExpired("offline-maatouch", timeout)
        return self.returncode


def pipe_benchmarks(module, iterations, delay):
    counts = {"processes": 0, "guards": 0}

    def spawn(*args, **kwargs):
        counts["processes"] += 1
        return Process(delay)

    def guard(*args, **kwargs):
        counts["guards"] += 1
        return kwargs["timeout"]

    offline_subprocess = SimpleNamespace(
        Popen=spawn,
        PIPE=subprocess.PIPE,
        CREATE_NO_WINDOW=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        TimeoutExpired=subprocess.TimeoutExpired,
    )
    adb = SimpleNamespace(
        adb_bin="offline-adb",
        device_id="offline-target",
        cmd_shell=lambda *a: "maatouch",
    )
    with (
        patch.object(module, "subprocess", offline_subprocess),
        patch.object(module, "guard_adb", guard),
        patch.object(core, "Session", module.Session),
        patch.object(config, "MNT_COMPATIBILITY_MODE", False),
    ):
        client = core.Client(adb)

        def start_send_close():
            with module.Session(adb) as connection:
                connection.send("d 0 20 30 100\nc\nu 0\nc\n")

        try:
            results = {
                "handshake_send_close": measure(start_send_close, iterations),
                "tap": measure(
                    lambda: client.tap([(20, 30)], (1920, 1080, 0)), iterations
                ),
                "swipe_100ms": measure(
                    lambda: client.swipe(
                        [(20, 30), (120, 30)], (1920, 1080, 0), duration=100
                    ),
                    iterations,
                ),
            }
        finally:
            client.close()
    results["counts"] = counts
    results["pipe_delay_ms"] = delay * 1000
    return results


def version_benchmark(module, adb, protocol, iterations):
    # The socket probe is replaced. The only real ADB invocation is version.
    if hasattr(module, "_ADB_VERSION_CACHE"):
        with module._ADB_VERSION_CACHE_LOCK:
            module._ADB_VERSION_CACHE.clear()
    popen = subprocess.Popen
    calls = 0

    def counted_popen(*args, **kwargs):
        nonlocal calls
        calls += 1
        return popen(*args, **kwargs)

    with patch.object(subprocess, "Popen", counted_popen):

        def guard():
            module.guard_adb(
                str(adb),
                timeout=5,
                run=module.run_command,
                probe=lambda timeout: protocol,
            )

        started = time.perf_counter()
        guard()
        cold_ms = (time.perf_counter() - started) * 1000
        warm = measure(guard, iterations)
    return {
        "first_ms": round(cold_ms, 3),
        "subsequent": warm,
        "version_processes": calls,
    }


def main():
    logging.disable(logging.CRITICAL)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline", required=True, help="Repository commit to compare"
    )
    parser.add_argument("--iterations", type=int, default=40)
    parser.add_argument("--pipe-delay-ms", type=float, default=1)
    parser.add_argument(
        "--adb", type=Path, help="Optional absolute executable; version only"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.iterations <= 0 or not 0 <= args.pipe_delay_ms <= 100:
        parser.error("iterations must be positive and pipe delay must be 0–100 ms")
    if args.adb is not None and (not args.adb.is_absolute() or not args.adb.is_file()):
        parser.error("--adb must identify an existing absolute executable path")
    try:
        baseline = subprocess.check_output(
            [
                "git",
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{args.baseline}^{{commit}}",
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            timeout=30,
        ).strip()
        old_sources, current_sources = comparison_sources(baseline)
    except (subprocess.CalledProcessError, ValueError) as exc:
        parser.error(str(exc))
    old_session = baseline_module(
        baseline, COMPARED_PATHS[0], old_sources[COMPARED_PATHS[0]]
    )
    old_server = baseline_module(
        baseline, COMPARED_PATHS[1], old_sources[COMPARED_PATHS[1]]
    )
    report = {
        "baseline": baseline,
        "source_hash_format": "SHA-256 of UTF-8 source with LF newlines",
        "harness_sha256": hashlib.sha256(
            Path(__file__).read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest(),
        "source_hashes": {
            "before": source_hashes(old_sources),
            "after": source_hashes(current_sources),
        },
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "scope": "Fake process/pipes/ADB probe; real gesture waits. Optional local version only.",
        "sampling_order": ["before", "after"],
        "warmup_samples": 0,
        "pipes": {},
    }
    for name, module in (("before", old_session), ("after", session)):
        report["pipes"][name] = pipe_benchmarks(
            module, args.iterations, args.pipe_delay_ms / 1000
        )
    if args.adb:
        protocol = old_server.adb_client_version(str(args.adb), timeout=5)
        with args.adb.open("rb") as executable:
            executable_hash = hashlib.file_digest(executable, "sha256").hexdigest()
        report["adb_executable"] = {
            "name": args.adb.name,
            "size_bytes": args.adb.stat().st_size,
            "protocol": protocol,
            "sha256": executable_hash,
        }
        report["local_version"] = {
            name: version_benchmark(module, args.adb, protocol, args.iterations)
            for name, module in (("before", old_server), ("after", server))
        }
    output = json.dumps(report, indent=2, ensure_ascii=False)
    print(output)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
