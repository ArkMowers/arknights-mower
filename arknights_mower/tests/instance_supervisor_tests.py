"""Actual temporary child exits; no application instances or device access."""

import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.utils import instance_supervisor as supervisor
from arknights_mower.utils import update_runtime as runtime


@pytest.fixture
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "updates")
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[2]))
    monkeypatch.setenv("MOWER_RECOVERY_RUN", "1")
    return tmp_path


def child_script(directory, body):
    script = directory / "child.py"
    script.write_text(
        "import json, os, time\n"
        "from pathlib import Path\n"
        "from arknights_mower.utils.instance_supervisor import child_report, child_exit, instance_lock\n"
        "from arknights_mower.utils import update_runtime as runtime\n"
        f"trace = Path({str(directory / 'trace.json')!r})\n"
        "events = json.loads(trace.read_text()) if trace.exists() else []\n"
        "events.append({'pid':os.getpid(),'time':time.monotonic(),'resume':os.environ.get('MOWER_RESUME_RUN')})\n"
        "trace.write_text(json.dumps(events))\n"
        "child_report(ready=True)\n" + body,
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


def test_crash_restores_one_child_after_backoff_and_removes_auto_resume(
    isolated_runtime,
):
    directory = isolated_runtime
    command = child_script(
        directory, "if len(events) == 1: os._exit(23)\nchild_exit('window')\n"
    )
    env = dict(os.environ, MOWER_RESUME_RUN="1")
    code = supervisor.supervise(
        command, directory, delays=(0.12,), poll_interval=0.01, environment=env
    )
    events = runtime.read_json(directory / "trace.json")
    assert code == 0
    assert len(events) == 2
    assert events[0]["pid"] != events[1]["pid"]
    assert events[1]["time"] - events[0]["time"] >= 0.12
    assert events[0]["resume"] == "1" and events[1]["resume"] is None
    notice = runtime.read_json(directory / "recovery.json")
    assert notice["active"] is True and notice["exit_code"] == 23
    assert notice["phase"] == "waiting"
    assert not list(directory.glob("child-*.json"))


@pytest.mark.parametrize("mode, active", [("1", True), ("2", True), ("2", False)])
def test_crash_preserves_requested_start_mode_only_during_pending_recovery(
    isolated_runtime, mode, active
):
    directory = isolated_runtime
    command = child_script(
        directory,
        "if len(events) == 1:\n"
        f" runtime.write_json(Path({str(directory / 'recovery.json')!r}), "
        f"{{'active': {active!r}, 'start_type': {mode!r}, 'resume_requested': True}})\n"
        " os._exit(23)\n"
        "child_exit('window')\n",
    )
    assert (
        supervisor.supervise(command, directory, delays=(0.01,), poll_interval=0.01)
        == 0
    )
    notice = runtime.read_json(directory / "recovery.json")
    assert notice.get("start_type", "0") == (mode if active else "0")


@pytest.mark.parametrize(
    "error",
    [OSError("Windows commit allocation refused"), MemoryError("allocation refused")],
)
def test_process_creation_failure_cools_down_and_retries(
    isolated_runtime, monkeypatch, error
):
    command = child_script(isolated_runtime, "child_exit('window')\n")
    real_popen = subprocess.Popen
    attempts = []

    def launch(*args, **kwargs):
        attempts.append(time.monotonic())
        if len(attempts) == 1:
            raise error
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", launch)
    assert (
        supervisor.supervise(
            command, isolated_runtime, delays=(0.04,), poll_interval=0.01
        )
        == 0
    )
    assert len(attempts) == 2 and attempts[1] - attempts[0] >= 0.04
    assert (
        runtime.read_json(isolated_runtime / "recovery.json")["reason"]
        == "process_creation"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="Windows startup ownership")
@pytest.mark.parametrize(
    "stage, failure",
    [
        ("intent", OSError),
        ("intent", MemoryError),
        ("job", OSError),
        ("job", MemoryError),
        ("assign", OSError),
        ("resume", OSError),
    ],
)
def test_windows_startup_resource_failure_retries_and_closes_intent(
    isolated_runtime, monkeypatch, stage, failure
):
    command = child_script(isolated_runtime, "child_exit('window')\n")
    original_mapping = supervisor.mmap.mmap
    original_job = supervisor.WindowsInstanceJob
    attempts, mappings, jobs, processes = [], [], [], []

    class TrackedMapping:
        def __init__(self, shared):
            self.shared = shared
            self.closed = False

        def __getitem__(self, key):
            return self.shared[key]

        def __setitem__(self, key, value):
            self.shared[key] = value

        def close(self):
            self.shared.close()
            self.closed = True

    def mapping(*args, **kwargs):
        if stage == "intent":
            attempts.append(time.monotonic())
            if len(attempts) == 1:
                raise failure("startup allocation refused")
        shared = TrackedMapping(original_mapping(*args, **kwargs))
        mappings.append(shared)
        return shared

    def job():
        if stage != "intent":
            attempts.append(time.monotonic())
            if len(attempts) == 1 and stage == "job":
                raise failure("startup allocation refused")
            if len(attempts) > 1:
                assert mappings[0].closed, "failed startup retained its intent mapping"
                assert all(child.poll() is not None for child in processes)
                assert all(owned.closed for owned in jobs)
        owned = original_job()
        owned.closed = False
        jobs.append(owned)
        original_close, original_start = owned.close, owned.start

        def close():
            original_close()
            owned.closed = True

        def start(process):
            processes.append(process)
            original_start(process)

        owned.close, owned.start = close, start
        if len(attempts) == 1 and stage == "assign":
            owned.kernel.AssignProcessToJobObject = lambda *args: False
        if len(attempts) == 1 and stage == "resume":
            owned.resume = lambda handle: 1
        return owned

    monkeypatch.setattr(supervisor.mmap, "mmap", mapping)
    monkeypatch.setattr(supervisor, "WindowsInstanceJob", job)
    assert (
        supervisor.supervise(
            command, isolated_runtime, delays=(0.04,), poll_interval=0.01
        )
        == 0
    )
    assert len(attempts) == 2 and attempts[1] - attempts[0] >= 0.04
    assert len(runtime.read_json(isolated_runtime / "trace.json")) == 1
    assert runtime.read_json(isolated_runtime / "recovery.json")["reason"] == (
        "process_creation"
    )
    assert all(shared.closed for shared in mappings)
    assert all(owned.closed for owned in jobs)
    assert all(child.poll() is not None for child in processes)


@pytest.mark.parametrize("desired_running", [False, True])
@pytest.mark.parametrize("creation_failure", [False, True])
def test_unknown_initial_intent_is_resolved_from_actual_startup_policy(
    isolated_runtime, monkeypatch, desired_running, creation_failure
):
    script = isolated_runtime / "startup-policy.py"
    script.write_text(
        "import json, os\nfrom pathlib import Path\nfrom types import SimpleNamespace\n"
        "from arknights_mower.utils.instance_supervisor import child_ready, child_exit\n"
        "from arknights_mower.utils import crash_recovery, update_runtime as runtime\n"
        f"directory=Path({str(isolated_runtime)!r})\n"
        "trace=directory/'startup-trace.json'\n"
        "events=runtime.read_json(trace,[])\nevents.append(os.getpid())\n"
        "runtime.write_json(trace,events)\n"
        + ("if len(events)==1: os._exit(23)\n" if not creation_failure else "")
        + "before=runtime.read_json(directory/'recovery.json')\n"
        + "registration=SimpleNamespace(record={'port':59998,'running':False},request=directory/'shutdown')\n"
        + f"child_ready(registration,desired_running={desired_running!r})\n"
        + "runtime.write_json(directory/'policy.json',{'before':before,'status':crash_recovery.status()})\n"
        + "child_exit('window')\n",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    for key in ("MOWER_RESUME_MODE", "MOWER_RESUME_RUN", "MOWER_RECOVERY_RUN"):
        environment.pop(key, None)
    if creation_failure:
        original = subprocess.Popen
        launched = []

        def launch(*args, **kwargs):
            launched.append(1)
            if len(launched) == 1:
                raise MemoryError("initial Windows commit refusal")
            return original(*args, **kwargs)

        monkeypatch.setattr(subprocess, "Popen", launch)
    assert (
        supervisor.supervise(
            [sys.executable, str(script)],
            isolated_runtime,
            delays=(0.01,),
            poll_interval=0.01,
            environment=environment,
        )
        == 0
    )
    policy = runtime.read_json(isolated_runtime / "policy.json")
    assert "resume_requested" not in policy["before"]
    assert policy["status"]["automatic"] is desired_running
    assert policy["status"]["resume_requested"] is desired_running


@pytest.mark.skipif(sys.platform != "win32", reason="named Windows intent map")
@pytest.mark.parametrize("active_notice", [False, True])
def test_initial_ready_publishing_cannot_override_earlier_user_stop(
    isolated_runtime, monkeypatch, active_notice
):
    import mmap
    from uuid import uuid4

    from arknights_mower.utils import crash_recovery

    name = f"Local\\MowerStopReadyTest_{uuid4().hex}"
    monkeypatch.setenv("MOWER_SUPERVISOR_DIRECTORY", str(isolated_runtime))
    monkeypatch.setenv("MOWER_SUPERVISOR_INTENT", name)
    monkeypatch.setattr(crash_recovery, "_cancelled", False)
    monkeypatch.setattr(crash_recovery, "_progress", {})
    if active_notice:
        runtime.write_json(isolated_runtime / "recovery.json", {"active": True})
    with mmap.mmap(-1, 1, tagname=name, access=mmap.ACCESS_WRITE) as intent:
        intent[0] = 255
        supervisor.task_intent(False)
        crash_recovery.cancel()
        supervisor.child_ready(
            SimpleNamespace(
                record={"port": 59998, "running": False},
                request=isolated_runtime / "shutdown",
            ),
            desired_running=True,
        )
        assert intent[0] == 0
        assert not crash_recovery.status()["automatic"]


@pytest.mark.skipif(sys.platform != "win32", reason="named Windows intent map")
@pytest.mark.parametrize("active_notice", [False, True])
def test_initial_ready_publishing_preserves_accepted_user_start(
    isolated_runtime, monkeypatch, active_notice
):
    import mmap
    from uuid import uuid4

    from arknights_mower.utils import crash_recovery

    name = f"Local\\MowerStartReadyTest_{uuid4().hex}"
    monkeypatch.setenv("MOWER_SUPERVISOR_DIRECTORY", str(isolated_runtime))
    monkeypatch.setenv("MOWER_SUPERVISOR_INTENT", name)
    monkeypatch.setattr(crash_recovery, "_cancelled", False)
    monkeypatch.setattr(crash_recovery, "_progress", {})
    if active_notice:
        runtime.write_json(isolated_runtime / "recovery.json", {"active": True})
    with mmap.mmap(-1, 1, tagname=name, access=mmap.ACCESS_WRITE) as intent:
        intent[0] = 255
        supervisor.task_intent(True)
        supervisor.child_ready(
            SimpleNamespace(
                record={"port": 59998, "running": False},
                request=isolated_runtime / "shutdown",
            ),
            desired_running=False,
        )
        assert intent[0] == 1
        if active_notice:
            assert crash_recovery.status()["automatic"]


def test_http_nonresponsiveness_recycles_only_owned_instance(isolated_runtime):
    command = child_script(
        isolated_runtime,
        "from arknights_mower.utils.instance_supervisor import task_intent\nchild_report(port=58991)\ntask_intent(True)\nif len(events)==1: time.sleep(5)\nchild_exit('window')\n",
    )
    innocent = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(5)"])
    try:
        assert (
            supervisor.supervise(
                command,
                isolated_runtime,
                delays=(0,),
                poll_interval=0.01,
                health_interval=0.02,
                health_failure_window=0.06,
                health_probe=lambda port, timeout: False,
            )
            == 0
        )
        assert innocent.poll() is None
        notice = runtime.read_json(isolated_runtime / "recovery.json")
        assert notice["reason"] == "http_unresponsive" and notice["resume_requested"]
        assert len(runtime.read_json(isolated_runtime / "trace.json")) == 2
    finally:
        innocent.terminate()
        innocent.wait(timeout=5)


def test_long_scheduler_wait_is_kept_while_http_is_healthy(isolated_runtime):
    command = child_script(
        isolated_runtime,
        "child_report(port=58991)\ntime.sleep(.2)\nchild_exit('window')\n",
    )
    probe = Mock(return_value=True)
    assert (
        supervisor.supervise(
            command,
            isolated_runtime,
            delays=(),
            cooldowns=(0,),
            poll_interval=0.01,
            health_interval=0.02,
            health_failure_window=0.04,
            health_probe=probe,
        )
        == 0
    )
    assert probe.call_count > 2 and not (isolated_runtime / "recovery.json").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows named shared intent")
def test_stop_intent_survives_json_write_failure_followed_by_native_exit(
    isolated_runtime,
):
    command = child_script(
        isolated_runtime,
        "from arknights_mower.utils.instance_supervisor import task_intent\n"
        "if len(events)==1:\n task_intent(True)\n"
        " def failed(*args,**kwargs): raise OSError('disk full')\n runtime.write_json=failed\n"
        " try: task_intent(False)\n except OSError: pass\n os._exit(23)\n"
        "child_exit('window')\n",
    )
    assert (
        supervisor.supervise(command, isolated_runtime, delays=(0,), poll_interval=0.01)
        == 0
    )
    notice = runtime.read_json(isolated_runtime / "recovery.json")
    assert notice["resume_requested"] is False


def test_repeated_exits_continue_after_fast_retries_with_bounded_cooldown(
    isolated_runtime,
):
    command = child_script(
        isolated_runtime, "if len(events)<5: os._exit(19)\nchild_exit('window')\n"
    )
    assert (
        supervisor.supervise(
            command,
            isolated_runtime,
            delays=(0.01, 0.01, 0.01),
            cooldowns=(0.06, 0.08),
            poll_interval=0.01,
        )
        == 0
    )
    events = runtime.read_json(isolated_runtime / "trace.json")
    assert len(events) == 5
    assert events[-1]["time"] - events[-2]["time"] >= 0.06


@pytest.mark.parametrize("reason", ["window", "tray", "ctrl_c", "runtime_request"])
def test_intentional_exit_does_not_restart(isolated_runtime, reason):
    command = child_script(isolated_runtime, f"child_exit({reason!r})\nos._exit(11)\n")
    assert (
        supervisor.supervise(command, isolated_runtime, delays=(0,), poll_interval=0.01)
        == 11
    )
    assert len(runtime.read_json(isolated_runtime / "trace.json")) == 1
    assert not (isolated_runtime / "recovery.json").exists()


def test_intentional_report_write_failure_closes_before_fallback_exit(isolated_runtime):
    command = child_script(
        isolated_runtime,
        "import webview_ui\nfrom arknights_mower.utils import instance_supervisor as owner\n"
        "from arknights_mower.utils.lifecycle import shutdown\n"
        "webview_ui._run_desktop=lambda: None\n"
        "def broken_report(reason): raise OSError('disk full')\n"
        "owner.child_exit=broken_report\n"
        f"shutdown.close=lambda reason: Path({str(isolated_runtime / 'closed')!r}).touch()\n"
        "webview_ui.run_desktop()\n",
    )
    assert (
        supervisor.supervise(command, isolated_runtime, delays=(0,), poll_interval=0.01)
        == supervisor.INTENTIONAL_EXIT_CODE
    )
    assert (isolated_runtime / "closed").exists()
    assert len(runtime.read_json(isolated_runtime / "trace.json")) == 1
    assert not (isolated_runtime / "recovery.json").exists()


def test_internal_device_fatal_exit_restarts_and_preserves_run_intent(isolated_runtime):
    command = child_script(
        isolated_runtime,
        "if len(events)==1:\n"
        " import webview_ui\n from arknights_mower.utils.lifecycle import shutdown\n"
        " from arknights_mower.utils.instance_supervisor import task_intent\n task_intent(True)\n"
        " shutdown.reason='device_recovery_failed'\n shutdown.close=lambda reason: None\n"
        " webview_ui._run_desktop=lambda:None\n webview_ui.run_desktop()\n"
        "else: child_exit('window')\n",
    )
    assert (
        supervisor.supervise(command, isolated_runtime, delays=(0,), poll_interval=0.01)
        == 0
    )
    notice = runtime.read_json(isolated_runtime / "recovery.json")
    assert (
        notice["resume_requested"]
        and len(runtime.read_json(isolated_runtime / "trace.json")) == 2
    )


def test_unmarked_native_exit_zero_still_recovers_automatically(isolated_runtime):
    command = child_script(
        isolated_runtime, "if len(events)==1: os._exit(0)\nchild_exit('window')\n"
    )
    assert (
        supervisor.supervise(command, isolated_runtime, delays=(0,), poll_interval=0.01)
        == 0
    )
    assert runtime.read_json(isolated_runtime / "recovery.json")["active"]
    assert len(runtime.read_json(isolated_runtime / "trace.json")) == 2


def test_pending_shutdown_request_suppresses_crash_restart(isolated_runtime):
    request = isolated_runtime / "shutdown.json"
    command = child_script(
        isolated_runtime,
        f"request = Path({str(request)!r})\nrequest.write_text('{{}}')\n"
        "child_report(shutdown_request=str(request))\nos._exit(17)\n",
    )
    assert (
        supervisor.supervise(command, isolated_runtime, delays=(0,), poll_interval=0.01)
        == 17
    )
    assert len(runtime.read_json(isolated_runtime / "trace.json")) == 1


def test_active_replacement_job_suppresses_crash_restart(isolated_runtime, monkeypatch):
    command = child_script(isolated_runtime, "os._exit(21)\n")
    monkeypatch.setattr(runtime, "active_job", lambda state: True)
    assert (
        supervisor.supervise(command, isolated_runtime, delays=(0,), poll_interval=0.01)
        == 21
    )
    assert len(runtime.read_json(isolated_runtime / "trace.json")) == 1


def test_startup_deadline_stops_only_owned_child(isolated_runtime):
    script = isolated_runtime / "slow.py"
    script.write_text(
        "import time\nfrom pathlib import Path\n"
        "from arknights_mower.utils.instance_supervisor import child_report,child_exit\n"
        f"flag=Path({str(isolated_runtime / 'attempted')!r})\n"
        "if not flag.exists():\n flag.touch()\n time.sleep(5)\n"
        "child_report(ready=True)\nchild_exit('window')\n",
        encoding="utf-8",
    )
    innocent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        code = supervisor.supervise(
            [sys.executable, str(script)],
            isolated_runtime,
            startup_timeout=2.0,
            delays=(0,),
            poll_interval=0.01,
        )
        assert code == 0
        assert (
            runtime.read_json(isolated_runtime / "failure.json")["reason"]
            == "startup_timeout"
        )
        assert innocent.poll() is None
    finally:
        innocent.terminate()
        innocent.wait(timeout=5)


def test_same_configuration_lock_survives_different_installation_roots(
    isolated_runtime, monkeypatch
):
    arguments = [str(isolated_runtime / "configuration"), "name"]
    first = supervisor.supervisor_directory(arguments)
    monkeypatch.setattr(
        runtime, "state_dir", lambda: isolated_runtime / "another-installation"
    )
    second = supervisor.supervisor_directory(arguments)
    assert first == second
    with supervisor.instance_lock(first, timeout=0):
        with pytest.raises(RuntimeError):
            with supervisor.instance_lock(second, timeout=0):
                pytest.fail("duplicate configuration-space owner")


def test_replacement_waits_for_guardian_release_without_terminating_it(
    isolated_runtime,
):
    ready = isolated_runtime / "guardian-ready"
    guardian = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import time\nfrom pathlib import Path\n"
            "from arknights_mower.utils.instance_supervisor import instance_lock\n"
            f"with instance_lock({str(isolated_runtime)!r},timeout=0):\n"
            f" Path({str(ready)!r}).touch()\n time.sleep(.5)\n",
        ]
    )
    try:
        deadline = time.monotonic() + 5
        while not ready.exists():
            assert guardian.poll() is None and time.monotonic() < deadline
            time.sleep(0.01)
        record = {"supervision_directory": str(isolated_runtime)}
        with pytest.raises(RuntimeError):
            supervisor.wait_for_release(record, time.monotonic() + 0.03)
        assert guardian.poll() is None
        supervisor.wait_for_release(record, deadline)
        guardian.wait(timeout=5)
    finally:
        if guardian.poll() is None:
            guardian.terminate()
            guardian.wait(timeout=5)


