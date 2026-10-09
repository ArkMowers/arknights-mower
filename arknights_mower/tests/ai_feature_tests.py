"""Local/online model configuration and explicit schedule-error analysis."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server
from arknights_mower.agent import agent
from arknights_mower.agent.schedule_error import prepare_schedule_error_evidence
from arknights_mower.agent.tools.captcha_ocr_match import match_captcha_order
from arknights_mower.utils.config.conf import AIAgentPart, Conf


class ModelConfigurationTests(unittest.TestCase):
    def test_deepseek_presets_keep_existing_endpoints(self):
        for model in ("deepseek-flash", "deepseek-v4-pro"):
            with self.subTest(model=model):
                settings = AIAgentPart(ai_type=model, ai_key="preset-test-key")
                with (
                    patch.object(agent.config, "conf", settings),
                    patch.object(agent, "ChatOpenAI") as factory,
                ):
                    agent.build_llm(settings.resolved_ai_key)
                self.assertEqual(factory.call_args.kwargs["model"], model)
                self.assertEqual(
                    factory.call_args.kwargs["base_url"], "https://api.deepseek.com"
                )
                self.assertEqual(factory.call_args.kwargs["api_key"], "preset-test-key")

    def test_legacy_flash_selection_loads_and_requests_current_model(self):
        saved = {"ai_type": "deepseek-v4-flash", "ai_key": "preset-test-key"}
        settings = Conf.model_validate(saved)
        self.assertEqual(saved["ai_type"], "deepseek-v4-flash")
        self.assertEqual(
            settings.model_dump(exclude_unset=True),
            {"ai_type": "deepseek-flash", "ai_key": "preset-test-key"},
        )
        with (
            patch.object(agent.config, "conf", settings),
            patch.object(agent, "ChatOpenAI") as factory,
        ):
            agent.build_llm(settings.resolved_ai_key, with_tools=True)
        self.assertEqual(factory.call_args.kwargs["model"], "deepseek-flash")
        self.assertEqual(
            factory.call_args.kwargs["base_url"], "https://api.deepseek.com"
        )
        self.assertEqual(factory.call_args.kwargs["api_key"], "preset-test-key")
        factory.return_value.bind_tools.assert_called_once_with(tools=agent.get_tools())

    def test_local_model_needs_no_key_and_uses_custom_endpoint(self):
        settings = AIAgentPart(
            ai_type="custom-local",
            ai_key="old-deepseek-key",
            ai_base_url="http://127.0.0.1:11434/v1",
            ai_model="qwen3:8b",
        )
        self.assertEqual(settings.resolved_ai_key, "")
        with (
            patch.object(agent.config, "conf", settings),
            patch.object(agent, "ChatOpenAI") as factory,
        ):
            agent.build_llm(settings.resolved_ai_key)
        self.assertEqual(factory.call_args.kwargs["model"], "qwen3:8b")
        self.assertEqual(
            factory.call_args.kwargs["base_url"], "http://127.0.0.1:11434/v1"
        )
        self.assertEqual(factory.call_args.kwargs["api_key"], "local-model")

    def test_online_relay_requires_https_and_uses_its_own_key(self):
        settings = AIAgentPart(
            ai_type="custom-online",
            ai_key="old-deepseek-key",
            ai_custom_key="relay-test-key",
            ai_base_url="https://relay.example/v1/",
            ai_model="provider-model",
        )
        self.assertEqual(settings.resolved_ai_key, "relay-test-key")
        with (
            patch.object(agent.config, "conf", settings),
            patch.object(agent, "ChatOpenAI") as factory,
        ):
            agent.build_llm(settings.resolved_ai_key)
        self.assertEqual(
            factory.call_args.kwargs["base_url"], "https://relay.example/v1"
        )
        self.assertEqual(factory.call_args.kwargs["api_key"], "relay-test-key")
        settings.ai_base_url = "http://relay.example/v1"
        with patch.object(agent.config, "conf", settings):
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                agent.build_llm(settings.resolved_ai_key)

    def test_keyless_local_model_can_match_captcha(self):
        settings = AIAgentPart(ai_type="custom-local")
        with (
            patch.object(agent.config, "conf", settings),
            patch("arknights_mower.agent.tools.captcha_ocr_match.build_llm") as build,
        ):
            build.return_value.invoke.return_value.content = "[0]"
            result = match_captcha_order("开", [{"word": "开"}])
        self.assertEqual(result, [0])
        build.assert_called_once_with("", with_tools=False)


class ScheduleErrorAnalysisTests(unittest.TestCase):
    def test_evidence_is_bounded_and_redacts_known_secrets(self):
        rows = [
            {
                "time": f"2026-09-28 00:00:{index:02d}",
                "message": "ERROR token=private-value 排班失败",
            }
            for index in range(40)
        ]
        evidence = prepare_schedule_error_evidence(
            {"time_ns": 123, "message": "排班报错 api_key=another-secret"}, rows
        )
        self.assertEqual(len(evidence["related_logs"]), 30)
        rendered = json.dumps(evidence, ensure_ascii=False)
        self.assertNotIn("private-value", rendered)
        self.assertNotIn("another-secret", rendered)

    def test_evidence_drops_nested_secret_values(self):
        evidence = prepare_schedule_error_evidence(
            {"message": "排班失败"},
            [
                {
                    "message": "ERROR skland_info=[{'cred': 'sensitive-credential', 'token': 'another-secret'}]"
                }
            ],
        )
        rendered = json.dumps(evidence, ensure_ascii=False)
        self.assertNotIn("sensitive-credential", rendered)
        self.assertNotIn("another-secret", rendered)

    def test_analysis_route_requires_token_and_selected_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            screenshot_root = root / "screenshot"
            archive = screenshot_root / "errors" / "123"
            archive.mkdir(parents=True)
            (archive / "event.json").write_text(
                json.dumps({"time_ns": 123, "message": "排班失败"}), encoding="utf-8"
            )
            (archive / "logs.json").write_text(
                json.dumps([{"time": "2026-09-28", "message": "ERROR 排班失败"}]),
                encoding="utf-8",
            )
            previous = getattr(server.app, "token", None)
            server.app.token = "test-token"
            original_get_path = server.get_path

            def local_path(value):
                return (
                    screenshot_root
                    if value == "@app/screenshot"
                    else original_get_path(value)
                )

            try:
                with (
                    patch.object(server, "get_path", side_effect=local_path),
                    patch(
                        "arknights_mower.agent.schedule_error.analyze_schedule_error",
                        return_value="## 可能原因\n排班冲突",
                    ) as analyze,
                ):
                    client = server.app.test_client()
                    url = "/diagnostics/errors/123/analyze"
                    self.assertEqual(client.post(url).status_code, 403)
                    response = client.post(
                        url,
                        headers={"token": "test-token", "X-Mower-Diagnostics": "1"},
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("排班冲突", response.json["analysis"])
                    analyze.assert_called_once()
            finally:
                if previous is None:
                    del server.app.token
                else:
                    server.app.token = previous


if __name__ == "__main__":
    unittest.main()
