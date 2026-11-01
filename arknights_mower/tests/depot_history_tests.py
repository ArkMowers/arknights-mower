import csv
import json

import pytest

import server
from arknights_mower.utils import depot as module
from arknights_mower.utils.csv_utils import read_csv_rows

HEADER = ["Timestamp", "Data", "json"]


@pytest.fixture
def history_path(tmp_path, monkeypatch):
    """把 读取仓库历史 的 CSV 路径指到临时文件，避免碰真实 tmp。"""
    path = tmp_path / "depotresult.csv"
    monkeypatch.setattr(module, "get_path", lambda _: path)
    return path


@pytest.fixture
def depot_lines(tmp_path, monkeypatch):
    """两条快照线各指一个临时文件：扫描线 depotresult.csv、完整库存线 depotmerged.csv。"""
    paths = {
        "@app/tmp/depotresult.csv": tmp_path / "depotresult.csv",
        "@app/tmp/depotmerged.csv": tmp_path / "depotmerged.csv",
    }
    monkeypatch.setattr(module, "get_path", lambda key: paths[key])
    return paths


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        for row in rows:
            writer.writerow(row)


def snapshot(at, items):
    return [at, json.dumps(items, ensure_ascii=False), json.dumps({"空": ""})]


def test_common_resources_include_gold_and_orundum_shards(tmp_path, monkeypatch):
    paths = {
        "@app/tmp/cultivate.json": tmp_path / "cultivate.json",
        "@app/tmp/depotresult.csv": tmp_path / "depotresult.csv",
    }
    monkeypatch.setattr(module, "get_path", lambda key: paths[key])
    monkeypatch.setattr(module, "save_inventory_counts", lambda counts, **_: counts)
    paths["@app/tmp/cultivate.json"].write_text(
        '{"data": {"items": []}}', encoding="utf-8"
    )
    write_rows(
        paths["@app/tmp/depotresult.csv"],
        [snapshot(1789895956, {"赤金": 12, "源石碎片": 8, "合成玉": 600})],
    )

    categories, _, _ = module.读取仓库()

    assert categories["A常用"]["赤金"]["number"] == 12
    assert categories["A常用"]["源石碎片"]["number"] == 8
    assert "赤金" not in categories["K未分类"]
    assert "源石碎片" not in categories["K未分类"]
    assert categories["A常用"]["额外+碎片"]["number"] == 1.1


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


def test_snapshot_without_draw_materials_has_no_fabricated_tiers(history_path):
    """没看到抽卡物料时四个档位必须缺键，而不是补 0。

    补 0 会被前端当成"这次扫描抽数为 0"，在下一次环比里造出一次假的 −20 抽；
    缺键才会走"本次没有数据"，档位差额与趋势线直接跳过这一段。
    """
    write_rows(history_path, [snapshot(1789895956, {"龙门币": 20000})])

    items = module.读取仓库历史()[0]["items"]

    assert items == {"龙门币": 20000}
    assert not set(module.抽数档位) & items.keys()


def test_non_finite_cells_are_skipped(history_path):
    """inf / 1e999 会抛 OverflowError，不能让它把 /depot/history 变成 500。"""
    write_rows(
        history_path,
        [
            ["inf", json.dumps({"合成玉": 600}), json.dumps({"空": ""})],
            [1789895956, json.dumps({"合成玉": float("inf")}), json.dumps({"空": ""})],
            snapshot(1789982356, {"合成玉": 1200}),
        ],
    )

    history = module.读取仓库历史()

    assert [entry["at"] for entry in history] == [1789982356]


def test_torn_last_row_falls_back_to_the_previous_snapshot(history_path):
    """append 写入被打断会在文件尾留下半行，当前库存要退回上一条完整快照。

    旧代码直接 json.loads(depotinfo[-1][1])，一行半截数据就能让 /depot/readdepot
    整个 500，页面连当前库存都看不到。
    """
    write_rows(history_path, [snapshot(1789895956, {"合成玉": 600})])
    with open(history_path, "a", encoding="utf-8", newline="") as f:
        f.write('1789982356,{"合成玉": 12')

    _, rows = read_csv_rows(history_path)
    at, items = module.最后有效快照(rows)

    assert at == 1789895956
    assert items == {"合成玉": 600}


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
    # 只有龙门币，没有看到任何抽卡物料，四个派生档位都不该出现。
    assert history[0]["items"] == {"龙门币": 20000}


