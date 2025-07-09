import platform
import sys
from pathlib import Path

__version__ = "2025.7.1.1"

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    __rootdir__ = Path(sys._MEIPASS).joinpath("arknights_mower").resolve()
else:
    __rootdir__ = Path(__file__).parent.resolve()

    from arknights_mower.utils.git_rev import revision_info

    __version__ += "+" + revision_info()[:7]

__system__ = platform.system().lower()
