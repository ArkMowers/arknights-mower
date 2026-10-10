import json
import sys
import unittest
from unittest.mock import MagicMock, call, patch

# base_schedule 的导入链会初始化森空岛模块；上报测试不依赖网络。
sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

import arknights_mower.solvers.base_schedule as base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils import maa_report  # noqa: E402
from arknights_mower.utils.maa_callback import MaaCallbackLog  # noqa: E402

LOG_NAME = "arknights_mower.utils.log"

PENGUIN_URL = "https://penguin-stats.io/PenguinStats/api/v2/report"
PENGUIN_BACKUP_URL = "https://penguin-stats.cn/PenguinStats/api/v2/report"


def payload(**fields) -> bytes:
    return json.dumps(fields, ensure_ascii=False).encode("utf-8")


def response(status: int) -> MagicMock:
    """响应替身：上传代码用 with 语句持有它，因此必须支持上下文管理器。"""
    item = MagicMock()
    item.status_code = status
    item.__enter__ = MagicMock(return_value=item)
    item.__exit__ = MagicMock(return_value=False)
    return item


class InlineThread:
    """同步执行目标函数，让上传在测试中无需等待真实线程。"""

    def __init__(self, target=None, args=(), **kwargs):
        self._target = target
        self._args = args

    def start(self):
        self._target(*self._args)


def penguin_request(**overrides):
    details = {
        "subtask": "ReportToPenguinStats",
        "url": PENGUIN_URL,
        "headers": {"User-Agent": "MaaAssistantArknights/6.18.0"},
        "body": '{"drops":[],"server":"CN"}',
        "uuid": "3176499b735f1245",
    }
    details.update(overrides)
    return details


