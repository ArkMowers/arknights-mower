import unittest

from arknights_mower.utils.weekly_stage import (
    build_options,
    select_latest_activity_stages,
)


def _drop(drop_id, drop_type, dropType="NORMAL"):
    return {"type": drop_type, "id": drop_id, "dropType": dropType}


def _stage(
    stage_id,
    event,
    start=None,
    end=None,
    stage_type="ACTIVITY",
    difficulty="NORMAL",
    drops=None,
):
    rec = {
        "id": stage_id,
        "name": stage_id,
        "stageType": stage_type,
        "zoneNameSecond": event,
        "difficulty": difficulty,
        "drop": drops,
    }
    if start is not None and end is not None:
        rec["endTs"] = {"startTs": start, "endTs": end}
    else:
        rec["endTs"] = None
    return rec


def _km(*ids_names):
    # key_mapping: id -> [id, itemtype, name, MATERIAL, sort]
    return {i: [i, "MTL", name, "MATERIAL", 1] for i, name in ids_names}


class TestSelectLatestActivityStages(unittest.TestCase):
    """选关纯逻辑：最近开启活动（max startTs 事件）的普通关 = 后三关 + 掉固源岩/装置关。"""

    def setUp(self):
        # 材质：30012 固源岩 / 30062 装置 / 其余普通材料
        self.km = _km(
            ("30011", "源岩"),
            ("30012", "固源岩"),
            ("30031", "糖"),
            ("30062", "装置"),
            ("30041", "异铁"),
            ("31033", "晶体元件"),
            ("31013", "凝胶"),
            ("30023", "糖组"),
            ("30052", "酮凝集"),
        )

    def _activity(self):
        # 旧活动（startTs=1000）、新活动（startTs=3000，max）——按活动名分区。
        return [
            # 旧活动组：不应被选中
            _stage(
                "AT-1",
                "旧活动",
                start=1000,
                end=2000,
                drops=[_drop("30031", "MATERIAL")],
            ),
            _stage(
                "AT-2",
                "旧活动",
                start=1000,
                end=2000,
                drops=[_drop("30041", "MATERIAL")],
            ),
            # 新活动组（max startTs）
            _stage(
                "BS-1",
                "新活动",
                start=3000,
                end=4000,
                drops=[_drop("30011", "MATERIAL")],
            ),
            _stage(
                "BS-2",
                "新活动",
                start=3000,
                end=4000,
                drops=[_drop("30012", "MATERIAL")],
            ),  # 固源岩
            _stage("BS-3", "新活动", start=3000, end=4000, drops=[]),
            # BS-4 同时是「旧三关之一」且掉装置
            _stage(
                "BS-4",
                "新活动",
                start=3000,
                end=4000,
                drops=[_drop("30062", "MATERIAL")],
            ),  # 装置
            _stage("BS-5", "新活动", start=3000, end=4000, drops=[]),
            # 特化子 zone（MO/S/EX）与突袭/挑战版都应被排除
            _stage(
                "BS-MO-1",
                "新活动",
                start=3000,
                end=4000,
                drops=[_drop("30012", "MATERIAL")],
            ),
            _stage("BS-S-1", "新活动", start=3000, end=4000, drops=[]),
            _stage("BS-S-2", "新活动", start=3000, end=4000, drops=[]),
            _stage("BS-EX-1", "新活动", start=3000, end=4000, drops=[]),
            _stage(
                "BS-3 突袭",
                "新活动",
                start=3000,
                end=4000,
                difficulty="FOUR_STAR",
                drops=[],
            ),
            # 无关记录：常驻 / 无窗口 / 非活动 —— 均忽略
            _stage("MAIN-7", "常驻", stage_type="MAIN"),
            _stage("X-1", "无窗口活动", start=None, end=None, drops=[]),
        ]

    def test_picks_most_recent_event(self):
        got = select_latest_activity_stages(self._activity(), self.km, 500)
        codes = [g["code"] for g in got]
        # 旧活动 AT-1/AT-2 与无关记录都不出现
        self.assertNotIn("AT-1", codes)
        self.assertNotIn("AT-2", codes)
        self.assertNotIn("MAIN-7", codes)
        self.assertNotIn("X-1", codes)

    def test_selects_top3_plus_material_stages_and_dedupes(self):
        got = select_latest_activity_stages(self._activity(), self.km, 500)
        codes = [g["code"] for g in got]
        # 后三关：BS-5/BS-4/BS-3；+ 掉材料关：BS-2/BS-4；BS-4 去重后仅一次
        self.assertEqual(sorted(codes), ["BS-2", "BS-3", "BS-4", "BS-5"])
        self.assertEqual(len(codes), 4)

    def test_sorted_by_trailing_number_desc(self):
        got = select_latest_activity_stages(self._activity(), self.km, 500)
        self.assertEqual([g["code"] for g in got], ["BS-5", "BS-4", "BS-3", "BS-2"])

    def test_excludes_mo_s_ex_and_challenge(self):
        got = select_latest_activity_stages(self._activity(), self.km, 500)
        codes = [g["code"] for g in got]
        for excluded in ("BS-MO-1", "BS-S-1", "BS-S-2", "BS-EX-1", "BS-3 突袭"):
            self.assertNotIn(excluded, codes)

    def test_materials_only_material_type_normal_drop(self):
        got = select_latest_activity_stages(self._activity(), self.km, 500)
        by_code = {g["code"]: g for g in got}
        self.assertEqual(
            by_code["BS-4"]["materials"], [{"id": "30062", "name": "装置"}]
        )
        self.assertEqual(
            by_code["BS-2"]["materials"], [{"id": "30012", "name": "固源岩"}]
        )
        self.assertEqual(by_code["BS-3"]["materials"], [])
        self.assertEqual(by_code["BS-5"]["materials"], [])

    def test_no_window_stages_returns_empty(self):
        got = select_latest_activity_stages(
            [
                _stage("MAIN-1", "常驻", stage_type="MAIN"),
                _stage("X-9", "活动", drops=[]),
            ],
            self.km,
            500,
        )
        self.assertEqual(got, [])

    def test_ended_activity_excluded_by_time(self):
        # 活动结束时间早于 now → 不显示
        s = _stage(
            "TO-5", "活动A", start=1000, end=2000, drops=[_drop("30062", "MATERIAL")]
        )
        got = select_latest_activity_stages([s], self.km, 3000)
        self.assertEqual(got, [])

    def test_ongoing_activity_shown_when_not_ended(self):
        s = _stage(
            "TO-9", "活动A", start=1000, end=5000, drops=[_drop("30012", "MATERIAL")]
        )
        got = select_latest_activity_stages([s], self.km, 3000)
        self.assertEqual([g["code"] for g in got], ["TO-9"])

    def test_mixed_ended_and_ongoing_picks_ongoing(self):
        # 已结束的活动被时间过滤掉，只留还没结束的
        ended = _stage("TO-1", "活动A", start=100, end=2000, drops=[])
        ongoing = _stage(
            "TO-9", "活动B", start=1000, end=5000, drops=[_drop("30012", "MATERIAL")]
        )
        got = select_latest_activity_stages([ended, ongoing], self.km, 3000)
        self.assertEqual([g["code"] for g in got], ["TO-9"])

    def test_activity_item_and_complete_drops_ignored(self):
        s = _stage(
            "ZZ-1",
            "活动",
            start=1,
            end=6000,
            drops=[
                _drop("act_token", "ACTIVITY_ITEM", dropType="COMPLETE"),
                _drop("30012", "MATERIAL", dropType="COMPLETE"),  # COMPLETE 非常规
            ],
        )
        got = select_latest_activity_stages([s], self.km, 500)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["materials"], [])

    def test_to_style_event_normal_last3_plus_material(self):
        # 复刻真实结构：一场活动有主关 TO-1..9、EX-1..8、S-1..4、MO-1。
        # MO/S/EX 全剔 → 主关后三 = TO-9/8/7（各自带常规材料）；+ 掉材料 TO-4(固源岩)/TO-5(装置)。
        stages = []
        non_target_drops = {
            7: [("30023", "糖组")],
            8: [("31013", "凝胶")],
            9: [("31033", "晶体元件")],
        }
        for i in range(1, 10):
            if i in (4, 5):
                continue
            stages.append(
                _stage(
                    f"TO-{i}",
                    "直到大地变成一颗酸橙",
                    start=1000,
                    end=2000,
                    drops=[
                        _drop(mat, "MATERIAL") for mat, _ in non_target_drops.get(i, [])
                    ],
                )
            )
        stages.append(
            _stage(
                "TO-4",
                "直到大地变成一颗酸橙",
                start=1000,
                end=2000,
                drops=[_drop("30041", "MATERIAL"), _drop("30012", "MATERIAL")],
            )
        )
        stages.append(
            _stage(
                "TO-5",
                "直到大地变成一颗酸橙",
                start=1000,
                end=2000,
                drops=[_drop("30062", "MATERIAL"), _drop("30052", "MATERIAL")],
            )
        )
        # EX / S / MO 子 zone（startTs 更晚，反正都剔）
        stages += [
            _stage(f"TO-EX-{i}", "直到大地变成一颗酸橙", start=1500, end=2000)
            for i in range(1, 9)
        ]
        stages += [
            _stage(f"TO-S-{i}", "直到大地变成一颗酸橙", start=2000, end=3000)
            for i in range(1, 5)
        ]
        stages.append(_stage("TO-MO-1", "直到大地变成一颗酸橙", start=2000, end=3000))
        got = select_latest_activity_stages(stages, self.km, 500)
        self.assertEqual(
            [g["code"] for g in got], ["TO-9", "TO-8", "TO-7", "TO-5", "TO-4"]
        )
        by_code = {g["code"]: g for g in got}
        # 掉材料关只展示目标材料，无关材料（异铁/酮凝集）不进
        self.assertEqual(
            by_code["TO-4"]["materials"], [{"id": "30012", "name": "固源岩"}]
        )
        self.assertEqual(
            by_code["TO-5"]["materials"], [{"id": "30062", "name": "装置"}]
        )
        # 后三关保留自己的常规材料
        self.assertEqual(
            by_code["TO-9"]["materials"], [{"id": "31033", "name": "晶体元件"}]
        )
        self.assertEqual(
            by_code["TO-8"]["materials"], [{"id": "31013", "name": "凝胶"}]
        )
        self.assertEqual(
            by_code["TO-7"]["materials"], [{"id": "30023", "name": "糖组"}]
        )
        # 库存前缀格式
        opts = build_options(got, {"30012": 443, "30062": 294, "31033": 190})
        label = {o["value"]: o["label"] for o in opts}
        self.assertEqual(label["TO-9"], "TO-9:晶体元件(库存:190)")
        self.assertEqual(label["TO-4"], "TO-4:固源岩(库存:443)")
        self.assertEqual(label["TO-5"], "TO-5:装置(库存:294)")