def test_surviving_child_excludes_new_launcher_after_guardian_exit(
    isolated_runtime, monkeypatch
):
    directory = isolated_runtime / "configuration/tmp/process-supervision"
    script = isolated_runtime / "survivor.py"
    script.write_text(
        "import os,time\nfrom pathlib import Path\n"
        "from arknights_mower.utils.instance_supervisor import instance_lock\n"
        f"with instance_lock({str(directory)!r},timeout=0,child=True):\n"
        f" Path({str(isolated_runtime / 'child-ready')!r}).write_text(str(os.getpid()))\n"
        " time.sleep(2)\n",
        encoding="utf-8",
    )
    guardian = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import subprocess,time\nfrom arknights_mower.utils.instance_supervisor import instance_lock\n"
            f"with instance_lock({str(directory)!r},timeout=0):\n"
            f" subprocess.Popen([{sys.executable!r},{str(script)!r}])\n time.sleep(5)\n",
        ]
    )
    try:
        deadline = time.monotonic() + 5
        while not (isolated_runtime / "child-ready").exists():
            assert guardian.poll() is None and time.monotonic() < deadline
            time.sleep(0.01)
        guardian.terminate()
        guardian.wait(timeout=5)
        monkeypatch.setattr(supervisor, "supervisor_directory", lambda args: directory)
        launch = Mock()
        monkeypatch.setattr(supervisor, "supervise", launch)
        with pytest.raises(RuntimeError):
            supervisor.run_launcher([])
        launch.assert_not_called()
    finally:
        if guardian.poll() is None:
            guardian.terminate()
            guardian.wait(timeout=5)
        # The temporary surviving child self-exits; no PID-based termination.
        with supervisor.instance_lock(directory, timeout=5, child=True):
            pass


