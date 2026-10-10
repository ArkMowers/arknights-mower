"""Compile runtime and development dependency locks with Python 3.12."""

import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
LOCKS = (
    ("requirements.in", "requirements.txt"),
    ("requirements-dev.in", "requirements-dev.txt"),
)


def compile_locks(
    version_info: Sequence[int] = sys.version_info,
    run: Callable = subprocess.run,
) -> None:
    if tuple(version_info[:2]) != (3, 12):
        raise RuntimeError(
            "Dependency locks must be compiled with Python 3.12; "
            f"got {version_info[0]}.{version_info[1]}"
        )

    for source, output in LOCKS:
        run(
            [
                sys.executable,
                "-m",
                "piptools",
                "compile",
                "--no-strip-extras",
                f"--output-file={output}",
                source,
            ],
            check=True,
            cwd=ROOT,
        )


if __name__ == "__main__":
    compile_locks()
