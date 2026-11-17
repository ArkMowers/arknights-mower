"""Offline checks for callable examples and model-visible tool arguments."""

import json
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from arknights_mower.agent import agent
from arknights_mower.agent.tools import call_db as db_tool
from arknights_mower.agent.tools import faq, mastery_plan, submit_issue
from arknights_mower.solvers.record import _DB_TABLE_STMTS
from arknights_mower.utils import performance
from arknights_mower.utils.config.conf import RIICPart


class AIPromptContractTests(unittest.TestCase):
    def test_performance_guidance_matches_the_runtime_starting_mode(self):
        guide = (
            Path(__file__).resolve().parents[2] / "ui/Mower入门指北.html"
        ).read_text(encoding="utf-8")
        answer = faq.get_faq("设备性能适配如何选择")
        for platform in ("android", "darwin", "windows", "linux"):
            with (
                self.subTest(platform=platform),
                patch.dict("os.environ", {"MOWER_ANDROID": "0"}),
                patch.object(performance, "__system__", platform),
            ):
                profile = performance.effective_performance_profile(RIICPart())
                self.assertEqual(profile.mode, "xhigh")
                baseline = "所有平台均从极高开始"
                self.assertIn(baseline, answer)
                self.assertIn(baseline, guide)

    def test_legacy_downloader_questions_use_current_software_update_entry(self):
        for question in ("Mower下载器报错怎么更新", "下崽器打不开", "更新器报错"):
            with self.subTest(question=question):
                result = faq.get_faq(question)
                self.assertIn("Mower 设置 → 软件更新", result)
                self.assertIn("不再使用独立的 Mower 下载器", result)
                self.assertNotIn("群文件下载最新的更新器", result)

    def test_faq_matching_handles_latin_case_and_current_task_switches(self):
        self.assertEqual(faq.get_faq("MAA缺少DLL"), faq.get_faq("maa缺少dll"))
        self.assertIn("大型任务由独立开关", faq.get_faq("生息演算需要开启刷理智吗"))
        self.assertIn("不需要为此开启一个空刷理智计划", faq.get_faq("生息演算"))
        result = faq.get_faq("心情报表不显示想清理")
        self.assertIn("数据库管理", result)
        self.assertIn("不要直接删除 data.db", result)

    def test_faq_sources_and_published_help_targets_exist(self):
        root = Path(__file__).resolve().parents[2]
        for item in faq.FAQ_LIST:
            self.assertTrue(item["sources"], item["question"])
            for source in item["sources"]:
                self.assertTrue((root / source).is_file(), source)

        class HelpParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids = []
                self.links = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if "id" in attrs:
                    self.ids.append(attrs["id"])
                if tag == "a" and "href" in attrs:
                    self.links.append(attrs["href"])

        parser = HelpParser()
        guide = (root / "ui/Mower入门指北.html").read_text(encoding="utf-8")
        parser.feed(guide)
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        for link in parser.links:
            if link.startswith("#"):
                self.assertIn(link[1:], parser.ids, link)
        sheet = "https://docs.qq.com/sheet/DUEJ6UWN5VFVRU0dG?tab=BB08J2"
        self.assertIn(sheet, parser.links)
        self.assertIn(sheet, faq.get_faq("我要反馈问题"))
        self.assertIn(
            sheet,
            (root / "ui/src/components/Feedback.vue").read_text(encoding="utf-8"),
        )
        self.assertNotIn("new WebSocket", guide)

    def test_database_examples_run_against_actual_schema_and_limit_history(self):
        description = db_tool.call_db_tool_def["function"]["description"]
        queries = re.findall(r"示例查询: (SELECT .*?);", description)
        self.assertEqual(len(queries), 3)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.db"
            with closing(sqlite3.connect(path)) as conn, conn:
                for statement in _DB_TABLE_STMTS:
                    conn.execute(statement)
                conn.executemany(
                    "INSERT INTO agent_action "
                    "(name, agent_current_room, current_room, current_time) "
                    "VALUES (?, ?, ?, ?)",
                    [
                        ("已入宿", "room_1_1", "dorm_1", "2026-10-09 10:00:00"),
                        ("已离宿", "dorm_1", "room_1_1", "2026-10-09 11:00:00"),
                    ],
                )
                conn.executemany(
                    "INSERT INTO trading_history (time, type) VALUES (?, '漏单')",
                    [(value,) for value in range(20)],
                )
                conn.executemany(
                    "INSERT INTO log (time, level, message) VALUES (?, 'ERROR', ?)",
                    [(value, f"报错{value}") for value in range(20)],
                )
                actions = conn.execute(queries[0]).fetchall()
                self.assertEqual([row[0] for row in actions], ["已入宿"])
                for query in queries[1:]:
                    rows = conn.execute(query).fetchall()
                    self.assertEqual(len(rows), 10)
                    self.assertGreater(rows[0][0], rows[-1][0])
            with patch.object(db_tool, "get_path", return_value=path):
                result = db_tool.call_db(queries[0])
            self.assertIn("已入宿", result)
            self.assertNotIn("已离宿", result)

    def test_all_advertised_mastery_statuses_select_matching_records(self):
        statuses = mastery_plan.list_plans_tool_def["function"]["parameters"][
            "properties"
        ]["status_filter"]["enum"]
        plans = [
            {"char_id": f"char_{status}", "skill_index": 0, "status": status}
            for status in (
                "idle",
                "arranging",
                "training",
                "waiting_collect",
                "completed",
                "failed",
            )
        ]
        with patch.object(mastery_plan, "get_all_plans", return_value=plans):
            for plan in plans:
                with self.subTest(status=plan["status"]):
                    self.assertIn(plan["status"], statuses)
                    result = mastery_plan.list_plans(plan["status"])
                    self.assertIn(plan["char_id"], result)
                    for other in plans:
                        if other is not plan:
                            self.assertNotIn(other["char_id"], result)

    def test_bug_report_datetime_examples_are_accepted_without_sending_mail(self):
        properties = submit_issue.submit_issue_tool_def["function"]["parameters"][
            "properties"
        ]
        values = {}
        for key in ("start_time", "end_time"):
            match = re.search(r"e.g. '([^']+)'", properties[key]["description"])
            self.assertIsNotNone(match)
            values[key] = match.group(1)

        def collect(logs, screenshots, start, end, output, screenshot_times):
            path = output / "sample.log"
            path.write_text("离线示例日志", encoding="utf-8")
            return [path]

        with (
            patch.object(
                submit_issue,
                "collect_evidence",
                side_effect=collect,
            ),
            patch.object(
                submit_issue,
                "collect_feedback_records",
                return_value=([], {"tables": {}}),
            ),
            patch.object(
                submit_issue,
                "collect_feedback_state",
                return_value=([], {"tables": {}}),
            ),
            patch.object(submit_issue, "Email") as email,
        ):
            result = submit_issue.submit_issue("实际无法启动，期望正常启动", **values)
        self.assertEqual(result, "邮件发送成功！")
        email.assert_called_once()
        email.return_value.send.assert_called_once_with(
            ["354013233@qq.com", "1273725854@qq.com"]
        )
        start = datetime.strptime(values["start_time"], "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(values["end_time"], "%Y-%m-%d %H:%M:%S")
        self.assertGreater((end - start).total_seconds(), 0)
        self.assertLessEqual((end - start).total_seconds(), 900)

    def test_manual_loop_preserves_system_prompt_and_emits_tool_progress(self):
        from langchain_core.messages import AIMessage

        tool_call = {"name": "get_faq", "args": {"question": "启动失败"}, "id": "faq-1"}
        responses = [
            AIMessage(content="", tool_calls=[tool_call]),
            AIMessage(content="建议"),
        ]
        messages = agent._build_messages("启动失败")
        with (
            patch.object(agent, "build_llm") as build,
            patch.dict(agent.tool_func_map, {"get_faq": lambda **_: "FAQ记录"}),
        ):
            build.return_value.stream.side_effect = [
                iter([reply]) for reply in responses
            ]
            result = list(agent._run_manual_tool_loop(messages, "test-key"))
        self.assertEqual(result[-1], "建议")
        self.assertIn(agent.tool_message_map["get_faq"], result[0])
        self.assertEqual(
            messages[0].content, build.return_value.stream.call_args.args[0][0].content
        )
        self.assertEqual(
            build.return_value.stream.call_args.args[0][-1].content, "FAQ记录"
        )
        self.assertEqual(
            {tool["function"]["name"] for tool in agent.get_tools()},
            set(agent.tool_func_map),
        )

    def _riic_review_guidance(self):
        from arknights_mower.agent.tools import riic

        prompt = agent._build_messages("检查现有表零心情并给已拥有干员养成建议")[
            0
        ].content
        topic_schema = riic.get_riic_knowledge_tool_def["function"]["parameters"][
            "properties"
        ]["topic"]
        self.assertIn("plan_review", topic_schema["enum"])
        self.assertIn("mower_tutorial", topic_schema["enum"])
        self.assertNotIn("plan_generation", topic_schema["enum"])
        with patch.object(
            riic,
            "load_skill_snapshot",
            return_value={
                "has_data": False,
                "message": "离线测试，无账户资料",
                "operators": [],
            },
        ):
            response = json.loads(
                agent.tool_func_map["get_riic_knowledge"](topic="plan_review")
            )
        self.assertEqual(response["topic"], "plan_review")
        return prompt, response["guide"]

    def test_existing_plan_review_scope_reaches_model_and_registered_tool(self):
        for text in self._riic_review_guidance():
            with self.subTest(
                source="prompt" if "工作范围是现有" in text else "knowledge"
            ):
                self.assertIn("不从零生成排班", text)
                self.assertIn("不为提高收益擅自更换布局", text)
                self.assertIn("原表", text)
                self.assertIn("最小修改", text)
                self.assertIn("normal_plan_issues", text)
                self.assertIn("mower_tutorial", text)
                self.assertIn("get_faq", text)
                self.assertIn("快照优先", text)
                self.assertIn("省略", text)
                self.assertIn("局部修改也", text)
                self.assertIn("清空被修改房间的旧绑定", text)
                self.assertIn("Mower 入门指北", text)
                self.assertIn("group_bindings", text)
                self.assertIn("不删除原表副表", text)
                self.assertIn("不声称副表已验证", text)
                self.assertIn("unchecked", text)

    def test_review_guidance_separates_actual_growth_identity_and_hypotheses(self):
        for text in self._riic_review_guidance():
            with self.subTest(
                source="prompt" if "工作范围是现有" in text else "knowledge"
            ):
                self.assertIn("本人技能与身份挂件分开判断", text)
                self.assertIn("目标练度只是假设", text)
                self.assertIn("不能作为实际roster_overrides", text.replace(" ", ""))
                self.assertIn("写回BOX", text)
                self.assertIn("实际练度", text)
                self.assertIn("未拥有干员", text)
                self.assertIn("成本", text)
                self.assertIn("未知", text)
        _, guide = self._riic_review_guidance()
        self.assertIn("至简精一、特克诺精零", guide)
        self.assertIn("身份挂件若当前已满足联动条件", guide)
        self.assertIn("仅升级技能", guide)
        self.assertIn("局部换人", guide)

    def test_income_diagnosis_requires_comparable_reports_and_event_evidence(self):
        for text in self._riic_review_guidance():
            with self.subTest(
                source="prompt" if "工作范围是现有" in text else "knowledge"
            ):
                self.assertIn("同条件对照", text)
                self.assertIn("AI", text)
                self.assertIn("不执行", text)
                self.assertIn("收益", text)
                self.assertIn("工作占比=工作时长/采样时长", text)
                self.assertIn("工休比=工作时长/休息时长", text)
                self.assertIn("无休息时显示—", text)
                self.assertIn("不含预热", text)
                self.assertIn("心情涣散驻岗", text)
                self.assertIn("零心情", text)
                self.assertIn("自动认定", text)
                self.assertIn("甘特图", text)
                self.assertIn("工作记录", text)
                self.assertIn("演算日志", text)
                self.assertIn("原因链", text)
                self.assertIn("关联不等于根因", text)
                self.assertIn("不编造收益数值", text)
        _, guide = self._riic_review_guidance()
        self.assertIn("workRestRatio为null", guide)
        self.assertIn("不是工作占比也不是无穷效率", guide)
        self.assertIn("原表与候选", guide)
        self.assertIn("不擅自加外源赤金", guide)
        self.assertIn("不能声称长期自给", guide)
        self.assertIn("没有事件或配置原因链", guide)

    def test_code_diagnosis_separates_simulation_source_and_feedback_evidence(self):
        from arknights_mower.agent.tools import riic

        schema = riic.get_riic_knowledge_tool_def["function"]["parameters"][
            "properties"
        ]["topic"]
        self.assertIn("code_diagnosis", schema["enum"])
        with patch.object(
            riic,
            "load_skill_snapshot",
            return_value={"has_data": False, "operators": []},
        ):
            result = json.loads(
                agent.tool_func_map["get_riic_knowledge"](topic="code_diagnosis")
            )
        self.assertEqual(result["topic"], "code_diagnosis")
        prompt, review = self._riic_review_guidance()
        for label, text in (
            ("prompt", prompt),
            ("code", result["guide"]),
        ):
            with self.subTest(source=label):
                for required in (
                    "配置问题",
                    "演算模型限制",
                    "调度实现缺陷",
                    "不强迫改表掩盖代码异常",
                    "get_source_snippet",
                    "扫描行号",
                    "SHA-256",
                    "缺失状态",
                    "历史版本",
                    "报告",
                    "inspect_feedback",
                    "evidence_windows",
                    "演算相对小时",
                    "不能编造实机日志日期",
                    "runtime.log",
                    "证据ID",
                    "反馈草稿",
                    "复现原表",
                    "预期与实际",
                    "submit_issue",
                    "用户明确同意发送",
                    "实际时间",
                    "引用",
                    "不声称已发送",
                ):
                    self.assertIn(required, text)
        self.assertIn("code_diagnosis", review)
        self.assertIn("不强迫改表掩盖代码异常", review)
        self.assertIn("不会自动修代码", prompt)
        self.assertIn("不声称自动修代码", result["guide"])


if __name__ == "__main__":
    unittest.main()