class UploadReportTests(unittest.TestCase):
    def setUp(self):
        thread_patch = patch.object(maa_report.threading, "Thread", InlineThread)
        thread_patch.start()
        self.addCleanup(thread_patch.stop)
        sleep_patch = patch.object(maa_report.time, "sleep")
        self.sleep = sleep_patch.start()
        self.addCleanup(sleep_patch.stop)
        # 非企鹅目标的首次失败会升级为告警，用例之间必须清掉这个一次性标记。
        maa_report._report_failure_reported = False
        self.addCleanup(setattr, maa_report, "_report_failure_reported", False)

    def test_request_without_url_is_refused(self):
        for details in (
            penguin_request(url=""),
            penguin_request(url=None),
            penguin_request(url=7),
            {"body": "x"},
        ):
            with self.subTest(details=details):
                with self.assertLogs(LOG_NAME, level="WARNING") as captured:
                    self.assertFalse(maa_report.upload_report(details))
                self.assertIn("缺少 url", captured.output[0])

    def test_request_without_body_is_refused(self):
        for details in (
            penguin_request(body=""),
            penguin_request(body=None),
            penguin_request(body={"a": 1}),
        ):
            with self.subTest(details=details):
                with self.assertLogs(LOG_NAME, level="WARNING") as captured:
                    self.assertFalse(maa_report.upload_report(details))
                self.assertIn("缺少 body", captured.output[0])

    def test_refused_payload_never_posts(self):
        with patch.object(maa_report.requests, "post") as post:
            maa_report.upload_report(penguin_request(url=""))
            maa_report.upload_report(penguin_request(body=""))
        post.assert_not_called()

    def test_post_uses_the_prepared_request(self):
        with (
            patch.object(
                maa_report.requests, "post", return_value=response(200)
            ) as post,
            self.assertLogs(LOG_NAME, level="INFO") as captured,
        ):
            self.assertTrue(maa_report.upload_report(penguin_request()))
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], PENGUIN_URL)
        self.assertEqual(post.call_args.kwargs["data"], b'{"drops":[],"server":"CN"}')
        self.assertEqual(post.call_args.kwargs["timeout"], maa_report.REPORT_TIMEOUT)
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(headers["accept"], "application/json")
        self.assertEqual(headers["User-Agent"], "MaaAssistantArknights/6.18.0")
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(maa_report.REPORT_TIMEOUT, 15)
        self.assertIn("企鹅物流上报成功", captured.output[0])

    def test_payload_content_type_wins_over_the_default(self):
        # HTTP 头部名不区分大小写；非规范拼写同样必须压过默认值。
        for spelling in ("Content-Type", "content-type", "CONTENT-TYPE"):
            with self.subTest(spelling=spelling):
                with patch.object(
                    maa_report.requests, "post", return_value=response(200)
                ) as post:
                    maa_report.upload_report(
                        penguin_request(headers={spelling: "application/json"})
                    )
                headers = post.call_args.kwargs["headers"]
                self.assertEqual(headers["Content-Type"], "application/json")
                self.assertEqual(headers["accept"], "application/json")

    def test_unparsable_url_is_refused_before_starting_a_thread(self):
        with (
            patch.object(maa_report.threading, "Thread") as thread,
            self.assertLogs(LOG_NAME, level="WARNING") as captured,
        ):
            self.assertFalse(maa_report.upload_report(penguin_request(url="http://")))
        thread.assert_not_called()
        self.assertIn("上报地址无法解析", captured.output[0])

    def test_thread_creation_failure_is_reported_not_raised(self):
        """线程资源耗尽时 upload_report 只回报 False，不把异常抛给回调线程。"""
        with (
            patch.object(
                maa_report.threading.Thread, "start", side_effect=RuntimeError("limit")
            ),
            self.assertLogs(LOG_NAME, level="WARNING") as captured,
        ):
            self.assertFalse(maa_report.upload_report(penguin_request()))
        self.assertIn("上报线程创建失败", captured.output[0])

    def test_worker_exception_becomes_a_log_line(self):
        """线程内逃逸的异常不进 logger，因此 _post 必须整体兜住。"""
        with (
            patch.object(
                maa_report,
                "_attempt_domain",
                side_effect=ValueError("boom"),
            ) as attempt,
            self.assertLogs(LOG_NAME, level="WARNING") as captured,
        ):
            self.assertTrue(maa_report.upload_report(penguin_request()))
        attempt.assert_called_once()
        self.assertIn("上报异常：boom", captured.output[0])

    def test_missing_headers_mapping_is_tolerated(self):
        for headers in (None, "not-a-mapping", 7):
            with self.subTest(headers=headers):
                with patch.object(
                    maa_report.requests, "post", return_value=response(200)
                ) as post:
                    self.assertTrue(
                        maa_report.upload_report(penguin_request(headers=headers))
                    )
                self.assertEqual(
                    post.call_args.kwargs["headers"]["Accept"], "application/json"
                )

    def test_success_is_strictly_status_200(self):
        # 客户端只认 200；201/204 等同样按失败处理，因此还会走一轮备用域名。
        for status in (201, 202, 204, 302):
            with self.subTest(status=status):
                with patch.object(
                    maa_report.requests, "post", return_value=response(status)
                ) as post:
                    maa_report.upload_report(penguin_request())
                self.assertEqual(
                    [item.args[0] for item in post.call_args_list],
                    [PENGUIN_URL, PENGUIN_BACKUP_URL],
                )

    def test_server_fault_is_retried_with_backoff_then_given_up(self):
        with (
            patch.object(
                maa_report.requests, "post", return_value=response(503)
            ) as post,
            self.assertLogs(LOG_NAME, level="WARNING") as captured,
        ):
            maa_report.upload_report(penguin_request())
        # 主域名 3 次 + 备用域名 3 次
        self.assertEqual(post.call_count, 6)
        self.assertEqual(self.sleep.call_args_list[:2], [call(3.0), call(4.5)])
        self.assertIn("企鹅物流上报失败，已放弃本次上报", captured.output[-1])

    def test_client_fault_is_not_retried_within_a_domain(self):
        with patch.object(
            maa_report.requests, "post", return_value=response(403)
        ) as post:
            maa_report.upload_report(penguin_request())
        # 每个域名只试一次；4xx 不触发同域名重试。
        self.assertEqual(
            [item.args[0] for item in post.call_args_list],
            [PENGUIN_URL, PENGUIN_BACKUP_URL],
        )
        self.sleep.assert_not_called()

    def test_network_failure_aborts_the_domain(self):
        with (
            patch.object(
                maa_report.requests,
                "post",
                side_effect=maa_report.requests.Timeout("timed out"),
            ) as post,
            self.assertLogs(LOG_NAME, level="WARNING"),
        ):
            maa_report.upload_report(penguin_request())
        # 异常立即结束该域名，不重试；备用域名仍会试一次。
        self.assertEqual(
            [item.args[0] for item in post.call_args_list],
            [PENGUIN_URL, PENGUIN_BACKUP_URL],
        )
        self.sleep.assert_not_called()

    def test_penguin_falls_back_to_the_backup_domain(self):
        with (
            patch.object(
                maa_report.requests,
                "post",
                side_effect=[
                    response(500),
                    response(500),
                    response(500),
                    response(200),
                ],
            ) as post,
            self.assertLogs(LOG_NAME, level="INFO") as captured,
        ):
            maa_report.upload_report(penguin_request())
        self.assertEqual(
            [item.args[0] for item in post.call_args_list],
            [PENGUIN_URL] * 3 + [PENGUIN_BACKUP_URL],
        )
        self.assertIn("企鹅物流上报成功", captured.output[-1])

    def test_yituliu_never_uses_the_backup_domain(self):
        with patch.object(
            maa_report.requests, "post", return_value=response(500)
        ) as post:
            maa_report.upload_report(
                penguin_request(subtask="ReportToYituliu", url=PENGUIN_URL)
            )
        self.assertTrue(
            all(item.args[0] == PENGUIN_URL for item in post.call_args_list)
        )

    def test_backup_domain_requires_the_penguin_url(self):
        other = "https://example.test/report"
        with patch.object(
            maa_report.requests, "post", return_value=response(500)
        ) as post:
            maa_report.upload_report(penguin_request(url=other))
        self.assertTrue(all(item.args[0] == other for item in post.call_args_list))

    def test_backup_domain_matches_the_host_not_a_substring(self):
        # 域名出现在查询串里不构成企鹅域名；替换只认主机名。
        embedded = "https://evil.test/collect?ref=https://penguin-stats.io/x"
        with patch.object(
            maa_report.requests, "post", return_value=response(500)
        ) as post:
            maa_report.upload_report(penguin_request(url=embedded))
        self.assertTrue(all(item.args[0] == embedded for item in post.call_args_list))

    def test_yituliu_first_failure_is_visible_once(self):
        # 与客户端一致保持安静，但首次失败升到告警，否则界面日志里没有任何线索。
        with (
            patch.object(maa_report.requests, "post", return_value=response(500)),
            self.assertLogs(LOG_NAME, level="WARNING") as captured,
        ):
            maa_report.upload_report(
                penguin_request(subtask="ReportToYituliu", url=PENGUIN_URL)
            )
        self.assertIn("一图流上报失败，已放弃本次上报", captured.output[-1])

    def test_yituliu_later_failures_stay_off_the_warning_level(self):
        maa_report._report_failure_reported = True
        with (
            patch.object(maa_report.requests, "post", return_value=response(500)),
            self.assertNoLogs(LOG_NAME, level="WARNING"),
            self.assertLogs(LOG_NAME, level="DEBUG") as captured,
        ):
            maa_report.upload_report(
                penguin_request(subtask="ReportToYituliu", url=PENGUIN_URL)
            )
        self.assertIn("一图流上报失败，已放弃本次上报", captured.output[-1])

    def test_yituliu_success_uses_its_own_label(self):
        with (
            patch.object(maa_report.requests, "post", return_value=response(200)),
            self.assertLogs(LOG_NAME, level="INFO") as captured,
        ):
            maa_report.upload_report(
                penguin_request(subtask="ReportToYituliu", url=PENGUIN_URL)
            )
        self.assertIn("一图流上报成功", captured.output[-1])

    def test_unknown_subtask_falls_back_to_its_own_name(self):
        self.assertEqual(
            maa_report.report_label("SomeFutureReport"), "SomeFutureReport"
        )
        self.assertEqual(maa_report.report_label(None), "MAA")
        self.assertEqual(maa_report.report_label(7), "MAA")


