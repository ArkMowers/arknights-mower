import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.config.plan import PlanModel  # noqa: E402
from arknights_mower.utils.factory_product import (  # noqa: E402
    FACTORY_PRODUCTS,
    drone_plan,
    parse_product_task_meta,
    product_task_meta,
)
from arknights_mower.utils.operators import (  # noqa: E402
    Operator,
    Operators,
    build_global_plan,
)
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.scheduler_task import (  # noqa: E402
    SchedulerTask,
    TaskTypes,
)


def product_plan(default="gold", backup="exp3"):
    room = "room_1_2"
    conf = PlanConfig("", "", "")
    return room, {
        "default_plan": Plan(
            {room: [Room("Lancet-2", "", [], "制造站", default)]},
            conf,
            products={room: default},
        ),
        "backup_plans": [
            Plan(
                {room: [Room("Current", "", [], "制造站", backup)]},
                conf,
                products={room: backup},
            )
        ],
    }


def test_build_global_plan_keeps_products_separate_from_operator_slots(monkeypatch):
    configured = PlanModel(
        plan1={
            "room_1_2": {
                "name": "制造站",
                "product": "gold",
                "plans": [{"agent": "Lancet-2"}],
            }
        },
        backup_plans=[
            {
                "conf": {
                    "rest_in_full": "",
                    "exhaust_require": "",
                    "resting_priority": "",
                    "resting_standby": "",
                    "ling_xi": 1,
                    "workaholic": "",
                    "free_blacklist": "",
                    "ope_resting_priority": "",
                    "refresh_trading": "",
                    "refresh_drained": "",
                },
                "plan": {
                    "room_1_2": {
                        "name": "制造站",
                        "product": "orirock",
                        "plans": [{"agent": "Current"}],
                    }
                },
                "task": {},
                "trigger": {"left": "", "operator": "", "right": ""},
            }
        ],
    )
    monkeypatch.setattr(config, "plan", configured)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(
        "arknights_mower.utils.logic_expression.get_logic_exp", lambda _: None
    )

    global_plan = build_global_plan()

    assert global_plan["default_plan"].products == {"room_1_2": "gold"}
    assert global_plan["backup_plans"][0].products == {"room_1_2": "orirock"}


def test_legacy_orirock_means_rock_recipe_and_device_is_separate():
    assert FACTORY_PRODUCTS["orirock"].name == "源石碎片（固源岩）"
    assert FACTORY_PRODUCTS["orirock"].recipe == (500, 250)
    assert FACTORY_PRODUCTS["orirock_device"].name == "源石碎片（装置）"
    assert FACTORY_PRODUCTS["orirock_device"].recipe == (1240, 250)
    assert parse_product_task_meta("room_1_2,orirock_device") == (
        "room_1_2",
        "orirock_device",
    )


def test_device_recipe_is_kept_in_backup_plan(monkeypatch):
    configured = PlanModel(
        plan1={
            "room_1_2": {
                "name": "制造站",
                "product": "orirock",
                "plans": [{"agent": "Lancet-2"}],
            }
        },
        backup_plans=[
            {
                "conf": {
                    "rest_in_full": "",
                    "exhaust_require": "",
                    "resting_priority": "",
                    "resting_standby": "",
                    "ling_xi": 1,
                    "workaholic": "",
                    "free_blacklist": "",
                    "ope_resting_priority": "",
                    "refresh_trading": "",
                    "refresh_drained": "",
                },
                "plan": {
                    "room_1_2": {
                        "name": "制造站",
                        "product": "orirock_device",
                        "plans": [{"agent": "Current"}],
                    }
                },
                "task": {},
                "trigger": {"left": "True", "operator": "==", "right": "True"},
            }
        ],
    )
    monkeypatch.setattr(config, "plan", configured)
    monkeypatch.setattr(config, "conf", config.Conf())

    global_plan = build_global_plan()

    assert global_plan["default_plan"].products == {"room_1_2": "orirock"}
    assert global_plan["backup_plans"][0].products == {"room_1_2": "orirock_device"}


