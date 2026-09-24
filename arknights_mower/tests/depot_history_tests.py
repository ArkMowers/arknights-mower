import json

import pytest

import server
from arknights_mower.utils import depot as module

HEADER = ["Timestamp", "Data", "json"]


@pytest.fixture
def history_path(tmp_path, monkeypatch):
    """把 读取仓库历史 的 CSV 路径指到临时文件，避免碰真实 tmp。"""
    path = tmp_path / "depotresult.csv"
    monkeypatch.setattr(module, "get_path", lambda _: path)
    return path


def write_rows(path, rows):
    import csv

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        for row in rows:
            writer.writerow(row)


def snapshot(at, items):
    return [at, json.dumps(items, ensure_ascii=False), json.dumps({"空": ""})]


def test_missing_file_returns_empty(history_path):
    assert module.读取仓库历史() == []


def test_empty_file_returns_empty(history_path):
    history_path.write_text("", encoding="utf-8")
    assert module.读取仓库历史() == []


def test_header_only_returns_empty(history_path):
    write_rows(history_path, [])
    assert module.读取仓库历史() == []


def test_placeholder_row_is_excluded(history_path):
    """创建文件时写的占位行没有真实物料，参与环比会制造一整份假增量。"""
    write_rows(
        history_path,
        [
            [1789809501, json.dumps({"还未开始过扫描": 0}), json.dumps({"空": ""})],
            snapshot(1789895956, {"至纯源石": 10, "合成玉": 3630}),
        ],
    )

    history = module.读取仓库历史()

    assert len(history) == 1
    assert history[0]["at"] == 1789895956
    # 原始物料原样保留；四个派生档位由 读取仓库历史 回填，具体数值见下面的换算用例。
    assert {key: history[0]["items"][key] for key in ("至纯源石", "合成玉")} == {
        "至纯源石": 10,
        "合成玉": 3630,
    }


def test_snapshots_are_sorted_ascending_and_limited(history_path):
    write_rows(
        history_path,
        [snapshot(at, {"龙门币": at}) for at in (300, 100, 200)],
    )

    history = module.读取仓库历史(limit=2)

    # 只留最近两条，且仍是时间升序（前端按顺序画折线）。
    assert [entry["at"] for entry in history] == [200, 300]


def test_limit_none_keeps_everything(history_path):
    write_rows(history_path, [snapshot(at, {"龙门币": at}) for at in (1, 2, 3)])

    assert len(module.读取仓库历史(limit=None)) == 3


def test_derived_draw_tiers_are_backfilled(history_path):
    """CSV 只存原始物料，抽数由 读取仓库历史 现算补上，前端才不用自己折算。"""
    write_rows(
        history_path,
        [snapshot(1789895956, {"合成玉": 3600, "寻访凭证": 4, "十连寻访凭证": 1})],
    )

    items = module.读取仓库历史()[0]["items"]

    # 寻访凭证按十连 ×10 并入：4 + 1 * 10 = 14，3600 / 600 + 14 = 20.0
    assert items["玉+卷"] == 20.0
    assert items["玉+卷+石"] == 20.0
    assert items["额外+碎片"] == 20.0
    assert items["额外+碎片+土"] == 20.0


def test_derived_tiers_use_the_same_conversion_as_read_depot(history_path):
    """历史快照与 读取仓库 的派生值必须同源，否则页面上的卡片和趋势线会互相打架。"""
    payload = {"合成玉": 70, "至纯源石": 3, "源石碎片": 3, "固源岩": 5}
    write_rows(history_path, [snapshot(1789895956, payload)])

    items = module.读取仓库历史()[0]["items"]
    expected = module.折算抽数(70, 0, 3, 3, 5)

    assert {档位: items[档位] for 档位 in module.抽数档位} == expected
    # 70 / 600 = 0.1166…，Python 的 round() 取到 0.1；JS 的 Math.round 在 .5 边界上
    # 与它不等价，前端因此只读后端结果、不再自己重算。
    assert expected["玉+卷"] == 0.1


