import json
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).parent / "fixtures/navigation/instance_path_worker.py"
REPOSITORY = Path(__file__).resolve().parents[2]


def tree_bytes(root):
    return {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize("default_state", ["missing", "invalid_conf", "invalid_plan"])
@pytest.mark.parametrize("absolute_space", [False, True])
def test_spawn_restores_instance_paths_before_configuration_import(
    tmp_path, default_state, absolute_space
):
    data = tmp_path / "data"
    default = data / "config"
    active = (
        tmp_path / "absolute-instance" if absolute_space else data / "selected-instance"
    )
    space = str(active) if absolute_space else "selected-instance"
    current = active / "config"
    current.mkdir(parents=True)
    (tmp_path / "cwd").mkdir()
    (current / "conf.yml").write_text(
        "ai_type: custom-local\nai_model: disk-instance-model\nai_base_url: http://127.0.0.1:9/v1\n",
        encoding="utf-8",
    )
    for name in ("plan.json", "rescue_plan.json"):
        (current / name).write_text('{"plan1": {}}', encoding="utf-8")
    if default_state != "missing":
        default.mkdir(parents=True)
        (default / "conf.yml").write_text(
            "[invalid" if default_state == "invalid_conf" else "{}", encoding="utf-8"
        )
        (default / "plan.json").write_text(
            "{" if default_state == "invalid_plan" else '{"plan1": {}}',
            encoding="utf-8",
        )
        (default / "rescue_plan.json").write_text('{"plan1": {}}', encoding="utf-8")
    before_default, before_current = tree_bytes(default), tree_bytes(current)
    completed = subprocess.run(
        [sys.executable, str(HARNESS), str(tmp_path), space],
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout.splitlines()[-1])
    assert "error" not in report, report
    assert report["result"] == {
        "conf_path": str(current / "conf.yml"),
        "plan_path": str(current / "plan.json"),
        "instance": str(active),
        "internal": str(REPOSITORY),
        "install": str(REPOSITORY),
        "disk_model": "disk-instance-model",
        "runtime_model": "runtime-instance-model",
    }
    assert tree_bytes(default) == before_default
    assert tree_bytes(current) == before_current
    if default_state == "missing":
        assert not default.exists()