def test_product_mapping_overrides_current_slots_and_restores_default():
    room, plan = product_plan()
    operators = Operators(plan)
    assert operators.products == {room: "gold"}

    operators.swap_plan([True])
    assert operators.products == {room: "exp3"}
    assert operators.plan[room][0].agent == "Lancet-2"

    operators.swap_plan([False])
    assert operators.products == {room: "gold"}


def test_product_task_deduplicates_by_room_and_keeps_latest(monkeypatch):
    room, plan = product_plan()
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = Operators(plan)
    solver.op_data.swap_plan([True])
    solver.tasks = [
        SchedulerTask(
            task_type=TaskTypes.SWITCH_PRODUCT,
            meta_data=product_task_meta(room, "gold"),
        )
    ]
    monkeypatch.setattr(config, "conf", config.Conf())

    solver.queue_product_switches({room: "gold"})

    tasks = [task for task in solver.tasks if task.type == TaskTypes.SWITCH_PRODUCT]
    assert len(tasks) == 1
    assert tasks[0].meta_data == product_task_meta(room, "exp3")


def test_trade_product_also_generates_a_switch_task(monkeypatch):
    room = "room_1_1"
    conf = PlanConfig("", "", "")
    plan = {
        "default_plan": Plan(
            {room: [Room("但书", "", [], "贸易站", "lmd")]},
            conf,
            products={room: "lmd"},
        ),
        "backup_plans": [],
    }
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = Operators(plan)
    solver.tasks = []
    monkeypatch.setattr(config, "conf", config.Conf())

    solver.queue_product_switches()

    assert solver.tasks[0].meta_data == product_task_meta(room, "lmd")


@pytest.mark.parametrize(
    ("total_seconds", "unit_seconds", "expected"),
    [
        (72 * 60, 72 * 60, (24, 0)),
        (72 * 60 + 100, 72 * 60, (0, 100)),
        (180 * 60 + 149, 180 * 60, (0, 149)),
        (180 * 60 + 150, 180 * 60, (1, 0)),
        (180 * 60 + 179, 180 * 60, (1, 0)),
        (180 * 60 + 181, 180 * 60, (1, 1)),
        (0, 72 * 60, (0, 0)),
    ],
)
def test_drone_plan_boundaries(total_seconds, unit_seconds, expected):
    assert drone_plan(total_seconds, unit_seconds) == expected


def test_drone_plan_respects_configured_loss_tolerance():
    total_seconds = 180 * 60 + 179
    assert drone_plan(total_seconds, 180 * 60, max_loss_seconds=0) == (0, 179)
    assert drone_plan(total_seconds, 180 * 60, max_loss_seconds=1) == (1, 0)


def acceleration_solver(*, available_drones, current_total):
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.recog = SimpleNamespace(gray=MagicMock(), h=1080, w=1920)
    solver.digit_reader = MagicMock()
    solver.digit_reader.get_drone.return_value = available_drones
    solver._open_factory_product_detail = MagicMock()
    solver.read_factory_product = MagicMock(return_value="gold")
    solver._tap_drone_accelerate = MagicMock()
    solver._read_factory_total_seconds = MagicMock(return_value=current_total)
    solver._confirm_drone_count = MagicMock()
    solver._tap_factory_point = MagicMock()
    solver.translate_room = MagicMock(return_value="制造站")
    return solver


def test_factory_execution_rechecks_progress_and_only_lowers_drone_count():
    solver = acceleration_solver(available_drones=10, current_total=4640)
    observation = {
        "room": "room_1_2",
        "target_product": "exp3",
        "current_product": "gold",
        "total_seconds": 5000,
        "current_remaining": 1000,
        "drone_count": 5,
    }

    wait_seconds = solver._execute_factory_acceleration(observation)

    solver._confirm_drone_count.assert_called_once_with(3)
    assert wait_seconds == 100


