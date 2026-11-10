from unittest.mock import Mock

import numpy as np
import pytest

from arknights_mower.solvers import depotREC as module
from arknights_mower.utils import depot


@pytest.mark.parametrize(
    "name",
    [
        "龙门币",
        "赤金",
        "源石碎片",
        "采购凭证",
        "事相碎片",
        "龙骨",
        "家具零件",
        "高级加固建材",
        "进阶加固建材",
        "基础加固建材",
        "碳素组",
        "碳素",
        "碳",
    ],
)
def test_skland_items_never_read_a_scanned_quantity(monkeypatch, name):
    solver = module.depotREC.__new__(module.depotREC)
    monkeypatch.setattr(module, "提取特征点", lambda _: np.zeros(1))
    monkeypatch.setattr(module.vision_np, "knn1_predict", lambda *args: name)
    solver.读取物品数字 = Mock(side_effect=AssertionError("unexpected OCR"))
    image = np.zeros((260, 260), dtype=np.uint8)
    assert solver.匹配物品一次(image, image, dict(X=None, y=None, classes=None)) == [
        name,
        None,
    ]
    solver.读取物品数字.assert_not_called()


@pytest.mark.parametrize("name", ["合成玉", "寻访凭证", "招聘许可", "应急理智顶液"])
def test_scan_only_items_keep_quantity_recognition(monkeypatch, name):
    solver = module.depotREC.__new__(module.depotREC)
    monkeypatch.setattr(module, "提取特征点", lambda _: np.zeros(1))
    monkeypatch.setattr(module.vision_np, "knn1_predict", lambda *args: name)
    solver.读取物品数字 = Mock(return_value=12)
    image = np.zeros((260, 260), dtype=np.uint8)
    assert solver.匹配物品一次(image, image, dict(X=None, y=None, classes=None)) == [
        name,
        12,
    ]
    solver.读取物品数字.assert_called_once()
    np.testing.assert_array_equal(
        solver.读取物品数字.call_args.args[0], image[160:210, 30:210]
    )


def test_cloud_integer_count_does_not_lose_magnitude():
    payload = {
        "_mower_inventory_observed_at": 123,
        "data": {"items": [{"id": "4001", "count": "100000000"}]},
    }
    counts, _ = depot.cloud_inventory_snapshot(payload)
    assert counts["龙门币"] == 100000000
