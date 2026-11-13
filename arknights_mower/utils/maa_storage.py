"""Keep Mower's MAA runtime files in its shared data directory."""

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from arknights_mower.utils.path import get_path


def installation_key(target):
    return hashlib.sha256(
        os.fsencode(os.path.normcase(str(Path(target).expanduser().resolve())))
    ).hexdigest()


def storage_root(target):
    return get_path("@app/tmp/maa", space="") / installation_key(target)


def load_options(target):
    if os.environ.get("MOWER_ANDROID") == "1":
        return {"path": Path(target), "incremental_path": Path(target) / "cache"}
    root = storage_root(target)
    cache = prepare_cache(target)
    user = root / "user"
    cache.mkdir(parents=True, exist_ok=True)
    user.mkdir(parents=True, exist_ok=True)
    return {"path": Path(target), "incremental_path": cache, "user_dir": user}


def prepare_cache(target):
    root = storage_root(target)
    cache = root / "cache"
    if cache.is_dir():
        return cache
    root.mkdir(parents=True, exist_ok=True)
    from arknights_mower.utils.update_runtime import supervision_lock

    with supervision_lock(root / "cache-migration", timeout=10):
        if not cache.exists():
            legacy = Path(target) / "cache"
            with tempfile.TemporaryDirectory(
                dir=root, prefix="cache-import-"
            ) as temporary:
                staged = Path(temporary) / "cache"
                if legacy.is_dir():
                    shutil.copytree(legacy, staged)
                else:
                    staged.mkdir()
                os.replace(staged, cache)
    return cache
