"""Shared operators expose complete mood history in every bound report group."""

import sqlite3
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from arknights_mower.solvers import record
from arknights_mower.utils import config
from arknights_mower.utils.config.plan import BackupPlan, PlanModel


@pytest.fixture
def history(monkeypatch):
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """CREATE TABLE agent_action (
            name TEXT, agent_current_room TEXT, current_room TEXT,
            is_high INTEGER, agent_group TEXT, mood REAL, current_time TEXT,
            related_operator TEXT, mood_event TEXT
        )"""
    )
    monkeypatch.setattr(
        record, "_fetchall", lambda sql, *args: connection.execute(sql, args).fetchall()
    )
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "plan", PlanModel())
    day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    def add(name, group, hour, mood, room="room_3_2", high=1, related=None, event=None):
        timestamp = (day + timedelta(hours=hour)).strftime("%Y-%m-%d %H:%M:%S.%f")
        connection.execute(
            "INSERT INTO agent_action VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, room, room, high, group, mood, timestamp, related, event),
        )

    yield add
    connection.close()


def bind_shared(monkeypatch, *, backup=False, room="room_3_2"):
    facilities = {
        room: {
            "plans": [
                {
                    "agent": "结城理",
                    "group": "深海",
                    "replacement": ["白面鸮"],
                    "group_bindings": [
                        {"group": "自动化", "replacement": ["白面鸮"]},
                        {"group": "sees", "replacement": ["斑点"]},
                    ],
                }
            ]
        }
    }
    plan = PlanModel.model_validate(
        {"backup_plans": [{"plan": facilities, "conf": {}, "task": {}, "trigger": {}}]}
        if backup
        else {"plan1": facilities}
    )
    monkeypatch.setattr(config, "plan", plan)
    return plan


@pytest.mark.parametrize("backup", [False, True])
def test_every_binding_contains_complete_chronological_history(
    history, monkeypatch, backup
):
    plan = bind_shared(monkeypatch, backup=backup)
    before = plan.model_dump()
    history("结城理", "自动化", 3, 24, related="菲亚梅塔", event="fiammetta_after")
    history("结城理", "深海", 1, 20)
    history("结城理", "sees", 2, 22)
    history("结城理", "", 0, 24, room="train", high=0)
    history("结城理", "旧组", -8 * 24, 19)
    history("歌蕾蒂娅", "深海", 1, 18)
    history("温蒂", "自动化", 1, 17)

    groups = {group["groupName"]: group for group in record.get_mood_ratios()}

    assert set(groups) == {"深海", "自动化", "sees"}
    curves = []
    for name, group in groups.items():
        datasets = group["moodData"]["datasets"]
        shared = [dataset for dataset in datasets if dataset["label"] == "结城理"]
        assert len(shared) == 1
        curves.append(shared[0]["data"])
        assert [point["y"] for point in curves[-1]] == [24, 20, 22, 24]
        assert curves[-1][-1]["relatedOperator"] == "菲亚梅塔"
        assert curves[-1][-1]["moodEvent"] == "fiammetta_after"
        assert [point["x"] for point in curves[-1]] == sorted(
            point["x"] for point in curves[-1]
        )
        expected = {"结城理"} | (
            {"歌蕾蒂娅"} if name == "深海" else {"温蒂"} if name == "自动化" else set()
        )
        assert {dataset["label"] for dataset in datasets} == expected
    assert curves[0] == curves[1] == curves[2]
    assert plan.model_dump() == before


def test_shared_dormitory_resident_is_not_filtered_out(history, monkeypatch):
    bind_shared(monkeypatch, room="dormitory_1")
    history("结城理", "深海", 1, 12, room="dormitory_1")
    history("结城理", "自动化", 2, 16, room="dormitory_1")
    history("塑心", "", 1, 24, room="dormitory_1")

    groups = record.get_mood_ratios()

    assert {group["groupName"] for group in groups} == {"深海", "自动化", "sees"}
    for group in groups:
        assert [dataset["label"] for dataset in group["moodData"]["datasets"]] == [
            "结城理"
        ]
        assert [point["y"] for point in group["moodData"]["datasets"][0]["data"]] == [
            12,
            16,
        ]
    assert record.get_work_rest_ratios()["结城理"]["datasets"][0]["data"] == [3600, 0]


