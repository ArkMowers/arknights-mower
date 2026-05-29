import importlib
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

with patch.dict("sys.modules", {"colorlog": MagicMock(), "requests": MagicMock()}):
    missed_order_mod = importlib.import_module("arknights_mower.agent.missed_order")
    analyze_mod = importlib.import_module(
        "arknights_mower.agent.tools.analyze_missed_order"
    )


class TestMissedOrderTool(unittest.TestCase):
    LOCAL_TZ = timezone(timedelta(hours=-8))

    @classmethod
    def _ts(cls, local_time: str) -> int:
        return int(
            datetime.strptime(local_time, "%Y-%m-%d %H:%M:%S")
            .replace(tzinfo=cls.LOCAL_TZ)
            .timestamp()
        )

    @classmethod
    def _log_row(
        cls,
        log_local_time: str,
        level: str,
        task: str = "{}",
        message: str = "",
    ) -> dict:
        return {
            "log_utc_time": cls._ts(log_local_time),
            "log_local_time": log_local_time,
            "level": level,
            "task": task,
            "message": message,
        }

    def test_analyze_by_order_current_task_miss(self):
        event_row = self._log_row(
            "2026-02-18 22:11:06",
            "ERROR",
            message=f"{analyze_mod.CURRENT_ORDER_MISS_KEYWORD}!",
        )
        rows = [
            self._log_row(
                "2026-02-18 21:57:06",
                "INFO",
                task=(
                    "SchedulerTask(time='2026-02-18 22:06:22',task_plan={'room_3_1': "
                    "['Current']},task_type=TaskTypes.RUN_ORDER,meta_data='room_3_1',"
                    "adjusted=False)"
                ),
                message="current room_3_1 run order",
            ),
            self._log_row(
                "2026-02-18 22:11:06",
                "ERROR",
                message=f"{analyze_mod.CURRENT_ORDER_MISS_KEYWORD}!",
            ),
        ]
        runtime_result = {
            "files": ["runtime.log.2026-02-18_22"],
            "entries": [
                {
                    "time": "2026-02-18 22:11:19",
                    "file": "runtime.log.2026-02-18_22",
                    "message": (
                        "2026-02-18 22:11:19 INFO "
                        f"{analyze_mod.CURRENT_ORDER_MISS_KEYWORD}"
                    ),
                }
            ],
        }
        with (
            patch.object(analyze_mod, "_connect", return_value=MagicMock()),
            patch.object(analyze_mod, "_get_run_order_delay_minutes", return_value=4.0),
            patch.object(
                analyze_mod, "fetch_missed_event_rows", return_value=[event_row]
            ),
            patch.object(
                analyze_mod, "fetch_logs_by_utc_window", side_effect=[rows, rows]
            ),
            patch.object(
                analyze_mod, "scan_runtime_info_logs", return_value=runtime_result
            ),
        ):
            result = analyze_mod.analyze_missed_order_by_order(
                order_time="2026-02-18 22:06:22",
                signal_type="current_task_miss",
                log_event_time=event_row["log_local_time"],
                log_event_ts=event_row["log_utc_time"],
                room="room_3_1",
            )

        self.assertEqual(result["signal_type"], "current_task_miss")
        self.assertEqual(result["target_task_time"], "2026-02-18 22:06:22")
        self.assertEqual(result["current_task_time"], "2026-02-18 22:06:22")
        self.assertEqual(result["detected_time"], "2026-02-18 22:11:19")
        self.assertEqual(result["room"], "room_3_1")

    def test_analyze_by_order_previous_order_miss(self):
        event_row = self._log_row(
            "2026-02-18 23:40:00",
            "ERROR",
            message=f"{analyze_mod.PREVIOUS_ORDER_MISS_KEYWORD}!",
        )
        rows = [
            self._log_row(
                "2026-02-18 23:16:20",
                "INFO",
                task=(
                    "SchedulerTask(time='2026-02-18 20:00:00',task_plan={'room_3_1': "
                    "['Current']},task_type=TaskTypes.RUN_ORDER,meta_data='room_3_1',"
                    "adjusted=False)"
                ),
                message="previous room_3_1 run order",
            ),
            self._log_row(
                "2026-02-18 23:22:11",
                "INFO",
                task=(
                    "SchedulerTask(time='2026-02-18 22:06:22',task_plan={'room_3_1': "
                    "['Current']},task_type=TaskTypes.RUN_ORDER,meta_data='room_3_1',"
                    "adjusted=False)"
                ),
                message="current room_3_1 run order",
            ),
            self._log_row(
                "2026-02-18 23:40:00",
                "ERROR",
                message=f"{analyze_mod.PREVIOUS_ORDER_MISS_KEYWORD}!",
            ),
        ]
        with (
            patch.object(analyze_mod, "_connect", return_value=MagicMock()),
            patch.object(analyze_mod, "_get_run_order_delay_minutes", return_value=4.0),
            patch.object(
                analyze_mod, "fetch_missed_event_rows", return_value=[event_row]
            ),
            patch.object(
                analyze_mod, "fetch_logs_by_utc_window", side_effect=[rows, rows]
            ),
            patch.object(
                analyze_mod,
                "scan_runtime_info_logs",
                return_value={"files": [], "entries": []},
            ),
        ):
            result = analyze_mod.analyze_missed_order_by_order(
                order_time="2026-02-18 20:00:00",
                signal_type="previous_order_miss",
                log_event_time=event_row["log_local_time"],
                log_event_ts=event_row["log_utc_time"],
                room="room_3_1",
            )

        self.assertEqual(result["signal_type"], "previous_order_miss")
        self.assertEqual(result["target_task_time"], "2026-02-18 20:00:00")
        self.assertEqual(result["current_task_time"], "2026-02-18 22:06:22")
        self.assertEqual(result["previous_task_time"], "2026-02-18 20:00:00")

    def test_analyze_by_time_matches_by_task_time(self):
        rows = [
            self._log_row(
                "2026-02-18 21:57:06",
                "INFO",
                task=(
                    "SchedulerTask(time='2026-02-18 22:06:22',task_plan={'room_3_1': "
                    "['Current']},task_type=TaskTypes.RUN_ORDER,meta_data='room_3_1',"
                    "adjusted=False)"
                ),
            ),
            self._log_row(
                "2026-02-18 22:11:06",
                "ERROR",
                message=f"{analyze_mod.CURRENT_ORDER_MISS_KEYWORD}!",
            ),
        ]
        with (
            patch.object(analyze_mod, "_connect", return_value=MagicMock()),
            patch.object(analyze_mod, "_get_run_order_delay_minutes", return_value=4.0),
            patch.object(
                analyze_mod,
                "find_matching_event_by_time",
                return_value=self._log_row(
                    "2026-02-18 22:11:06",
                    "ERROR",
                    message=f"{analyze_mod.CURRENT_ORDER_MISS_KEYWORD}!",
                ),
            ),
            patch.object(analyze_mod, "fetch_logs_by_utc_window", return_value=rows),
            patch.object(
                analyze_mod,
                "scan_runtime_info_logs",
                return_value={"files": [], "entries": []},
            ),
        ):
            result = analyze_mod.analyze_missed_order_by_time("2026-02-18 22:06:22")

        self.assertEqual(result["target_task_time"], "2026-02-18 22:06:22")
        self.assertEqual(result["room"], "room_3_1")

    def test_list_orders_mode(self):
        with (
            patch.object(
                analyze_mod,
                "fetch_missed_event_rows",
                return_value=[
                    self._log_row(
                        "2026-02-18 22:11:06",
                        "ERROR",
                        message=f"{analyze_mod.CURRENT_ORDER_MISS_KEYWORD}!",
                    )
                ],
            ),
            patch.object(
                analyze_mod,
                "resolve_event_context",
                return_value={
                    "signal_type": "current_task_miss",
                    "target_task": {"task_time": "2026-02-18 22:06:22"},
                    "current_task": {"task_time": "2026-02-18 22:06:22"},
                    "previous_task": None,
                    "room": "room_3_1",
                },
            ) as mock_resolve_context,
        ):
            payload = json.loads(analyze_mod.analyze_missed_order(mode="list_orders"))

        mock_resolve_context.assert_called_once()
        self.assertEqual(payload["mode"], "list_orders")
        self.assertTrue(payload["has_orders"])
        self.assertEqual(payload["orders"][0]["signal_type"], "current_task_miss")
        self.assertEqual(payload["orders"][0]["task_time"], "2026-02-18 22:06:22")

    def test_format_report_uses_new_fields(self):
        result = {
            "signal_type": "current_task_miss",
            "room": "room_3_1",
            "target_task_time": "2026-02-18 22:06:22",
            "current_task_time": "2026-02-18 22:06:22",
            "previous_task_time": None,
            "detected_time": "2026-02-18 22:11:19",
            "db_query_window": {"start": 1, "end": 2},
            "runtime_window": {
                "start": "2026-02-18 22:01:22",
                "end": "2026-02-18 22:11:19",
            },
            "timeline_logs": [],
            "runtime_info_logs": [],
            "candidate_reasons": [
                {
                    "type": "execution_failed",
                    "confidence_hint": "medium",
                    "supported_evidence": ["database timeline contains an ERROR log"],
                }
            ],
        }
        text = missed_order_mod.format_missed_order_task_records(result)
        self.assertIn("目标任务时间：2026-02-18 22:06:22", text)
        self.assertIn("检测到漏单时间：2026-02-18 22:11:19", text)
        self.assertNotIn("A/B/C", text)

    def test_list_format_uses_new_fields(self):
        text = missed_order_mod.format_missed_order_list(
            [
                {
                    "index": 1,
                    "log_local_time": "2026-02-18 22:11:06",
                    "level": "ERROR",
                    "message": f"{analyze_mod.CURRENT_ORDER_MISS_KEYWORD}!",
                    "task_time": "2026-02-18 22:06:22",
                    "room": "room_3_1",
                }
            ]
        )
        self.assertIn(
            "事件=2026-02-18 22:11:06 | 任务=2026-02-18 22:06:22 | 房间=room_3_1",
            text,
        )

    def test_summary_fallback_uses_new_fields(self):
        text = missed_order_mod.summarize_missed_order_result(
            {
                "target_task_time": "2026-02-18 22:06:22",
                "current_task_time": "2026-02-18 22:06:22",
                "previous_task_time": None,
                "detected_time": "2026-02-18 22:11:19",
                "room": "room_3_1",
                "candidate_reasons": [{"type": "execution_failed"}],
            },
            llm=None,
        )
        self.assertIn("目标任务时间：2026-02-18 22:06:22", text)
        self.assertNotIn("A/B/C", text)

    def test_build_candidate_reasons_detects_wait_run_order_as_session_interrupt(self):
        runtime_logs = [
            {
                "time": "2026-04-08 08:46:36",
                "file": "runtime.log.2026-04-08_08",
                "message": "2026-04-08 08:46:36,623 INFO tap_confirm: 等待跑单 43.7 秒",
            }
        ]

        reasons = analyze_mod.build_candidate_reasons(
            "current_task_miss",
            timeline_logs=[],
            runtime_info_logs=runtime_logs,
            target_task={"task_time": "2026-04-08 08:42:36"},
        )

        session_reason = next(
            item
            for item in reasons
            if item["type"] == "session_interrupted_during_run_order"
        )
        self.assertEqual(session_reason["confidence_hint"], "medium")
        self.assertIn("等待跑单", session_reason["supported_evidence"][0])

    def test_build_candidate_reasons_promotes_session_interrupt_when_game_exits(self):
        runtime_logs = [
            {
                "time": "2026-04-08 08:46:36",
                "file": "runtime.log.2026-04-08_08",
                "message": "2026-04-08 08:46:36,623 INFO tap_confirm: 等待跑单 43.7 秒",
            },
            {
                "time": "2026-04-08 08:47:34",
                "file": "runtime.log.2026-04-08_08",
                "message": "2026-04-08 08:47:34,983 INFO back_to_infrastructure: 场景图导航：back_to_infrastructure",
            },
            {
                "time": "2026-04-08 08:47:35",
                "file": "runtime.log.2026-04-08_08",
                "message": "2026-04-08 08:47:35,557 INFO exit: 退出游戏",
            },
        ]

        reasons = analyze_mod.build_candidate_reasons(
            "current_task_miss",
            timeline_logs=[],
            runtime_info_logs=runtime_logs,
            target_task={"task_time": "2026-04-08 08:42:36"},
        )

        session_reason = next(
            item
            for item in reasons
            if item["type"] == "session_interrupted_during_run_order"
        )
        self.assertEqual(session_reason["confidence_hint"], "high")
        self.assertIn(
            "场景异常/回基建/退出游戏线索", session_reason["supported_evidence"][1]
        )

    def test_build_candidate_reasons_promotes_session_interrupt_on_unknown_scene(self):
        runtime_logs = [
            {
                "time": "2026-04-08 08:46:36",
                "file": "runtime.log.2026-04-08_08",
                "message": "2026-04-08 08:46:36,623 INFO tap_confirm: 等待跑单 43.7 秒",
            },
            {
                "time": "2026-04-08 08:46:40",
                "file": "runtime.log.2026-04-08_08",
                "message": "2026-04-08 08:46:40,100 INFO scene_graph_navigation abort: unknown scene persists current=UNKNOWN",
            },
        ]

        reasons = analyze_mod.build_candidate_reasons(
            "current_task_miss",
            timeline_logs=[],
            runtime_info_logs=runtime_logs,
            target_task={"task_time": "2026-04-08 08:42:36"},
        )

        session_reason = next(
            item
            for item in reasons
            if item["type"] == "session_interrupted_during_run_order"
        )
        self.assertEqual(session_reason["confidence_hint"], "high")

    def test_build_candidate_reasons_does_not_infer_session_interrupt_from_exit_alone(
        self,
    ):
        runtime_logs = [
            {
                "time": "2026-04-08 08:47:35",
                "file": "runtime.log.2026-04-08_08",
                "message": "2026-04-08 08:47:35,557 INFO exit: 退出游戏",
            }
        ]

        reasons = analyze_mod.build_candidate_reasons(
            "current_task_miss",
            timeline_logs=[],
            runtime_info_logs=runtime_logs,
            target_task={"task_time": "2026-04-08 08:42:36"},
        )

        self.assertFalse(
            any(
                item["type"] == "session_interrupted_during_run_order"
                for item in reasons
            )
        )


if __name__ == "__main__":
    unittest.main()
