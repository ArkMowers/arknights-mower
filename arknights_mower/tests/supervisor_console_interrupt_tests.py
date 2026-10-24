"""Isolated Windows console broadcasts exercise launcher shutdown without devices."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from arknights_mower.utils import instance_supervisor as supervisor
from arknights_mower.utils import update_runtime as runtime


def test_interrupt_while_waiting_for_lock_preserves_existing_owner(
    tmp_path, monkeypatch
):
    previous = signal.getsignal(signal.SIGINT)
    monkeypatch.setattr(supervisor, "supervisor_directory", lambda args: tmp_path)
    launched = []
    monkeypatch.setattr(
        supervisor, "supervise", lambda *args, **kwargs: launched.append(1)
    )
    slept = runtime.time.sleep

    def interrupt_wait(seconds):
        signal.raise_signal(signal.SIGINT)
        slept(seconds)

    with supervisor.instance_lock(tmp_path, timeout=0):
        monkeypatch.setattr(runtime.time, "sleep", interrupt_wait)
        assert supervisor.run_launcher([]) == supervisor.INTENTIONAL_EXIT_CODE
        with pytest.raises(RuntimeError):
            with supervisor.instance_lock(tmp_path, timeout=0):
                pytest.fail("existing owner was released")
    assert not launched
    assert signal.getsignal(signal.SIGINT) is previous
    with supervisor.instance_lock(tmp_path, timeout=0):
        pass


@pytest.mark.skipif(sys.platform != "win32", reason="Windows suspended child creation")
def test_interrupt_during_child_creation_waits_for_cooperative_close(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "updates")
    monkeypatch.setattr(supervisor, "supervisor_directory", lambda args: tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[2]))
    child = tmp_path / "child.py"
    child.write_text(
        "import time\nfrom pathlib import Path\n"
        "from arknights_mower.utils.instance_supervisor import child_report,child_exit,instance_lock\n"
        f"directory=Path({str(tmp_path)!r})\nrequest=directory/'shutdown.json'\n"
        "with instance_lock(directory,child=True):\n"
        " child_report(ready=True,shutdown_request=str(request))\n"
        " while not request.exists(): time.sleep(.01)\n"
        " child_exit('runtime_request')\n (directory/'closed').touch()\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        supervisor, "child_command", lambda args: [sys.executable, str(child)]
    )
    popen = subprocess.Popen

    def interrupted_creation(*args, **kwargs):
        process = popen(*args, **kwargs)
        signal.raise_signal(signal.SIGINT)
        return process

    monkeypatch.setattr(subprocess, "Popen", interrupted_creation)
    assert supervisor.run_launcher([]) == supervisor.INTENTIONAL_EXIT_CODE
    assert (tmp_path / "closed").exists()
    assert not (tmp_path / "recovery.json").exists()
    with supervisor.instance_lock(tmp_path, timeout=0, child=True):
        pass


def test_interrupt_during_backoff_retains_fault_and_cancels_replacement(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "updates")
    monkeypatch.setattr(supervisor, "supervisor_directory", lambda args: tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[2]))
    child = tmp_path / "crash.py"
    child.write_text(
        "import os\nfrom pathlib import Path\n"
        "from arknights_mower.utils.instance_supervisor import child_report\n"
        f"with Path({str(tmp_path / 'launches')!r}).open('a') as stream: stream.write('start\\n')\n"
        "child_report(ready=True)\nos._exit(23)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        supervisor, "child_command", lambda args: [sys.executable, str(child)]
    )
    supervise = supervisor.supervise
    monkeypatch.setattr(
        supervisor,
        "supervise",
        lambda *args, **kwargs: supervise(
            *args, **kwargs, delays=(30,), poll_interval=0.01
        ),
    )
    slept = runtime.time.sleep
    before = {}

    def interrupt_backoff(seconds):
        if (
            runtime.read_json(tmp_path / "supervisor.json", {}).get("phase")
            == "backoff"
        ):
            before.update(runtime.read_json(tmp_path / "recovery.json"))
            signal.raise_signal(signal.SIGINT)
        slept(seconds)

    monkeypatch.setattr(runtime.time, "sleep", interrupt_backoff)
    assert supervisor.run_launcher([]) == supervisor.INTENTIONAL_EXIT_CODE
    assert (tmp_path / "launches").read_text().splitlines() == ["start"]
    notice = runtime.read_json(tmp_path / "recovery.json")
    assert notice["active"] is True and notice["reason"] == "process_exit"
    assert notice["occurred_at"] == before["occurred_at"]
    assert notice["resume_requested"] is False and notice["phase"] == "stopped"


@pytest.mark.parametrize("raw", ['{"active":true', '{"active":"unknown"}', "[]"])
def test_console_stop_keeps_damaged_notice_unchanged(tmp_path, monkeypatch, raw):
    path = tmp_path / "recovery.json"
    path.write_text(raw)
    monkeypatch.setattr(supervisor, "supervisor_directory", lambda args: tmp_path)

    def stopped(*args, **kwargs):
        signal.raise_signal(signal.SIGINT)
        return supervisor.INTENTIONAL_EXIT_CODE

    monkeypatch.setattr(supervisor, "supervise", stopped)
    assert supervisor.run_launcher([]) == supervisor.INTENTIONAL_EXIT_CODE
    assert path.read_text() == raw


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shared console")
@pytest.mark.parametrize("case", ["graceful", "cleanup", "force", "deadline"])
def test_console_interrupt_keeps_shutdown_owned_and_lock_cleanup_complete(
    tmp_path, case
):
    root = Path(__file__).resolve().parents[2]
    child = tmp_path / "child.py"
    child.write_text(
        "import os,signal,time\nfrom pathlib import Path\n"
        "from arknights_mower.utils.instance_supervisor import child_report,child_exit,instance_lock\n"
        f"directory=Path({str(tmp_path)!r})\n"
        "request=directory/'shutdown.json'\n"
        "with instance_lock(directory,child=True):\n"
        " child_report(ready=True,shutdown_request=str(request))\n"
        " (directory/'child-ready').touch()\n"
        " while not request.exists(): time.sleep(.01)\n"
        " child_exit('runtime_request')\n"
        " (directory/'child-stopping').touch()\n"
        f" time.sleep({30 if case in ('force', 'deadline') else 0.1})\n"
        " (directory/'child-closed').touch()\n",
        encoding="utf-8",
    )
    harness = tmp_path / "harness.py"
    harness.write_text(
        "import ctypes,json,signal,subprocess,sys,threading,time\n"
        "from contextlib import contextmanager\nfrom pathlib import Path\n"
        "from arknights_mower.utils import instance_supervisor as owner,update_runtime as runtime\n"
        f"directory=Path({str(tmp_path)!r})\ncase={case!r}\n"
        "runtime.state_dir=lambda: directory/'updates'\n"
        "owner.supervisor_directory=lambda arguments: directory\n"
        f"owner.child_command=lambda arguments: [sys.executable,{str(child)!r}]\n"
        "real_supervise=owner.supervise\n"
        "owner.supervise=lambda *args,**kwargs: real_supervise(*args,**kwargs,poll_interval=.01,"
        "**({'shutdown_timeout':.3} if case=='deadline' else {}))\n"
        "original_lock=owner.instance_lock\n"
        "@contextmanager\ndef observed_lock(*args,**kwargs):\n"
        " with original_lock(*args,**kwargs):\n"
        "  try: yield\n"
        "  finally:\n"
        "   if not kwargs.get('child'):\n"
        "    (directory/'lock-cleanup').touch()\n"
        "    time.sleep(.25)\n"
        "    (directory/'lock-cleanup-complete').touch()\n"
        "owner.instance_lock=observed_lock\n"
        "def wait_for(name):\n"
        " deadline=time.monotonic()+10\n"
        " while not (directory/name).exists():\n"
        "  if time.monotonic()>=deadline: raise TimeoutError(name)\n"
        "  time.sleep(.005)\n"
        "def send_interrupts():\n"
        " wait_for('child-ready')\n"
        " ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0,0)\n"
        " if case in ('cleanup','force'):\n"
        "  wait_for('lock-cleanup' if case=='cleanup' else 'child-stopping')\n"
        "  for unused in range(4):\n"
        "   ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0,0)\n"
        "   time.sleep(.02)\n"
        "innocent=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],"
        "creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)\n"
        "sender=threading.Thread(target=send_interrupts,daemon=True)\nsender.start()\n"
        "result={}\nstarted=time.monotonic()\n"
        "try:\n"
        " try: result['code']=owner.run_launcher([])\n"
        " except BaseException as error: result['error']=type(error).__name__\n"
        " result['elapsed']=time.monotonic()-started\n"
        " result['innocent_alive']=innocent.poll() is None\n"
        " with original_lock(directory,timeout=0): pass\n"
        " with original_lock(directory,timeout=0,child=True): pass\n"
        " result['locks_released']=True\n"
        "finally:\n"
        " innocent.terminate()\n innocent.wait(timeout=5)\n"
        " (directory/'result.json').write_text(json.dumps(result))\n",
        encoding="utf-8",
    )
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    completed = subprocess.run(
        [sys.executable, str(harness)],
        env=dict(os.environ, PYTHONPATH=str(root)),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
        startupinfo=startup,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        text=True,
    )
    result = json.loads((tmp_path / "result.json").read_text())
    assert completed.returncode == 0, completed.stderr
    assert "error" not in result, result
    assert result["code"] == 73
    assert result["innocent_alive"] and result["locks_released"]
    assert (tmp_path / "lock-cleanup-complete").exists()
    assert not (tmp_path / "recovery.json").exists()
    if case in ("graceful", "cleanup"):
        assert (tmp_path / "child-closed").exists()
    else:
        assert not (tmp_path / "child-closed").exists()
        assert result["elapsed"] < 5
