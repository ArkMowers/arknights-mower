"""Point app data at a scratch directory so tests never read a user config.

``arknights_mower.utils.path`` resolves the data root when it is first imported,
so the environment has to be set here, before any test module pulls in config.
A developer's real ``config/conf.yml`` can otherwise change timing and profile
values that assertions depend on.
"""

import atexit
import base64
import os
import shutil
import tempfile

if not os.environ.get("MOWER_DATA_DIR"):
    _scratch = tempfile.mkdtemp(prefix="mower-tests-")
    os.environ["MOWER_DATA_DIR"] = _scratch
    atexit.register(shutil.rmtree, _scratch, ignore_errors=True)

# Keep credential tests independent of the developer's system keychain and keys.
_credential_scratch = tempfile.mkdtemp(prefix="mower-test-credentials-")
_credential_key = os.path.join(_credential_scratch, "private.key")
with open(_credential_key, "wb") as _key_file:
    _key_file.write(base64.urlsafe_b64encode(os.urandom(96)))
os.chmod(_credential_key, 0o600)
os.environ["MOWER_CREDENTIAL_KEY_FILE"] = _credential_key
atexit.register(shutil.rmtree, _credential_scratch, ignore_errors=True)
