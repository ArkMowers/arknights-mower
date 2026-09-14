"""页面反馈延迟时等待新帧，丢点时有界重试，不把残影当成第二次确认。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.recognize import RecognizeError

BLUE = ((1550, 40), (1800, 100))
DETAIL = ((10, 400), (150, 480))


def solver_for(frames):
    """一次缓存失效对应一张新帧；同一帧中的全部模板查询共享状态。"""
    solver = object.__new__(BaseSchedulerSolver)
    solver.op_data = SimpleNamespace(run_order_rooms={})
    state = {"frame": 0}

    def advance(*args, **kwargs):
        state["frame"] = min(state["frame"] + 1, len(frames) - 1)

    def find(name, score=0):
        frame = frames[state["frame"]]
        value = frame.get(name)
        return None if score and frame.get("fading") else value

    solver.recog = SimpleNamespace(w=1920, h=1080, update=MagicMock())
    solver.find = MagicMock(side_effect=find)
    solver.tap = MagicMock(side_effect=advance)
    solver.sleep = MagicMock(side_effect=advance)
    return solver


def test_confirmation_disappearance_needs_no_extra_wait_or_click():
    solver = solver_for([{"confirm_blue": BLUE}, {"room_detail": DETAIL}])
    solver.tap_confirm("room_1_1")
    solver.tap.assert_called_once_with(BLUE, interval=0.2)
    solver.sleep.assert_not_called()


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
    solver.sleep.assert_called_once_with()
    solver.tap.assert_called_once_with(BLUE, interval=0.2)


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


def test_unrelated_factory_button_is_not_trade_success():
    solver = solver_for([{"factory_accelerate": BLUE}, {"bill_accelerate": BLUE}])
    solver._wait_drone_interface(accelerate_template="bill_accelerate")
    assert solver.tap.call_count == 1


@pytest.mark.parametrize("template", ["factory_accelerate", "bill_accelerate"])
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