def test_stale_derived_tiers_in_the_csv_are_recomputed(history_path):
    """旧快照里残留的同名派生键必须按当前口径覆盖，不能留在 items 里当原始物料。"""
    write_rows(
        history_path,
        [snapshot(1789895956, {"合成玉": 600, "玉+卷": 999.9})],
    )

    items = module.读取仓库历史()[0]["items"]

    assert items["玉+卷"] == 1.0
    assert set(module.抽数档位) <= items.keys()


def test_snapshot_without_draw_materials_still_carries_the_four_tiers(history_path):
    """没有可折算物料时四个档位是 0，而不是缺键——前端按"四个键齐全"判断能否直读。"""
    write_rows(history_path, [snapshot(1789895956, {"龙门币": 20000})])

    items = module.读取仓库历史()[0]["items"]

    assert {档位: items[档位] for 档位 in module.抽数档位} == dict.fromkeys(
        module.抽数档位, 0.0
    )


def test_undecodable_file_is_treated_as_no_history(history_path):
    """文件被别的编辑器存成非 UTF-8 时返回 []，不让 /depot/history 变成 500。"""
    history_path.write_bytes(b"Timestamp,Data,json\n123,\xff\xfe not utf8,{}\n")

    assert module.读取仓库历史() == []


def test_corrupt_and_partial_rows_are_skipped(history_path):
    write_rows(
        history_path,
        [
            ["not-a-timestamp", json.dumps({"龙门币": 1}), "{}"],
            [1789895956, "not-json", "{}"],
            [1789895957, json.dumps(["not", "a", "dict"]), "{}"],
            [1789895958, json.dumps({"龙门币": "两千"}), "{}"],
            [1789895959, json.dumps({}), "{}"],
            ["1789895960"],  # 残行：列数不足
            snapshot(1789895961, {"龙门币": 20000}),
        ],
    )

    history = module.读取仓库历史()

    assert len(history) == 1
    # 只有龙门币，四个派生档位都为 0。
    assert history[0]["items"]["龙门币"] == 20000
    assert {
        档位: history[0]["items"][档位] for 档位 in module.抽数档位
    } == dict.fromkeys(module.抽数档位, 0.0)


def test_numeric_string_counts_are_coerced(history_path):
    """CSV 里数量可能以字符串/浮点形式落盘，统一收敛成 int。"""
    write_rows(
        history_path,
        [
            [
                1789895956,
                json.dumps({"合成玉": "3630", "至纯源石": 10.0}),
                "{}",
            ]
        ],
    )

    items = module.读取仓库历史()[0]["items"]

    assert items["合成玉"] == 3630
    assert items["至纯源石"] == 10
    assert isinstance(items["合成玉"], int)
    assert isinstance(items["至纯源石"], int)


class TestDepotHistoryRoute:
    """路由层：limit 参数钳制与空数据兜底。"""

    def setup_method(self):
        self.client = server.app.test_client()

    def test_route_returns_snapshots(self, monkeypatch):
        monkeypatch.setattr(
            module,
            "读取仓库历史",
            lambda limit: [{"at": limit, "items": {"龙门币": 1}}],
        )

        response = self.client.get("/depot/history?limit=5")

        assert response.status_code == 200
        assert response.get_json()["snapshots"] == [{"at": 5, "items": {"龙门币": 1}}]

    @pytest.mark.parametrize("raw,expected", [("0", 1), ("-3", 1), ("99999", 500)])
    def test_route_clamps_limit(self, raw, expected, monkeypatch):
        seen = {}

        def fake(limit):
            seen["limit"] = limit
            return []

        monkeypatch.setattr(module, "读取仓库历史", fake)

        self.client.get(f"/depot/history?limit={raw}")

        assert seen["limit"] == expected

    @pytest.mark.parametrize("raw", ["abc", ""])
    def test_route_falls_back_to_default_limit(self, raw, monkeypatch):
        seen = {}

        def fake(limit):
            seen["limit"] = limit
            return []

        monkeypatch.setattr(module, "读取仓库历史", fake)

        self.client.get(f"/depot/history?limit={raw}")

        assert seen["limit"] == 60

    def test_route_is_empty_when_no_history(self, monkeypatch):
        monkeypatch.setattr(module, "读取仓库历史", lambda limit: [])

        response = self.client.get("/depot/history")

        assert response.status_code == 200
        assert response.get_json() == {"snapshots": []}
