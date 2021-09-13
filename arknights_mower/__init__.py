from pathlib import Path
from .utils.config import LOGFILE_PATH, SCREENSHOT_PATH

Path(LOGFILE_PATH).parent.mkdir(exist_ok=True)
Path(SCREENSHOT_PATH).mkdir(exist_ok=True)

__rootdir__ = Path(__file__).parent.resolve()
__version__ = '0.3.2'