class TestBuildOptions(unittest.TestCase):
    """label/value 组装：库存有则 (库存:n)，无则省略。"""

    def setUp(self):
        self.selected = [
            {"code": "BS-5", "materials": []},
            {"code": "BS-4", "materials": [{"id": "30062", "name": "装置"}]},
            {"code": "BS-2", "materials": [{"id": "30012", "name": "固源岩"}]},
        ]

    def test_label_includes_stock_when_present(self):
        got = build_options(self.selected, {"30012": 7})
        by = {g["value"]: g for g in got}
        self.assertEqual(by["BS-2"]["label"], "BS-2:固源岩(库存:7)")
        self.assertEqual(by["BS-4"]["label"], "BS-4:装置")
        self.assertEqual(by["BS-5"]["label"], "BS-5")

    def test_zero_or_missing_stock_omits_parenthetical(self):
        got = build_options(self.selected, {"30062": 0, "30012": 0})
        by = {g["value"]: g for g in got}
        self.assertEqual(by["BS-2"]["label"], "BS-2:固源岩")
        self.assertEqual(by["BS-4"]["label"], "BS-4:装置")

    def test_value_is_code_and_preserves_selection_order(self):
        got = build_options(self.selected, {"30012": 7, "30062": 3})
        self.assertEqual([g["value"] for g in got], ["BS-5", "BS-4", "BS-2"])
        self.assertEqual([g["code"] for g in got], ["BS-5", "BS-4", "BS-2"])
        for g in got:
            self.assertIn("label", g)

    def test_multiple_materials_joined_by_comma(self):
        selected = [
            {
                "code": "AT-9",
                "materials": [
                    {"id": "30012", "name": "固源岩"},
                    {"id": "30062", "name": "装置"},
                ],
            }
        ]
        got = build_options(selected, {"30012": 10, "30062": 2})
        self.assertEqual(got[0]["label"], "AT-9:固源岩(库存:10),装置(库存:2)")


if __name__ == "__main__":
    unittest.main()