def test_factory_execution_below_loss_threshold_uses_no_drone():
    solver = acceleration_solver(available_drones=10, current_total=4149)
    observation = {
        "room": "room_1_2",
        "target_product": "exp3",
        "current_product": "gold",
        "total_seconds": 5000,
        "current_remaining": 1000,
        "drone_count": 0,
    }

    wait_seconds = solver._execute_factory_acceleration(observation)

    solver._confirm_drone_count.assert_not_called()
    solver._tap_factory_point.assert_called_once_with((480, 864))
    assert wait_seconds == 149


def test_factory_execution_at_loss_threshold_uses_one_drone():
    solver = acceleration_solver(available_drones=10, current_total=4150)
    observation = {
        "room": "room_1_2",
        "target_product": "exp3",
        "current_product": "gold",
        "total_seconds": 5000,
        "current_remaining": 1000,
        "drone_count": 1,
    }

    wait_seconds = solver._execute_factory_acceleration(observation)

    solver._confirm_drone_count.assert_called_once_with(1)
    assert wait_seconds == 0


def test_factory_execution_without_grandet_mode_finishes_immediately(monkeypatch):
    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.product_switching.grandet_mode = False
    solver = acceleration_solver(available_drones=10, current_total=4149)
    observation = {
        "room": "room_1_2",
        "target_product": "exp3",
        "current_product": "gold",
        "total_seconds": 5000,
        "current_remaining": 1000,
        "drone_count": 1,
    }

    wait_seconds = solver._execute_factory_acceleration(observation)

    solver._confirm_drone_count.assert_called_once_with(1)
    assert wait_seconds == 0


def test_factory_product_change_handles_both_confirms_and_fills_queue():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver._tap_factory_point = MagicMock()
    solver._wait_factory_resource = MagicMock()

    solver._select_factory_product("exp3")

    assert [item.args for item in solver._tap_factory_point.call_args_list] == [
        ((1680, 500),),
        ((180, 195),),
        ((500, 525),),
        ((1425, 895),),
        ((1440, 742),),
        ((1450, 305),),
        ((1425, 895),),
    ]
    solver._wait_factory_resource.assert_any_call("factory_product_cancel_confirm")
    solver._wait_factory_resource.assert_any_call(
        "factory_product_cancel_confirm", present=False
    )


@pytest.mark.parametrize(
    ("product_id", "recipe"),
    [("orirock", (500, 250)), ("orirock_device", (1240, 250))],
)
def test_factory_product_change_selects_each_orundum_recipe(product_id, recipe):
    solver = object.__new__(base.BaseSchedulerSolver)
    solver._tap_factory_point = MagicMock()
    solver._wait_factory_resource = MagicMock()

    solver._select_factory_product(product_id)

    taps = [item.args[0] for item in solver._tap_factory_point.call_args_list]
    assert taps[:3] == [(1680, 500), (180, 620), recipe]


@pytest.mark.parametrize(
    ("material_text", "expected"),
    [("固源岩", "orirock"), ("装置", "orirock_device")],
)
def test_read_factory_product_distinguishes_orundum_material(material_text, expected):
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.recog = SimpleNamespace(w=1920, h=1080)
    solver._factory_ocr_text = MagicMock(side_effect=["", material_text])

    assert solver.read_factory_product() == expected
    assert solver._factory_ocr_text.call_count == 2


def test_orundum_recipes_require_switching_between_each_other():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver._open_factory_product_detail = MagicMock()
    solver.read_factory_product = MagicMock(return_value="orirock")
    solver.digit_reader = MagicMock()
    solver.digit_reader.get_drone.return_value = 100
    solver.recog = SimpleNamespace(gray=MagicMock(), h=1080, w=1920)
    solver._tap_drone_accelerate = MagicMock()
    solver._read_factory_total_seconds = MagicMock(return_value=3600)
    solver._tap_factory_point = MagicMock()

    observation = solver._survey_factory_switch("room_1_2", "orirock_device")

    assert observation["needs_switch"] is True
    assert observation["current_product"] == "orirock"