class SchedulerReportWiringTests(unittest.TestCase):
    """on_maa_callback 把上报请求交给上传模块。"""

    def setUp(self):
        self.solver = BaseSchedulerSolver.__new__(BaseSchedulerSolver)
        self.solver.maa_callback = MaaCallbackLog(clock=lambda: 0.0)

    def test_report_request_is_uploaded(self):
        with patch.object(base_schedule, "upload_report") as upload:
            self.solver.on_maa_callback(30000, payload(**penguin_request()), None)
        upload.assert_called_once()
        self.assertEqual(upload.call_args.args[0]["subtask"], "ReportToPenguinStats")

    def test_other_messages_are_not_uploaded(self):
        for message in (20003, 10001, 0, 20001):
            with self.subTest(message=message):
                with patch.object(base_schedule, "upload_report") as upload:
                    self.solver.on_maa_callback(
                        message, payload(taskchain="Fight"), None
                    )
                upload.assert_not_called()

    def test_report_request_still_produces_no_log_line(self):
        # 上报请求本身不产出进度行，也没有回落成异常。
        with (
            patch.object(base_schedule, "upload_report"),
            self.assertNoLogs(LOG_NAME, level="INFO"),
            self.assertLogs(LOG_NAME, level="DEBUG"),
        ):
            self.solver.on_maa_callback(30000, payload(**penguin_request()), None)

    def test_upload_failure_never_escapes_the_callback(self):
        """[INV-MAA-01]：上报抛错时回调只记一行，不得把异常抛回 MAA。"""
        with (
            patch.object(
                base_schedule, "upload_report", side_effect=RuntimeError("no threads")
            ),
            self.assertLogs(LOG_NAME, level="WARNING") as captured,
        ):
            self.solver.on_maa_callback(30000, payload(**penguin_request()), None)
        self.assertIn("MAA 上报请求处理失败", captured.output[0])


if __name__ == "__main__":
    unittest.main()
