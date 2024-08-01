import platform
import sys
from pathlib import Path

__version__ = "2024.08"

# Use sys.frozen to check if run through pyinstaller frozen exe, and sys._MEIPASS to get temp path.
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    __pyinstall__ = True
    # Why they create a  __init__ folder here...idk.
    __rootdir__ = (
        Path(sys._MEIPASS).joinpath("arknights_mower").joinpath("__init__").resolve()
    )
else:
    __pyinstall__ = False
    __rootdir__ = Path(__file__).parent.resolve()

    from arknights_mower.utils.git_rev import revision_info

    __version__ += "+" + revision_info()[:7]

# Command line mode
__cli__ = not (__pyinstall__ and not sys.argv[1:])

__system__ = platform.system().lower()
