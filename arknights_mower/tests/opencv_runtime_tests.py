"""Keep Windows shutdown independent of native OpenCL driver cleanup."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_PROBE = """
import json
import os
import sys

sys.path.insert(0, sys.argv[1])
sys.platform = sys.argv[2]
if sys.argv[3] == 'frozen':
    sys.frozen = True
    sys._MEIPASS = sys.argv[1]
import arknights_mower
print(json.dumps({
    'runtime': os.environ.get('OPENCV_OPENCL_RUNTIME'),
    'cv2_imported': 'cv2' in sys.modules,
}))
"""


def probe(script, *args, runtime=None):
    environment = dict(os.environ, PYTHONUTF8="1")
    environment.pop("OPENCV_OPENCL_RUNTIME", None)
    if runtime is not None:
        environment["OPENCV_OPENCL_RUNTIME"] = runtime
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(ROOT), *args],
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("deployment", ["source", "frozen"])
def test_windows_bootstrap_disables_opencl_before_native_import(deployment):
    assert probe(BOOTSTRAP_PROBE, "win32", deployment) == {
        "runtime": "disabled",
        "cv2_imported": False,
    }


@pytest.mark.parametrize("runtime", ["", "custom-opencl-runtime"])
def test_windows_bootstrap_preserves_explicit_opencl_runtime(runtime):
    assert probe(BOOTSTRAP_PROBE, "win32", "frozen", runtime=runtime) == {
        "runtime": runtime,
        "cv2_imported": False,
    }


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_non_windows_bootstrap_preserves_opencl_default(platform):
    assert probe(BOOTSTRAP_PROBE, platform, "frozen") == {
        "runtime": None,
        "cv2_imported": False,
    }


@pytest.mark.skipif(sys.platform != "win32", reason="Windows OpenCL shutdown")
def test_windows_native_operations_and_spawned_helper_exit_without_opencl():
    result = probe(
        """
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, sys.argv[1])
import arknights_mower
import cv2
import numpy as np

def recognize():
    cv2.ocl.setUseOpenCL(True)
    assert not cv2.ocl.haveOpenCL()
    assert not cv2.ocl.useOpenCL()
    rgb = np.zeros((32, 32, 3), dtype=np.uint8)
    rgb[8:24, 8:24] = (255, 0, 0)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    assert int(gray[16, 16]) == 76
    assert int(gray[0, 0]) == 0
    template = gray[4:28, 4:28].copy()
    scores = cv2.matchTemplate(gray, template, cv2.TM_SQDIFF)
    assert cv2.minMaxLoc(scores)[2] == (4, 4)
    cv2.ORB_create().detectAndCompute(gray, None)
    ok, encoded = cv2.imencode('.jpg', rgb)
    assert ok and cv2.imdecode(encoded, cv2.IMREAD_COLOR).shape == rgb.shape
    cv2.UMat(gray).get()

recognize()
with ThreadPoolExecutor(max_workers=1) as pool:
    pool.submit(recognize).result(timeout=5)
helper = subprocess.run(
    [sys.executable, '-I', '-c',
     'import cv2; assert not cv2.ocl.haveOpenCL(); assert not cv2.ocl.useOpenCL()'],
    stdin=subprocess.DEVNULL, capture_output=True, timeout=10,
    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
)
assert helper.returncode == 0, helper.stderr
print(json.dumps({'recognized': True, 'helper_exited': True}))
"""
    )
    assert result == {"recognized": True, "helper_exited": True}