def test_inventory_count_supports_selected_materials_and_total_exp(monkeypatch):
    counts = {
        "赤金": 123,
        "基础作战记录": 1,
        "初级作战记录": 2,
        "中级作战记录": 3,
        "高级作战记录": 4,
    }
    monkeypatch.setattr(
        base.Operators.__module__ + ".get_inventory_counts",
        lambda names=None: {name: counts[name] for name in names if name in counts},
    )
    operators = object.__new__(Operators)

    assert operators.inventory_count("赤金") == 123
    assert operators.inventory_count("装置") == 0
    assert operators.inventory_count("全部经验（计算）") == 12_000


def test_inventory_count_can_be_used_in_backup_expression(monkeypatch):
    room, plan = product_plan()
    monkeypatch.setattr(
        base.Operators.__module__ + ".get_inventory_counts",
        lambda names=None: {"固源岩": 80},
    )
    operators = Operators(plan)

    assert operators.evaluate_expression("op_data.inventory_count('固源岩') >= 60")


def test_facility_state_is_cached_and_available_to_backup_expression():
    room, plan = product_plan()
    operators = Operators(plan)

    operators.update_facility_state(
        room, "factory", "exp3", updated_at="2026-09-20T12:00:00"
    )

    assert operators.facility_states[room] == {
        "facility": "factory",
        "product": "exp3",
        "updated_at": "2026-09-20T12:00:00",
    }
    assert operators.facility_product(room) == "exp3"
    assert operators.evaluate_expression("op_data.facility_product('room_1_2') == exp3")


def test_facility_operator_count_supports_all_base_rooms():
    room, plan = product_plan()
    operators = Operators(plan)
    operators.operators["测试干员"] = SimpleNamespace(current_room="central")

    assert operators.facility_operator_count("central") == 1
    assert operators.facility_operator_count(room) == 0
    assert operators.evaluate_expression(
        "op_data.facility_operator_count('central') >= 1"
    )


def test_facility_type_reuses_current_plan():
    room, plan = product_plan()
    operators = Operators(plan)

    assert operators.facility_type(room) == "制造站"
    assert operators.evaluate_expression(
        "op_data.facility_type('room_1_2') == '制造站'"
    )


def test_facility_operator_binding_and_work_relation_are_available_to_expression():
    room, plan = product_plan()
    operators = Operators(plan)
    operators.add(Operator("Lancet-2", ""))
    operators.add(Operator("阿米娅", ""))
    lancet = operators.operators["Lancet-2"]
    amiya = operators.operators["阿米娅"]
    lancet.current_room = room
    lancet.current_index = 0
    amiya.current_room = room
    amiya.current_index = 1

    assert operators.operators_work_together("Lancet-2", "阿米娅")
    assert operators.evaluate_expression(
        "op_data.operators_work_together('Lancet-2', '阿米娅')"
    )

    amiya.current_room = "dormitory_1"
    assert not operators.operators_work_together("Lancet-2", "阿米娅")


def test_facility_product_statistics_are_available_to_expression():
    room, plan = product_plan()
    operators = Operators(plan)
    operators.update_facility_state(room, "factory", "gold")
    operators.update_facility_state("room_1_1", "trade", "lmd")
    operators.update_facility_state("room_2_1", "factory", "gold")

    assert operators.facility_product_count("gold") == 2
    assert operators.facility_product_type_count() == 2
    assert operators.evaluate_expression("op_data.facility_product_count('gold') == 2")
    assert operators.evaluate_expression("op_data.facility_product_type_count() == 2")


def test_facility_state_can_hold_inventory_backup_until_lower_threshold(monkeypatch):
    room, plan = product_plan()
    inventory = {"赤金": 6_000}
    monkeypatch.setattr(
        base.Operators.__module__ + ".get_inventory_counts",
        lambda names=None: {name: inventory.get(name, 0) for name in names},
    )
    operators = Operators(plan)
    operators.update_facility_state(room, "factory", "exp3")
    expression = (
        "op_data.inventory_count('赤金') >= 7000 or "
        "(op_data.inventory_count('赤金') > 200 and "
        "op_data.facility_product('room_1_2') == exp3)"
    )

    assert operators.evaluate_expression(expression)
    inventory["赤金"] = 200
    assert not operators.evaluate_expression(expression)


