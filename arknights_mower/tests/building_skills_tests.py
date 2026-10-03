"""Building skills share the automatic-mastery BOX and current unlock versions."""

import json

import pytest

from arknights_mower.utils import building_skills as module
from arknights_mower.utils import mastery_recommendation as mastery


@pytest.fixture
def snapshot_path(tmp_path, monkeypatch):
    path = tmp_path / "cultivate.json"
    monkeypatch.setattr(mastery, "get_path", lambda _: path)
    return path


def write_snapshot(path, *characters):
    path.write_text(
        json.dumps(
            {
                "code": 0,
                "data": {"characters": list(characters)},
            }
        ),
        encoding="utf-8",
    )


def operator(snapshot, name):
    return next(a for a in snapshot["operators"] if a["name"] == name)


def test_elite_upgrade_replaces_same_key_skill(snapshot_path):
    write_snapshot(
        snapshot_path, {"id": "char_108_silent", "evolvePhase": 2, "level": 1}
    )
    snapshot = module.load_skill_snapshot()
    assert snapshot["has_data"]
    entry = operator(snapshot, "赫默")
    assert entry["owned"] is True
    assert [s["status"] for s in entry["skills"]] == ["replaced", "active"]
    assert [
        s["skillIcon"] for s in module.unlocked_skills("赫默", "制造站", snapshot)
    ] == ["bskill_man_spd2"]


def test_low_progress_and_unowned_skills_are_not_assumed(snapshot_path):
    write_snapshot(
        snapshot_path, {"id": "char_108_silent", "evolvePhase": 0, "level": 1}
    )
    snapshot = module.load_skill_snapshot()
    assert [s["status"] for s in operator(snapshot, "赫默")["skills"]] == [
        "active",
        "locked",
    ]
    assert module.owned_operator("赫默", snapshot) is True
    assert module.owned_operator("泡泡", snapshot) is False
    assert module.unlocked_skills("泡泡", "制造站", snapshot) == ()
    assert module.unlocked_skills("赫默", "贸易站", snapshot) == ()


def test_level_unlock_in_same_elite_phase(snapshot_path):
    # Low-rarity room skills can unlock at level 30 without promotion.
    write_snapshot(
        snapshot_path, {"id": "char_285_medic2", "evolvePhase": 0, "level": 1}
    )
    before = operator(module.load_skill_snapshot(), "Lancet-2")
    write_snapshot(
        snapshot_path, {"id": "char_285_medic2", "evolvePhase": 0, "level": 30}
    )
    after = operator(module.load_skill_snapshot(), "Lancet-2")
    assert len(after["active_skills"]) > len(before["active_skills"])


@pytest.mark.parametrize(
    "character",
    [
        {"id": "char_108_silent"},
        {"id": "char_108_silent", "evolvePhase": 2},
        {"id": "char_108_silent", "level": 1},
    ],
)
def test_missing_growth_keeps_owned_but_unknown_skills(snapshot_path, character):
    write_snapshot(snapshot_path, character)
    snapshot = module.load_skill_snapshot()
    assert module.owned_operator("赫默", snapshot) is True
    assert module.unlocked_skills("赫默", "制造站", snapshot) is None
    assert all(s["status"] == "unknown" for s in operator(snapshot, "赫默")["skills"])


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"data": {"items": []}},
        {"data": {"characters": []}},
        {"data": {"characters": [{"id": "char_108_silent", "evolvePhase": "2"}]}},
    ],
)
def test_invalid_snapshot_keeps_unknown(snapshot_path, payload):
    snapshot_path.write_text(json.dumps(payload), encoding="utf-8")
    snapshot = module.load_skill_snapshot()
    assert not snapshot["has_data"]
    assert module.owned_operator("赫默", snapshot) is None
    assert module.unlocked_skills("赫默", "制造站", snapshot) is None


