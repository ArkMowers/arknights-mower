"""Exercise real loader reference counts in an isolated, device-free process."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SDK = """
import ctypes
from pathlib import Path

class Asst:
    @staticmethod
    def load(path, incremental_path=None):
        library = ctypes.CDLL(str(Path(path) / CORE_NAME))
        Asst.__lib = library
        library.AsstGetVersion.restype = ctypes.c_char_p
        library.AsstCreateEx.argtypes = [ctypes.c_void_p]
        library.AsstCreateEx.restype = ctypes.c_void_p
        library.AsstDestroy.argtypes = [ctypes.c_void_p]
        library.AsstSetLog.argtypes = [ctypes.c_char_p]
        library.AsstSetLog(str(Path(path) / "unloaded.txt").encode())
        return True

    def __init__(self, callback):
        self.__callback = callback
        self.__ptr = Asst.__lib.AsstCreateEx(callback)

    def __del__(self):
        Asst.__lib.AsstDestroy(self.__ptr)

    def get_version(self):
        return Asst.__lib.AsstGetVersion().decode()

    def get_build(self):
        return Asst.__lib.AsstBuild()

    def stop(self):
        return True
"""

CORE = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef void (*Callback)(int, const char *, void *);
static char log_path[4096];
static int loads;
const char *AsstGetVersion(void) { return "v1.0.0"; }
int AsstBuild(void) { return BUILD_ID; }
int AsstLoads(void) { return loads; }
void AsstSetLog(const char *path) { ++loads; snprintf(log_path, sizeof(log_path), "%s", path); }
void *AsstCreateEx(Callback cb) {
    Callback *ptr = malloc(sizeof(Callback));
    *ptr = cb;
    return ptr;
}
void AsstDestroy(void *ptr) {
    Callback *cb = ptr;
    (*cb)(5, "{}", NULL);
    free(ptr);
}
__attribute__((destructor)) static void unloaded(void) {
    if (!log_path[0]) return;
    FILE *file = fopen(log_path, "a");
    if (file) { fprintf(file, "%d\n", BUILD_ID); fclose(file); }
}
"""

WORKER = r"""
import gc
import os
import sys
from pathlib import Path
from arknights_mower.utils.maa_runtime import load_verified_maa, MaaCoreRestartRequired
from arknights_mower.utils import maa_update

target, replacement, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(target / "Python"))
from asst.asst import Asst
# This C fixture has no Objective-C classes; exercise the Windows/Linux policy.
maa_update.platform.system = lambda: "Darwin" if mode == "darwin" else "Linux"

for _ in range(3):
    instance = load_verified_maa(Asst, target, lambda *args: None)
    assert instance.get_build() == 1
    instance.stop()
    del instance
    gc.collect()

if mode == "retained":
    retained = load_verified_maa(Asst, target, lambda *args: None)
    retained.stop()
elif mode in ("raw", "old-sdk"):
    from ctypes import CFUNCTYPE, c_int, c_char_p, c_void_p
    callback = CFUNCTYPE(None, c_int, c_char_p, c_void_p)(lambda *args: None)
    retained = Asst(callback)
    if mode == "old-sdk":
        import importlib
        sys.modules.pop("asst.asst")
        Asst = importlib.import_module("asst.asst").Asst
        instance = load_verified_maa(Asst, target, lambda *args: None)
        instance.stop()
        del instance
        gc.collect()
elif mode == "unknown":
    # An out-of-band SDK load cannot contribute to a trusted reference count.
    Asst.load(target)
elif mode == "close-failed":
    failed_close = []
    def fail(*args, **kwargs):
        failed_close.append(True)
        raise OSError("library close failed")
    maa_update._close_dynamic_library = fail
    # Reach the injected close failure even on hosts without Linux process maps.
    maa_update._maa_core_image_mapped = lambda address: True
elif mode == "extra-open":
    import ctypes
    untracked_open = ctypes.CDLL(str(target / replacement.name))

if mode in ("nodelete", "extra-open"):
    resource_loads = Asst._Asst__lib.AsstLoads

if mode == "symlink":
    physical = target / "physical-core.so"
    os.replace(replacement, physical)
else:
    os.replace(replacement, target / replacement.name)
if mode not in ("reload", "symlink"):
    try:
        load_verified_maa(Asst, target, lambda *args: None)
    except MaaCoreRestartRequired as error:
        assert error.code == "maa_core_restart_required"
    else:
        raise AssertionError("unsafe core was admitted")
    assert not (target / "unloaded.txt").exists()
    if mode == "close-failed":
        assert failed_close == [True]
    if mode in ("nodelete", "extra-open"):
        assert resource_loads() == 3, "replacement resources reached the old image"
    if mode in ("close-failed", "nodelete", "extra-open"):
        # A partially invalidated SDK cannot retry into an unverified image.
        try:
            load_verified_maa(Asst, target, lambda *args: None)
        except MaaCoreRestartRequired:
            pass
        else:
            raise AssertionError("failed unload was reused")
        if mode in ("nodelete", "extra-open"):
            assert resource_loads() == 3
else:
    instance = load_verified_maa(Asst, target, lambda *args: None)
    assert instance.get_version() == "v1.0.0"
    assert instance.get_build() == 2, "same version retained the old native image"
    from asst.asst import Asst as NewAsst
    assert NewAsst is not Asst
    assert (target / "unloaded.txt").read_text().splitlines() == ["1"]
    instance.stop()
    del instance
    gc.collect()
    maa_update.clear_loaded_maa_cache(target)
    assert (target / "unloaded.txt").read_text().splitlines() == ["1", "2"]
"""


