"""Desktop startup retains its owners without loading unused runtime solvers."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path


def run_isolated(source, data_dir):
    data_dir.mkdir()
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=Path(__file__).parents[2],
        env={
            **os.environ,
            "MOWER_DATA_DIR": str(data_dir),
            "PYTHONIOENCODING": "utf-8",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_initial_requests_and_shutdown_retain_the_existing_device_owner(tmp_path):
    run_isolated(
        """
        import importlib.abc
        import sys
        from unittest.mock import patch

        class RejectSolverImports(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname in {
                    "arknights_mower.solvers.base_schedule",
                    "arknights_mower.solvers.reclamation_algorithm",
                    "arknights_mower.solvers.secret_front",
                }:
                    raise AssertionError(f"Unused startup solver: {fullname}")

        sys.meta_path.insert(0, RejectSolverImports())
        import server
        from arknights_mower import __main__ as mower
        from arknights_mower.utils import log
        from arknights_mower.utils.device import application

        control = mower.device_control
        assert not control.active
        assert log.get_screenshot_store() is None
        server.app.token = "startup-test-token"
        client = server.app.test_client()
        with patch.object(
            application, "create_device_control",
            side_effect=AssertionError("Device owner must not be replaced"),
        ):
            response = client.get("/conf", headers={"token": server.app.token})
            assert response.status_code == 200
            assert response.json["device"]
            response = client.get("/status")
            assert response.status_code == 200
            assert response.json["status"] == "stopped"
            assert mower.device_control is control
            server.shutdown.close("startup-test")
            assert control.shutdown_requested
            assert control.status().status == "closed"
            assert server.shutdown.errors == []
            assert log.get_screenshot_store() is None
        """,
        tmp_path / "server",
    )


def test_logging_and_unused_store_shutdown_do_not_load_image_dependencies(tmp_path):
    run_isolated(
        """
        import importlib.abc
        import sys

        class RejectImageImports(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname in {"numpy", "arknights_mower.utils.screenshot"}:
                    raise AssertionError(f"Unused logging dependency: {fullname}")

        sys.meta_path.insert(0, RejectImageImports())
        from arknights_mower.utils import log

        assert log.get_screenshot_store() is None
        assert log.close_screenshot_store() == {"remaining_threads": []}
        log.save_screenshot(b"late frame")
        assert log.get_screenshot_store() is None
        """,
        tmp_path / "logging",
    )