def test_mastery_and_building_skills_share_reads_and_refresh(
    snapshot_path, monkeypatch
):
    character = {
        "id": "char_108_silent",
        "evolvePhase": 2,
        "level": 1,
        "skills": [{"level": 1}],
    }
    write_snapshot(snapshot_path, character)
    loads = []
    original_load = mastery.json.load

    def observe_load(file, *args, **kwargs):
        if str(file.name) == str(snapshot_path):
            loads.append(file.name)
        return original_load(file, *args, **kwargs)

    monkeypatch.setattr(mastery.json, "load", observe_load)
    assert mastery.get_current_mastery_level(character["id"], 0) == 1
    assert operator(module.load_skill_snapshot(), "赫默")["level"] == 1
    assert mastery.get_cultivate_characters()[character["id"]]["level"] == 1
    assert len(loads) == 1

    character["level"] = 85
    character["skills"][0]["level"] = 2
    write_snapshot(snapshot_path, character)
    assert operator(module.load_skill_snapshot(), "赫默")["level"] == 85
    assert mastery.get_current_mastery_level(character["id"], 0) == 2
    assert len(loads) == 2


def test_unknown_resource_id_mapping_does_not_claim_unowned(snapshot_path, monkeypatch):
    write_snapshot(
        snapshot_path, {"id": "char_108_silent", "evolvePhase": 2, "level": 1}
    )
    monkeypatch.setattr(module, "_operator_ids_by_name", lambda: {})
    snapshot = module.load_skill_snapshot()
    assert snapshot["has_data"]
    assert module.owned_operator("赫默", snapshot) is None
    assert module.unlocked_skills("赫默", "制造站", snapshot) is None


def test_missing_cache_is_unavailable(snapshot_path):
    assert not module.load_skill_snapshot()["has_data"]


def test_snapshot_endpoint_is_read_only_and_authenticated(snapshot_path, monkeypatch):
    import server

    write_snapshot(
        snapshot_path, {"id": "char_108_silent", "evolvePhase": 2, "level": 1}
    )
    monkeypatch.setattr(server.app, "token", "local-test", raising=False)
    client = server.app.test_client()
    assert client.get("/basement-skill/operators").status_code == 403
    response = client.get("/basement-skill/operators", headers={"token": "local-test"})
    assert response.status_code == 200
    assert response.json["has_data"] is True
    assert operator(response.json, "赫默")["active_skills"] == [
        {"skill_key": 0, "skill_level": 1}
    ]


@pytest.mark.parametrize("extra_forms", [0, 1, 5])
def test_amiya_forms_share_building_unlocks(snapshot_path, monkeypatch, extra_forms):
    ids = ["char_002_amiya", "char_1001_amiya2", "char_1037_amiya3"]
    ids += [f"future_amiya_{i}" for i in range(extra_forms)]
    monkeypatch.setattr(module, "_operator_ids_by_name", lambda: {"阿米娅": set(ids)})
    write_snapshot(
        snapshot_path, *[{"id": cid, "evolvePhase": 2, "level": 80} for cid in ids]
    )
    snapshot = module.load_skill_snapshot()
    entry = operator(snapshot, "阿米娅")
    assert (entry["owned"], entry["phase"], entry["level"]) == (True, 2, 80)
    assert module.unlocked_skills("阿米娅", "中枢", snapshot)
    assert module.unlocked_skills("阿米娅", "发电站", snapshot) == ()
    assert all(s["status"] != "unknown" for s in entry["skills"])


def test_shared_forms_use_valid_progress_without_losing_unlocks(
    snapshot_path, monkeypatch
):
    monkeypatch.setattr(
        module,
        "_operator_ids_by_name",
        lambda: {"阿米娅": {"base", "other", "missing"}},
    )
    write_snapshot(
        snapshot_path,
        {"id": "base", "evolvePhase": 0, "level": 1},
        {"id": "other", "evolvePhase": 2, "level": 80},
        {"id": "missing"},
    )
    entry = operator(module.load_skill_snapshot(), "阿米娅")
    assert (entry["phase"], entry["level"]) == (2, 80)
