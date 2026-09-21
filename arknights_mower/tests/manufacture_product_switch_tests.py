import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers import base_schedule as base  # noqa: E402
from arknights_mower.utils import config  # noqa: E402
from arknights_mower.utils.config.plan import PlanModel  # noqa: E402
from arknights_mower.utils.manufacture_product import (  # noqa: E402
    MANUFACTURE_PRODUCTS,
    drone_plan,
    parse_product_task_meta,
    product_task_meta,
)
from arknights_mower.utils.operators import Operators, build_global_plan  # noqa: E402
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
    assert MANUFACTURE_PRODUCTS["orirock"].name == "源石碎片（固源岩）"
    assert MANUFACTURE_PRODUCTS["orirock"].recipe == (500, 250)
    assert MANUFACTURE_PRODUCTS["orirock_device"].name == "源石碎片（装置）"
    assert MANUFACTURE_PRODUCTS["orirock_device"].recipe == (1240, 250)
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
    solver.op_data.update_facility_state(room, "manufacture", "gold")
    solver.op_data.swap_plan([True])
    solver.tasks = [
        SchedulerTask(
            task_type=TaskTypes.SWITCH_PRODUCT,
            meta_data=product_task_meta(room, "gold"),
        )
    ]
    monkeypatch.setattr(config, "conf", config.Conf())

    solver.queue_product_switches()

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
    solver.op_data.update_facility_state(room, "trade", "orundum")
    solver.tasks = []
    monkeypatch.setattr(config, "conf", config.Conf())

    solver.queue_product_switches()

    assert solver.tasks[0].meta_data == product_task_meta(room, "lmd")


def test_product_task_is_not_generated_before_facility_state_is_read():
    room, plan = product_plan()
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = Operators(plan)
    stale_task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta(room, "exp3"),
    )
    unrelated_task = SchedulerTask(task_type=TaskTypes.NOT_SPECIFIC)
    solver.tasks = [stale_task, unrelated_task]
    solver.task = stale_task

    solver.queue_product_switches()

    assert solver.tasks == [unrelated_task]
    assert solver.task is None


def test_matching_facility_state_removes_stale_product_task():
    room, plan = product_plan()
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = Operators(plan)
    solver.op_data.update_facility_state(room, "manufacture", "gold")
    stale_task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta(room, "exp3"),
    )
    unrelated_task = SchedulerTask(task_type=TaskTypes.NOT_SPECIFIC)
    solver.tasks = [stale_task, unrelated_task]

    solver.queue_product_switches()

    assert solver.tasks == [unrelated_task]


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
    solver._open_manufacture_product_detail = MagicMock()
    solver.read_manufacture_product = MagicMock(return_value="gold")
    solver._manufacture_is_idle = MagicMock(return_value=False)
    solver._tap_drone_accelerate = MagicMock()
    solver._read_manufacture_total_seconds = MagicMock(return_value=current_total)
    solver._confirm_drone_count = MagicMock()
    solver._tap_product_point = MagicMock()
    solver.translate_room = MagicMock(return_value="制造站")
    return solver


def test_manufacture_execution_rechecks_progress_and_only_lowers_drone_count():
    solver = acceleration_solver(available_drones=10, current_total=4640)
    observation = {
        "room": "room_1_2",
        "target_product": "exp3",
        "current_product": "gold",
        "total_seconds": 5000,
        "current_remaining": 1000,
        "drone_count": 5,
    }

    wait_seconds = solver._execute_manufacture_acceleration(observation)

    solver._confirm_drone_count.assert_called_once_with(3)
    assert wait_seconds == 100


def test_manufacture_execution_below_loss_threshold_uses_no_drone():
    solver = acceleration_solver(available_drones=10, current_total=4149)
    observation = {
        "room": "room_1_2",
        "target_product": "exp3",
        "current_product": "gold",
        "total_seconds": 5000,
        "current_remaining": 1000,
        "drone_count": 0,
    }

    wait_seconds = solver._execute_manufacture_acceleration(observation)

    solver._confirm_drone_count.assert_not_called()
    solver._tap_product_point.assert_called_once_with((480, 864))
    assert wait_seconds == 149


def test_manufacture_execution_at_loss_threshold_uses_one_drone():
    solver = acceleration_solver(available_drones=10, current_total=4150)
    observation = {
        "room": "room_1_2",
        "target_product": "exp3",
        "current_product": "gold",
        "total_seconds": 5000,
        "current_remaining": 1000,
        "drone_count": 1,
    }

    wait_seconds = solver._execute_manufacture_acceleration(observation)

    solver._confirm_drone_count.assert_called_once_with(1)
    assert wait_seconds == 0