def test_source_and_frozen_arguments_keep_instance_identity():
    args = [r"D:\config space\设备", "one"]
    assert supervisor.child_command(
        args, executable="python.exe", entry="webview_ui.py", frozen=False
    ) == ["python.exe", "webview_ui.py", "--supervised-instance", *args]
    assert supervisor.child_command(args, executable="mower.exe", frozen=True) == [
        "mower.exe",
        "--supervised-instance",
        *args,
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job ownership")
def test_job_retains_exact_leaf_handle_and_rejects_unrelated_pid(isolated_runtime):
    job = supervisor.WindowsInstanceJob()
    owned = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        creationflags=0x00000004,
    )
    outsider = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    retained = None
    try:
        job.start(owned)
        retained = supervisor.OwnedWindowsProcess(owned.pid, job)
        assert retained.poll() is None
        with pytest.raises(RuntimeError, match="不属于"):
            supervisor.OwnedWindowsProcess(outsider.pid, job)
        assert outsider.poll() is None
        retained.stop()
        assert retained.poll() is not None
    finally:
        if retained is not None:
            retained.close()
        for child in (owned, outsider):
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=5)
        job.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher descendant")
def test_wrapper_exit_waits_for_real_registered_leaf(isolated_runtime):
    leaf = isolated_runtime / "leaf.py"
    ready = isolated_runtime / "leaf-ready"
    leaf.write_text(
        "import time,os\nfrom pathlib import Path\n"
        "from arknights_mower.utils.instance_supervisor import child_report,child_exit\n"
        "child_report(ready=True)\n"
        f"Path({str(ready)!r}).touch()\n"
        f"flag=Path({str(isolated_runtime / 'leaf-attempt')!r})\n"
        "prior=flag.exists()\nflag.touch()\ntime.sleep(1.5)\n"
        "if prior: child_exit('window')\nos._exit(29)\n",
        encoding="utf-8",
    )
    wrapper = isolated_runtime / "wrapper.py"
    wrapper.write_text(
        "import subprocess,time,os\nfrom pathlib import Path\n"
        f"Path({str(ready)!r}).unlink(missing_ok=True)\n"
        f"subprocess.Popen([{sys.executable!r},{str(leaf)!r}])\n"
        f"while not Path({str(ready)!r}).exists(): time.sleep(.01)\n"
        "os._exit(7)\n",
        encoding="utf-8",
    )
    started = time.monotonic()
    assert (
        supervisor.supervise(
            [sys.executable, str(wrapper)],
            isolated_runtime,
            delays=(),
            cooldowns=(0,),
            poll_interval=0.6,
        )
        == 29
    )
    assert time.monotonic() - started >= 1.5
    assert runtime.read_json(isolated_runtime / "recovery.json")["exit_code"] == 29
