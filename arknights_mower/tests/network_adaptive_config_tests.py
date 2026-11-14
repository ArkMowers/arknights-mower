import pytest
import yaml

from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf


def test_legacy_configuration_keeps_adaptive_switches_disabled_without_rewriting(
    tmp_path, monkeypatch
):
    path = tmp_path / "conf.yml"
    original = "run_order_delay: 3.75\nwaiting_scene:\n  CONNECTING: [3, 10]\n"
    path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(config, "conf_path", path)
    monkeypatch.setattr(config, "conf", Conf())
    monkeypatch.setattr(config, "_load_rescue_plan", lambda *_: None)

    config.load_conf()

    assert config.conf.run_order_network_adaptive is False
    assert config.conf.waiting_scene_network_adaptive is False
    assert config.conf.run_order_delay == 3.75
    assert config.conf.waiting_scene.CONNECTING == (3, 10)
    explicit = config.conf.model_dump(exclude_unset=True)
    assert "run_order_network_adaptive" not in explicit
    assert "waiting_scene_network_adaptive" not in explicit
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("run_order", [False, True])
@pytest.mark.parametrize("waiting_scene", [False, True])
def test_switches_save_and_reload_independently_without_changing_base_values(
    tmp_path, monkeypatch, run_order, waiting_scene
):
    path = tmp_path / "conf.yml"
    original = Conf(
        run_order_delay=3.75,
        run_order_grandet_mode={"enable": True, "buffer_time": 22},
        waiting_scene={"CONNECTING": [3, 10], "LOADING": [2, 30]},
    )
    assert original.run_order_network_adaptive is False
    assert original.waiting_scene_network_adaptive is False
    changed = original.updated(
        {
            "run_order_network_adaptive": run_order,
            "waiting_scene_network_adaptive": waiting_scene,
        }
    )
    monkeypatch.setattr(config, "conf_path", path)
    monkeypatch.setattr(config, "conf", changed)
    monkeypatch.setattr(config, "_load_rescue_plan", lambda *_: None)

    config.save_conf()
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["run_order_network_adaptive"] is run_order
    assert saved["waiting_scene_network_adaptive"] is waiting_scene
    config.conf = Conf()
    config.load_conf()

    assert config.conf.run_order_network_adaptive is run_order
    assert config.conf.waiting_scene_network_adaptive is waiting_scene
    assert config.conf.run_order_delay == original.run_order_delay
    assert config.conf.run_order_grandet_mode == original.run_order_grandet_mode
    assert config.conf.waiting_scene == original.waiting_scene
    assert original.run_order_network_adaptive is False
    assert original.waiting_scene_network_adaptive is False
