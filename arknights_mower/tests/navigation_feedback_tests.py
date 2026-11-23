"""页面反馈延迟时等待新帧，丢点时有界重试，不把残影当成第二次确认。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.performance import PERFORMANCE_PRESETS
from arknights_mower.utils.recognize import RecognizeError, Recognizer
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import SchedulerTask

BLUE = ((1550, 40), (1800, 100))
DETAIL = ((10, 400), (150, 480))


@pytest.mark.parametrize(
    "feedback,expected_taps",
    [
        ("immediate", 1),
        ("slow", 1),
        ("slow_low", 1),
        ("zero_interval", 1),
        ("dropped", 2),
        ("popup", 1),
        ("wrong_room", 0),
    ],
)
def test_open_room_selection_waits_for_identity_and_retries_the_room(
    monkeypatch, feedback, expected_taps
):
    from arknights_mower.solvers import base_schedule

    directory = Path(__file__).parent / "fixtures"
    solver = object.__new__(BaseSchedulerSolver)
    frames = {
        key: (directory / path).read_bytes()
        for key, path in {
            "room": "manufacture/b102_check_in_exp_20261123.jpg",
            "selection": "selection/trade_single_selected_20261021.jpg",
            "popup": "selection/staffing_secondary_confirm_20261024.jpg",
        }.items()
    }
    device = solver.device = MagicMock()
    current_time = 0
    if feedback == "slow_low":
        solver._selection_profile_snapshot = PERFORMANCE_PRESETS["low"]
    else:
        solver._selection_profile_snapshot = SimpleNamespace(
            transition_timeout=2.5,
            poll_interval=0.5,
            low_frame_rate=feedback == "zero_interval",
            screenshot_interval=0 if feedback == "zero_interval" else 500,
        )
    monkeypatch.setattr(base_schedule, "monotonic", lambda: current_time)
    solver.recog = Recognizer(device, frames["room"])
    device.check_current_focus.return_value = False

    def capture():
        key = "selection"
        if feedback == "popup":
            key = "popup"
        elif feedback == "slow" and current_time < 1.5:
            key = "room"
        elif feedback == "slow_low" and current_time < 5.25:
            key = "room"
        elif feedback == "dropped" and device.tap.call_count < 2:
            key = "room"
        r = Recognizer(device, frames[key])
        return r.screencap, r.img, r.gray

    def sleep(interval):
        nonlocal current_time
        current_time += interval
        solver.recog.update()

    device.screencap.side_effect = capture
    solver.sleep = sleep
    if feedback in ("popup", "wrong_room"):
        with pytest.raises(RecognizeError):
            solver._open_room_selection(
                "room_1_1" if feedback == "wrong_room" else "room_1_2"
            )
    else:
        solver._open_room_selection("room_1_2")
        assert solver.scene() == Scene.INFRA_ARRANGE_ORDER
        if feedback in ("immediate", "zero_interval"):
            assert current_time == 0
            assert device.screencap.call_count == 1
        if feedback == "dropped":
            assert current_time >= 2.5
    assert device.tap.call_count == expected_taps


@pytest.mark.parametrize("map_after", [0, 1.5, 2.9, None])
def test_completed_room_waits_for_a_new_map_frame_before_retiring_plan(
    monkeypatch, map_after
):
    from arknights_mower.solvers import base_schedule
    from arknights_mower.utils.scheduler_task import TaskTypes

    solver = object.__new__(BaseSchedulerSolver)
    solver.task = SchedulerTask(task_type=TaskTypes.SELF_CORRECTION)
    solver.op_data = SimpleNamespace()
    solver._selection_profile_snapshot = SimpleNamespace(
        transition_timeout=2.5, poll_interval=0.5, screenshot_interval=500
    )
    solver._confirm_facility_arrangement_log = MagicMock()
    directory = Path(__file__).parent / "fixtures"
    device = solver.device = MagicMock()
    room = Recognizer(
        device, (directory / "manufacture/b102_check_in_exp_20261123.jpg").read_bytes()
    )
    base_map = Recognizer(device, (directory / "recycle/map.png").read_bytes())
    solver.recog = Recognizer(device, room.screencap)
    room_frame = room.screencap, room.img, room.gray
    map_frame = base_map.screencap, base_map.img, base_map.gray
    clock = 0
    monkeypatch.setattr(base_schedule, "monotonic", lambda: clock)
    device.screencap.side_effect = lambda: (
        map_frame if map_after is not None and clock >= map_after else room_frame
    )

    def sleep(interval):
        nonlocal clock
        clock += interval
        solver.recog.update()

    solver.sleep = sleep
    plan = {"room_1_2": ["余"]}
    observed = [{"agent": "余"}]
    if map_after is None:
        with pytest.raises(RecognizeError, match="全局视角"):
            solver._complete_room_arrangement({}, "room_1_2", plan, observed=observed)
        assert plan == {"room_1_2": ["余"]}
        solver._confirm_facility_arrangement_log.assert_not_called()
    else:
        solver._complete_room_arrangement({}, "room_1_2", plan, observed=observed)
        assert clock >= map_after
        if map_after == 0:
            assert clock == 0.375
            assert device.screencap.call_count == 1
        assert not plan
        solver._confirm_facility_arrangement_log.assert_called_once_with(
            "room_1_2", ["余"], observed
        )
    device.send_keyevent.assert_called_once()


def solver_for(frames):
    """一次缓存失效对应一张新帧；同一帧中的全部模板查询共享状态。"""
    solver = object.__new__(BaseSchedulerSolver)
    solver.task = SchedulerTask()
    solver.op_data = SimpleNamespace(run_order_rooms={})
    state = {"frame": 0}

    def advance(*args, **kwargs):
        state["frame"] = min(state["frame"] + 1, len(frames) - 1)

    def find(name, score=0):
        frame = frames[state["frame"]]
        value = frame.get(name)
        return None if score and frame.get("fading") else value

    solver.recog = SimpleNamespace(
        w=1920,
        h=1080,
        update=MagicMock(),
        get_scene=lambda: (
            Scene.CONNECTING
            if frames[state["frame"]].get("connecting")
            else Scene.INFRA_DETAILS
        ),
    )
    solver.find = MagicMock(side_effect=find)
    solver.tap = MagicMock(side_effect=advance)
    solver.sleep = MagicMock(side_effect=advance)
    return solver


def test_confirmation_disappearance_needs_no_extra_wait_or_click():
    solver = solver_for([{"confirm_blue": BLUE}, {"room_detail": DETAIL}])
    solver.tap_confirm("room_1_1")
    solver.tap.assert_called_once_with(BLUE, interval=0.2)
    solver.sleep.assert_not_called()
    checked = [call.args[0] for call in solver.find.call_args_list]
    assert checked.count("confirm_blue") == 2
    assert checked.count("confirm_train") == checked.count("arrange_confirm") == 1


def test_fading_confirmation_is_observed_without_reclicking():
    solver = solver_for(
        [
            {"confirm_blue": BLUE},
            {"confirm_blue": BLUE, "fading": True},
            {"room_detail": DETAIL},
        ]
    )
    solver.tap_confirm("room_1_1")
    solver.tap.assert_called_once_with(BLUE, interval=0.2)
    solver.sleep.assert_called_once_with(0.2)


def test_delayed_clear_frame_does_not_receive_duplicate_confirmation():
    solver = solver_for([{"confirm_blue": BLUE}] * 2 + [{"room_detail": DETAIL}])
    solver.tap_confirm("room_1_1")
    assert solver.tap.call_count == 1
    assert solver.sleep.call_count == 1


def test_lost_confirmation_retries_after_another_observation():
    solver = solver_for([{"confirm_blue": BLUE}] * 3 + [{"room_detail": DETAIL}])
    solver.tap_confirm("room_1_1")
    assert solver.tap.call_count == 2
    assert solver.sleep.call_count == 1


@pytest.mark.parametrize("first", ["confirm_blue", "confirm_train"])
def test_real_secondary_confirmation_is_preserved(first):
    solver = solver_for(
        [{first: BLUE}, {"arrange_confirm": BLUE}, {"room_detail": DETAIL}]
    )
    solver.tap_confirm("train")
    assert [c.args[0] for c in solver.tap.call_args_list] == [BLUE, (1280, 1070)]


@pytest.mark.parametrize("first", ["confirm_blue", "confirm_train"])
def test_dimmed_confirmation_with_secondary_popup(first):
    # 遮罩下主确认按钮残影（fading）与二次确认弹窗（arrange_confirm）共存时，必须正常进入二次确认
    solver = solver_for(
        [
            {first: BLUE},
            {first: BLUE, "fading": True, "arrange_confirm": BLUE},
            {"room_detail": DETAIL},
        ]
    )
    solver.tap_confirm("train")
    assert [c.args[0] for c in solver.tap.call_args_list] == [BLUE, (1280, 1070)]


def test_empty_transition_does_not_skip_delayed_secondary_confirmation():
    solver = solver_for(
        [
            {"confirm_blue": BLUE},
            {},
            {"arrange_confirm": BLUE},
            {"room_detail": DETAIL},
        ]
    )
    solver.tap_confirm("room_1_1")
    assert [c.args[0] for c in solver.tap.call_args_list] == [BLUE, (1280, 1070)]
    solver.sleep.assert_called_once_with(0.2)


def test_missing_confirmation_destination_is_not_silent_success():
    solver = solver_for([{"confirm_blue": BLUE}, {}])
    with pytest.raises(RecognizeError):
        solver.tap_confirm("room_1_1")
    assert solver.tap.call_count == 1


@pytest.mark.parametrize("fading", [False, True])
def test_stuck_confirmation_raises_for_original_recovery(fading):
    solver = solver_for(
        [{"confirm_blue": BLUE}, {"confirm_blue": BLUE, "fading": fading}]
    )
    with pytest.raises(RecognizeError):
        solver.tap_confirm("room_1_1")
    assert 1 <= solver.tap.call_count <= 4


def test_connecting_prevents_confirming_underneath_overlay():
    solver = solver_for(
        [
            {"connecting": True, "confirm_blue": BLUE},
            {"confirm_blue": BLUE},
            {"room_detail": DETAIL},
        ]
    )
    solver.tap_confirm("room_1_1")
    solver.sleep.assert_called_once_with(1)
    solver.tap.assert_called_once_with(BLUE, interval=0.2)


@pytest.mark.parametrize("before_click", [False, True])
@pytest.mark.parametrize("secondary", [False, True])
def test_confirmation_uses_configured_connection_budget(
    monkeypatch, before_click, secondary
):
    monkeypatch.setattr(config.conf.waiting_scene, "CONNECTING", (1, 20))
    connection = [{"connecting": True, "confirm_blue": BLUE}] * 13
    destination = ([{"arrange_confirm": BLUE}] if secondary else []) + [
        {"room_detail": DETAIL}
    ]
    frames = (
        connection + [{"confirm_blue": BLUE}] + destination
        if before_click
        else [{"confirm_blue": BLUE}] + connection + destination
    )
    solver = solver_for(frames)

    solver.tap_confirm("room_1_1")

    assert [call.args[0] for call in solver.tap.call_args_list] == [BLUE] + (
        [(1280, 1070)] if secondary else []
    )
    assert solver.sleep.call_count == 13


def test_connection_timeout_recovers_without_reporting_confirmation_success(
    monkeypatch,
):
    from arknights_mower.utils import solver as solver_module

    monkeypatch.setattr(config.conf.waiting_scene, "CONNECTING", (1, 3))
    recovery_sleep = MagicMock()
    monkeypatch.setattr(solver_module, "csleep", recovery_sleep)
    solver = solver_for([{"confirm_blue": BLUE}, {"connecting": True}])
    solver.device = MagicMock()
    solver.check_current_focus = MagicMock()
    solver.back_to_infrastructure = MagicMock()

    with pytest.raises(RecognizeError, match="联网等待超时"):
        solver.tap_confirm("room_1_1")

    solver.tap.assert_called_once_with(BLUE, interval=0.2)
    assert sum(call.args[0] for call in solver.sleep.call_args_list) == pytest.approx(3)
    solver.device.exit.assert_called_once_with()
    recovery_sleep.assert_called_once_with(3)
    solver.check_current_focus.assert_called_once_with()
    solver.back_to_infrastructure.assert_called_once_with()


def test_short_connection_after_submission_uses_next_capture_opportunity(monkeypatch):
    monkeypatch.setattr(config.conf.waiting_scene, "CONNECTING", (3, 5))
    monkeypatch.setattr(config.conf, "performance_mode", "xhigh")
    solver = solver_for(
        [{"confirm_blue": BLUE}, {"connecting": True}, {"room_detail": DETAIL}]
    )
    solver.tap_confirm("room_1_1")
    solver.tap.assert_called_once_with(BLUE, interval=0.2)
    solver.sleep.assert_called_once_with(0.5)


def test_detail_is_closed_before_opening_orders():
    solver = solver_for(
        [{"arrange_check_in_on": DETAIL}, {}, {"bill_accelerate": BLUE}]
    )
    solver._wait_drone_interface(accelerate_template="bill_accelerate")
    assert [c.args[0] for c in solver.tap.call_args_list] == [DETAIL, (96, 1026)]


def test_order_entrance_waits_for_feedback_before_reclicking():
    solver = solver_for([{}, {}, {"bill_accelerate": BLUE}])
    solver._wait_drone_interface(accelerate_template="bill_accelerate")
    solver.tap.assert_called_once_with((96, 1026), interval=0.2)
    solver.sleep.assert_called_once_with(0.2)


def test_order_entrance_lost_tap_can_retry():
    solver = solver_for([{}, {}, {}, {"bill_accelerate": BLUE}])
    solver._wait_drone_interface()
    assert solver.tap.call_count == 2


def test_product_read_waits_through_delayed_entrance_frames(monkeypatch):
    from arknights_mower.solvers import base_schedule

    solver = solver_for(
        [{"arrange_check_in_on": DETAIL}] * 4
        + [{}] * 4
        + [{"manufacture_accelerate": BLUE}]
    )
    monkeypatch.setattr(
        base_schedule,
        "monotonic",
        lambda: (solver.tap.call_count + solver.sleep.call_count) / 5,
    )
    solver._wait_drone_interface(
        accelerate_template="manufacture_accelerate", retry_after=3
    )

    assert [c.args[0] for c in solver.tap.call_args_list] == [DETAIL, (96, 1026)]
    assert all(call.args[0] <= 0.2 for call in solver.sleep.call_args_list)


def test_unrelated_factory_button_is_not_trade_success():
    solver = solver_for([{"manufacture_accelerate": BLUE}, {"bill_accelerate": BLUE}])
    solver._wait_drone_interface(accelerate_template="bill_accelerate")
    assert solver.tap.call_count == 1


@pytest.mark.parametrize("template", ["manufacture_accelerate", "bill_accelerate"])
def test_ready_drone_page_receives_no_input(template):
    solver = solver_for([{template: BLUE}])
    solver._wait_drone_interface()
    solver.tap.assert_not_called()
    solver.sleep.assert_not_called()


def test_orders_wait_for_overlay_to_clear_even_when_button_is_visible():
    solver = solver_for(
        [{"connecting": True, "bill_accelerate": BLUE}, {"bill_accelerate": BLUE}]
    )
    solver._wait_drone_interface()
    solver.tap.assert_not_called()
    solver.sleep.assert_called_once_with()


def test_last_order_click_result_is_checked():
    # 连接遮罩占用一次观察，使最后一次观察恰好发出点击。
    frames = [{"connecting": True}] + [{}] * 9 + [{"bill_accelerate": BLUE}]
    solver = solver_for(frames)
    solver._wait_drone_interface()
    assert solver.tap.call_count == 5


def test_stuck_orders_return_to_bounded_room_recovery():
    solver = solver_for([{}])
    with pytest.raises(RecognizeError):
        solver._wait_drone_interface()
    assert solver.tap.call_count == 5


@pytest.mark.parametrize("button", ["arrange_check_in", "arrange_check_in_small"])
def test_detail_waits_for_old_frame_without_toggling_panel_again(button):
    solver = solver_for([{button: DETAIL}] * 2 + [{"room_detail": DETAIL}])
    solver.get_color = MagicMock(return_value=np.array([255] * 3))
    solver.turn_on_room_detail("room_1_1")
    solver.tap.assert_called_once_with(DETAIL, interval=0.2)
    solver.sleep.assert_called_once_with(0.2)


def test_detail_background_must_finish_animation():
    solver = solver_for([{"room_detail": DETAIL}] * 2)
    solver.get_color = MagicMock(side_effect=[np.array([230] * 3), np.array([255] * 3)])
    solver.turn_on_room_detail("room_1_1")
    solver.tap.assert_not_called()
    solver.sleep.assert_called_once_with(interval=0.5)


def test_detail_does_not_tap_through_connection_overlay():
    solver = solver_for(
        [{"connecting": True, "arrange_check_in": DETAIL}, {"room_detail": DETAIL}]
    )
    solver.get_color = MagicMock(return_value=np.array([255] * 3))
    solver.turn_on_room_detail("room_1_1")
    solver.tap.assert_not_called()


def test_detail_final_click_is_checked_before_returning_to_base():
    solver = solver_for([{"arrange_check_in": DETAIL}] * 19 + [{"room_detail": DETAIL}])
    solver.get_color = MagicMock(return_value=np.array([255] * 3))
    solver.back = MagicMock()
    solver.turn_on_room_detail("room_1_1")
    assert solver.tap.call_count == 10
    solver.back.assert_not_called()


@pytest.mark.parametrize("operation", ["confirm", "orders"])
def test_stop_during_feedback_wait_is_propagated(operation):
    solver = solver_for([{"connecting": True}])
    solver.sleep.side_effect = MowerExit
    with pytest.raises(MowerExit):
        if operation == "confirm":
            solver.tap_confirm("room_1_1")
        else:
            solver._wait_drone_interface()
    solver.tap.assert_not_called()