def test_idle_manufacture_execution_skips_drone_panel():
    solver = acceleration_solver(available_drones=10, current_total=5000)
    solver._manufacture_is_idle.return_value = True
    observation = {
        "room": "room_1_2",
        "target_product": "exp3",
        "current_product": "gold",
        "total_seconds": 0,
        "current_remaining": 0,
        "drone_count": 0,
    }

    wait_seconds = solver._execute_manufacture_acceleration(observation)

    assert wait_seconds == 0
    solver._tap_drone_accelerate.assert_not_called()
    solver._read_manufacture_total_seconds.assert_not_called()


def test_manufacture_execution_without_grandet_mode_finishes_immediately(monkeypatch):
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

    wait_seconds = solver._execute_manufacture_acceleration(observation)

    solver._confirm_drone_count.assert_called_once_with(1)
    assert wait_seconds == 0


def test_manufacture_product_change_handles_both_confirms_and_fills_queue():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver._tap_product_point = MagicMock()
    solver._wait_product_resource = MagicMock()

    solver._select_manufacture_product("exp3")

    assert [item.args for item in solver._tap_product_point.call_args_list] == [
        ((1680, 500),),
        ((180, 195),),
        ((500, 525),),
        ((1425, 895),),
        ((1440, 742),),
        ((1450, 305),),
        ((1425, 895),),
    ]
    solver._wait_product_resource.assert_any_call("manufacture_product_cancel_confirm")
    solver._wait_product_resource.assert_any_call(
        "manufacture_product_cancel_confirm", present=False
    )


@pytest.mark.parametrize(
    ("product_id", "recipe"),
    [("orirock", (500, 250)), ("orirock_device", (1240, 250))],
)
def test_manufacture_product_change_selects_each_orundum_recipe(product_id, recipe):
    solver = object.__new__(base.BaseSchedulerSolver)
    solver._tap_product_point = MagicMock()
    solver._wait_product_resource = MagicMock()

    solver._select_manufacture_product(product_id)

    taps = [item.args[0] for item in solver._tap_product_point.call_args_list]
    assert taps[:3] == [(1680, 500), (180, 620), recipe]


@pytest.mark.parametrize(
    ("material_text", "expected"),
    [("固源岩", "orirock"), ("装置", "orirock_device")],
)
def test_read_manufacture_product_distinguishes_orundum_material(
    material_text, expected
):
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.recog = SimpleNamespace(w=1920, h=1080)
    solver._product_ocr_text = MagicMock(side_effect=["", material_text])

    assert solver.read_manufacture_product() == expected
    assert solver._product_ocr_text.call_count == 2


def test_manufacture_idle_state_is_read_from_status_text():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.recog = SimpleNamespace(w=1920, h=1080)
    solver._product_ocr_text = MagicMock(return_value="已完成总剩余时间00:00:00")

    assert solver._manufacture_is_idle()
    solver._product_ocr_text.assert_called_once_with(((1540, 430), (1835, 700)))


def test_orundum_recipes_require_switching_between_each_other():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver._open_manufacture_product_detail = MagicMock()
    solver.read_manufacture_product = MagicMock(return_value="orirock")
    solver.digit_reader = MagicMock()
    solver.digit_reader.get_drone.return_value = 100
    solver.recog = SimpleNamespace(gray=MagicMock(), h=1080, w=1920)
    solver._manufacture_is_idle = MagicMock(return_value=False)
    solver._tap_drone_accelerate = MagicMock()
    solver._read_manufacture_total_seconds = MagicMock(return_value=3600)
    solver._tap_product_point = MagicMock()

    observation = solver._survey_manufacture_switch("room_1_2", "orirock_device")

    assert observation["needs_switch"] is True
    assert observation["current_product"] == "orirock"


