"""Detached updater credentials stay out of retained jobs and build processes."""

import base64
import hashlib
import io
import json
import os
import shutil
import sys
import zipfile
from unittest.mock import MagicMock, Mock, patch

import pytest

from arknights_mower.utils import network_settings as network
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.software_update_worker import UpdateCancelled, Worker

TOKEN = "github_pat_synthetic_worker_test"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    path = tmp_path / "config/network.json"
    monkeypatch.setattr(network, "settings_path", lambda: path)
    monkeypatch.setattr(network, "_base_environment", None)
    monkeypatch.setattr(network, "_effective_settings", None)
    # Child-process evidence must never capture unrelated credentials from the host.
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR"}
    }
    with patch.dict(os.environ, environment, clear=True):
        runtime.write_json(
            path, {"http_proxy": "", "github_proxy": "", "github_token": TOKEN}
        )
        yield path


def make_worker(tmp_path, settings, **changes):
    root = tmp_path / "install"
    root.mkdir(exist_ok=True)
    path = tmp_path / "tmp/updates/installation/jobs/current/job.json"
    job = {
        "id": "test-job",
        "root": str(root),
        "state_dir": str(path.parents[2]),
        "deployment": "release",
        "version": "v4.2.0",
        "background": False,
        "git": "git",
        "python": sys.executable,
        "base_python": sys.executable,
        "npm": "npm",
        "asset": {"name": "package.zip"},
        "network_settings_path": str(settings),
        **changes,
    }
    runtime.write_json(path, job)
    return Worker(path)


@pytest.mark.parametrize("outcome", ["succeeded", "failed", "cancelled"])
def test_actual_worker_never_records_token_in_any_terminal_state(
    tmp_path, settings, outcome
):
    worker = make_worker(tmp_path, settings)

    def prepare():
        if outcome == "cancelled":
            raise UpdateCancelled("synthetic cancellation")
        if outcome == "failed":
            raise ValueError("synthetic failure")

    worker.prepare_package = prepare
    worker.stop_instances = Mock()
    worker.install_package = Mock()
    worker.restart = Mock()
    worker.execute()
    assert runtime.read_json(worker.state / "status.json")["status"] == outcome
    for file in worker.work.rglob("*.json"):
        assert TOKEN not in file.read_text()
    assert "github_token" not in worker.job
    assert runtime.read_json(worker.job_path)["version"] == "v4.2.0"


def test_actual_non_git_child_and_pip_environment_never_receive_token(
    tmp_path, settings
):
    worker = make_worker(tmp_path, settings)
    captured = tmp_path / "child-environment.json"
    script = "import json, os, sys; open(sys.argv[1], 'w').write(json.dumps(dict(os.environ)))"
    worker.run_command([sys.executable, "-c", script, str(captured)])
    encoded = base64.b64encode(("x-access-token:" + TOKEN).encode()).decode()
    assert TOKEN not in captured.read_text()
    assert encoded not in captured.read_text()
    assert encoded not in json.dumps(
        worker.pip_environment() if hasattr(worker, "pip_environment") else worker.env
    )
    assert encoded not in json.dumps(worker.env)


def test_git_fetch_reads_current_settings_and_build_commands_remain_clean(
    tmp_path, settings
):
    worker = make_worker(tmp_path, settings)
    worker.job.update(
        commit="a" * 40, source_url="https://github.com/ArkMowers/arknights-mower.git"
    )
    process = Mock()
    process.wait.return_value = 0
    encoded = base64.b64encode(("x-access-token:" + TOKEN).encode()).decode()
    with (
        patch("subprocess.Popen", return_value=process) as popen,
        patch(
            "arknights_mower.utils.software_update_worker.WindowsCommandJob",
            create=True,
        ),
        patch.object(worker, "git_output", return_value="a" * 40),
    ):
        worker.fetch_source("refs/heads/alpha", "a" * 40)
        assert encoded in json.dumps(popen.call_args.kwargs["env"])
        assert encoded not in json.dumps(worker.env)
        for args in (
            ["npm", "run", "build"],
            [sys.executable, "-m", "pip", "install", "fixture"],
        ):
            worker.run_command(args)
            assert encoded not in json.dumps(popen.call_args.kwargs["env"])
        network.save_settings(
            {"http_proxy": "", "github_proxy": "", "github_token": ""}
        )
        worker.fetch_source("refs/heads/alpha", "a" * 40)
        assert encoded not in json.dumps(popen.call_args.kwargs["env"])
    assert TOKEN not in worker.job_path.read_text()