def test_mood_room_visit_refreshes_factory_state_before_operator_detail():
    room, plan = product_plan()
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = Operators(plan)
    solver._tap_factory_point = MagicMock()
    solver._wait_factory_resource = MagicMock()
    solver.read_factory_product = MagicMock(return_value="gold")
    solver.scene_graph_navigation = MagicMock()
    solver.translate_room = MagicMock(return_value="B102")

    solver.refresh_facility_state(room)

    assert solver.op_data.facility_product(room) == "gold"
    solver._tap_factory_point.assert_called_once_with((96, 1026), interval=3)
    solver._wait_factory_resource.assert_called_once_with("factory_accelerate")
    solver.scene_graph_navigation.assert_called_once_with(base.Scene.INFRA_DETAILS)


def test_mood_room_visit_refreshes_trade_order_state():
    room = "room_1_1"
    conf = PlanConfig("", "", "")
    plan = {
        "default_plan": Plan(
            {room: [Room("Lancet-2", "", [], "贸易站", "lmd")]},
            conf,
            products={room: "lmd"},
        ),
        "backup_plans": [],
    }
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = Operators(plan)
    solver._tap_factory_point = MagicMock()
    solver._wait_factory_resource = MagicMock()
    solver.read_trade_product = MagicMock(return_value="orundum")
    solver._close_trade_product_select = MagicMock()
    solver.scene_graph_navigation = MagicMock()
    solver.translate_room = MagicMock(return_value="B101")

    solver.refresh_facility_state(room)

    assert solver.op_data.facility_product(room) == "orundum"
    assert [call.args for call in solver._tap_factory_point.call_args_list] == [
        ((96, 1026),),
        ((1580, 955),),
    ]
    solver._close_trade_product_select.assert_called_once()
    solver.scene_graph_navigation.assert_called_once_with(base.Scene.INFRA_DETAILS)


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("6 * 7", 42),
        ("8 / 4", 2),
        ("8 // 3", 2),
        ("8 % 3", 2),
        ("2 ** 3", 8),
    ],
)
def test_backup_expression_supports_common_arithmetic(expression, expected):
    _, plan = product_plan()
    operators = Operators(plan)

    assert operators.evaluate_expression(expression) == expected


def test_batch_surveys_every_station_before_spending_drones():
    tasks = [
        SchedulerTask(
            task_type=TaskTypes.SWITCH_PRODUCT,
            meta_data=product_task_meta("room_1_2", "gold"),
        ),
        SchedulerTask(
            task_type=TaskTypes.SWITCH_PRODUCT,
            meta_data=product_task_meta("room_2_2", "exp3"),
        ),
        SchedulerTask(
            task_type=TaskTypes.SWITCH_PRODUCT,
            meta_data=product_task_meta("room_1_1", "orundum"),
        ),
    ]
    events = []
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.tasks = list(tasks)
    solver.recog = SimpleNamespace(update=MagicMock())
    solver.sleep = MagicMock()

    factory_observations = {
        "room_1_2": {
            "room": "room_1_2",
            "facility": "factory",
            "target_product": "gold",
            "needs_switch": True,
            "drone_count": 4,
            "wait_seconds": 150,
            "available_drones": 20,
        },
        "room_2_2": {
            "room": "room_2_2",
            "facility": "factory",
            "target_product": "exp3",
            "needs_switch": True,
            "drone_count": 3,
            "wait_seconds": 20,
            "available_drones": 20,
        },
    }

    def survey_factory(room, target):
        events.append(("survey", room))
        return factory_observations[room]

    solver._survey_factory_switch = MagicMock(side_effect=survey_factory)
    solver._survey_trade_switch = MagicMock(
        side_effect=lambda room, target: (
            events.append(("survey", room))
            or {
                "room": room,
                "facility": "trade",
                "target_product": target,
                "needs_switch": True,
            }
        )
    )
    solver._execute_factory_acceleration = MagicMock(
        side_effect=lambda item: events.append(("accelerate", item["room"])) or 10
    )
    solver._change_factory_product = MagicMock(
        side_effect=lambda item: events.append(("change", item["room"]))
    )
    solver._change_trade_product = MagicMock(
        side_effect=lambda item: events.append(("change", item["room"]))
    )

    solver.switch_base_products(tasks)

    assert events[:3] == [
        ("survey", "room_1_2"),
        ("survey", "room_2_2"),
        ("survey", "room_1_1"),
    ]
    assert events[3:6] == [
        ("change", "room_1_1"),
        ("accelerate", "room_1_2"),
        ("accelerate", "room_2_2"),
    ]
    assert solver.tasks == []


