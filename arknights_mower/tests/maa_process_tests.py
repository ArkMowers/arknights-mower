"""Exercise desktop worker IPC without a device or an installed MAA SDK."""

import gc
import json
import os
import shutil
import subprocess
import sys
import weakref
from pathlib import Path
from unittest.mock import Mock

import pytest

from arknights_mower.utils import maa_process as processes
from arknights_mower.utils import maa_runtime as runtime
from arknights_mower.utils import maa_update
from arknights_mower.utils.maa_backup import MaaCallError, maa_instances_alive

SDK = """
import json
import time
from pathlib import Path

class Asst:
    @classmethod
    def load(cls, path, incremental_path):
        cls.settings = json.loads((Path(path) / "settings.json").read_text())
        return not cls.settings.get("bad_resource")

    def __init__(self, callback):
        self.callback = callback
        self.options = []
        self.tasks = []

    def get_version(self):
        return self.settings["version"]

    def connect(self, *args):
        time.sleep(self.settings.get("connect_delay", 0))
        return True

    def set_instance_option(self, key, value):
        self.options.append((key, value))
        return True

    def append_task(self, kind, params):
        if kind == "Rejected": return 0
        self.tasks.append(self.settings["build"])
        return self.tasks[-1]

    def set_task_params(self, task_id, params):
        self.callback(77, b'{"parameter_changed": true}', None)
        return True

    def start(self):
        if self.settings.get("reject_start"): return False
        for _ in range(self.settings.get("start_events", 0)):
            self.callback(77, b'{}', None)
        self.callback(10001, b'{"taskchain": "Fight"}', None)
        self.callback(20003, b'{"what": "StageDrops"}', None)
        return True

    def running(self):
        for _ in range(self.settings.get("extra_events", 0)):
            self.callback(77, b'{}', None)
        self.callback(10002, b'{"taskchain": "Fight"}', None)
        self.callback(3, b'{}', None)
        return False

    def stop(self):
        time.sleep(self.settings.get("stop_delay", 0))
        return True

    def get_tasks_list(self):
        return self.tasks
"""


@pytest.fixture
def installation(tmp_path, monkeypatch):
    monkeypatch.setenv("MOWER_ANDROID", "0")
    sdk = tmp_path / "Python/asst"
    sdk.mkdir(parents=True)
    (sdk / "__init__.py").write_text("")
    (sdk / "asst.py").write_text(SDK)
    (sdk / "utils.py").write_text(
        "class InstanceOptionType:\n touch_type=2\n adblite_enabled=4\n kill_on_adb_exit=5\n"
    )
    (tmp_path / "MaaCore.dll").write_bytes(b"first native build")
    (tmp_path / "settings.json").write_text(
        json.dumps({"version": "v1.0.0", "build": 17})
    )
    monkeypatch.setattr(runtime, "read_installed_version", lambda *a, **kw: "v1.0.0")
    yield tmp_path
    processes.close_idle_maa_processes(tmp_path)


def test_actual_worker_runs_tasks_and_drains_reentrant_callbacks(installation):
    seen = []
    holder = []

    def callback(message, detail, argument):
        seen.append(message)
        if message == 20003:
            assert holder[0].set_task_params(17, {"times": 0})

    instance = runtime.load_maa_process(installation, callback)
    holder.append(instance)
    process = instance._asst._process
    assert process.pid != os.getpid()
    assert instance.instance_options.touch_type == 2
    assert instance.connect("adb", "serial", "General")
    assert instance.append_task("Fight", {"stage": "1-7"}) == 17
    assert instance.start()
    assert not instance.running()
    assert instance.run_successful
    assert seen == [10001, 20003, 77, 10002, 3]
    instance.close()
    assert process.poll() is not None


def test_replacement_uses_new_build_without_restarting_parent(installation):
    parent_pid = os.getpid()
    first = runtime.load_maa_process(installation, None)
    first_process = first._asst._process
    first.close()
    replacement = installation / "replacement"
    replacement.write_bytes(b"second native build with same version string")
    replacement.replace(installation / "MaaCore.dll")
    (installation / "settings.json").write_text(
        json.dumps({"version": "v1.0.0", "build": 29})
    )
    second = runtime.load_maa_process(installation, None)
    assert second.get_version() == "v1.0.0"
    assert second.append_task("Build", {}) == 29
    assert second._asst._process.pid != first_process.pid
    assert os.getpid() == parent_pid
    second.close()