def test_idle_manufacture_survey_skips_drone_panel_and_waiting():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver._open_manufacture_product_detail = MagicMock()
    solver.read_manufacture_product = MagicMock(return_value="orirock_device")
    solver.digit_reader = MagicMock()
    solver.digit_reader.get_drone.return_value = 540
    solver.recog = SimpleNamespace(gray=MagicMock(), h=1080, w=1920)
    solver._manufacture_is_idle = MagicMock(return_value=True)
    solver._tap_drone_accelerate = MagicMock()
    solver._read_manufacture_total_seconds = MagicMock()
    solver._tap_product_point = MagicMock()
    solver.translate_room = MagicMock(return_value="B303")

    observation = solver._survey_manufacture_switch("room_3_3", "orirock")

    assert observation == {
        "room": "room_3_3",
        "facility": "manufacture",
        "target_product": "orirock",
        "current_product": "orirock_device",
        "needs_switch": True,
        "available_drones": 540,
        "total_seconds": 0,
        "current_remaining": 0,
        "drone_count": 0,
        "wait_seconds": 0,
    }
    solver._tap_drone_accelerate.assert_not_called()
    solver._read_manufacture_total_seconds.assert_not_called()
    solver._tap_product_point.assert_not_called()


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
        room, "manufacture", "exp3", updated_at="2026-09-20T12:00:00"
    )

    assert operators.facility_states[room] == {
        "facility": "manufacture",
        "product": "exp3",
        "updated_at": "2026-09-20T12:00:00",
    }
    assert operators.facility_product(room) == "exp3"
    assert operators.evaluate_expression("op_data.facility_product('room_1_2') == exp3")


def test_facility_product_conditions_fall_back_to_main_plan_until_cached():
    room, plan = product_plan(default="gold")
    operators = Operators(plan)

    assert operators.facility_product(room) == "gold"
    assert operators.facility_product_count("gold") == 1
    assert operators.facility_product_type_count() == 1

    operators.update_facility_state(room, "manufacture", "exp3")

    assert operators.facility_product(room) == "exp3"
    assert operators.facility_product_count("gold") == 0
    assert operators.facility_product_count("exp3") == 1
    assert operators.facility_product_type_count() == 1


def test_facility_operator_count_supports_all_base_rooms():
    room, plan = product_plan()
    operators = Operators(plan)
    operators.operators["测试干员"] = SimpleNamespace(current_room="central")

    assert operators.facility_operator_count("central") == 1
    assert operators.facility_operator_count(room) == 0
    assert operators.evaluate_expression(
        "op_data.facility_operator_count('central') >= 1"
    )


def test_training_room_conditions_reuse_mastery_plan_state(monkeypatch):
    _, plan = product_plan()
    operators = Operators(plan)
    mastery_db = "arknights_mower.utils.mastery_db"

    monkeypatch.setattr(f"{mastery_db}.get_reconcile_plans", lambda: [{"id": 1}])
    monkeypatch.setattr(
        f"{mastery_db}.get_active_plan", lambda: {"id": 1, "status": "training"}
    )

    assert operators.evaluate_expression(
        "op_data.facility_has_mastery_plan('train') == True"
    )
    assert operators.evaluate_expression(
        "op_data.facility_is_training('train') == True"
    )

    monkeypatch.setattr(f"{mastery_db}.get_reconcile_plans", lambda: [])
    monkeypatch.setattr(
        f"{mastery_db}.get_active_plan",
        lambda: {"id": 1, "status": "waiting_collect"},
    )

    assert not operators.facility_has_mastery_plan("train")
    assert not operators.facility_is_training("train")


def test_training_room_conditions_reject_other_rooms():
    _, plan = product_plan()
    operators = Operators(plan)

    with pytest.raises(ValueError, match="训练室位置"):
        operators.facility_has_mastery_plan("room_1_1")


def test_facility_type_reuses_current_plan():
    room, plan = product_plan()
    operators = Operators(plan)

    assert operators.facility_type(room) == "manufacture"
    assert operators.evaluate_expression(
        "op_data.facility_type('room_1_2') == manufacture"
    )


def test_trade_facility_type_expression_is_true():
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
    operators = Operators(plan)

    assert operators.facility_type(room) == "trade"
    assert operators.evaluate_expression("op_data.facility_type('room_1_1') == trade")


def test_product_constant_is_valid_in_expression():
    _, plan = product_plan()
    operators = Operators(plan)

    assert operators.evaluate_expression("gold == 'gold'")
    assert operators.evaluate_expression("gold != True")


def test_facility_product_statistics_are_available_to_expression():
    room, plan = product_plan()
    operators = Operators(plan)
    operators.update_facility_state(room, "manufacture", "gold")
    operators.update_facility_state("room_1_1", "trade", "lmd")
    operators.update_facility_state("room_2_1", "manufacture", "gold")

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
    operators.update_facility_state(room, "manufacture", "exp3")
    expression = (
        "op_data.inventory_count('赤金') >= 7000 or "
        "(op_data.inventory_count('赤金') > 200 and "
        "op_data.facility_product('room_1_2') == exp3)"
    )

    assert operators.evaluate_expression(expression)
    inventory["赤金"] = 200
    assert not operators.evaluate_expression(expression)


