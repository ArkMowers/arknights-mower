from pathlib import Path
import platform

__rootdir__ = Path(__file__).parent.resolve()
__system__ = platform.system().lower()
__version__ = '1.1.7'
