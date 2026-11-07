"""Remove unused optional OpenCV assets after dependency installation.

The bundled FFmpeg libraries named ``libav*``/``libsw*`` in Linux wheels are
link-time dependencies of ``cv2.abi3.so`` and must remain. This script only
removes separately-loadable videoio FFmpeg plugins and the unused cascade data.
It stages every candidate and imports/exercises core recognition APIs before
making the deletion permanent. The command line requires exactly one installed
OpenCV distribution before pruning.
"""

import argparse
import importlib.metadata
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, List, Optional, Tuple

VIDEOIO_PATTERNS = (
    "opencv_videoio_ffmpeg*.dll",
    "opencv_videoio_ffmpeg*.so",
    "libopencv_videoio_ffmpeg*.so*",
)
OPENCV_LIBRARY_DIRS = ("opencv_python.libs", "opencv_python_headless.libs")
OPENCV_DISTRIBUTIONS = frozenset(
    {
        "opencv-python",
        "opencv-python-headless",
        "opencv-contrib-python",
        "opencv-contrib-python-headless",
    }
)


def check_opencv_distribution() -> None:
    installed = []
    for distribution in importlib.metadata.distributions():
        name = re.sub(r"[-_.]+", "-", distribution.metadata.get("Name", "")).lower()
        if name in OPENCV_DISTRIBUTIONS:
            installed.append(f"{name}=={distribution.version}")
    if len(installed) != 1:
        found = ", ".join(sorted(installed)) or "none"
        raise SystemExit(
            "Install exactly one OpenCV distribution before pruning; "
            f"found {len(installed)}: {found}. "
            "OpenCV distributions share the 'cv2' package."
        )


def find_cv2_root() -> Path:
    spec = importlib.util.find_spec("cv2")
    if spec is None or spec.origin is None:
        raise SystemExit("OpenCV package 'cv2' is not installed.")
    return Path(spec.origin).resolve().parent


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _size(path: Path) -> int:
    if path.is_dir():
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    return path.stat().st_size


def find_candidates(cv2_root: Path) -> List[Path]:
    cv2_root = cv2_root.resolve()
    site_packages = cv2_root.parent.resolve()
    roots = [cv2_root]
    for name in OPENCV_LIBRARY_DIRS:
        path = site_packages / name
        if not path.is_dir():
            continue
        resolved = path.resolve()
        if resolved.parent != site_packages or resolved != path.absolute():
            raise RuntimeError(f"Refusing linked OpenCV library root: {path}")
        roots.append(resolved)

    candidates = []
    data_dir = cv2_root / "data"
    if data_dir.is_dir():
        candidates.append(data_dir)
    for root in roots:
        for pattern in VIDEOIO_PATTERNS:
            candidates.extend(path for path in root.rglob(pattern) if path.is_file())

    unique = sorted({path.resolve() for path in candidates}, key=str)
    for path in unique:
        if not any(_is_within(path, root.resolve()) for root in roots):
            raise RuntimeError(f"Refusing to prune path outside OpenCV: {path}")
    return unique


def smoke_test_core_apis() -> None:
    code = """
import cv2
import numpy as np

gray = np.zeros((32, 32), dtype=np.uint8)
color = np.zeros((32, 32, 3), dtype=np.uint8)
cv2.blur(gray, (7, 7))
cv2.cvtColor(color, cv2.COLOR_RGB2GRAY)
cv2.matchTemplate(gray, gray[:8, :8], cv2.TM_CCOEFF_NORMED)
cv2.ORB_create().detectAndCompute(gray, None)
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def prune_opencv(
    cv2_root: Path,
    dry_run: bool = False,
    smoke_test: Optional[Callable[[], None]] = smoke_test_core_apis,
) -> Tuple[List[Path], int]:
    candidates = find_candidates(cv2_root)
    removed_bytes = sum(_size(path) for path in candidates)
    if dry_run or not candidates:
        return candidates, removed_bytes

    staging = Path(tempfile.mkdtemp(prefix="mower-opencv-prune-"))
    moved = []
    try:
        for index, original in enumerate(candidates):
            staged = staging / f"{index}-{original.name}"
            shutil.move(str(original), staged)
            moved.append((original, staged))
        if smoke_test is not None:
            smoke_test()
    except Exception as prune_error:
        restore_errors = []
        for original, staged in reversed(moved):
            try:
                original.parent.mkdir(parents=True, exist_ok=True)
                if staged.exists():
                    shutil.move(str(staged), original)
            except Exception as restore_error:
                restore_errors.append(f"{original}: {restore_error}")
        if restore_errors:
            details = "; ".join(restore_errors)
            raise RuntimeError(
                f"OpenCV prune failed and rollback is incomplete; "
                f"staged files remain at {staging}: {details}"
            ) from prune_error
        shutil.rmtree(staging)
        raise
    shutil.rmtree(staging)
    return candidates, removed_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="list candidates without deleting them"
    )
    args = parser.parse_args()

    check_opencv_distribution()
    candidates, removed_bytes = prune_opencv(find_cv2_root(), dry_run=args.dry_run)
    if not args.dry_run and not candidates:
        smoke_test_core_apis()
    action = "Would remove" if args.dry_run else "Removed"
    for path in candidates:
        print(f"{action}: {path}")
    print(f"{action} {removed_bytes / 1024 / 1024:.1f} MiB from OpenCV")


if __name__ == "__main__":
    main()
