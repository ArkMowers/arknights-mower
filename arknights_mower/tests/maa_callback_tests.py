import json
import logging
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# base_schedule 的导入链会初始化森空岛模块；回调转译测试不依赖网络。
sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

import arknights_mower.solvers.base_schedule as base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils.maa_callback import (  # noqa: E402
    CONNECTION_TEXT,
    SUB_TASK_INFO,
    MaaCallbackLog,
    MaaLogLine,
    parse_details,
)

LOG_NAME = "arknights_mower.utils.log"


class FakeClock:
    """单调推进的时钟，让心跳间隔在测试中无需真实等待。"""

    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def payload(**fields) -> bytes:
    return json.dumps(fields, ensure_ascii=False).encode("utf-8")


class ParseDetailsTests(unittest.TestCase):
    def test_empty_payloads_yield_an_empty_mapping(self):
        # MAA 在部分消息码下不传 details，ctypes 会给到 None 或空字节串。
        for raw in (None, b"", ""):
            with self.subTest(raw=raw):
                self.assertEqual(parse_details(raw), {})

    def test_unparsable_payload_yields_an_empty_mapping(self):
        for raw in (b"{not json", b"\xff\xfe", b"[1, 2]"):
            with self.subTest(raw=raw):
                self.assertEqual(parse_details(raw), {})

    def test_object_payload_is_decoded(self):
        self.assertEqual(
            parse_details(payload(what="StageDrops")), {"what": "StageDrops"}
        )


class MaaMalformedPayloadTests(unittest.TestCase):
    """[INV-MAA-01]：任何 MAA 可能发出的字段形态都不得让回调抛错。

    ctypes 会吞掉回调里抛出的异常，一旦抛出，本轮 MAA 之后的进度行全部丢失，
    所以受测的失败形态是「抛出」而不是「输出不好看」。
    """

    def setUp(self):
        self.log = MaaCallbackLog(clock=FakeClock())
        self.messages = (
            0,
            1,
            2,
            3,
            4,
            5,
            10000,
            10001,
            10002,
            10003,
            10004,
            20000,
            20001,
            20002,
            20003,
            20004,
            30000,
        )

    def test_wrong_typed_fields_never_raise(self):
        # 每个已知 what 都至少喂一次把字段换成别的类型，覆盖所有取值分支。
        whats = (
            list(SUB_TASK_INFO) + list(CONNECTION_TEXT) + ["RoutingRestart", "Whatever"]
        )
        for message in self.messages:
            for what in whats:
                for details in (
                    {"what": what},
                    {"what": what, "details": "not-a-mapping"},
                    {"what": what, "details": {"tags": 7, "drops": 7, "result": 7}},
                    {"what": what, "details": {"stage": 7, "result": "text"}},
                    {"what": what, "details": {"drops": [7], "result": [7]}},
                    {
                        "what": what,
                        "details": {"result": [{"opers": 7}], "task": 7, "text": 7},
                    },
                    {"what": what, "details": {"result": [{"opers": [7]}]}},
                    # 干员名会参与哈希与拼接，非字符串曾在此抛 TypeError。
                    {"what": what, "details": {"result": [{"opers": [{"name": 7}]}]}},
                    {
                        "what": what,
                        "details": {"result": [{"opers": [{"name": ["a"]}]}]},
                    },
                    {
                        "what": what,
                        "details": {"result": [{"opers": [{"name": {"x": 1}}]}]},
                    },
                    {"why": ["unhashable"], "subtask": what, "taskchain": what},
                    {"why": 7, "subtask": 7, "taskchain": 7, "what": 7},
                    {"taskchain": ["unhashable"], "what": what},
                    "not-a-mapping",
                ):
                    with self.subTest(message=message, what=what, details=details):
                        self.log.describe(message, details)

    def test_malformed_payload_yields_a_line_or_none(self):
        line = self.log.describe(20003, {"what": "StageDrops", "details": "broken"})
        self.assertEqual(line.level, logging.INFO)
        self.assertEqual(line.text, "关卡 作战结束，无掉落")
        # 不可用的字段退化成缺省结论，而不是抛错。
        self.assertEqual(
            self.log.describe(20003, {"what": "StageDrops", "details": {}}).text,
            "关卡 作战结束，无掉落",
        )
        self.assertIsNone(self.log.describe(20003, "not-a-mapping"))

    def test_unhashable_what_does_not_raise(self):
        self.assertIsNone(self.log.describe(2, {"what": ["ConnectFailed"]}))
        self.assertIsNone(self.log.describe(20004, {}))

    def test_unhashable_why_does_not_raise(self):
        line = self.log.describe(
            20000, {"subtask": "ReportToPenguinStats", "why": ["x"]}
        )
        self.assertEqual(line.text, "出现错误，放弃上传企鹅物流")


class MaaCallbackLogTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.log = MaaCallbackLog(clock=self.clock)

    def test_unknown_message_has_no_line(self):
        self.assertIsNone(self.log.describe(30000, {}))
        self.assertIsNone(self.log.describe(5, {}))

    def test_internal_error_and_init_failed_are_errors(self):
        internal = self.log.describe(0, {})
        self.assertEqual(internal.level, logging.ERROR)
        self.assertEqual(internal.text, "MAA 内部错误")

        failed = self.log.describe(1, {"what": "LoadResourceFailed", "why": "资源缺失"})
        self.assertEqual(failed.level, logging.ERROR)
        self.assertEqual(failed.text, "MAA 初始化失败：LoadResourceFailed（资源缺失）")

    def test_connection_failures_and_events(self):
        cases = {
            "ConnectFailed": logging.ERROR,
            "UnsupportedResolution": logging.ERROR,
            "ResolutionChanged": logging.ERROR,
            "Disconnect": logging.ERROR,
            "ScreencapFailed": logging.ERROR,
            "TouchModeNotAvailable": logging.ERROR,
            "Reconnecting": logging.ERROR,
            "Reconnected": logging.INFO,
            "Connected": logging.DEBUG,
            "UuidGot": logging.DEBUG,
            "ResolutionInfo": logging.DEBUG,
        }
        for what, level in cases.items():
            with self.subTest(what=what):
                line = self.log.describe(2, {"what": what})
                self.assertEqual(line.level, level)

    def test_periodic_connection_telemetry_stays_off_the_info_level(self):
        # 截图耗时每 10 次回传一条、帧率每分钟一条，逐条播报会淹没日志。
        for what, level in (
            ("ScreencapCost", None),
            ("EmulatorFPS", logging.DEBUG),
            ("FastestWayToScreencap", logging.DEBUG),
            ("MuMuExtrasInputStatus", logging.DEBUG),
        ):
            with self.subTest(what=what):
                line = self.log.describe(2, {"what": what})
                self.assertEqual(line.level if line else None, level)

    def test_task_chain_lifecycle(self):
        started = self.log.describe(10001, {"taskchain": "Fight"})
        self.assertEqual(started, MaaLogLine(logging.INFO, "开始任务：理智作战"))
        self.assertEqual(self.log.taskchain, "Fight")

        completed = self.log.describe(10002, {"taskchain": "Fight"})
        self.assertEqual(completed, MaaLogLine(logging.INFO, "完成任务：理智作战"))
        # 链结束后心跳不再声称该链仍在运行。
        self.assertEqual(self.log.taskchain, "")

    def test_all_tasks_completed_clears_the_running_task_chain(self):
        self.log.describe(10001, {"taskchain": "Fight"})
        self.log.describe(3, {"taskchain": "Fight"})
        self.assertEqual(self.log.taskchain, "")

    def test_task_chain_stopped_ends_the_chain(self):
        # 停止多为调度器自己发起，仍要留一行，否则日志里会出现没有下文的链。
        self.log.describe(10001, {"taskchain": "Fight"})
        line = self.log.describe(10004, {"taskchain": "Fight"})
        self.assertEqual(line, MaaLogLine(logging.INFO, "已停止任务：理智作战"))
        # 已停止的链不得再被心跳报成运行中。
        self.assertEqual(self.log.taskchain, "")
        self.clock.advance(60)
        self.assertEqual(
            self.log.heartbeat(), MaaLogLine(logging.INFO, "MAA 运行中（已运行 01:00）")
        )

    def test_task_chain_error_reports_the_core_exception(self):
        line = self.log.describe(
            10000, {"taskchain": "Fight", "details": {"error": "OpenCVException"}}
        )
        self.assertEqual(
            line, MaaLogLine(logging.ERROR, "任务出错：理智作战（OpenCVException）")
        )

    def test_out_of_memory_error_is_actionable(self):
        line = self.log.describe(
            10000, {"taskchain": "Roguelike", "details": {"error": "OutOfMemory"}}
        )
        self.assertEqual(
            line,
            MaaLogLine(
                logging.ERROR,
                "自动肉鸽任务因内存不足停止，请关闭部分程序或重启 MAA 后重试",
            ),
        )

    def test_unknown_task_chain_keeps_the_reported_name(self):
        line = self.log.describe(10001, {"taskchain": "SomeFutureChain"})
        self.assertEqual(line.text, "开始任务：SomeFutureChain")

    def test_all_tasks_completed_names_the_last_chain(self):
        line = self.log.describe(3, {"taskchain": "Award"})
        self.assertEqual(
            line, MaaLogLine(logging.INFO, "MAA 全部任务完成（最后：领取奖励）")
        )

    def test_stage_drops_are_summarised(self):
        line = self.log.describe(
            20003,
            {
                "what": "StageDrops",
                "taskchain": "Fight",
                "details": {
                    "stage": {"stageCode": "1-7"},
                    "drops": [
                        {"itemName": "源岩", "quantity": 2},
                        {"itemName": "龙门币", "quantity": 100},
                    ],
                },
            },
        )
        self.assertEqual(line.level, logging.INFO)
        self.assertEqual(line.text, "1-7 作战结束，掉落：源岩×2、龙门币×100")

    def test_stage_drops_without_items_is_still_reported(self):
        line = self.log.describe(
            20003, {"what": "StageDrops", "details": {"drops": [], "stage": {}}}
        )
        self.assertEqual(line.text, "关卡 作战结束，无掉落")

    def test_recruit_result_lists_operators_and_caps_the_line(self):
        def combo(name):
            return {"tags": ["输出"], "level": 5, "opers": [{"name": name}]}

        line = self.log.describe(
            20003,
            {
                "what": "RecruitResult",
                "details": {
                    "level": 5,
                    "result": [combo(f"干员{index}") for index in range(11)],
                },
            },
        )
        self.assertEqual(line.level, logging.INFO)
        self.assertTrue(line.text.startswith("公招识别到 5 星组合：干员0、"))
        self.assertTrue(line.text.endswith("等 11 名干员"))

    def test_recruit_result_without_operators_reports_only_the_level(self):
        line = self.log.describe(
            20003, {"what": "RecruitResult", "details": {"level": 3}}
        )
        self.assertEqual(line.text, "公招识别到 3 星组合")

    def test_recruit_result_ignores_names_that_are_not_strings(self):
        # 干员名要参与哈希去重与拼接，非字符串必须被丢弃而不是让回调抛错。
        line = self.log.describe(
            20003,
            {
                "what": "RecruitResult",
                "details": {
                    "level": 5,
                    "result": [
                        {
                            "opers": [
                                {"name": name} for name in (7, ["a"], {"x": 1}, None)
                            ]
                        }
                    ],
                },
            },
        )
        self.assertEqual(line, MaaLogLine(logging.INFO, "公招识别到 5 星组合"))

    def test_recruit_result_keeps_valid_names_alongside_invalid_ones(self):
        line = self.log.describe(
            20003,
            {
                "what": "RecruitResult",
                "details": {
                    "level": 5,
                    "result": [{"opers": [{"name": 7}, {"name": "能天使"}]}],
                },
            },
        )
        self.assertEqual(line.text, "公招识别到 5 星组合：能天使")

    def test_recruit_tags_split_across_detected_and_selected(self):
        detected = self.log.describe(
            20003,
            {"what": "RecruitTagsDetected", "details": {"tags": ["输出", "生存"]}},
        )
        self.assertEqual(detected.text, "公招识别到标签：输出、生存")
        selected = self.log.describe(
            20003, {"what": "RecruitTagsSelected", "details": {"tags": ["输出"]}}
        )
        self.assertEqual(selected.text, "公招已选择标签：输出")

    def test_recruit_special_tag_reads_the_documented_singular_field(self):
        line = self.log.describe(
            20003, {"what": "RecruitSpecialTag", "details": {"tag": "高级资深干员"}}
        )
        self.assertEqual(
            line, MaaLogLine(logging.INFO, "公招识别到特殊标签：高级资深干员")
        )

    def test_recruit_problems_are_warnings(self):
        for what in ("RecruitError", "RecruitPermitCountRecognitionFailed"):
            with self.subTest(what=what):
                self.assertEqual(
                    self.log.describe(20003, {"what": what}).level, logging.WARNING
                )

    def test_streaming_depot_and_operbox_progress_is_not_reported(self):
        # done 为假表示仍在识别中，MAA 会连续回传多条中间态。
        for what in ("DepotInfo", "OperBoxInfo"):
            with self.subTest(what=what):
                self.assertIsNone(
                    self.log.describe(20003, {"what": what, "details": {"done": False}})
                )
                line = self.log.describe(
                    20003, {"what": what, "details": {"done": True}}
                )
                self.assertEqual(line.level, logging.DEBUG)

    def test_facility_traffic_levels(self):
        # 设施进出沿用客户端的常规级别；产物收取在客户端只进工具箱面板。
        for what, level in (
            ("EnterFacility", logging.INFO),
            ("ProductOfFacility", logging.DEBUG),
        ):
            with self.subTest(what=what):
                line = self.log.describe(
                    20003,
                    {
                        "what": what,
                        "details": {"facility": "Mfg", "index": 1, "product": "赤金"},
                    },
                )
                self.assertEqual(line.level, level)

    def test_not_enough_staff_is_an_error(self):
        line = self.log.describe(
            20003,
            {"what": "NotEnoughStaff", "details": {"facility": "Trade", "index": 2}},
        )
        self.assertEqual(line, MaaLogLine(logging.ERROR, "Trade 2 可用干员不足"))

    def test_stage_queue_results_are_reported(self):
        completed = self.log.describe(
            20003,
            {
                "what": "StageQueueMissionCompleted",
                "details": {"stage_code": "CE-6", "stars": 3},
            },
        )
        self.assertEqual(completed.text, "关卡队列：CE-6 - 3 ★")
        unable = self.log.describe(
            20003,
            {"what": "StageQueueUnableToAgent", "details": {"stage_code": "CE-6"}},
        )
        self.assertEqual(unable.text, "关卡队列：CE-6 无法使用代理指挥")

    def test_reclamation_and_sss_results_are_reported(self):
        report = self.log.describe(
            20003,
            {
                "what": "ReclamationReport",
                "details": {
                    "total_badges": 120,
                    "badges": 5,
                    "total_construction_points": 40,
                    "construction_points": 2,
                },
            },
        )
        self.assertEqual(report.text, "生息演算结束：繁荣证章 120(+5)，建造点数 40(+2)")
        self.assertEqual(
            self.log.describe(
                20003, {"what": "SSSStage", "details": {"stage": "8-3"}}
            ).text,
            "保全派驻当前关卡：8-3",
        )
        self.assertEqual(
            self.log.describe(20003, {"what": "SSSGamePass"}).text, "保全派驻通关"
        )

    def test_credit_overflow_is_informational(self):
        # 客户端对该节点用默认级别（Message），即普通信息。
        line = self.log.describe(
            20003, {"what": "CreditFullOnlyBuyDiscount", "details": {"credit": 300}}
        )
        self.assertEqual(line.level, logging.INFO)
        self.assertEqual(line.text, "只购买折扣商品让信用点数溢出了，剩余信用点数：300")

    def test_theme_switch_results_are_reported(self):
        switched = self.log.describe(
            20002,
            {
                "taskchain": "SwitchTheme",
                "subtask": "ProcessTask",
                "details": {
                    "task": "SwitchThemeByNameConfirmTheme",
                    "result": {"text": "夜间"},
                },
            },
        )
        self.assertEqual(switched, MaaLogLine(logging.INFO, "已更换主题：夜间"))
        locked = self.log.describe(
            20002,
            {
                "taskchain": "SwitchTheme",
                "subtask": "ProcessTask",
                "details": {
                    "task": "SwitchThemeByNameLockedTheme",
                    "result": {"text": "彩虹"},
                },
            },
        )
        self.assertEqual(locked.level, logging.ERROR)

    def test_process_task_milestones_are_reported(self):
        for task, text in (
            ("StartButton2", "开始战斗"),
            ("MedicineConfirm", "使用理智药"),
            ("RecruitConfirm", "已确认招募"),
        ):
            with self.subTest(task=task):
                line = self.log.describe(
                    20001, {"subtask": "ProcessTask", "details": {"task": task}}
                )
                self.assertEqual(line, MaaLogLine(logging.INFO, text))

    def test_process_task_completion_is_reported_per_task_chain(self):
        line = self.log.describe(
            20002,
            {
                "taskchain": "Roguelike",
                "subtask": "ProcessTask",
                "details": {"task": "StartExplore", "exec_times": 3},
            },
        )
        self.assertEqual(line, MaaLogLine(logging.INFO, "肉鸽已开始探索 3 次"))

    def test_process_task_milestone_levels_follow_the_client(self):
        cases = {
            "AbandonAction": logging.ERROR,
            "OfflineConfirm": logging.ERROR,
            "MissionFailedFlag": logging.ERROR,
            "CheckEncounter-Uncollected": logging.WARNING,
            "MissionCompletedFlag": logging.INFO,
        }
        for task, level in cases.items():
            with self.subTest(task=task):
                line = self.log.describe(
                    20001,
                    {
                        "subtask": "ProcessTask",
                        "taskchain": "Fight",
                        "details": {"task": task},
                    },
                )
                self.assertEqual(line.level, level)

    def test_offline_confirm_is_suppressed_during_startup(self):
        """开始唤醒链本就要在游戏未启动时接管，重连成功不该报错。"""
        for task in ("OfflineConfirm", "OfflineConfirmAfterBattle"):
            for taskchain, expected in (("StartUp", None), ("Fight", logging.ERROR)):
                with self.subTest(task=task, taskchain=taskchain):
                    line = self.log.describe(
                        20001,
                        {
                            "subtask": "ProcessTask",
                            "taskchain": taskchain,
                            "details": {"task": task},
                        },
                    )
                    self.assertEqual(line.level if line else None, expected)

    def test_ordinary_process_task_recognition_is_not_reported(self):
        # ProcessTask 的识别动作每秒多次，全部播报会重新淹没日志。
        for task in ("ProcessTask", "ClickSelf", "UnknownTask"):
            with self.subTest(task=task):
                self.assertIsNone(
                    self.log.describe(
                        20001, {"subtask": "ProcessTask", "details": {"task": task}}
                    )
                )
        self.assertIsNone(
            self.log.describe(20001, {"subtask": "ReportToPenguinStats", "details": {}})
        )

    def test_subtask_error_uses_the_node_whitelist(self):
        # 上报跳过沿用客户端级别：告警。
        line = self.log.describe(
            20000, {"subtask": "ReportToPenguinStats", "why": "NotThreeStars"}
        )
        self.assertEqual(
            line, MaaLogLine(logging.WARNING, "非三星结算，放弃上传企鹅物流")
        )
        self.assertEqual(
            self.log.describe(20000, {"subtask": "ReportToYituliu"}).level,
            logging.WARNING,
        )
        line = self.log.describe(20000, {"subtask": "StartGameTask"})
        self.assertEqual(line.level, logging.ERROR)
        # 未列出的子任务仍有通用出错行。
        line = self.log.describe(
            20000, {"taskchain": "Fight", "subtask": "SomeFutureTask", "why": "mystery"}
        )
        self.assertEqual(
            line, MaaLogLine(logging.WARNING, "理智作战：SomeFutureTask 出错")
        )

    def test_subtask_stopped_is_not_reported(self):
        self.assertIsNone(
            self.log.describe(20004, {"taskchain": "Fight", "subtask": "ProcessTask"})
        )

    def test_routing_restart_reads_the_top_level_node_cost(self):
        line = self.log.describe(
            10003,
            {"what": "RoutingRestart", "why": "TooManyBattlesAhead", "node_cost": 7},
        )
        self.assertEqual(line, MaaLogLine(logging.WARNING, "前方战斗数：7，重开路线"))

    def test_other_task_chain_extra_info_is_not_reported(self):
        self.assertIsNone(self.log.describe(10003, {"taskchain": "Fight"}))

    def test_async_call_failure_is_reported(self):
        self.assertIsNone(
            self.log.describe(
                4, {"what": "Screencap", "details": {"ret": True, "cost": 12}}
            )
        )
        line = self.log.describe(
            4, {"what": "Screencap", "details": {"ret": False, "error": "Timeout"}}
        )
        self.assertEqual(line.level, logging.WARNING)
        self.assertEqual(line.text, "MAA 异步调用 Screencap 失败：Timeout")


class MaaHeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.log = MaaCallbackLog(clock=self.clock, interval=60, stall_after=180)

    def test_heartbeat_is_throttled_to_the_interval(self):
        self.assertIsNone(self.log.heartbeat())
        self.clock.advance(59)
        self.assertIsNone(self.log.heartbeat())
        self.clock.advance(1)
        self.assertIsNotNone(self.log.heartbeat())
        self.assertIsNone(self.log.heartbeat())

    def test_heartbeat_names_the_running_task_chain(self):
        self.log.describe(10001, {"taskchain": "Fight"})
        self.clock.advance(90)
        self.assertEqual(
            self.log.heartbeat(),
            MaaLogLine(logging.INFO, "MAA 运行中：理智作战（已运行 01:30）"),
        )

    def test_heartbeat_without_a_task_chain_still_reports_progress(self):
        self.clock.advance(90)
        self.assertEqual(
            self.log.heartbeat(), MaaLogLine(logging.INFO, "MAA 运行中（已运行 01:30）")
        )

    def test_heartbeat_mentions_a_silent_core(self):
        self.log.describe(10001, {"taskchain": "Fight"})
        self.clock.advance(100)
        self.log.describe(
            20001, {"subtask": "ProcessTask", "details": {"task": "StartButton2"}}
        )
        self.clock.advance(200)
        self.assertEqual(
            self.log.heartbeat(),
            MaaLogLine(
                logging.INFO,
                "MAA 运行中：理智作战（已运行 05:00，最近 03:20 没有收到 MAA 回调）",
            ),
        )

    def test_heartbeat_uses_hours_once_the_run_is_long(self):
        log = MaaCallbackLog(clock=self.clock, interval=60, stall_after=10**6)
        self.clock.advance(3725)
        self.assertEqual(log.heartbeat().text, "MAA 运行中（已运行 1:02:05）")