def test_mood_room_visit_refreshes_manufacture_state_before_operator_detail():
    room, plan = product_plan()
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.op_data = Operators(plan)
    solver._wait_drone_interface = MagicMock()
    solver.read_manufacture_product = MagicMock(return_value="gold")
    solver.scene_graph_navigation = MagicMock()
    solver.translate_room = MagicMock(return_value="B102")

    solver.refresh_facility_state(room)

    assert solver.op_data.facility_product(room) == "gold"
    solver._wait_drone_interface.assert_called_once_with(
        interval=3, accelerate_template="manufacture_accelerate"
    )
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
    solver._wait_drone_interface = MagicMock()
    solver._read_trade_product_card = MagicMock(return_value=("orundum", True))
    solver.scene_graph_navigation = MagicMock()
    solver.translate_room = MagicMock(return_value="B101")

    solver.refresh_facility_state(room)

    assert solver.op_data.facility_product(room) == "orundum"
    solver._wait_drone_interface.assert_called_once_with(
        interval=3,
        accelerate_template="bill_accelerate",
        page_template="order_label",
    )
    solver.scene_graph_navigation.assert_called_once_with(base.Scene.INFRA_DETAILS)


def test_trade_order_page_can_open_without_drone_button():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.recog = SimpleNamespace(w=1920, h=1080)
    phase = {"value": 0}

    def find(resource):
        if resource == "arrange_check_in_on" and phase["value"] == 0:
            return (100, 100)
        if resource == "order_label" and phase["value"] >= 2:
            return (400, 137)
        return None

    def tap(*args, **kwargs):
        phase["value"] += 1

    solver.find = MagicMock(side_effect=find)
    solver.tap = MagicMock(side_effect=tap)
    solver.sleep = MagicMock()

    solver._wait_drone_interface(
        interval=0,
        accelerate_template="bill_accelerate",
        page_template="order_label",
    )

    assert solver.tap.call_count == 2


def test_mood_room_visit_caches_locked_trade_as_lmd_without_opening_selector():
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
    solver._wait_drone_interface = MagicMock()
    solver._read_trade_product_card = MagicMock(return_value=("lmd", False))
    solver.scene_graph_navigation = MagicMock()
    solver.translate_room = MagicMock(return_value="B101")

    solver.refresh_facility_state(room)

    assert solver.op_data.facility_product(room) == "lmd"
    solver._wait_drone_interface.assert_called_once_with(
        interval=3,
        accelerate_template="bill_accelerate",
        page_template="order_label",
    )
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