def test_update_cleanup_releases_idle_worker_with_retained_python_reference(
    installation,
):
    instance = runtime.load_maa_process(installation, None)
    process = instance._asst._process
    maa_update.clear_loaded_maa_cache(installation)
    assert process.poll() is not None
    assert not maa_instances_alive()
    with processes.installation_lease(installation, exclusive=True):
        pass
    with pytest.raises(processes.MaaProcessError, match="已关闭"):
        instance.get_version()


def test_rejected_resource_load_preserves_diagnostic_and_releases_lease(installation):
    (installation / "settings.json").write_text(json.dumps({"bad_resource": True}))
    with pytest.raises(MaaCallError, match="配置文件不存在"):
        runtime.load_maa_process(installation, None)
    with processes.installation_lease(installation, exclusive=True):
        pass


def test_real_worker_version_mismatch_is_rejected_before_connection(
    installation, monkeypatch
):
    monkeypatch.setattr(runtime, "read_installed_version", lambda *a, **kw: "v2.0.0")
    with pytest.raises(processes.MaaProcessError, match="不一致"):
        runtime.load_maa_process(installation, None)
    with processes.installation_lease(installation, exclusive=True):
        pass


def test_task_admission_and_start_rejection_keep_existing_errors(installation):
    instance = runtime.load_maa_process(installation, None)
    with pytest.raises(MaaCallError) as caught:
        instance.append_task("Rejected", {"stage": "1-7"})
    assert caught.value.operation == "append_task"
    instance.close()
    (installation / "settings.json").write_text(
        json.dumps({"version": "v1.0.0", "build": 17, "reject_start": True})
    )
    instance = runtime.load_maa_process(installation, None)
    with pytest.raises(MaaCallError) as caught:
        instance.start()
    assert caught.value.operation == "start"
    instance.close()


def test_dead_worker_fails_without_replaying_task(installation):
    instance = runtime.load_maa_process(installation, None)
    child = instance._asst._process
    child.kill()
    child.wait(3)
    with pytest.raises(processes.MaaProcessError, match="通信失败"):
        instance.append_task("Fight", {})
    assert instance._asst._closed
    instance.close()


def test_timeout_reaps_worker_and_releases_installation(installation):
    (installation / "settings.json").write_text(
        json.dumps({"version": "v1.0.0", "build": 17, "connect_delay": 10})
    )
    instance = runtime.load_maa_process(installation, None)
    instance._asst._timeout = 0.1
    process = instance._asst._process
    with pytest.raises(processes.MaaProcessError, match="通信失败"):
        instance.connect("adb", "serial", "General")
    assert process.poll() is not None
    instance.close()
    with processes.installation_lease(installation, exclusive=True):
        pass


def test_startup_failure_does_not_strand_worker_or_lease(installation):
    (installation / "Python/asst/asst.py").write_text(
        "raise RuntimeError('broken SDK')"
    )
    with pytest.raises(processes.MaaProcessError, match="broken SDK"):
        runtime.load_maa_process(installation, None)
    with processes.installation_lease(installation, exclusive=True):
        pass


def test_native_worker_is_reaped_after_owner_becomes_unreachable(installation):
    instance = runtime.load_maa_process(installation, None)
    child = instance._asst._process
    reference = weakref.ref(instance)
    del instance
    gc.collect()
    assert reference() is None
    assert child.poll() is not None


