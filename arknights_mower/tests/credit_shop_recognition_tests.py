"""信用商店保留未完成的识别，未知数字不参与购买或信用缺口计算。"""

from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import clue_credit
from arknights_mower.solvers import shop as shop_module
from arknights_mower.solvers.shop import CreditShop, CreditShopIncomplete
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.scene import Scene

FIXTURES = Path(__file__).parent / "fixtures" / "credit_shop"
PRICE_SCOPE = ((40, 522), (365, 555))
DISCOUNT_SCOPE = ((52, 287), (91, 317))
VOLUME_SCOPE = ((277, 236), (295, 262))
POLICIES = [(False, False), (True, False), (False, True)]


@pytest.fixture
def shopping(monkeypatch):
    monkeypatch.setattr(
        config,
        "conf",
        Conf(
            credit_shop_by_value=False,
            visit_friend_enable=True,
            visit_friend_mode="mower",
            maa_mall_enable=True,
            maa_mall_mode="mower",
            maa_mall_buy="技巧概要·卷2",
            maa_mall_blacklist="",
        ),
    )
    solver = object.__new__(CreditShop)
    solver.recog = SimpleNamespace(gray=np.zeros((1080, 1920), dtype=np.uint8))
    solver.on_demand = False
    solver.credit_deficit = None
    solver.selected_product = None
    solver.rejected_product = None
    solver.purchase_rechecks = 0
    solver.value_catalog = None
    solver.scene = Mock(return_value=Scene.SHOP_CREDIT)
    solver.find = Mock(return_value=None)
    solver.tap = Mock()
    solver.tap_element = Mock()
    solver.back = Mock()
    solver.sleep = Mock()
    solver.waiting_solver = Mock()
    solver.scene_graph_navigation = Mock()
    return solver


def assert_no_purchase_or_recovery(solver):
    assert solver.credit_deficit is None
    assert solver.selected_product is None
    solver.tap.assert_not_called()
    solver.tap_element.assert_not_called()
    solver.back.assert_not_called()
    solver.sleep.assert_not_called()
    solver.waiting_solver.assert_not_called()
    solver.scene_graph_navigation.assert_not_called()


def render_digits(templates, digits):
    image = np.zeros((80, 200), dtype=np.uint8)
    x = 15
    for digit in digits:
        glyph = templates[digit]
        h, w = glyph.shape
        image[20 : 20 + h, x : x + w] = glyph
        x += w + 8
    return image, x


def read_image(solver, image, font="noto"):
    solver.recog.gray = image
    return solver.number(((0, 0), (image.shape[1], image.shape[0])), font)


@pytest.mark.parametrize("font", ["noto", "riic_base"])
def test_each_bundled_digit_remains_readable(shopping, font):
    templates = (
        shop_module.noto_sans if font == "noto" else shop_module.riic_base_digits
    )
    for expected in range(10):
        image, _ = render_digits(templates, [expected])
        assert read_image(shopping, image, font) == expected


@pytest.mark.parametrize("expected", [1, 2])
@pytest.mark.parametrize("height", [20, 22, 24, 26])
def test_small_skill_book_volume_uses_the_digit_shape(shopping, expected, height):
    glyph = shop_module.noto_sans[expected]
    scale = height / glyph.shape[0]
    glyph = cv2.resize(glyph, None, fx=scale, fy=scale)
    image = np.zeros((26, 18), dtype=np.uint8)
    h, w = glyph.shape
    image[:h, :w] = glyph

    assert read_image(shopping, image) == expected


@pytest.mark.parametrize("width,height", [(1, 5), (1, 7), (2, 7), (1, 20), (5, 13)])
def test_short_field_does_not_enlarge_particles_into_digits(shopping, width, height):
    image = np.zeros((26, 18), dtype=np.uint8)
    image[2 : 2 + height, 5 : 5 + width] = 255

    assert read_image(shopping, image) is None


@pytest.mark.parametrize("size", [1, 3, 4])
def test_tiny_isolated_points_do_not_become_extra_digits(shopping, size):
    image, x = render_digits(shop_module.noto_sans, [5, 0])
    image[23 : 23 + size, x : x + size] = 255
    assert read_image(shopping, image) == 50