@pytest.mark.parametrize(
    "expression",
    [
        "10 ** 1000000000",
        "10 ** op_data.inventory_count('赤金')",
        "(10 ** 64) ** 64",
        "'x' * 1000000000",
        "room_1_1 * 1000000000",
    ],
)
def test_backup_expression_rejects_unbounded_arithmetic(expression):
    _, plan = product_plan()
    operators = Operators(plan)

    assert operators.evaluate_expression(expression) is None


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

    manufacture_observations = {
        "room_1_2": {
            "room": "room_1_2",
            "facility": "manufacture",
            "target_product": "gold",
            "needs_switch": True,
            "drone_count": 4,
            "wait_seconds": 150,
            "available_drones": 20,
        },
        "room_2_2": {
            "room": "room_2_2",
            "facility": "manufacture",
            "target_product": "exp3",
            "needs_switch": True,
            "drone_count": 3,
            "wait_seconds": 20,
            "available_drones": 20,
        },
    }

    def survey_manufacture(room, target):
        events.append(("survey", room))
        return manufacture_observations[room]

    solver._survey_manufacture_switch = MagicMock(side_effect=survey_manufacture)
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
    solver._execute_manufacture_acceleration = MagicMock(
        side_effect=lambda item: events.append(("accelerate", item["room"])) or 10
    )
    solver._change_manufacture_product = MagicMock(
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
    solver._survey_manufacture_switch = MagicMock(
        side_effect=[
            {
                "room": "room_1_2",
                "facility": "manufacture",
                "target_product": "gold",
                "needs_switch": True,
                "drone_count": 4,
                "wait_seconds": 100,
                "available_drones": 6,
            },
            {
                "room": "room_2_2",
                "facility": "manufacture",
                "target_product": "exp3",
                "needs_switch": True,
                "drone_count": 3,
                "wait_seconds": 50,
                "available_drones": 6,
            },
        ]
    )
    solver._execute_manufacture_acceleration = MagicMock()
    solver._change_manufacture_product = MagicMock()

    with pytest.raises(base.ProductSwitchDeferred):
        solver.switch_base_products(tasks)

    assert solver._survey_manufacture_switch.call_count == 2
    solver._execute_manufacture_acceleration.assert_not_called()
    solver._change_manufacture_product.assert_not_called()
    assert solver.tasks == tasks


def test_insufficient_manufacture_drones_do_not_block_direct_trade_switch():
    manufacture_task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_1_2", "gold"),
    )
    trade_task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_1_1", "orundum"),
    )
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.tasks = [manufacture_task, trade_task]
    solver._survey_manufacture_switch = MagicMock(
        return_value={
            "room": "room_1_2",
            "facility": "manufacture",
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
    solver._execute_manufacture_acceleration = MagicMock()

    with pytest.raises(base.ProductSwitchDeferred):
        solver.switch_base_products([manufacture_task, trade_task])

    solver._change_trade_product.assert_called_once_with(trade_observation)
    solver._execute_manufacture_acceleration.assert_not_called()
    assert solver.tasks == [manufacture_task]


def test_trade_only_batch_never_enters_manufacture_drone_flow():
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
    solver._survey_manufacture_switch = MagicMock()
    solver._execute_manufacture_acceleration = MagicMock()
    solver._change_manufacture_product = MagicMock()
    solver._change_trade_product = MagicMock()

    solver.switch_base_products([task])

    solver._survey_manufacture_switch.assert_not_called()
    solver._execute_manufacture_acceleration.assert_not_called()
    solver._change_manufacture_product.assert_not_called()
    solver._change_trade_product.assert_called_once()
    assert solver.tasks == []


def test_mixed_batch_accelerates_manufacture_and_switches_both_facilities(
    monkeypatch,
):
    manufacture_task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_1_2", "exp3"),
    )
    trade_task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_1_1", "orundum"),
    )
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.tasks = [manufacture_task, trade_task]
    solver.recog = SimpleNamespace(update=MagicMock())
    solver.sleep = MagicMock()
    manufacture_observation = {
        "room": "room_1_2",
        "facility": "manufacture",
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
    solver._survey_manufacture_switch = MagicMock(return_value=manufacture_observation)
    solver._survey_trade_switch = MagicMock(return_value=trade_observation)
    solver._execute_manufacture_acceleration = MagicMock(return_value=30)
    solver._change_manufacture_product = MagicMock()
    solver._change_trade_product = MagicMock()
    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.product_switching.waiting_seconds = 5

    solver.switch_base_products([manufacture_task, trade_task])

    solver._execute_manufacture_acceleration.assert_called_once_with(
        manufacture_observation
    )
    solver._change_manufacture_product.assert_called_once_with(manufacture_observation)
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
        "facility": "manufacture",
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
    solver._survey_manufacture_switch = MagicMock(return_value=observation)
    solver._execute_manufacture_acceleration = MagicMock(return_value=0)
    solver._change_manufacture_product = MagicMock()
    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.product_switching.grandet_mode = False

    solver.switch_base_products([task])

    solver.sleep.assert_not_called()
    solver.recog.update.assert_not_called()
    solver._change_manufacture_product.assert_called_once_with(observation)
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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("龙门商法", ("lmd", True)),
        ("开采协力", ("orundum", True)),
        ("贸易站3级后可切换", ("lmd", False)),
    ],
)
def test_trade_product_is_read_from_order_list_card(text, expected):
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.recog = SimpleNamespace(w=1920, h=1080)
    solver._product_ocr_text = MagicMock(return_value=text)

    assert solver._read_trade_product_card() == expected
    solver._product_ocr_text.assert_called_once_with(((1400, 840), (1810, 1040)))


def test_locked_trade_survey_only_caches_fixed_lmd_order():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver._open_trade_product_detail = MagicMock()
    solver._read_trade_product_card = MagicMock(return_value=("lmd", False))
    solver._tap_product_point = MagicMock()
    solver._cache_facility_state = MagicMock()

    observation = solver._survey_trade_switch("room_1_1", "lmd")

    assert observation == {
        "room": "room_1_1",
        "facility": "trade",
        "target_product": "lmd",
        "current_product": "lmd",
        "needs_switch": False,
        "switchable": False,
    }
    solver._cache_facility_state.assert_called_once_with("room_1_1", "trade", "lmd")
    solver._tap_product_point.assert_not_called()