def test_shared_leases_allow_instances_and_reject_concurrent_installation(installation):
    script = (
        "import sys; from arknights_mower.utils.maa_process import installation_lease; "
        "lease=installation_lease(sys.argv[1]); print('ready', flush=True); sys.stdin.read()"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(installation)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    try:
        assert child.stdout.readline().rstrip(b"\r\n") == b"ready"
        with processes.installation_lease(installation):
            with pytest.raises(maa_update.MaaUpdateError, match="其他实例"):
                with processes.maa_installation_transaction(installation):
                    pytest.fail(
                        "installation was admitted during another instance's use"
                    )
    finally:
        child.stdin.close()
        child.wait(5)
        child.stdout.close()
    with processes.maa_installation_transaction(installation):
        pass


def test_frozen_worker_command_uses_launcher_not_python_c(monkeypatch):
    monkeypatch.setattr("arknights_mower.utils.update_runtime.frozen", lambda: True)
    assert processes.worker_command() == [sys.executable, "--maa-runtime-worker"]


def test_installation_alias_cannot_bypass_lease(installation):
    alias = installation.with_name(installation.name + "-alias")
    try:
        alias.symlink_to(installation, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")
    with processes.installation_lease(alias):
        with pytest.raises(maa_update.MaaUpdateError, match="其他实例"):
            processes.installation_lease(installation, exclusive=True)


def test_launcher_dispatches_worker_before_gui_initialization(
    installation, monkeypatch
):
    launcher = Path(__file__).resolve().parents[2] / "webview_ui.py"
    monkeypatch.setattr(
        processes,
        "worker_command",
        lambda: [sys.executable, str(launcher), "--maa-runtime-worker"],
    )
    instance = runtime.load_maa_process(installation, None)
    assert instance.append_task("Build", {}) == 17
    instance.close()


def test_parent_pipe_eof_exits_worker_and_releases_installation(installation):
    instance = runtime.load_maa_process(installation, None)
    child = instance._asst._process
    child.stdin.close()
    assert child.wait(5) == 0
    with pytest.raises(processes.MaaProcessError):
        instance.get_version()
    with processes.installation_lease(installation, exclusive=True):
        pass


def test_callback_overflow_fails_run_and_reaps_worker(installation):
    (installation / "settings.json").write_text(
        json.dumps(
            {
                "version": "v1.0.0",
                "build": 17,
                "extra_events": processes.MAX_EVENTS + 1,
            }
        )
    )
    instance = runtime.load_maa_process(installation, None)
    assert instance.start()
    with pytest.raises(processes.MaaProcessError, match="回调缓冲区溢出"):
        instance.running()
    assert not instance.run_successful
    assert instance._asst._process.poll() is not None


def test_close_has_short_deadline_and_reaps_stalled_stop(installation, monkeypatch):
    (installation / "settings.json").write_text(
        json.dumps(
            {
                "version": "v1.0.0",
                "build": 17,
                "stop_delay": 10,
            }
        )
    )
    instance = runtime.load_maa_process(installation, None)
    monkeypatch.setattr(processes, "CLOSE_TIMEOUT", 0.1)
    with pytest.raises(processes.MaaProcessError, match="通信失败"):
        instance.close()
    assert instance._asst._process.poll() is not None
    with processes.installation_lease(installation, exclusive=True):
        pass


def test_reentrant_callbacks_cannot_grow_parent_queue_without_bound(installation):
    (installation / "settings.json").write_text(
        json.dumps(
            {
                "version": "v1.0.0",
                "build": 17,
                "start_events": processes.MAX_EVENTS - 2,
            }
        )
    )
    holder = []

    def callback(*args):
        holder[0].running()

    instance = processes.MaaProcess(installation, callback)
    holder.append(instance)
    with pytest.raises(processes.MaaProcessError, match="回调缓冲区溢出"):
        instance.start()
    assert instance._closed
    assert not instance._events
    assert instance._process.poll() is not None


def test_successful_backup_cleanup_waits_for_worker_and_other_readers(installation):
    backup = installation / ".old"
    backup.mkdir()
    (backup / "retained").write_text("old core")
    instance = runtime.load_maa_process(installation, None)
    assert instance.start()
    assert not instance.running()
    assert backup.exists()
    with processes.installation_lease(installation):
        instance.close()
        instance._cleanup_thread.join(3)
        assert not instance._retired
        assert backup.exists()
    instance._cleanup()
    instance._cleanup_thread.join(3)
    assert instance._retired
    assert not backup.exists()


def test_same_version_replacement_during_worker_start_is_rejected(
    installation, monkeypatch
):
    factory = processes.MaaProcess

    def replace_core(target, callback):
        worker = factory(target, callback)
        (installation / "MaaCore.dll").write_bytes(b"changed after process launch")
        return worker

    monkeypatch.setattr(processes, "MaaProcess", replace_core)
    with pytest.raises(processes.MaaProcessError, match="不一致"):
        runtime.load_maa_process(installation, None)
    with processes.installation_lease(installation, exclusive=True):
        pass


def test_update_job_activates_new_worker_without_restart_warning(
    installation, monkeypatch
):
    import server

    first = runtime.load_maa_process(installation, None)
    first_process = first._asst._process
    monkeypatch.setattr(server, "maa_update_job", {})

    def install(target, **kwargs):
        with processes.maa_installation_transaction(target):
            (installation / "MaaCore.dll").write_bytes(b"replacement core")
            (installation / "settings.json").write_text(
                json.dumps({"version": "v1.0.0", "build": 29})
            )
        return {
            "updated": True,
            "target": str(target),
            "operation": "update",
            "platform": "darwin",
            "channel": "beta",
            "version": "v1.0.0",
            "source": "github",
            "python_downloaded": 0,
            "python_full_size": 0,
        }

    monkeypatch.setattr(maa_update, "install_latest_maa", install)
    monkeypatch.setattr(maa_update, "read_installed_version", lambda *a, **kw: "v1.0.0")
    server._run_maa_update(str(installation), "github", "", "darwin", "beta")
    assert server.maa_update_job["status"] == "success"
    assert not server.maa_update_job["result"]["restart_required"]
    assert "请重启" not in server.maa_update_job["message"]
    assert first_process.poll() is not None
    second = runtime.load_maa_process(installation, None)
    assert second.append_task("Build", {}) == 29
    second.close()


@pytest.mark.parametrize("nodelete", [False, True])
def test_actual_native_core_replacement_uses_fresh_process(
    tmp_path, monkeypatch, nodelete
):
    from arknights_mower.tests.maa_runtime_native_tests import CORE
    from arknights_mower.tests.maa_runtime_native_tests import SDK as NATIVE_SDK

    compiler = shutil.which("cc")
    if os.name == "nt" or compiler is None:
        pytest.skip("native fixture requires a POSIX C compiler")
    if nodelete and sys.platform != "linux":
        pytest.skip("NODELETE is a Linux loader flag")
    monkeypatch.setenv("MOWER_ANDROID", "0")
    core_name = "libMaaCore.dylib" if sys.platform == "darwin" else "libMaaCore.so"
    target = tmp_path / "maa"
    sdk = target / "Python/asst"
    sdk.mkdir(parents=True)
    (sdk / "__init__.py").write_text("")
    (sdk / "utils.py").write_text("class InstanceOptionType:\n touch_type=2\n")
    (sdk / "asst.py").write_text(
        f"CORE_NAME={core_name!r}\n"
        + NATIVE_SDK
        + """
    def connect(self, *args):
        return True
    def append_task(self, kind, params):
        return Asst.__lib.AsstBuild()
"""
    )
    source = tmp_path / "core.c"
    source.write_text(CORE)
    for build in (1, 2):
        output = tmp_path / f"build-{build}"
        subprocess.run(
            [
                compiler,
                "-shared",
                "-fPIC",
                f"-DBUILD_ID={build}",
                *(["-Wl,-z,nodelete"] if nodelete else []),
                str(source),
                "-o",
                str(output),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        output.replace(target / core_name)
        instance = runtime.load_maa_process(target, None)
        child = instance._asst._process
        assert instance.get_version() == "v1.0.0"
        assert instance.append_task("Build", {}) == build
        if sys.platform == "darwin":
            with pytest.raises(maa_update.MaaUpdateError, match="仍被其他进程使用"):
                with processes.maa_client_guard(target):
                    pytest.fail("a mapped native core passed update admission")
        instance.close()
        assert child.poll() is not None
        if sys.platform == "darwin":
            with processes.maa_client_guard(target):
                pass


def test_android_cache_cleanup_does_not_touch_desktop_workers(monkeypatch):
    monkeypatch.setenv("MOWER_ANDROID", "1")
    close = Mock()
    monkeypatch.setattr(processes, "close_idle_maa_processes", close)
    maa_update.clear_loaded_maa_cache("/android/component")
    close.assert_not_called()


def test_android_installation_keeps_host_coordination(monkeypatch):
    monkeypatch.setenv("MOWER_ANDROID", "1")
    close = Mock(side_effect=AssertionError("desktop cleanup reached Android"))
    lease = Mock(side_effect=AssertionError("desktop lease reached Android"))
    monkeypatch.setattr(processes, "close_idle_maa_processes", close)
    monkeypatch.setattr(processes, "installation_lease", lease)
    with processes.maa_installation_transaction("/android/component"):
        pass
    close.assert_not_called()
    lease.assert_not_called()