FAILED_INIT_WORKER = r"""
import gc
import os
import sys
from pathlib import Path
from unittest.mock import patch
from arknights_mower.utils import maa_runtime as runtime, maa_update
from arknights_mower.utils.maa_backup import MaaCallError

target, replacement, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(target / "Python"))
from asst.asst import Asst

original_load = Asst.load
def failed_load(**kwargs):
    original_load(**kwargs)
    if mode == "failed-load-raised":
        raise RuntimeError("SDK failed after native open")
    return False

for _ in range(2):
    if mode in ("failed-resource", "failed-resource-retry", "failed-load-raised"):
        fault = patch.object(Asst, "load", side_effect=failed_load)
    elif mode == "failed-constructor":
        fault = patch.object(runtime, "VerifiedAsst", side_effect=RuntimeError("constructor failed"))
    else:
        fault = patch.object(runtime, "read_installed_version", return_value="")
    with fault:
        try:
            runtime.load_verified_maa(Asst, target, lambda *args: None)
        except (runtime.MaaUpdateError, MaaCallError, RuntimeError):
            pass
        else:
            raise AssertionError("initialization should fail")
    gc.collect()
    assert "_mower_core_generation" not in vars(Asst)

assert Asst._Asst__lib.AsstBuild() == 1
assert Asst._Asst__lib.AsstLoads() == 2
unchanged = mode.endswith("-retry")
if not unchanged:
    os.replace(replacement, target / replacement.name)

with patch.object(runtime, "clear_loaded_maa_cache", wraps=runtime.clear_loaded_maa_cache) as cleanup:
    if sys.platform == "darwin" and not unchanged:
        try:
            runtime.load_verified_maa(Asst, target, lambda *args: None)
        except runtime.MaaCoreRestartRequired:
            pass
        else:
            raise AssertionError("macOS must require restart")
        assert Asst._Asst__lib.AsstLoads() == 2, "new resources reached the failed old load"
        assert "_mower_core_generation" not in vars(Asst)
        assert cleanup.call_count == 1
    else:
        instance = runtime.load_verified_maa(Asst, target, lambda *args: None)
        assert instance.get_build() == (1 if unchanged else 2), "failed initialization retained old build"
        assert cleanup.call_count == (0 if unchanged else 1)
        from asst.asst import Asst as CurrentAsst
        assert CurrentAsst._mower_core_generation[1] == "v1.0.0"
        assert (CurrentAsst is Asst) == unchanged
        assert CurrentAsst._Asst__lib.AsstLoads() == (3 if unchanged else 1)
        if not unchanged:
            assert (target / "unloaded.txt").read_text().splitlines() == ["1"]
        instance.stop()
        del instance
        gc.collect()
"""


@pytest.mark.parametrize(
    "mode",
    [
        "reload",
        "symlink",
        "nodelete",
        "extra-open",
        "retained",
        "raw",
        "old-sdk",
        "unknown",
        "close-failed",
        "darwin",
        "failed-resource",
        "failed-probe",
        "failed-load-raised",
        "failed-constructor",
        "failed-resource-retry",
        "failed-probe-retry",
    ],
)
def test_native_core_generation_reload(tmp_path, mode):
    compiler = shutil.which("cc")
    if os.name == "nt" or compiler is None:
        pytest.skip("native fixture requires a POSIX C compiler")
    if (
        mode in ("reload", "symlink", "nodelete", "extra-open")
        and sys.platform != "linux"
    ):
        pytest.skip("native unload verification requires Linux process maps")
    core_name = "libMaaCore.dylib" if sys.platform == "darwin" else "libMaaCore.so"
    target = tmp_path / "maa"
    sdk_dir = target / "Python" / "asst"
    sdk_dir.mkdir(parents=True)
    (sdk_dir / "__init__.py").write_text("")
    (sdk_dir / "asst.py").write_text(f"CORE_NAME = {core_name!r}\n" + SDK)
    source = tmp_path / "core.c"
    source.write_text(CORE)
    replacement_dir = tmp_path / "replacement"
    replacement_dir.mkdir()
    for build, directory in [(1, target), (2, replacement_dir)]:
        subprocess.run(
            [
                compiler,
                "-shared",
                "-fPIC",
                f"-DBUILD_ID={build}",
                *(["-Wl,-z,nodelete"] if mode == "nodelete" else []),
                str(source),
                "-o",
                str(directory / core_name),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
    if mode == "symlink":
        (target / core_name).rename(target / "physical-core.so")
        (target / core_name).symlink_to("physical-core.so")
    worker = tmp_path / "worker.py"
    worker.write_text(FAILED_INIT_WORKER if mode.startswith("failed-") else WORKER)
    environment = dict(
        os.environ,
        MOWER_ANDROID="0",
        PYTHONPATH=str(Path(__file__).resolve().parents[2]),
    )
    result = subprocess.run(
        [
            sys.executable,
            str(worker),
            str(target),
            str(replacement_dir / core_name),
            mode,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    assert result.returncode == 0, result.stdout + result.stderr
