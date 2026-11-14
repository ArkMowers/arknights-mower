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


def protected_storage_paths(target):
    """Include configured aliases and their actual storage locations."""
    root = get_path("@app", space="").resolve()
    runtime = storage_root(target)
    runtime_paths = (runtime, runtime / "updates", runtime / "cache", runtime / "user")
    paths = [root, *runtime_paths, *(item.resolve() for item in runtime_paths)]
    configured = os.environ.get("MOWER_DATA_DIR")
    if configured:
        alias = Path(os.path.abspath(Path(configured).expanduser()))
        if alias != root and alias.resolve() == root:
            paths.append(alias)
    return tuple(dict.fromkeys(paths))


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
                    excluded = {
                        get_path("@app", space="").resolve(),
                        get_path("@app/tmp/maa", space="").resolve(),
                        root.resolve(),
                        staged.parent.resolve(),
                    }

                    def ignore_storage(directory, names):
                        parent = Path(directory).resolve()
                        return {
                            name
                            for name in names
                            if (entry := parent / name) in excluded
                            or (
                                (entry.is_symlink() or entry.is_junction())
                                and entry.resolve() in excluded
                            )
                        }

                    shutil.copytree(legacy, staged, ignore=ignore_storage)
                else:
                    staged.mkdir()
                os.replace(staged, cache)
    return cache
