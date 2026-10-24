"""Exercise the copied source updater without access to the application package."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_detached_updater_waits_for_supervision_without_checkout_imports(tmp_path):
    source = Path(__file__).resolve().parents[1] / "utils"
    copied = tmp_path / "detached"
    copied.mkdir()
    for name in (
        "software_update_worker.py",
        "software_update_progress.py",
        "update_runtime.py",
        "github_download.py",
    ):
        shutil.copy2(source / name, copied / name)

    probe = tmp_path / "probe.py"
    probe.write_text(
        """
import importlib.abc
import json
import socket
import subprocess
import sys
from pathlib import Path

class DenyApplicationImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'arknights_mower' or fullname.startswith('arknights_mower.'):
            raise AssertionError('Detached updater imported the application package')

sys.meta_path.insert(0, DenyApplicationImports())
sys.path.insert(0, sys.argv[1])
import software_update_worker as worker
import update_runtime as runtime

def forbidden(*args, **kwargs):
    raise AssertionError('No live network or process operations in this probe')

socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
subprocess.Popen = forbidden

folder = Path.cwd()
record = {
    'id': 'fixture', 'kind': 'instance', 'pid': 0,
    'supervision_directory': str(folder / 'supervision'),
}
worker.instances = lambda state: [record]
worker.process_alive = lambda pid: False
instance = object.__new__(worker.Worker)
instance.state = folder / 'state'
instance.work = folder / 'work'
instance.job = {'id': 'offline-update'}
instance.report = lambda *args: None
instance.stop_instances()

assert instance.stopped == [record]
assert runtime.read_json(instance.state / 'shutdown/fixture.json') == {
    'job': 'offline-update',
}
assert (folder / 'supervision/instance.lock').is_file()
print(json.dumps({'stopped': True, 'supervisor_released': True}))
""",
        encoding="utf-8",
    )
    environment = dict(os.environ, PYTHONUTF8="1")
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-I", str(probe), str(copied)],
        cwd=tmp_path,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"stopped": True, "supervisor_released": True}
