import os
from unittest.mock import Mock

import pytest

from arknights_mower.tests.manager_instance_controls_tests import manager as manager
from arknights_mower.utils import software_update as update
from arknights_mower.utils import update_runtime as runtime


@pytest.mark.parametrize("owner", ["manager", "unrelated", "none"])
def test_update_admission_with_no_running_instances(manager, monkeypatch, owner):
    monkeypatch.setattr(runtime, "frozen", lambda: True)
    monkeypatch.setattr(
        runtime, "installation_root", lambda: manager._storage_path.parent
    )
    registered = (
        []
        if owner == "none"
        else [
            dict(
                kind="manager",
                pid=os.getppid() if owner == "manager" else os.getpid() + 100,
            )
        ]
    )
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: registered)
    monkeypatch.setattr(update, "get_settings", lambda: {"background": False})
    result = manager.get_mower_update_info()
    assert result["instances"] == []
    assert bool(result["blockers"]) is (owner != "manager")


def test_empty_manager_submits_update_without_launching_an_instance(
    manager, monkeypatch
):
    manager.remove(0)
    submit = Mock(return_value={"ok": True, "id": "job"})
    monkeypatch.setattr(update, "submit", submit)
    assert manager.start_mower_update("checked", False) == {"ok": True, "id": "job"}
    submit.assert_called_once_with("checked", False)


@pytest.mark.parametrize("value", [None, 1, "false"])
def test_manager_rejects_invalid_restart_mode_before_submitting(
    manager, monkeypatch, value
):
    submit = Mock()
    monkeypatch.setattr(update, "submit", submit)
    with pytest.raises(ValueError, match="更新请求无效"):
        manager.start_mower_update("checked", value)
    submit.assert_not_called()