def test_merged_snapshot_writes_only_owned_items_with_the_complete_flag(depot_lines):
    """完整库存快照只写持有数量，并打上"完整"标记。

    写全 790 个名字每行 18KB，只写持有的大约 2.4KB；读取端看到标记就把没列出来的
    名字当成 0，所以"没写"不等于"这次没看到"。
    """
    module.记录合并快照(1789895956, {"固源岩": 600, "龙门币": 0, "至纯源石": 3})

    text = depot_lines["@app/tmp/depotmerged.csv"].read_text(encoding="utf-8")
    # 走一遍 csv 解析：Data/标记列里都是 JSON，直接被引号转义，别拿子串去比。
    rows = list(csv.reader(text.splitlines()))

    assert rows[0] == HEADER
    assert len(rows) == 2
    assert json.loads(rows[1][1]) == {"固源岩": 600, "至纯源石": 3}
    assert json.loads(rows[1][2]) == {"完整": True}


def test_scan_and_merged_rows_merge_into_one_complete_snapshot(depot_lines):
    """同一次扫描写的两行必须并成一条：材料来自合并行，基础物品来自扫描行。

    只有扫描行时历史里永远没有固源岩，第 4 档位也就永远等于第 3 档；并起来之后
    "额外+碎片+土"才是真的按固源岩算出来的。
    """
    write_rows(
        depot_lines["@app/tmp/depotresult.csv"],
        [snapshot(1789895956, {"龙门币": 20000})],
    )
    module.记录合并快照(1789895956, {"龙门币": 20000, "固源岩": 600, "至纯源石": 3})

    history = module.读取仓库历史()

    assert len(history) == 1
    快照 = history[0]
    assert 快照["at"] == 1789895956
    assert 快照["complete"] is True
    assert 快照["items"]["龙门币"] == 20000
    assert 快照["items"]["固源岩"] == 600
    # 完整快照六个来源都在（缺席即 0），档位一律补算：
    # (3 * 180 + int((0 + 600 / 2) / 2) * 20) / 600 = (540 + 3000) / 600 = 5.9
    assert 快照["items"]["额外+碎片+土"] == 5.9
    assert 快照["items"]["额外+碎片"] == 0.9


def test_partial_scan_rows_are_not_marked_complete(depot_lines):
    """只有扫描行时不能被当成完整库存：缺的名字是"没扫到"，不是 0。"""
    write_rows(
        depot_lines["@app/tmp/depotresult.csv"],
        [snapshot(1789895956, {"龙门币": 20000})],
    )

    history = module.读取仓库历史()

    assert "complete" not in history[0]
    assert not set(module.抽数档位) & history[0]["items"].keys()


def test_merged_row_without_a_scan_is_a_valid_snapshot(depot_lines):
    """只有合并行的快照也要能读出来（例如扫描没跑成、但库存被记录了一次）。"""
    module.记录合并快照(1789895956, {"固源岩": 600})

    history = module.读取仓库历史()

    assert len(history) == 1
    assert history[0]["complete"] is True
    assert history[0]["items"]["固源岩"] == 600


def test_history_limit_follows_the_setting(monkeypatch):
    """取用条数以设置为上限：请求参数只能再往下收，缺失/写坏都按设置走。"""
    from arknights_mower.utils import config as config_module

    monkeypatch.setattr(config_module.conf, "depot_history_limit", 800)

    assert module.历史条数() == 800
    assert module.历史条数("100") == 100
    assert module.历史条数("99999") == 800
    assert module.历史条数("abc") == 800
    assert module.历史条数("0") == 1


def test_history_limit_survives_a_broken_setting(monkeypatch):
    from arknights_mower.utils import config as config_module

    monkeypatch.setattr(config_module.conf, "depot_history_limit", "not-a-number")
    assert module.历史条数() == 3000

    # 配置写太大时按防呆上限收，免得一次把整份历史吐出来
    monkeypatch.setattr(config_module.conf, "depot_history_limit", 999999)
    assert module.历史条数() == 20000