def test_http_download_reads_current_token_without_recording_it(tmp_path, settings):
    worker = make_worker(tmp_path, settings)
    assert worker.github_token() == TOKEN
    network.save_settings({"http_proxy": "", "github_proxy": "", "github_token": ""})
    assert worker.github_token() == ""
    assert TOKEN not in worker.job_path.read_text()


def test_lfs_fetch_receives_token_but_lfs_version_and_local_git_do_not(
    tmp_path, settings
):
    worker = make_worker(
        tmp_path, settings, deployment="source", commit="a" * 40, ref="refs/heads/alpha"
    )
    worker.fetch_source = Mock()
    worker.git_output = Mock(return_value="a" * 40)
    worker.target_uses_lfs = Mock(return_value=True)
    process = Mock()
    process.wait.return_value = 0
    encoded = base64.b64encode(("x-access-token:" + TOKEN).encode()).decode()
    with (
        patch("arknights_mower.utils.software_update_worker.require_clean_source"),
        patch("subprocess.Popen", return_value=process) as popen,
        patch(
            "arknights_mower.utils.software_update_worker.WindowsCommandJob",
            create=True,
        ),
    ):
        worker.prepare_source()
        assert popen.call_args_list[0].args[0][1:] == ["lfs", "version"]
        assert encoded not in json.dumps(popen.call_args_list[0].kwargs["env"])
        assert popen.call_args_list[1].args[0][1:3] == ["lfs", "fetch"]
        assert encoded in json.dumps(popen.call_args_list[1].kwargs["env"])
    with patch("subprocess.check_output", return_value="clean") as output:
        Worker.git_output(worker, "status", "--porcelain")
        assert encoded not in json.dumps(output.call_args.kwargs["env"])


@pytest.mark.parametrize("command", [["npm", "run", "build"], ["git", "status"]])
def test_credential_opt_in_cannot_be_used_for_other_commands(
    tmp_path, settings, command
):
    worker = make_worker(tmp_path, settings)
    with (
        patch("subprocess.Popen") as popen,
        pytest.raises(ValueError, match="Git fetch"),
    ):
        worker.run_command(command, github_auth=True)
    popen.assert_not_called()


def test_real_package_download_reloads_token_after_clearing_settings(
    tmp_path, settings
):
    worker = make_worker(tmp_path, settings)
    archive = io.BytesIO()
    executable = "mower.exe" if sys.platform == "win32" else "mower"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("mower/" + executable, b"fixture")
        package.writestr(
            "mower/_internal/arknights_mower/utils/update_runtime.py", b"fixture"
        )
    data = archive.getvalue()
    worker.job["asset"].update(
        url="https://github.com/ArkMowers/arknights-mower/releases/download/v4.2.0/package.zip",
        sha256=hashlib.sha256(data).hexdigest(),
    )
    for expected in (TOKEN, ""):
        response = MagicMock()
        response.__enter__.return_value = response
        response.iter_content.return_value = [data]
        with patch("requests.get", return_value=response) as get:
            worker.prepare_package()
        headers = get.call_args.kwargs.get("headers", {})
        assert headers.get("Authorization", "") == (
            "Bearer " + expected if expected else ""
        )
        assert (worker.prepared / executable).read_bytes() == b"fixture"
        assert TOKEN not in worker.job_path.read_text()
        (worker.work / "package.zip").unlink()
        shutil.rmtree(worker.prepared)
        shutil.rmtree(worker.work / "payload", ignore_errors=True)
        network.save_settings(
            {"http_proxy": "", "github_proxy": "", "github_token": ""}
        )