class MaaSchedulerLoggingTests(unittest.TestCase):
    """on_maa_callback 与 report_maa_progress 在调度器上的接线。"""

    def setUp(self):
        self.clock = FakeClock()
        self.solver = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
        self.solver.maa_callback = MaaCallbackLog(clock=self.clock)
        self.original_stage_drop = getattr(base_schedule, "stage_drop", None)
        base_schedule.stage_drop = {"details": [], "summary": {}}
        self.addCleanup(self._restore_stage_drop)

    def _restore_stage_drop(self):
        if self.original_stage_drop is None:
            del base_schedule.stage_drop
        else:
            base_schedule.stage_drop = self.original_stage_drop

    def test_on_maa_callback_keeps_accumulating_stage_drops(self):
        drops = [{"itemName": "源岩", "quantity": 1}]
        stats = [{"itemName": "源岩", "quantity": 1, "addQuantity": 1}]
        with self.assertLogs(LOG_NAME, level="INFO") as captured:
            self.solver.on_maa_callback(
                20003,
                payload(
                    what="StageDrops",
                    taskchain="Fight",
                    details={
                        "drops": drops,
                        "stats": stats,
                        "stage": {"stageCode": "1-7"},
                    },
                ),
                None,
            )
        self.assertEqual(base_schedule.stage_drop["details"], [drops])
        self.assertEqual(base_schedule.stage_drop["summary"], stats)
        self.assertIn("1-7 作战结束，掉落：源岩×1", captured.output[0])

    def test_on_maa_callback_survives_an_empty_payload(self):
        with self.assertLogs(LOG_NAME, level="DEBUG"):
            self.solver.on_maa_callback(0, None, None)

    def test_on_maa_callback_ignores_malformed_stage_drops(self):
        """[INV-MAA-01]：畸形掉落负载不得抛错，也不得污染掉落统计。"""
        for raw in (
            payload(what="StageDrops"),
            payload(what="StageDrops", details="broken"),
            payload(what="StageDrops", details={"drops": 7, "stats": 7}),
            payload(what="StageDrops", details={"drops": None, "stats": None}),
            payload(what="StageDrops", details={"drops": [7], "stats": "x"}),
        ):
            with self.subTest(raw=raw):
                with self.assertLogs(LOG_NAME, level="DEBUG"):
                    self.solver.on_maa_callback(20003, raw, None)
        self.assertEqual(base_schedule.stage_drop["details"], [])
        self.assertEqual(base_schedule.stage_drop["summary"], {})

    def test_on_maa_callback_accumulates_only_well_formed_stage_drops(self):
        drops = [{"itemName": "源岩", "quantity": 1}]
        with self.assertLogs(LOG_NAME, level="DEBUG"):
            self.solver.on_maa_callback(
                20003, payload(what="StageDrops", details={"drops": drops}), None
            )
            self.solver.on_maa_callback(
                20003, payload(what="StageDrops", details={"drops": None}), None
            )
        self.assertEqual(base_schedule.stage_drop["details"], [drops])

    def test_reset_stage_drop_clears_both_buckets(self):
        base_schedule.stage_drop["details"].append([{"itemName": "源岩"}])
        base_schedule.stage_drop["summary"] = [{"itemName": "源岩"}]
        base_schedule.reset_stage_drop()
        self.assertEqual(base_schedule.stage_drop, {"details": [], "summary": {}})

    def test_on_maa_callback_is_inert_without_a_callback_log(self):
        self.solver.maa_callback = None
        with self.assertNoLogs(LOG_NAME, level="INFO"):
            self.solver.on_maa_callback(10001, payload(taskchain="Fight"), None)

    def test_report_maa_progress_is_inert_without_a_callback_log(self):
        self.solver.maa_callback = None
        with self.assertNoLogs(LOG_NAME, level="INFO"):
            self.solver.report_maa_progress()

    def test_report_maa_progress_emits_the_heartbeat_once_per_interval(self):
        self.solver.on_maa_callback(10001, payload(taskchain="Fight"), None)
        self.clock.advance(60)
        with self.assertLogs(LOG_NAME, level="INFO") as captured:
            self.solver.report_maa_progress()
            self.solver.report_maa_progress()
        self.assertEqual(len(captured.output), 1)
        self.assertIn("MAA 运行中：理智作战", captured.output[0])

    def test_verified_asst_routes_callbacks_through_the_reporting_method(self):
        """VerifiedAsst 把消费者包成 CFUNCTYPE；改装成实例方法后仍须能回调。"""
        consumer = MagicMock()
        with patch(
            "arknights_mower.utils.maa_backup.VerifiedAsst.__init__",
            lambda instance, *args, **kwargs: None,
        ):
            from arknights_mower.utils.maa_backup import VerifiedAsst

            instance = VerifiedAsst.__new__(VerifiedAsst)
            instance._consumer = self.solver.on_maa_callback
            instance._outcome = MagicMock()
            with self.assertLogs(LOG_NAME, level="INFO") as captured:
                VerifiedAsst._message(instance, 10001, payload(taskchain="Fight"), None)
        consumer.assert_not_called()
        self.assertIn("开始任务：理智作战", captured.output[0])


