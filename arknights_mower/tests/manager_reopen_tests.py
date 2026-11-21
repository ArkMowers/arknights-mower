"""Manager recreation uses live registrations rather than launcher ownership."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from arknights_mower.utils import manager_instances as controls
from arknights_mower.utils import update_runtime as runtime

INSTANCE = """
import json
import sys
import time
from pathlib import Path
from arknights_mower.utils import update_runtime as runtime

state, space, gate, commands = map(Path, sys.argv[1:5])
runtime.state_dir = lambda *args: state
registration = runtime.RuntimeRegistration(
    'instance', space=str(space), name='first', port=58721,
    directory=state, maintenance=False,
)
try:
    while not registration.shutdown_requested():
        if gate.exists() and not registration.record['ready']:
            registration.record['ready'] = True
            registration.publish()
        for action in registration.take_commands():
            commands.parent.mkdir(parents=True, exist_ok=True)
            with commands.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps({'id': registration.id, 'action': action}) + '\\n')
        time.sleep(0.02)
finally:
    registration.close()
"""

STARTER = """
import json
import sys
from pathlib import Path
from arknights_mower.utils import manager_instances as controls
from arknights_mower.utils import update_runtime as runtime

storage, state, script, gate, commands, result = map(Path, sys.argv[1:])
runtime.state_dir = lambda *args: state
real_popen = controls.subprocess.Popen
def launch(command, **kwargs):
    return real_popen(
        [sys.executable, str(script), str(state), command[-2], str(gate), str(commands)],
        stdout=controls.subprocess.DEVNULL, stderr=controls.subprocess.DEVNULL, **kwargs,
    )
controls.subprocess.Popen = launch
registration = runtime.RuntimeRegistration('manager', directory=state, maintenance=False)
manager = controls.InstanceController(storage)
manager.add('first', str(storage.parent / 'first'))
outcome = manager.start(0, manager.instances[0].copy())
result.write_text(json.dumps(outcome), encoding='utf-8')
registration.close()
if not outcome['ok']:
    raise RuntimeError(outcome['message'])