def test_locked_trade_with_incompatible_target_defers_without_switching():
    task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_1_1", "orundum"),
    )
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.tasks = [task]
    solver.translate_room = MagicMock(return_value="B101")
    solver._survey_trade_switch = MagicMock(
        return_value={
            "room": "room_1_1",
            "facility": "trade",
            "target_product": "orundum",
            "current_product": "lmd",
            "needs_switch": True,
            "switchable": False,
        }
    )
    solver._change_trade_product = MagicMock()

    started_at = datetime.now()
    solver.switch_base_products([task])

    solver._change_trade_product.assert_not_called()
    assert solver.tasks == [task]
    assert task.time >= started_at + timedelta(minutes=59)


def test_locked_trade_does_not_block_other_product_switches(monkeypatch):
    locked_task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_1_1", "orundum"),
    )
    trade_task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_2_1", "orundum"),
    )
    manufacture_task = SchedulerTask(
        task_type=TaskTypes.SWITCH_PRODUCT,
        meta_data=product_task_meta("room_1_2", "exp3"),
    )
    locked_observation = {
        "room": "room_1_1",
        "facility": "trade",
        "target_product": "orundum",
        "current_product": "lmd",
        "needs_switch": True,
        "switchable": False,
    }
    trade_observation = {
        "room": "room_2_1",
        "facility": "trade",
        "target_product": "orundum",
        "current_product": "lmd",
        "needs_switch": True,
        "switchable": True,
    }
    manufacture_observation = {
        "room": "room_1_2",
        "facility": "manufacture",
        "target_product": "exp3",
        "needs_switch": True,
        "drone_count": 2,
        "wait_seconds": 0,
        "available_drones": 10,
    }
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.tasks = [locked_task, trade_task, manufacture_task]
    solver.translate_room = MagicMock(return_value="B101")
    solver.recog = SimpleNamespace(update=MagicMock())
    solver.sleep = MagicMock()
    solver._survey_trade_switch = MagicMock(
        side_effect=[locked_observation, trade_observation]
    )
    solver._survey_manufacture_switch = MagicMock(
        return_value=manufacture_observation
    )
    solver._change_trade_product = MagicMock()
    solver._execute_manufacture_acceleration = MagicMock(return_value=0)
    solver._change_manufacture_product = MagicMock()
    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.product_switching.grandet_mode = False

    started_at = datetime.now()
    solver.switch_base_products([locked_task, trade_task, manufacture_task])

    solver._change_trade_product.assert_called_once_with(trade_observation)
    solver._execute_manufacture_acceleration.assert_called_once_with(
        manufacture_observation
    )
    solver._change_manufacture_product.assert_called_once_with(
        manufacture_observation
    )
    assert solver.tasks == [locked_task]
    assert locked_task.time >= started_at + timedelta(minutes=59)


def test_trade_switch_opens_selector_only_when_needed_and_verifies_card():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver.recog = SimpleNamespace(update=MagicMock())
    solver._open_trade_product_detail = MagicMock()
    solver._tap_product_point = MagicMock()
    solver._wait_product_resource = MagicMock()
    solver._read_trade_product_card = MagicMock(
        side_effect=[("lmd", True), ("orundum", True)]
    )
    solver._cache_facility_state = MagicMock()

    solver._change_trade_product(
        {
            "room": "room_1_1",
            "target_product": "orundum",
        }
    )

    assert [item.args for item in solver._tap_product_point.call_args_list] == [
        ((1580, 955),),
        ((1140, 530),),
        ((1600, 200),),
    ]
    assert solver._read_trade_product_card.call_count == 2


def test_matching_trade_order_never_opens_strategy_selector():
    solver = object.__new__(base.BaseSchedulerSolver)
    solver._open_trade_product_detail = MagicMock()
    solver._read_trade_product_card = MagicMock(return_value=("lmd", True))
    solver._cache_facility_state = MagicMock()
    solver._tap_product_point = MagicMock()
    solver._wait_product_resource = MagicMock()

    solver._change_trade_product(
        {
            "room": "room_1_1",
            "target_product": "lmd",
        }
    )

    solver._tap_product_point.assert_not_called()
    solver._wait_product_resource.assert_not_called()
