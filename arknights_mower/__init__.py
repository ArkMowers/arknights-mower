import os
import platform
import sys
from pathlib import Path

if sys.platform == "win32":
    # Configure before importing cv2; native OpenCL cleanup can hang on Windows
    # after application resources have already closed. Helpers inherit this.
    os.environ.setdefault("OPENCV_OPENCL_RUNTIME", "disabled")

    # A single OpenBLAS thread avoids per-thread memory commits on Windows.
    if not any(
        name in os.environ
        for name in (
            "OPENBLAS_NUM_THREADS",
            "OPENBLAS_DEFAULT_NUM_THREADS",
            "GOTO_NUM_THREADS",
            "OMP_NUM_THREADS",
        )
    ):
        os.environ["OPENBLAS_NUM_THREADS"] = "1"

__version__ = "4.1.6-alpha.14"
__release_system__ = ""
__release_arch__ = ""
__release_archive__ = ""

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    __rootdir__ = Path(sys._MEIPASS).joinpath("arknights_mower").resolve()
else:
    __rootdir__ = Path(__file__).parent.resolve()

    from arknights_mower.utils.git_rev import revision_info

    __version__ += "+" + revision_info()[:7]

__system__ = platform.system().lower()
