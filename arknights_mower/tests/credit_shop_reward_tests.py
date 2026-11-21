"""领取和购买后的动画结束后继续购物，未确认结果不能当作完成。"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import pytest

from arknights_mower.solvers import shop as shop_module
from arknights_mower.solvers.shop import CreditShop
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver

FIXTURES = Path(__file__).parent / "fixtures" / "credit_shop"
SUGAR = ((25, 222), (377, 576))
ROCK = ((1165, 222), (1517, 576))
POLICIES = [(False, False), (True, False), (False, True)]


class PurchaseSelected(Exception):
    """测试已观察到下一次合法商品选择，在输入边界结束回放。"""


class RecordedShop:
    def __init__(self, scenario, *, stuck=None):
        self.scenario = scenario
        self.stuck = stuck
        self.stage = "collect" if scenario == "collect" else "ready"
        self.now = 0.0
        self.inputs = []
        self.observed = []
        self.refreshes = 0
        self.sleep_error = None
        self.frames = {
            "collect": "shop_collect_20261031_052431.jpg",
            "ready": "shop_ready_20261031_071521.jpg",
            "confirm": "shop_confirm_20261031_071522.jpg",
            "collect_particles": "shop_particles_20261031_052432.jpg",
            "collect_reward": "shop_credit_reward_20261031_052432.jpg",
            "collect_stable": "shop_after_collect_20261031_052434.jpg",
            "purchase_particles": "shop_particles_20261031_071524.jpg",
            "purchase_reward": "shop_sugar_reward_20261031_071525.jpg",
            "purchase_stable": "shop_after_purchase_20261031_071536.jpg",
        }
        self.images = {
            stage: cv2.imread(str(FIXTURES / filename), cv2.IMREAD_GRAYSCALE)
            for stage, filename in self.frames.items()
        }
        assert all(image is not None for image in self.images.values())

    @property
    def gray(self):
        return self.images[self.stage]

    def update(self):
        self.refreshes += 1
        assert self.refreshes < 100, "reward observation must have a finite bound"

    def scene(self):
        self.observed.append(self.stage)
        if self.stage.endswith("_reward"):
            return Scene.MATERIEL
        if self.stage == "confirm":
            return Scene.SHOP_CREDIT_CONFIRM
        return Scene.SHOP_CREDIT

    def find(self, name, *_args, **_kwargs):
        if name == "shop_collect" and self.stage == "collect":
            return (1498, 60)
        return None

    def tap(self, position, *_args, **_kwargs):
        self.inputs.append((self.stage, position))
        if self.stage == "collect" and position == (1498, 60):
            self.stage = "collect_particles"
        elif self.stage.endswith("_reward") and position == (960, 960):
            if self.stuck != "reward":
                self.stage = f"{self.scenario}_stable"
        elif self.stage == "collect_stable" and position == SUGAR:
            raise PurchaseSelected("sugar after collecting credit")
        elif self.stage == "ready" and position == SUGAR:
            self.stage = "confirm"
        elif self.stage == "purchase_stable" and position == ROCK:
            raise PurchaseSelected("rock after the confirmed sugar purchase")
        else:
            pytest.fail(f"unexpected input on {self.stage}: {position}")

    def confirm(self, name, *_args, **_kwargs):
        assert self.stage == "confirm"
        assert name == "shop_cart"
        self.inputs.append((self.stage, name))
        self.stage = "purchase_particles"
        return True

    def sleep(self, seconds=1):
        assert seconds > 0
        if self.sleep_error is not None:
            raise self.sleep_error
        self.now += seconds
        if self.stage.endswith("_particles") and self.stuck != "particles":
            self.stage = f"{self.scenario}_reward"


@pytest.fixture
def recorded_shopping(monkeypatch):
    monkeypatch.setattr(
        config,
        "conf",
        Conf(
            credit_shop_by_value=False,
            visit_friend_enable=True,
            visit_friend_mode="mower",
            maa_mall_enable=True,
            maa_mall_mode="mower",
            maa_mall_buy="糖,固源岩",
            maa_mall_blacklist="",
        ),
    )
    monkeypatch.setattr(config, "stop_mower", Event())

    def build(scenario, *, stuck=None):
        frames = RecordedShop(scenario, stuck=stuck)
        solver = object.__new__(CreditShop)
        solver.recog = frames
        solver.scene = frames.scene
        solver.find = frames.find
        solver.tap = Mock(side_effect=frames.tap)
        solver.tap_element = Mock(side_effect=frames.confirm)
        solver.sleep = Mock(side_effect=frames.sleep)
        solver.check_current_focus = Mock()
        solver.back = Mock(side_effect=AssertionError("unexpected back input"))
        solver.waiting_solver = Mock(
            side_effect=AssertionError("reward observation must stay in the shop")
        )
        solver.scene_graph_navigation = Mock(
            side_effect=AssertionError("reward observation must not leave the shop")
        )
        monkeypatch.setattr(shop_module, "monotonic", lambda: frames.now, raising=False)
        return solver, frames

    return build


@pytest.mark.parametrize("by_value,on_demand", POLICIES)
def test_collect_credit_animation_continues_to_the_configured_purchase(
    recorded_shopping, by_value, on_demand
):
    solver, frames = recorded_shopping("collect")
    config.conf.credit_shop_by_value = by_value

    with pytest.raises(PurchaseSelected, match="sugar after collecting"):
        solver.run(on_demand=on_demand)

    assert frames.inputs == [
        ("collect", (1498, 60)),
        ("collect_reward", (960, 960)),
        ("collect_stable", SUGAR),
    ]
    assert "collect_particles" in frames.observed
    assert "collect_reward" in frames.observed
    assert solver.credit_remain() == 612
    assert solver.selected_product["name"] == "糖"
    assert solver.credit_deficit is None
    assert not getattr(solver, "pending_reward", None)
    solver.tap_element.assert_not_called()


@pytest.mark.parametrize("by_value,on_demand", POLICIES)
def test_purchase_animation_reconciles_sold_stock_before_buying_the_next_item(
    recorded_shopping, by_value, on_demand
):
    solver, frames = recorded_shopping("purchase")
    config.conf.credit_shop_by_value = by_value
    assert solver.credit_remain() == 632

    with pytest.raises(PurchaseSelected, match="rock after the confirmed"):
        solver.run(on_demand=on_demand)

    assert frames.inputs == [
        ("ready", SUGAR),
        ("confirm", "shop_cart"),
        ("purchase_reward", (960, 960)),
        ("purchase_stable", ROCK),
    ]
    assert "purchase_particles" in frames.observed
    assert solver.credit_remain() == 582
    assert solver.products[0] is None
    assert solver.selected_product["name"] == "固源岩"
    assert solver.credit_deficit is None
    assert not getattr(solver, "pending_reward", None)
    solver.tap_element.assert_called_once_with("shop_cart", interval=0)


@pytest.mark.parametrize("stuck", ["particles", "reward"])
def test_unfinished_reward_exhausts_the_original_budget_without_completing(
    recorded_shopping, stuck
):
    solver, frames = recorded_shopping("collect", stuck=stuck)

    with pytest.raises(Exception) as caught:
        solver.run(on_demand=True)

    assert isinstance(caught.value, shop_module.CreditShopIncomplete)
    assert caught.value.pending_reward["kind"] == "collect"
    assert caught.value.pending_reward["dismissed"] is (stuck == "reward")
    assert 0 < frames.now <= 10.25
    assert frames.inputs.count(("collect", (1498, 60))) == 1
    assert frames.inputs.count(("collect_reward", (960, 960))) == (
        1 if stuck == "reward" else 0
    )
    assert solver.credit_deficit is None
    assert not config.stop_mower.is_set()
    solver.tap_element.assert_not_called()


@pytest.mark.parametrize("error_type", [MowerExit, DeviceRecoveryError])
def test_stop_and_device_failure_propagate_during_reward_observation(
    recorded_shopping, error_type
):
    solver, frames = recorded_shopping("collect", stuck="particles")
    expected = error_type("observation interrupted")
    frames.sleep_error = expected

    with pytest.raises(error_type) as caught:
        solver.run(on_demand=True)

    assert caught.value is expected
    assert frames.inputs == [("collect", (1498, 60))]
    assert solver.credit_deficit is None
    solver.tap_element.assert_not_called()


def test_unknown_frame_without_a_known_action_is_incomplete_without_a_wait(
    recorded_shopping,
):
    solver, frames = recorded_shopping("collect")
    frames.stage = "collect_particles"

    with pytest.raises(Exception) as caught:
        solver.run(on_demand=True)

    assert isinstance(caught.value, shop_module.CreditShopIncomplete)
    assert not caught.value.pending_reward
    assert frames.now == 0
    assert frames.inputs == []
    assert solver.credit_deficit is None
    solver.sleep.assert_not_called()


def test_missing_confirmation_button_does_not_begin_a_purchase_reward(
    recorded_shopping,
):
    solver, frames = recorded_shopping("purchase")
    frames.stage = "confirm"
    solver.on_demand = False
    solver.credit_deficit = None
    solver.pending_reward = None
    solver.selected_product = {"name": "糖", "touch": SUGAR, "price": 50}
    solver.selected_balance = 632
    solver.tap_element = Mock(return_value=False)

    with pytest.raises(shop_module.CreditShopIncomplete):
        solver.transition()

    assert solver.pending_reward is None
    assert solver.credit_deficit is None
    assert frames.inputs == []
    solver.tap_element.assert_called_once_with("shop_cart", interval=0)
    solver.sleep.assert_not_called()


def test_slow_observation_cannot_send_a_receipt_close_after_the_deadline(
    recorded_shopping,
):
    solver, frames = recorded_shopping("collect")
    solver.pending_reward = {"kind": "collect", "dismissed": False}
    solver.credit_deficit = None

    def slow_observation():
        frames.now = solver.REWARD_TIMEOUT + 1
        return {
            "scene": Scene.MATERIEL,
            "balance": None,
            "products": None,
            "collectable": False,
        }

    solver._shop_observation = slow_observation
    solver.tap = Mock()

    with pytest.raises(shop_module.CreditShopIncomplete):
        solver._finish_reward()

    solver.tap.assert_not_called()


@pytest.mark.parametrize("error_type", [MowerExit, DeviceRecoveryError])
def test_real_confirm_input_records_pending_before_any_interruptible_wait(
    recorded_shopping, error_type
):
    solver, frames = recorded_shopping("purchase")
    frames.stage = "confirm"
    solver.pending_reward = None
    solver.credit_deficit = None
    solver.selected_product = {"name": "糖", "touch": SUGAR, "price": 50}
    solver.selected_slot = 0
    solver.selected_balance = 632
    solver.find = Mock(
        side_effect=lambda name, *_args, **_kwargs: (
            (1252, 842) if name == "shop_cart" else None
        )
    )
    solver.device = SimpleNamespace(
        tap=Mock(
            side_effect=lambda *_args: setattr(frames, "stage", "purchase_particles")
        )
    )
    solver.tap = BaseSolver.tap.__get__(solver)
    solver.tap_element = BaseSolver.tap_element.__get__(solver)
    expected = error_type("observation interrupted")
    solver.sleep = Mock(side_effect=expected)

    solver.transition()

    assert solver.pending_reward["kind"] == "purchase"
    solver.sleep.assert_not_called()
    with pytest.raises(error_type) as caught:
        solver.transition()
    assert caught.value is expected
    assert solver.pending_reward["kind"] == "purchase"
    solver.device.tap.assert_called_once_with((1252, 842))


@pytest.mark.parametrize("new_day", [False, True])
def test_receipt_confirmation_distinguishes_the_refreshed_shop_from_old_stock(
    recorded_shopping, monkeypatch, new_day
):
    solver, frames = recorded_shopping("purchase")
    frames.images["purchase_stable"] = frames.images["ready"]
    before_reset = datetime(
        2026, 10, 30, 23, 59, 59, tzinfo=timezone(timedelta(hours=4))
    )
    after_reset = before_reset + timedelta(seconds=2)
    monkeypatch.setattr(
        shop_module,
        "get_server_time",
        lambda: (
            after_reset
            if new_day and frames.stage == "purchase_stable"
            else before_reset
        ),
        raising=False,
    )
    tap = frames.tap
    find = frames.find
    solver.find = lambda name, *args, **kwargs: (
        (1498, 60)
        if new_day and frames.stage == "purchase_stable" and name == "shop_collect"
        else find(name, *args, **kwargs)
    )

    def select_new_stock(position, *args, **kwargs):
        if frames.stage == "purchase_stable" and position == (1498, 60):
            raise PurchaseSelected("new daily credit from the refreshed shop")
        tap(position, *args, **kwargs)

    solver.tap.side_effect = select_new_stock
    if new_day:
        with pytest.raises(PurchaseSelected, match="refreshed shop"):
            solver.run(on_demand=True)
    else:
        with pytest.raises(shop_module.CreditShopIncomplete):
            solver.run(on_demand=True)
    assert frames.inputs == [
        ("ready", SUGAR),
        ("confirm", "shop_cart"),
        ("purchase_reward", (960, 960)),
    ]


def test_daily_credit_visible_after_a_receipt_is_claimed_before_a_shortage(
    recorded_shopping,
):
    solver, frames = recorded_shopping("purchase")
    frames.stage = "purchase_stable"
    solver.pending_reward = {"kind": "purchase", "dismissed": True}
    solver.on_demand = True
    solver.credit_deficit = None
    solver.rejected_product = None
    solver.products = [None, {"name": "固源岩", "price": 100, "touch": ROCK}]
    solver._finish_reward = Mock(
        return_value={
            "scene": Scene.SHOP_CREDIT,
            "balance": 10,
            "products": solver.products,
            "collectable": True,
        }
    )
    solver.find = Mock(
        side_effect=lambda name: (1498, 60) if name == "shop_collect" else None
    )
    solver.tap = Mock()

    assert solver.transition() is None

    solver.tap.assert_called_once_with((1498, 60), interval=0)
    assert solver.pending_reward["kind"] == "collect"
    assert solver.pending_reward["dismissed"] is False
    assert solver.credit_deficit is None


@pytest.mark.parametrize(
    "missing",
    ["receipt", "shop", "products", "balance", "new_day_evidence", "unchanged_stock"],
)
def test_game_day_change_alone_cannot_confirm_a_purchase(missing):
    reward = {
        "kind": "purchase",
        "dismissed": True,
        "slot": 0,
        "game_day": "2026-10-30",
    }
    observation = {
        "scene": Scene.SHOP_CREDIT,
        "balance": 582,
        "products": [{"name": "糖", "price": 50, "discount": 75}],
        "collectable": True,
        "game_day": "2026-10-31",
    }
    if missing == "receipt":
        reward["dismissed"] = False
    elif missing == "shop":
        observation["scene"] = Scene.INFRA_MAIN
    elif missing == "new_day_evidence":
        observation["collectable"] = False
    elif missing == "unchanged_stock":
        observation["collectable"] = False
        reward["catalog"] = [{"name": "糖", "price": 50, "discount": 75}]
    else:
        observation[missing] = None

    assert CreditShop._reward_complete(observation, reward) is False


def test_new_day_stock_change_confirms_received_goods_without_reclaiming_daily_credit():
    reward = {
        "kind": "purchase",
        "dismissed": True,
        "slot": 0,
        "game_day": "2026-10-30",
        "catalog": [{"name": "糖", "price": 50, "discount": 75}],
    }
    observation = {
        "scene": Scene.SHOP_CREDIT,
        "balance": 582,
        "products": [{"name": "固源岩", "price": 100, "discount": 50}],
        "collectable": False,
        "game_day": "2026-10-31",
    }

    assert CreditShop._reward_complete(observation, reward) is True
