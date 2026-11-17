"""Build checks exercise real HPKE without importing application configuration."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric import mlkem

from scripts.check_credential_crypto import check_credential_crypto

ROOT = Path(__file__).resolve().parents[2]


def test_crypto_build_check_runs_without_application_or_user_files(tmp_path):
    source = (
        "import runpy, sys; "
        "runpy.run_path(sys.argv[1], run_name='__main__'); "
        "assert 'arknights_mower.utils.config' not in sys.modules"
    )
    environment = dict(os.environ, MOWER_DATA_DIR=str(tmp_path / "unused-data"))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            source,
            str(ROOT / "scripts/check_credential_crypto.py"),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "X-Wing / HKDF-SHA256 / AES-256-GCM" in result.stdout
    assert not list(tmp_path.iterdir())


def test_crypto_build_check_rejects_a_backend_without_mlkem(capsys):
    with patch.object(
        mlkem.MLKEM768PrivateKey,
        "generate",
        side_effect=UnsupportedAlgorithm("synthetic backend without ML-KEM"),
    ):
        with pytest.raises(UnsupportedAlgorithm):
            check_credential_crypto()
    assert "passed" not in capsys.readouterr().out


@pytest.mark.parametrize(
    ("dockerfile", "probe", "installation"),
    [
        ("Dockerfile", "python scripts/check_credential_crypto.py", "pip install -r"),
        (
            "docker/Dockerfile",
            "/opt/venv/bin/python scripts/check_credential_crypto.py",
            "uv pip check --python /opt/venv/bin/python",
        ),
        (
            "scripts/android-runtime.Dockerfile",
            "python /tmp/check_credential_crypto.py",
            "python -m pip check",
        ),
    ],
)
def test_container_builds_check_the_installed_crypto_backend(
    dockerfile, probe, installation
):
    source = (ROOT / dockerfile).read_text(encoding="utf-8")
    assert source.index(installation) < source.index(probe)


def test_desktop_release_builds_verify_the_installed_crypto_backend():
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/release-build.yml").read_text(encoding="utf-8")
    )
    for job_name in ("build-windows", "build-linux", "build-macos"):
        steps = workflow["jobs"][job_name]["steps"]
        commands = "\n".join(step.get("run", "") for step in steps)
        assert commands.index("python -m pip check") < commands.index(
            "python scripts/check_credential_crypto.py"
        )
        assert commands.index(
            "python scripts/check_credential_crypto.py"
        ) < commands.index("python -m PyInstaller ")
