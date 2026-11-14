"""救急排班独立存储、旧配置迁移及失败保留。"""

import json

import pytest
import yaml

from arknights_mower.utils import config


@pytest.fixture
def storage(tmp_path, monkeypatch):
    root = tmp_path / "instance" / "config"
    root.mkdir(parents=True)
    monkeypatch.setattr(config, "conf_path", root / "conf.yml")
    monkeypatch.setattr(config, "rescue_plan_path", root / "rescue_plan.json")
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "rescue_plan", config.PlanModel())
    for name in ("_legacy_dorm_order", "_retired_dorm_conf"):
        monkeypatch.setattr(config, name, getattr(config, name))
    return root


def document(agent="红"):
    return {
        "plan1": {"central": {"plans": [{"agent": agent}]}},
        "backup_plans": [{"name": "救急副表", "plan": {}, "trigger": {"left": "1"}}],
        "conf": {"workaholic": agent, "dorm_order": "dormitory_3,dormitory_1"},
    }


def test_legacy_rescue_migrates_and_general_saves_do_not_write_roster(storage):
    original = document()
    config.conf_path.write_text(
        yaml.safe_dump(
            {
                "account": "saved",
                "automatic_rescue_enable": True,
                "automatic_rescue_plan": original,
            }
        ),
        encoding="utf-8",
    )
    config.load_conf()
    saved = json.loads(config.rescue_plan_path.read_text(encoding="utf-8"))
    assert saved["plan1"]["central"]["plans"][0]["agent"] == "红"
    assert saved["backup_plans"][0]["name"] == "救急副表"
    assert saved["conf"]["workaholic"] == "红"
    assert "automatic_rescue_plan" not in yaml.safe_load(config.conf_path.read_text())
    assert config.conf.automatic_rescue_enable is True
    before = config.rescue_plan_path.read_bytes()
    config.conf.theme = "dark"
    config.save_conf()
    assert config.rescue_plan_path.read_bytes() == before
    config.load_conf()
    assert config.rescue_plan.plan1.central.plans[0].agent == "红"
    assert config.conf.account == "saved"


def test_existing_rescue_file_wins_over_legacy_field(storage):
    config.rescue_plan_path.write_text(json.dumps(document("砾")), encoding="utf-8")
    config.conf_path.write_text(yaml.safe_dump({"automatic_rescue_plan": document()}))
    config.load_conf()
    assert config.rescue_plan.plan1.central.plans[0].agent == "砾"
    assert "automatic_rescue_plan" not in yaml.safe_load(config.conf_path.read_text())


def test_migration_write_failure_keeps_legacy_file(storage, monkeypatch):
    original = yaml.safe_dump({"automatic_rescue_plan": document()})
    config.conf_path.write_text(original)
    write = config.atomic_write

    def fail(path, writer, **kwargs):
        if path == config.rescue_plan_path:
            raise OSError("readonly")
        return write(path, writer, **kwargs)

    monkeypatch.setattr(config, "atomic_write", fail)
    with pytest.raises(OSError, match="readonly"):
        config.load_conf()
    assert config.conf_path.read_text() == original
    assert not config.rescue_plan_path.exists()


def test_legacy_cleanup_failure_keeps_both_files_and_can_retry(storage, monkeypatch):
    original = yaml.safe_dump({"automatic_rescue_plan": document()})
    config.conf_path.write_text(original)
    write = config.atomic_write

    def fail(path, writer, **kwargs):
        if path == config.conf_path:
            raise OSError("readonly")
        return write(path, writer, **kwargs)

    monkeypatch.setattr(config, "atomic_write", fail)
    with pytest.raises(OSError, match="readonly"):
        config.load_conf()
    assert config.conf_path.read_text() == original
    assert (
        json.loads(config.rescue_plan_path.read_text())["plan1"]["central"]["plans"][0][
            "agent"
        ]
        == "红"
    )
    monkeypatch.setattr(config, "atomic_write", write)
    config.load_conf()
    assert config.rescue_plan.plan1.central.plans[0].agent == "红"
    assert "automatic_rescue_plan" not in config.conf_path.read_text()


@pytest.mark.parametrize("content", ["{", "[]", '{"unrelated": true}'])
def test_invalid_rescue_file_does_not_fall_back_or_rewrite(storage, content):
    config.rescue_plan_path.write_text(content)
    original = yaml.safe_dump({"automatic_rescue_plan": document()})
    config.conf_path.write_text(original)
    with pytest.raises(ValueError):
        config.load_conf()
    assert config.conf_path.read_text() == original
    assert config.rescue_plan_path.read_text() == content


def test_migration_preserves_other_pending_legacy_fields(storage):
    config.conf_path.write_text(
        yaml.safe_dump(
            {
                "automatic_rescue_plan": document(),
                "dorm_order": "dormitory_3,dormitory_1",
            }
        )
    )
    config.load_conf()
    assert (
        yaml.safe_load(config.conf_path.read_text())["dorm_order"]
        == "dormitory_3,dormitory_1"
    )