"""


def await_condition(condition):
    deadline = time.monotonic() + 15
    while True:
        result = condition()
        if result:
            return result
        if time.monotonic() >= deadline:
            raise AssertionError("fixture process did not reach the requested state")
        time.sleep(0.02)


@pytest.fixture
def reopened_manager(tmp_path, monkeypatch):
    state = tmp_path / "runtime"
    storage = tmp_path / "data/instances.json"
    storage.parent.mkdir()
    instance = tmp_path / "instance.py"
    instance.write_text(INSTANCE, encoding="utf-8")
    starter = tmp_path / "starter.py"
    starter.write_text(STARTER, encoding="utf-8")
    gate, commands, result = (
        tmp_path / name for name in ("ready", "commands", "result")
    )
    environment = {
        **os.environ,
        "MOWER_DATA_DIR": str(storage.parent),
        "PYTHONPATH": str(runtime.installation_root()),
    }
    for key in tuple(environment):
        if key.startswith(("MOWER_SUPERVISOR_", "MOWER_RESTART_")) or key in {
            "MOWER_LAUNCH_ID",
            "MOWER_MANAGER_PORT",
        }:
            environment.pop(key)
    original_manager = subprocess.run(
        [
            sys.executable,
            str(starter),
            *map(str, (storage, state, instance, gate, commands, result)),
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert original_manager.returncode == 0, original_manager.stderr
    assert json.loads(result.read_text()) == {"ok": True}
    monkeypatch.setattr(runtime, "state_dir", lambda *args: state)
    monkeypatch.setenv("MOWER_DATA_DIR", str(storage.parent))
    monkeypatch.setenv("PYTHONPATH", str(runtime.installation_root()))
    manager = controls.InstanceController(storage)
    launched = []
    pending = json.loads(next((state / "manager-controls").glob("*.json")).read_text())
    launched.append(pending)
    real_popen = subprocess.Popen

    def launch(command, **kwargs):
        child = real_popen(
            [
                sys.executable,
                str(instance),
                str(state),
                command[-2],
                str(gate),
                str(commands),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs,
        )
        launched.append({"id": kwargs["env"]["MOWER_LAUNCH_ID"], "pid": child.pid})
        return child

    monkeypatch.setattr(controls.subprocess, "Popen", launch)
    try:
        yield manager, pending, gate, commands
    finally:
        for record in launched:
            runtime.send_instance_command(record, "exit")
        await_condition(
            lambda: all(not runtime.process_alive(r["pid"]) for r in launched)
        )


def test_reopened_manager_controls_live_instance_after_original_manager_process_exits(
    reopened_manager,
):
    manager, pending, gate, commands = reopened_manager
    target = manager.instances[0].copy()
    assert runtime.process_alive(pending["pid"])
    assert all(record["kind"] == "instance" for record in runtime.instances(timeout=0))
    item = manager.get_instances()[0]
    assert item["state"] == "starting"
    assert item["can_stop"] and not item["can_start"] and not item["editable"]
    assert manager.start(0, target)["ok"] is False
    gate.touch()
    await_condition(lambda: manager.get_instances()[0]["state"] == "running")
    assert manager.get_instances()[0]["can_open_browser"]
    assert manager.open_browser(0, target) == {"ok": True}
    await_condition(lambda: commands.exists() and commands.read_text())
    assert json.loads(commands.read_text().splitlines()[0]) == {
        "id": pending["id"],
        "action": "browser",
    }
    assert manager.stop(0, target) == {"ok": True}
    await_condition(lambda: manager.get_instances()[0]["state"] == "stopped")
    assert manager.get_instances()[0]["can_start"]
    assert manager.get_instances()[0]["editable"]
    assert manager.start(0, target) == {"ok": True}
    await_condition(lambda: manager.get_instances()[0]["state"] == "running")
    registrations = runtime.instances(timeout=0)
    assert len(registrations) == 1
    assert registrations[0]["id"] != pending["id"]
    before = commands.read_text().splitlines()
    saved = manager._storage_path.read_bytes()
    assert manager.start(0, target) == {"ok": True}
    await_condition(lambda: len(commands.read_text().splitlines()) > len(before))
    assert json.loads(commands.read_text().splitlines()[-1]) == {
        "id": registrations[0]["id"],
        "action": "show",
    }
    assert [record["id"] for record in runtime.instances(timeout=0)] == [
        registrations[0]["id"]
    ]
    assert manager._storage_path.read_bytes() == saved
    assert manager.stop(0, target) == {"ok": True}
    await_condition(lambda: manager.get_instances()[0]["state"] == "stopped")


@pytest.mark.parametrize("same_directory", [True, False])
def test_reopened_manager_does_not_adopt_standalone_or_same_port_other_instance(
    tmp_path, monkeypatch, same_directory
):
    state = tmp_path / "runtime"
    monkeypatch.setattr(runtime, "state_dir", lambda *args: state)
    manager = controls.InstanceController(tmp_path / "instances.json")
    manager.add("first", str(tmp_path / "first"))
    target = manager.instances[0].copy()
    configuration = Path(target["path"]) / "config/conf.yml"
    configuration.parent.mkdir(parents=True)
    configuration.write_text("webview:\n  port: 58721\n", encoding="utf-8")
    before = configuration.read_bytes()
    record = {
        "id": "other-process",
        "pid": os.getpid(),
        "kind": "instance",
        "space": target["path"] if same_directory else str(tmp_path / "other"),
        "port": 58721,
        "ready": True,
        "managed": not same_directory,
    }
    runtime.write_json(state / "instances/other-process.json", record)
    item = manager.get_instances()[0]
    assert item["state"] == ("running" if same_directory else "stopped")
    assert item["can_stop"] is False and item["can_open_browser"] is False
    assert manager.start(0, target)["ok"] is False
    assert manager.open_browser(0, target)["ok"] is False
    manager.stop(0, target)
    assert list((state / "shutdown").glob("*.json")) == []
    assert list((state / "commands").rglob("*.json")) == []
    assert configuration.read_bytes() == before