class MaaInitializeCallbackTests(unittest.TestCase):
    def test_initialize_maa_starts_a_fresh_callback_log_and_routes_events(self):
        with tempfile.TemporaryDirectory() as maa_path:
            solver = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
            solver.device = SimpleNamespace(
                client=SimpleNamespace(adb_bin="sdk-adb", device_id="USB-123")
            )
            asst = MagicMock()
            asst.return_value.connect.return_value = True
            response = MagicMock()
            response.__enter__.return_value.content = b"{}"
            conf = SimpleNamespace(
                maa_path=maa_path,
                maa_adb_path="",
                maa_touch_option="maatouch",
                maa_conn_preset="General",
            )
            with (
                patch.object(base_schedule.config, "conf", conf),
                patch.dict(base_schedule.os.environ, {"MOWER_ANDROID": "0"}),
                patch.object(sys, "path", list(sys.path)),
                patch.dict(
                    sys.modules,
                    {
                        "asst": MagicMock(),
                        "asst.asst": SimpleNamespace(Asst=asst),
                        "asst.utils": SimpleNamespace(
                            InstanceOptionType=SimpleNamespace(touch_type=2)
                        ),
                    },
                ),
                patch.object(base_schedule.requests, "get", return_value=response),
                # initialize_maa 在连接前会确认共享 ADB 服务；本用例只验证回调装配。
                patch.object(base_schedule, "guard_adb"),
            ):
                solver.initialize_maa()
                self.addCleanup(solver.MAA.stop)
                self.assertIsInstance(solver.maa_callback, MaaCallbackLog)
                with self.assertLogs(LOG_NAME, level="INFO") as captured:
                    solver.MAA._message(10001, payload(taskchain="Award"), None)
            self.assertIn("开始任务：领取奖励", captured.output[0])


if __name__ == "__main__":
    unittest.main()