@pytest.mark.parametrize("token", [None, "wrong", "preset-storage"])
def test_legacy_preset_route_reads_canonical_file_only_after_auth(
    storage, monkeypatch, token
):
    import server

    monkeypatch.setattr(server.app, "token", "preset-storage", raising=False)
    requested = []
    preset = storage / "workshop_preset.json"
    preset.write_text('[{"name": "saved"}]')

    def get_path(name):
        requested.append(name)
        return preset

    monkeypatch.setattr(server, "get_path", get_path)
    response = server.app.test_client().get(
        "/workshop-preset", headers={"token": token} if token else {}
    )
    if token == "preset-storage":
        assert response.status_code == 200
        assert response.json == [{"name": "saved"}]
        assert requested == ["@app/config/workshop_preset.json"]
    else:
        assert response.status_code == 403
        assert not requested


@pytest.mark.parametrize("imported", [False, True])
def test_rescue_route_persists_only_independent_file(storage, monkeypatch, imported):
    from io import BytesIO

    import server

    monkeypatch.setattr(server.app, "token", "rescue-storage", raising=False)
    monkeypatch.setattr(config, "plan", config.PlanModel())
    config.save_conf()
    before = config.conf_path.read_bytes()
    client = server.app.test_client()
    headers = {"token": "rescue-storage"}
    if imported:
        response = client.post(
            "/import?rescue=1",
            headers=headers,
            data={
                "img": (BytesIO(json.dumps(document()).encode()), "rescue.json"),
            },
        )
    else:
        response = client.post("/rescue-plan", headers=headers, json=document())
    assert response.status_code == 200
    assert config.conf_path.read_bytes() == before
    assert not (storage / "plan.json").exists()
    assert (
        json.loads(config.rescue_plan_path.read_text())["plan1"]["central"]["plans"][0][
            "agent"
        ]
        == "红"
    )
    config.load_conf()
    assert (
        client.get("/rescue-plan", headers=headers).json["plan1"]["central"]["plans"][
            0
        ]["agent"]
        == "红"
    )


@pytest.mark.parametrize("crlf", [False, True])
def test_collected_installation_migrates_per_instance_and_starts_fresh(tmp_path, crlf):
    import os
    import subprocess
    import sys
    from pathlib import Path

    import build_assets

    installed = tmp_path / "installed"
    # 使用桌面打包器实际收集的源码，不依赖仓库或测试文件。
    for source, destination in build_assets._collect_arknights_mower_datas():
        if Path(source).suffix != ".py":
            continue
        target = installed / destination / Path(source).name
        target.parent.mkdir(parents=True, exist_ok=True)
        content = Path(source).read_bytes()
        target.write_bytes(content.replace(b"\n", b"\r\n") if crlf else content)
    data_root = tmp_path / "data"
    for space, agent in (("first", "红"), ("second", "砾"), ("fresh", None)):
        root = data_root / space / "config"
        # 实例入口创建数据目录，配置目录由配置加载器建立。
        root.parent.mkdir(parents=True, exist_ok=True)
        if agent:
            root.mkdir(parents=True)
            content = yaml.safe_dump(
                {"automatic_rescue_plan": document(agent)}, allow_unicode=True
            )
            (root / "conf.yml").write_bytes(
                content.replace("\n", "\r\n").encode() if crlf else content.encode()
            )
            legacy = root.parent / "tmp"
            legacy.mkdir()
            (legacy / "growth_plan.json").write_text('[{"char_id": "saved"}]')
            (legacy / "workshop_preset.json").write_text('[{"name": "saved"}]')
            if space == "second":
                (root / "growth_plan.json").write_text('[{"char_id": "current"}]')
                (root / "workshop_preset.json").write_text('[{"name": "current"}]')
        code = """
import json, sys, yaml
from arknights_mower.utils import path
path.global_space = sys.argv[1]
from arknights_mower.utils import config
from arknights_mower.utils import growth, ui_state
from arknights_mower.utils.config import gui
assert config.rescue_plan_path == path.get_path('@app/config/rescue_plan.json')
assert 'automatic_rescue_plan' not in yaml.safe_load(config.conf_path.read_text())
if sys.argv[2]:
    assert config.rescue_plan.plan1.central.plans[0].agent == sys.argv[2]
else:
    assert config.rescue_plan.plan1.central is None
if sys.argv[2]:
    expected = 'saved' if sys.argv[1] == 'first' else 'current'
    assert growth.load_goals()[0]['char_id'] == expected
    assert json.loads(config.workshop_preset_path.read_text())[0]['name'] == expected
    legacy = path.get_path('@app/tmp/growth_plan.json')
    assert legacy.exists() == (sys.argv[1] == 'second')
assert ui_state.get_mood_board()['preferences'] is None
ui_state.save_mood_board({'hiddenGroups': [sys.argv[1]]})
gui.save_window_mode('maximized')
assert gui.gui_path == path.get_path('@app/config/gui.yml')
assert ui_state.get_mood_board()['preferences']['hiddenGroups'] == [sys.argv[1]]
config.load_conf()
assert json.loads(config.rescue_plan_path.read_text())['plan1'] == config.rescue_plan.model_dump(exclude_none=True)['plan1']
"""
        environment = {
            **os.environ,
            "MOWER_DATA_DIR": str(data_root),
            "PYTHONPATH": str(installed),
        }
        result = subprocess.run(
            [sys.executable, "-c", code, space, agent or ""],
            cwd=installed,
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr
    assert (
        json.loads((data_root / "first/config/rescue_plan.json").read_text())["plan1"][
            "central"
        ]["plans"][0]["agent"]
        == "红"
    )