def test_cleanup_keeps_only_the_newest_rows(depot_lines, monkeypatch):
    """清理按设置的条数裁剪，表头保留，两份文件一起裁。"""
    from arknights_mower.utils import config as config_module

    monkeypatch.setattr(config_module.conf, "depot_history_keep", 3)
    write_rows(
        depot_lines["@app/tmp/depotresult.csv"],
        [snapshot(1789895900 + i, {"龙门币": i}) for i in range(6)],
    )
    module.记录合并快照(1789895905, {"固源岩": 1})

    module.清理历史()

    rows = list(
        csv.reader(
            depot_lines["@app/tmp/depotresult.csv"]
            .read_text(encoding="utf-8")
            .splitlines()
        )
    )
    assert rows[0] == HEADER
    assert [row[0] for row in rows[1:]] == ["1789895903", "1789895904", "1789895905"]
    # 合并文件只有一条，没到上限就别动它
    merged = (
        depot_lines["@app/tmp/depotmerged.csv"].read_text(encoding="utf-8").splitlines()
    )
    assert len(merged) == 2


def test_cleanup_is_off_by_default(depot_lines, monkeypatch):
    from arknights_mower.utils import config as config_module

    monkeypatch.setattr(config_module.conf, "depot_history_keep", 0)
    write_rows(
        depot_lines["@app/tmp/depotresult.csv"],
        [snapshot(1789895900 + i, {"龙门币": i}) for i in range(6)],
    )

    module.清理历史()

    lines = (
        depot_lines["@app/tmp/depotresult.csv"].read_text(encoding="utf-8").splitlines()
    )
    assert len(lines) == 7  # 表头 + 6 条，一条没删


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


def test_tokens_are_excluded_from_history(history_path):
    """信物类物品不应出现在仓库历史快照中。"""
    write_rows(
        history_path,
        [
            [
                1789895956,
                json.dumps({"合成玉": 3630, "阿米娅的信物": 1, "先锋皇家信物": 4}),
                "{}",
            ]
        ],
    )

    items = module.读取仓库历史()[0]["items"]

    assert "合成玉" in items
    assert "阿米娅的信物" not in items
    assert "先锋皇家信物" not in items


def test_tokens_are_excluded_from_cloud_snapshot():
    payload = {
        "_mower_inventory_observed_at": 1789895956,
        "data": {
            "items": [
                {"id": "30012", "count": 100},
                {"id": "p_char_002_amiya", "count": 1},
            ]
        },
    }
    counts, observed_at = module.cloud_inventory_snapshot(payload)
    assert observed_at == 1789895956
    assert "固源岩" in counts
    assert counts["固源岩"] == 100
    assert "阿米娅的信物" not in counts
    assert not any("信物" in name for name in counts)


class TestDepotHistoryRoute:
    """路由层：取用条数按设置钳制，以及空数据兜底。"""

    def setup_method(self):
        self.client = server.app.test_client()

    @pytest.fixture(autouse=True)
    def pinned_limit(self, monkeypatch):
        """钉住设置里的条数，别让本机 config.json 影响断言。"""
        from arknights_mower.utils import config as config_module

        monkeypatch.setattr(config_module.conf, "depot_history_limit", 3000)

    def test_route_returns_snapshots(self, monkeypatch):
        monkeypatch.setattr(
            module,
            "读取仓库历史",
            lambda limit: [{"at": limit, "items": {"龙门币": 1}}],
        )

        response = self.client.get("/depot/history?limit=5")

        assert response.status_code == 200
        assert response.get_json()["snapshots"] == [{"at": 5, "items": {"龙门币": 1}}]

    @pytest.mark.parametrize("raw,expected", [("0", 1), ("-3", 1), ("99999", 3000)])
    def test_route_clamps_limit(self, raw, expected, monkeypatch):
        seen = {}

        def fake(limit):
            seen["limit"] = limit
            return []

        monkeypatch.setattr(module, "读取仓库历史", fake)

        self.client.get(f"/depot/history?limit={raw}")

        assert seen["limit"] == expected

    @pytest.mark.parametrize("raw", ["abc", ""])
    def test_route_falls_back_to_the_configured_limit(self, raw, monkeypatch):
        """参数缺失/写坏都按设置里的"仓库历史条数"走，所以页面不用自己知道这个数。"""
        seen = {}

        def fake(limit):
            seen["limit"] = limit
            return []

        monkeypatch.setattr(module, "读取仓库历史", fake)

        self.client.get(f"/depot/history?limit={raw}")

        assert seen["limit"] == module.历史条数()

    def test_route_is_empty_when_no_history(self, monkeypatch):
        monkeypatch.setattr(module, "读取仓库历史", lambda limit: [])

        response = self.client.get("/depot/history")

        assert response.status_code == 200
        assert response.get_json() == {"snapshots": []}
