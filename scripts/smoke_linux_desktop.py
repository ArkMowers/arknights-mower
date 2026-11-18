"""Start an unpacked Linux desktop and request its bundled Web UI."""

import argparse
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arknights_mower.utils import update_runtime as runtime  # noqa: E402


def wait_for_desktop(bundle, process, state, timeout=120):
    index = (bundle / "_internal/ui/dist/index.html").read_bytes()
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Linux desktop exited with {process.returncode}")
        for record in runtime.instances(state, timeout=0, strict=False):
            if not (
                record.get("kind") == "instance"
                and record.get("root") == str(bundle)
                and record.get("ready")
            ):
                continue
            request = Request(
                f"http://127.0.0.1:{record['port']}/",
                headers={"Accept": "text/html", "Accept-Encoding": "identity"},
            )
            try:
                with opener.open(request, timeout=2) as response:
                    if (
                        response.status == 200
                        and response.read(len(index) + 1) == index
                    ):
                        print(
                            "Linux desktop is ready and served its bundled index.html"
                        )
                        return
            except OSError:
                pass
        time.sleep(0.5)
    raise TimeoutError("Linux desktop did not register as ready and serve its Web UI")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    bundle = parser.parse_args().bundle.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="mower-linux-smoke-") as data:
        os.environ["MOWER_DATA_DIR"] = data
        state = runtime.state_dir(bundle)
        process = subprocess.Popen(
            [bundle / "mower"], cwd=bundle, start_new_session=True
        )
        try:
            wait_for_desktop(bundle, process, state)
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
            except ProcessLookupError:
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
