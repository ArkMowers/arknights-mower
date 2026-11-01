"""Point app data at a scratch directory so tests never read a user config.

``arknights_mower.utils.path`` resolves the data root when it is first imported,
so the environment has to be set here, before any test module pulls in config.
A developer's real ``config/conf.yml`` can otherwise change timing and profile
values that assertions depend on.
"""

import atexit
import os
import shutil
import tempfile

if not os.environ.get("MOWER_DATA_DIR"):
    _scratch = tempfile.mkdtemp(prefix="mower-tests-")
    os.environ["MOWER_DATA_DIR"] = _scratch
    atexit.register(shutil.rmtree, _scratch, ignore_errors=True)