def test_single_binding_favorites_and_fiammetta_keep_existing_membership(
    history, monkeypatch
):
    monkeypatch.setattr(config.conf, "favorite", "红")
    monkeypatch.setattr(
        config,
        "plan",
        PlanModel.model_validate(
            {
                "plan1": {
                    "contact": {"plans": [{"agent": "阿米娅", "group": "主表组"}]}
                },
                "backup_plans": [
                    {
                        "plan": {
                            "contact": {
                                "plans": [{"agent": "阿米娅", "group": "副表组"}]
                            }
                        }
                    }
                ],
            }
        ),
    )
    history("阿米娅", "主表组", 1, 20)
    history("阿米娅", "副表组", 2, 18)
    history("红", "", 1, 12, room="dormitory_1", high=0)
    history("菲亚梅塔", "", 1, 24, room="dormitory_1")
    history("黑角", "替班", 1, 12, high=0)

    groups = {group["groupName"]: group for group in record.get_mood_ratios()}

    assert set(groups) == {"主表组", "副表组", "红", "菲亚梅塔"}
    assert [
        point["y"] for point in groups["主表组"]["moodData"]["datasets"][0]["data"]
    ] == [20]
    assert [
        point["y"] for point in groups["副表组"]["moodData"]["datasets"][0]["data"]
    ] == [18]


def test_repeated_plan_declarations_do_not_duplicate_shared_samples(
    history, monkeypatch
):
    plan = bind_shared(monkeypatch)
    plan.backup_plans = [
        BackupPlan(plan=plan.plan1.model_copy(deep=True), conf={}, task={}, trigger={})
    ]
    history("结城理", "深海", 1, 20)

    groups = record.get_mood_ratios()

    assert len(groups) == 3
    assert all(len(group["moodData"]["datasets"][0]["data"]) == 1 for group in groups)


@pytest.mark.parametrize("options", [{}, {"include_work_rest": True}])
def test_curve_only_reports_skip_monthly_work_rest_and_preserve_curves(
    history, monkeypatch, options
):
    bind_shared(monkeypatch)
    history("结城理", "旧组", 0, 24, room="dormitory_1")
    history("结城理", "深海", 1, 20)
    history("结城理", "自动化", 2, 24, related="菲亚梅塔", event="fiammetta_after")
    complete = record.get_mood_ratios(**options)
    assert len(complete) == 3
    assert all(
        group["workRestData"]
        == {
            "labels": ["休息时间", "工作时间"],
            "datasets": [{"data": [3600, 3600]}],
        }
        for group in complete
    )
    monthly = Mock(
        side_effect=AssertionError("curve requests do not read monthly history")
    )
    monkeypatch.setattr(record, "get_work_rest_ratios", monthly)

    curves = record.get_mood_ratios(include_work_rest=False)

    monthly.assert_not_called()
    assert curves == [
        {"groupName": group["groupName"], "moodData": group["moodData"]}
        for group in complete
    ]
    for group in curves:
        points = group["moodData"]["datasets"][0]["data"]
        assert [point["y"] for point in points] == [24, 20, 24]
        assert points[-1]["relatedOperator"] == "菲亚梅塔"
        assert points[-1]["moodEvent"] == "fiammetta_after"


@pytest.mark.parametrize("flag", [None, "true", "false"])
def test_mood_report_http_keeps_legacy_default_and_accepts_curve_only_requests(
    history, monkeypatch, flag
):
    with (
        patch("threading.Thread.start"),
        patch("arknights_mower.utils.network_settings.start_proxy_sync"),
    ):
        from server import app

    history("歌蕾蒂娅", "深海", 0, 20)
    history("歌蕾蒂娅", "深海", 1, 18)
    monthly = Mock(wraps=record.get_work_rest_ratios)
    monkeypatch.setattr(record, "get_work_rest_ratios", monthly)

    response = app.test_client().get(
        "/record/getMoodRatios",
        query_string={} if flag is None else {"include_work_rest": flag},
    )

    assert response.status_code == 200
    assert [
        point["y"] for point in response.json[0]["moodData"]["datasets"][0]["data"]
    ] == [20, 18]
    assert ("workRestData" in response.json[0]) is (flag != "false")
    assert monthly.call_count == (0 if flag == "false" else 1)