def test_batch_with_insufficient_drones_does_not_accelerate_any_station():
    tasks = [
        SchedulerTask(
            task_type=TaskTypes.SWITCH_PRODUCT,
            meta_data=product_task_meta("room_1_2", "gold"),
        ),
        SchedulerTask(
            task_type=TaskTypes.SWITCH_PRODUCT,
            meta_data=product_task_meta("room_2_2", "exp3"),
        ),
    ]
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.tasks = list(tasks)
    solver._survey_factory_switch = MagicMock(
        side_effect=[
            {
                "room": "room_1_2",
                "facility": "factory",
                "target_product": "gold",
                "needs_switch": True,
                "drone_count": 4,
                "wait_seconds": 100,
                "available_drones": 6,
            },
            {
                "room": "room_2_2",
                "facility": "factory",
                "target_product": "exp3",
                "needs_switch": True,
                "drone_count": 3,
                "wait_seconds": 50,
                "available_drones": 6,
            },
        ]
    )
    solver._execute_factory_acceleration = MagicMock()
    solver._change_factory_product = MagicMock()

    with pytest.raises(base.ProductSwitchDeferred):
        solver.switch_base_products(tasks)

    assert solver._survey_factory_switch.call_count == 2
    solver._execute_factory_acceleration.assert_not_called()
    solver._change_factory_product.assert_not_called()
    assert solver.tasks == tasks


def test_insufficient_factory_drones_do_not_block_direct_trade_switch():
    factory_task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_1_2", "gold"),
    )
    trade_task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_1_1", "orundum"),
    )
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.tasks = [factory_task, trade_task]
    solver._survey_factory_switch = MagicMock(
        return_value={
            "room": "room_1_2",
            "facility": "factory",
            "target_product": "gold",
            "needs_switch": True,
            "drone_count": 7,
            "wait_seconds": 50,
            "available_drones": 6,
        }
    )
    trade_observation = {
        "room": "room_1_1",
        "facility": "trade",
        "target_product": "orundum",
        "needs_switch": True,
    }
    solver._survey_trade_switch = MagicMock(return_value=trade_observation)
    solver._change_trade_product = MagicMock()
    solver._execute_factory_acceleration = MagicMock()

    with pytest.raises(base.ProductSwitchDeferred):
        solver.switch_base_products([factory_task, trade_task])

    solver._change_trade_product.assert_called_once_with(trade_observation)
    solver._execute_factory_acceleration.assert_not_called()
    assert solver.tasks == [factory_task]


def test_trade_only_batch_never_enters_factory_drone_flow():
    task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_1_1", "orundum"),
    )
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.tasks = [task]
    solver._survey_trade_switch = MagicMock(
        return_value={
            "room": "room_1_1",
            "facility": "trade",
            "target_product": "orundum",
            "needs_switch": True,
        }
    )
    solver._survey_factory_switch = MagicMock()
    solver._execute_factory_acceleration = MagicMock()
    solver._change_factory_product = MagicMock()
    solver._change_trade_product = MagicMock()

    solver.switch_base_products([task])

    solver._survey_factory_switch.assert_not_called()
    solver._execute_factory_acceleration.assert_not_called()
    solver._change_factory_product.assert_not_called()
    solver._change_trade_product.assert_called_once()
    assert solver.tasks == []


