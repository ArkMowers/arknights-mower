from io import BytesIO

import pytest
import yaml
from flask import Flask

from arknights_mower.tests.config_profiles_tests import storage as storage
from arknights_mower.utils import config, manager_common, workshop_config
from arknights_mower.utils import config_backup as backup
from arknights_mower.utils import config_profiles as profiles
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.manager_instances import InstanceController
from arknights_mower.views.config_backup import config_backup_bp
from arknights_mower.views.config_profiles import config_profiles_bp


@pytest.fixture
def inherited(storage, tmp_path, monkeypatch, request):
    explicit = request.param
    monkeypatch.setattr(config, "manager_inherited_settings", frozenset())
    monkeypatch.delenv("MOWER_MANAGED", raising=False)
    profiles.list_profiles()
    original_id = profiles.list_profiles()["active_id"]
    profiles.create_profile(
        "alternate", [], expected_generation=profiles.current_generation()
    )
    values = (
        {"maa_path": "/local/maa", "screenshot": 7, "screenshot_archive_limit_mb": 987}
        if explicit
        else {}
    )
    config.conf = config.Conf(extra_settings_visible=True, **values)
    config.save_conf()
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "runtime")
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [])
    monkeypatch.setattr(runtime, "active_job", lambda: False)
    controller = InstanceController(tmp_path / "instances.json")
    instance_root = config.conf_path.parent.parent
    controller.add("one", str(instance_root))
    original = controller.get_common_settings()["values"]
    controller.update_all_settings(
        [],
        controller.instances.copy(),
        {
            "values": {
                **original,
                "maa_path": "/common/maa",
                "screenshot": 2,
                "screenshot_archive_limit_mb": 456,
            },
            "original": original,
        },
    )
    monkeypatch.setattr(
        manager_common, "settings_path", lambda: controller._common_path
    )
    monkeypatch.setattr(manager_common, "get_path", lambda name: instance_root)
    monkeypatch.setenv("MOWER_MANAGED", "1")
    launched, keys = manager_common.launch_snapshot(config.conf, managed=True)
    monkeypatch.setattr(config, "conf", launched)
    monkeypatch.setattr(config, "manager_inherited_settings", keys)
    app = Flask(__name__)
    app.token = "instance-token"
    app.config["CONFIG_BACKUP_BUSY"] = lambda: False
    app.register_blueprint(config_profiles_bp)
    app.register_blueprint(config_backup_bp)
    return controller, app.test_client(), original_id, values


def effective_values():
    return (
        config.conf.maa_path,
        config.conf.screenshot,
        config.conf.screenshot_archive_limit_mb,
    )


@pytest.mark.parametrize("inherited", [True, False], indirect=True)
@pytest.mark.parametrize(
    "operation",
    ["save_conf", "save_user_config", "create", "import", "activate", "zip"],
)
def test_launch_inheritance_retains_local_conf_through_real_writers(
    inherited, operation
):
    controller, client, original_id, values = inherited
    incoming = backup.export_archive()
    before_common = controller._common_path.read_bytes()
    assert effective_values() == ("/common/maa", 2, 456)
    assert config.manager_inherited_settings == manager_common.LOCAL_OVERRIDE_KEYS
    headers = {
        "token": "instance-token",
        "X-Mower-Settings": "1",
        "X-Mower-Config-Generation": profiles.current_generation(),
    }
    if operation == "save_conf":
        config.conf.drone_count_limit = 77
        config.save_conf()
    elif operation == "save_user_config":
        workshop_config.save_user_config({"drone_count_limit": 77})
    elif operation == "create":
        response = client.post(
            "/config-profiles", headers=headers, json={"name": "created", "inherit": []}
        )
        assert response.status_code == 200, response.json
    elif operation == "import":
        response = client.post(
            "/config-profiles/import",
            headers=headers,
            data={
                "name": "imported",
                "keep": "[]",
                "backup": (BytesIO(incoming), "incoming.zip"),
            },
        )
        assert response.status_code == 200, response.json
    elif operation == "activate":
        response = client.post(
            f"/config-profiles/{original_id}/activate",
            headers=headers,
            json={"keep": []},
        )
        assert response.status_code == 200, response.json
    else:
        response = client.post(
            "/config-backup/import",
            headers=headers,
            data={"backup": (BytesIO(incoming), "incoming.zip")},
        )
        assert response.status_code == 200, response.json
    assert effective_values() == ("/common/maa", 2, 456)
    saved = yaml.safe_load(config.conf_path.read_text())
    assert {key: saved[key] for key in values} == values
    assert not (manager_common.LOCAL_OVERRIDE_KEYS - values.keys()) & saved.keys()
    assert controller._common_path.read_bytes() == before_common
    target = controller.instances[0].copy()
    state = controller.get_device_settings(0, target)
    assert state["original_policy"]["local_values"] == {
        key: getattr(config.Conf(**values), key)
        for key in manager_common.LOCAL_OVERRIDE_KEYS
    }
    controller.update_device_settings(
        0,
        {},
        target,
        state["values"],
        {
            "independent_configuration": state["independent_configuration"],
            "original_policy": state["original_policy"],
            "instance_override": {
                "local_keys": sorted(manager_common.LOCAL_OVERRIDE_KEYS),
                "manager_values": {},
            },
        },
    )
    relaunched, keys = manager_common.launch_snapshot(
        config.Conf(**yaml.safe_load(config.conf_path.read_text())), managed=True
    )
    assert (
        relaunched.maa_path,
        relaunched.screenshot,
        relaunched.screenshot_archive_limit_mb,
    ) == tuple(
        getattr(config.Conf(**values), key)
        for key in ("maa_path", "screenshot", "screenshot_archive_limit_mb")
    )
    assert keys == frozenset()


@pytest.mark.parametrize("inherited", [True], indirect=True)
def test_later_common_change_does_not_change_the_persistence_snapshot(inherited):
    controller, _, _, _ = inherited
    original = controller.get_common_settings()["values"]
    controller.update_all_settings(
        [],
        controller.instances.copy(),
        {
            "values": {
                key: value
                for key, value in original.items()
                if key not in manager_common.LOCAL_OVERRIDE_KEYS
            },
            "original": original,
        },
    )
    workshop_config.save_user_config({"drone_count_limit": 78})
    assert effective_values() == ("/common/maa", 2, 456)
    assert yaml.safe_load(config.conf_path.read_text())["screenshot"] == 7


@pytest.mark.parametrize("inherited", [True], indirect=True)
@pytest.mark.parametrize("operation", ["ordinary", "import"])
def test_invalid_local_conf_aborts_before_replacement_and_preserves_runtime(
    inherited, operation
):
    _, _, _, _ = inherited
    incoming = backup.export_archive()
    config.conf_path.write_text("screenshot: invalid\n")
    before = config.conf_path.read_bytes()
    previous = config.conf
    with pytest.raises(ValueError):
        if operation == "ordinary":
            workshop_config.save_user_config({"drone_count_limit": 77})
        else:
            backup.import_configuration(incoming)
    assert config.conf is previous
    assert effective_values() == ("/common/maa", 2, 456)
    assert config.conf_path.read_bytes() == before