@pytest.mark.parametrize("shape", ["triangle", "block"])
def test_digit_sized_noise_invalidates_the_whole_number(shopping, shape):
    image, x = render_digits(shop_module.noto_sans, [5, 0])
    if shape == "triangle":
        cv2.fillConvexPoly(
            image,
            np.array([[x, 20], [x + 22, 20], [x + 11, 49]], dtype=np.int32),
            255,
        )
    else:
        image[20:50, 0:10] = 255
    assert read_image(shopping, image) is None


def test_empty_field_is_unknown_but_a_visible_zero_is_zero(shopping):
    assert read_image(shopping, np.zeros((40, 80), dtype=np.uint8)) is None
    image, _ = render_digits(shop_module.noto_sans, [0])
    assert read_image(shopping, image) == 0
    assert shopping.number(((0, 0), (0, 0))) is None


@pytest.mark.parametrize(
    "glyph_shape,template_shape", [((8, 40), (70, 15)), ((40, 8), (15, 70))]
)
def test_crossed_width_and_height_never_reach_opencv_assertion(
    shopping, monkeypatch, glyph_shape, template_shape
):
    image = np.zeros((80, 80), dtype=np.uint8)
    h, w = glyph_shape
    image[10 : 10 + h, 10 : 10 + w] = 255
    monkeypatch.setattr(
        shop_module,
        "noto_sans",
        {digit: np.full(template_shape, 255, dtype=np.uint8) for digit in range(10)},
    )
    assert read_image(shopping, image) is None


@pytest.mark.parametrize("score", [0.5, 0.8, float("nan")])
def test_unreliable_match_never_becomes_a_digit(shopping, monkeypatch, score):
    image, _ = render_digits(shop_module.noto_sans, [5])
    monkeypatch.setattr(
        shop_module.cv2,
        "matchTemplate",
        lambda *_args: np.array([[score]], dtype=np.float32),
    )
    assert read_image(shopping, image) is None


@pytest.mark.parametrize(
    "filename,balance",
    [
        ("shop_particles_20261031_052432.jpg", 612),
        ("shop_particles_20261031_071524.jpg", 582),
    ],
)
def test_archived_particle_frames_without_action_remain_unconfirmed(
    shopping, filename, balance
):
    image = cv2.imread(str(FIXTURES / filename), cv2.IMREAD_GRAYSCALE)
    assert image is not None
    assert image.shape == (1080, 1920)
    shopping.recog.gray = image
    assert shopping.credit_remain() == balance
    assert shopping.number(PRICE_SCOPE, thres=180) is None
    assert shopping.product_info() is False
    shopping.on_demand = True
    with pytest.raises(CreditShopIncomplete):
        shopping.transition()
    assert_no_purchase_or_recovery(shopping)


def test_ready_shop_frame_keeps_full_prices_and_can_purchase(shopping):
    image = cv2.imread(
        str(FIXTURES / "shop_ready_20261031_071521.jpg"), cv2.IMREAD_GRAYSCALE
    )
    assert image is not None
    shopping.recog.gray = image

    assert shopping.credit_remain() == 632
    assert shopping.product_info() is True
    assert [product["price"] for product in shopping.products] == [
        50,
        100,
        100,
        100,
        100,
        120,
        240,
        200,
        200,
        160,
    ]
    assert [product["discount"] for product in shopping.products] == [
        75,
        50,
        50,
        50,
        50,
        50,
        0,
        0,
        0,
        0,
    ]

    shopping.transition()

    assert shopping.selected_product["name"] == "糖"
    shopping.tap.assert_called_once_with(((25, 222), (377, 576)))


def skill_book_card(solver, monkeypatch):
    image = np.full((1080, 1920), 255, dtype=np.uint8)
    image[252, 55] = 0
    image[282, 31] = 0
    image[233:267, 85:345] = 0
    title = np.zeros((10, 20), dtype=np.uint8)
    title[2:8, 3:17] = 255
    image[240:250, 100:120] = title
    solver.recog.gray = image
    monkeypatch.setattr(shop_module, "shop", {"技巧概要": title})