def test_mixed_batch_accelerates_factory_and_switches_both_facilities(monkeypatch):
    factory_task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_1_2", "exp3"),
    )
    trade_task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_1_1", "orundum"),
    )
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.tasks = [factory_task, trade_task]
    solver.recog = SimpleNamespace(update=MagicMock())
    solver.sleep = MagicMock()
    factory_observation = {
        "room": "room_1_2",
        "facility": "factory",
        "target_product": "exp3",
        "needs_switch": True,
        "drone_count": 2,
        "wait_seconds": 90,
        "available_drones": 10,
    }
    trade_observation = {
        "room": "room_1_1",
        "facility": "trade",
        "target_product": "orundum",
        "needs_switch": True,
    }
    solver._survey_factory_switch = MagicMock(return_value=factory_observation)
    solver._survey_trade_switch = MagicMock(return_value=trade_observation)
    solver._execute_factory_acceleration = MagicMock(return_value=30)
    solver._change_factory_product = MagicMock()
    solver._change_trade_product = MagicMock()
    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.product_switching.waiting_seconds = 5

    solver.switch_base_products([factory_task, trade_task])

    solver._execute_factory_acceleration.assert_called_once_with(factory_observation)
    solver._change_factory_product.assert_called_once_with(factory_observation)
    solver._change_trade_product.assert_called_once_with(trade_observation)
    solver.sleep.assert_called_once_with(35)
    assert solver.tasks == []


def test_non_grandet_batch_switches_immediately_without_buffer(monkeypatch):
    task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_1_2", "exp3"),
    )
    observation = {
        "room": "room_1_2",
        "facility": "factory",
        "target_product": "exp3",
        "needs_switch": True,
        "drone_count": 1,
        "wait_seconds": 0,
        "available_drones": 10,
    }
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.tasks = [task]
    solver.recog = SimpleNamespace(update=MagicMock())
    solver.sleep = MagicMock()
    solver._survey_factory_switch = MagicMock(return_value=observation)
    solver._execute_factory_acceleration = MagicMock(return_value=0)
    solver._change_factory_product = MagicMock()
    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.product_switching.grandet_mode = False

    solver.switch_base_products([task])

    solver.sleep.assert_not_called()
    solver.recog.update.assert_not_called()
    solver._change_factory_product.assert_called_once_with(observation)
    assert solver.tasks == []


def test_trade_verification_failure_keeps_batch_tasks():
    task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_1_1", "orundum"),
    )
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.tasks = [task]
    solver._survey_trade_switch = MagicMock(
        return_value={
            "room": "room_1_1",
            "facility": "trade",
            "target_product": "orundum",
            "needs_switch": True,
        }
    )
    solver._change_trade_product = MagicMock(
        side_effect=base.RecognizeError("订单切换校验失败")
    )

    with pytest.raises(base.RecognizeError):
        solver.switch_base_products([task])

    assert solver.tasks == [task]


def test_trade_strategy_uses_selected_checkbox_brightness():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.recog = MagicMock()
    solver.recog.color.side_effect = ([255, 255, 255], [40, 40, 40])
    assert solver.read_trade_product() == "lmd"

    solver.recog.color.side_effect = ([40, 40, 40], [255, 255, 255])
    assert solver.read_trade_product() == "orundum"


def test_trade_switch_closes_persistent_selector_and_reopens_to_verify():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.recog = SimpleNamespace(update=MagicMock())
    solver._open_trade_product_detail = MagicMock()
    solver._tap_factory_point = MagicMock()
    solver._wait_factory_resource = MagicMock()
    solver.read_trade_product = MagicMock(side_effect=["lmd", "orundum"])

    solver._change_trade_product(
        {
            "room": "room_1_1",
            "target_product": "orundum",
        }
    )

    assert [item.args for item in solver._tap_factory_point.call_args_list] == [
        ((1580, 955),),
        ((1140, 530),),
        ((1600, 200),),
        ((1580, 955),),
        ((1600, 200),),
    ]
    assert solver.read_trade_product.call_count == 2