def test_particle_instead_of_skill_book_volume_invalidates_product_list(
    shopping, monkeypatch
):
    skill_book_card(shopping, monkeypatch)
    image = shopping.recog.gray
    image[282, 31] = 255
    image[522:555, 40:365] = 0
    x = 60
    for digit in (1, 0, 0):
        glyph = shop_module.noto_sans[digit]
        h, w = glyph.shape
        image[523 : 523 + h, x : x + w] = glyph
        x += w + 8
    image[236:262, 277:295] = 0
    image[241:246, 282:283] = 255

    assert shopping.product_info() is False
    assert shopping.products == []


@pytest.mark.parametrize("field", ["discount", "price", "volume"])
@pytest.mark.parametrize("by_value,on_demand", POLICIES)
def test_unknown_product_field_retains_each_shopping_policy(
    shopping, monkeypatch, field, by_value, on_demand
):
    skill_book_card(shopping, monkeypatch)
    readings = {DISCOUNT_SCOPE: 50, PRICE_SCOPE: 100, VOLUME_SCOPE: 2}
    unknown = {"discount": DISCOUNT_SCOPE, "price": PRICE_SCOPE, "volume": VOLUME_SCOPE}
    readings[unknown[field]] = None
    shopping.number = Mock(side_effect=lambda scope, *_args, **_kwargs: readings[scope])
    shopping.credit_remain = Mock(return_value=500)
    config.conf.credit_shop_by_value = by_value
    shopping.on_demand = on_demand
    assert shopping.product_info() is False
    with pytest.raises(CreditShopIncomplete):
        shopping.transition()
    assert_no_purchase_or_recovery(shopping)


def test_confirmed_skill_book_fields_keep_the_correct_volume(shopping, monkeypatch):
    skill_book_card(shopping, monkeypatch)
    readings = {DISCOUNT_SCOPE: 50, PRICE_SCOPE: 100, VOLUME_SCOPE: 1}
    shopping.number = Mock(side_effect=lambda scope, *_args, **_kwargs: readings[scope])
    assert shopping.product_info() is True
    assert shopping.products[0] == {
        "name": "技巧概要·卷1",
        "touch": ((25, 222), (377, 576)),
        "discount": 50,
        "price": 100,
    }
    assert shopping.products[1:] == [None] * 9


def test_incomplete_product_reading_exposes_no_partial_or_previous_list(
    shopping, monkeypatch
):
    skill_book_card(shopping, monkeypatch)
    shopping.recog.gray[252, 435] = 0
    shopping.number = Mock(side_effect=[50, 100, 1, None])
    shopping.products = [{"name": "previous reading"}]

    assert shopping.product_info() is False

    assert shopping.products == []


@pytest.mark.parametrize("by_value,on_demand", POLICIES)
def test_unknown_balance_remains_unfinished_without_purchase_decisions(
    shopping, by_value, on_demand
):
    shopping.product_info = Mock(return_value=True)
    config.conf.credit_shop_by_value = by_value
    shopping.on_demand = on_demand
    assert shopping.credit_remain() is None
    with pytest.raises(CreditShopIncomplete):
        shopping.transition()
    shopping.product_info.assert_not_called()
    assert_no_purchase_or_recovery(shopping)


@pytest.mark.parametrize("by_value", [False, True])
def test_on_demand_caller_does_not_collect_board_credit_for_unknown_readings(
    shopping, monkeypatch, by_value
):
    monkeypatch.setattr(config, "stop_mower", Event())
    config.conf.clue_credit_on_demand = True
    config.conf.credit_shop_by_value = by_value
    shopping.check_current_focus = Mock()
    monkeypatch.setattr(clue_credit, "CreditShop", lambda *_args: shopping)
    caller = clue_credit.ClueCreditMixin()
    caller.device = Mock()
    caller.recog = shopping.recog
    caller.daily_visit_friend_attempt = clue_credit.get_server_time().date()
    caller._visit_clue_message_board = Mock()
    caller.scene_graph_navigation = Mock()

    with pytest.raises(CreditShopIncomplete):
        caller._run_on_demand_clue_shop()

    assert_no_purchase_or_recovery(shopping)
    caller._visit_clue_message_board.assert_not_called()
    caller.scene_graph_navigation.assert_not_called()
    assert not config.stop_mower.is_set()
