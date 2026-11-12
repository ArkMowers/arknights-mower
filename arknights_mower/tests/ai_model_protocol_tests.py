"""Exercise the assistant's synchronous SDK and graph with offline HTTP responses."""

import json
from unittest.mock import Mock

import httpx
import pytest
from openai import APIStatusError

from arknights_mower.agent import agent


@pytest.fixture
def serve(monkeypatch):
    monkeypatch.setattr(agent.config.conf, "ai_api_protocol", "auto")
    monkeypatch.setattr(agent.config.conf, "ai_type", "custom-online")
    monkeypatch.setattr(agent.config.conf, "ai_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(agent.config.conf, "ai_model", "fixture-model")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    def install(handler):
        def handle(transport, request):
            return handler(request.url.path, json.loads(request.content))

        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)

    return install


def event_stream(*events):
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content="".join(f"data: {json.dumps(e)}\n\n" for e in events),
    )


@pytest.mark.parametrize(
    "protocol,url",
    [
        ("auto", "https://api.openai.com/v1"),
        ("responses", "https://relay.example/v1"),
    ],
)
def test_two_streamed_questions_in_one_process(serve, monkeypatch, protocol, url):
    monkeypatch.setattr(agent.config.conf, "ai_api_protocol", protocol)
    monkeypatch.setattr(agent.config.conf, "ai_base_url", url)
    tool = Mock(side_effect=["first plan", "second plan"])
    monkeypatch.setitem(agent.tool_func_map, "list_plans", tool)
    requests = []

    def respond(path, body):
        assert path == "/v1/responses" and body["stream"]
        requests.append(body)
        turn = (len(requests) + 1) // 2
        if len(requests) % 2:
            return event_stream(
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {
                        "type": "function_call",
                        "id": f"fc_{turn}",
                        "call_id": f"call_{turn}",
                        "name": "list_plans",
                        "arguments": "{}",
                    },
                }
            )
        result = body["input"][-1]
        assert result["type"] == "function_call_output"
        assert result["call_id"] == f"call_{turn}"
        return event_stream(
            {
                "type": "response.output_text.delta",
                "item_id": f"msg_{turn}",
                "output_index": 0,
                "content_index": 0,
                "delta": result["output"],
            }
        )

    serve(respond)
    history = []
    for question, expected in [("First?", "first plan"), ("Again?", "second plan")]:
        chunks = list(agent.ask_llm(question, history, api_key="test-key"))
        assert chunks[-1] == expected
        history.extend(
            [
                {"role": "user", "content": question},
                {"role": "assistant", "content": expected},
            ]
        )
    assert len(requests) == 4 and tool.call_count == 2
    previous_reply = next(
        m for m in requests[2]["input"] if m.get("role") == "assistant"
    )
    assert previous_reply["content"] == [{"type": "output_text", "text": "first plan"}]


def rejection(status, message, code=None, param=None):
    return httpx.Response(
        status,
        json={
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "code": code,
                "param": param,
            }
        },
    )


def test_chat_only_model_keeps_tool_results_after_fallback(serve, monkeypatch):
    paths = []
    tool = Mock(return_value="one plan")
    monkeypatch.setitem(agent.tool_func_map, "list_plans", tool)

    def respond(path, body):
        paths.append(path)
        if path == "/v1/responses":
            return rejection(
                400, "This model is not supported in the v1/responses endpoint."
            )
        assert body["stream"]
        if body["messages"][-1]["role"] == "user":
            delta = {
                "tool_calls": [
                    {
                        "index": 0,
                        "type": "function",
                        "id": "call_1",
                        "function": {"name": "list_plans", "arguments": "{}"},
                    }
                ]
            }
            reason = "tool_calls"
        else:
            result = body["messages"][-1]
            assert result["role"] == "tool" and result["tool_call_id"] == "call_1"
            delta = {"content": result["content"]}
            reason = "stop"
        return event_stream(
            {
                "id": "chatcmpl-1",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "fixture-model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", **delta},
                        "finish_reason": reason,
                    }
                ],
            }
        )

    serve(respond)
    assert list(agent.ask_llm("Check plans", api_key="test-key"))[-1] == "one plan"
    assert paths == ["/v1/responses", "/v1/chat/completions", "/v1/chat/completions"]
    tool.assert_called_once_with()


@pytest.mark.parametrize(
    "status,code,message",
    [
        (404, "model_not_found", "Model not found"),
        (400, None, "The model `fixture-3.5` does not support the Responses API."),
        (400, None, "This model only supports Chat Completions."),
    ],
)
def test_model_unavailable_can_fall_back_for_text_only_callers(
    serve, status, code, message
):
    paths = []

    def respond(path, body):
        paths.append(path)
        if path == "/v1/responses":
            return rejection(status, message, code=code)
        assert body["model"] == "fixture-model" and "tools" not in body
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 1,
                "model": "fixture-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "answer"},
                    }
                ],
            },
        )

    serve(respond)
    assert agent.build_llm("test-key").invoke("Query").content == "answer"
    assert paths == ["/v1/responses", "/v1/chat/completions"]


def test_failed_chat_fallback_surfaces_its_error_once(serve):
    paths = []

    def respond(path, body):
        paths.append(path)
        if path == "/v1/responses":
            return rejection(404, "Model not found", "model_not_found")
        return rejection(403, "No access to this model", "permission_denied")

    serve(respond)
    with pytest.raises(APIStatusError) as caught:
        agent.build_llm("test-key", max_retries=0).invoke("Query")
    assert caught.value.status_code == 403
    assert paths == ["/v1/responses", "/v1/chat/completions"]


@pytest.mark.parametrize(
    "status,code,param",
    [
        (400, "invalid_function_parameters", "tools[0].parameters"),
        (404, "resource_not_found", "previous_response_id"),
        (401, "invalid_api_key", None),
        (403, "permission_denied", None),
        (429, "rate_limit_exceeded", None),
        (500, "server_error", None),
    ],
)
def test_unrelated_api_error_does_not_switch_protocol(serve, status, code, param):
    paths = []

    def respond(path, body):
        paths.append(path)
        return rejection(status, "Request failed", code=code, param=param)

    serve(respond)
    with pytest.raises(APIStatusError) as caught:
        agent.build_llm("test-key", max_retries=0).invoke("Query")
    assert caught.value.code == code
    assert paths == ["/v1/responses"]


def responses_text(text):
    return httpx.Response(
        200,
        json={
            "id": "resp-fixture",
            "object": "response",
            "created_at": 1,
            "status": "completed",
            "model": "fixture-model",
            "output": [
                {
                    "type": "message",
                    "id": "msg-fixture",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {"type": "output_text", "text": text, "annotations": []}
                    ],
                }
            ],
        },
    )


@pytest.mark.parametrize(
    "service,url,protocol,expected",
    [
        ("custom-online", "https://api.openai.com/v1/", "auto", "/v1/responses"),
        ("custom-online", "https://relay.example/v1", "auto", "/v1/chat/completions"),
        ("custom-local", "http://localhost:11434/v1", "auto", "/v1/chat/completions"),
        (
            "custom-online",
            "https://api.openai.com/v1",
            "chat-completions",
            "/v1/chat/completions",
        ),
        (
            "custom-online",
            "https://relay.example/v1",
            "chat-completions",
            "/v1/chat/completions",
        ),
        ("custom-online", "https://relay.example/v1", "responses", "/v1/responses"),
        ("custom-local", "http://localhost:11434/v1", "responses", "/v1/responses"),
        ("deepseek", "https://ignored.example/v1", "responses", "/chat/completions"),
    ],
)
def test_selected_protocol_controls_actual_request(
    serve, monkeypatch, service, url, protocol, expected
):
    monkeypatch.setattr(agent.config.conf, "ai_type", service)
    monkeypatch.setattr(agent.config.conf, "ai_base_url", url)
    monkeypatch.setattr(agent.config.conf, "ai_api_protocol", protocol)
    paths = []

    def respond(path, body):
        paths.append(path)
        if path.endswith("/responses"):
            assert "temperature" not in body
            return responses_text("answer")
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-fixture",
                "object": "chat.completion",
                "created": 1,
                "model": "fixture-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "answer"},
                    }
                ],
            },
        )

    serve(respond)
    assert agent.build_llm("test-key").invoke("Query").content == "answer"
    assert paths == [expected]


@pytest.mark.parametrize(
    "protocol,endpoint",
    [
        ("responses", "/v1/responses"),
        ("chat-completions", "/v1/chat/completions"),
    ],
)
def test_explicit_protocol_never_falls_back(serve, monkeypatch, protocol, endpoint):
    monkeypatch.setattr(agent.config.conf, "ai_api_protocol", protocol)
    paths = []

    def respond(path, body):
        paths.append(path)
        return rejection(404, "Model not found", "model_not_found")

    serve(respond)
    with pytest.raises(APIStatusError):
        agent.build_llm("test-key", max_retries=0).invoke("Query")
    assert paths == [endpoint]


def test_protocol_configuration_round_trip_and_validation():
    from pydantic import ValidationError

    from arknights_mower.utils.config.conf import Conf

    old = Conf(ai_type="custom-online")
    assert old.ai_api_protocol == "auto"
    assert "ai_api_protocol" not in old.model_dump(exclude_unset=True)
    for protocol in ("auto", "chat-completions", "responses"):
        saved = {"ai_api_protocol": protocol, "ai_model": "custom-model"}
        assert Conf.model_validate(saved).model_dump(exclude_unset=True) == saved
    with pytest.raises(ValidationError):
        Conf(ai_api_protocol="unknown")


@pytest.mark.parametrize(
    "consumer", ["schedule", "captcha", "missed_order", "navigation"]
)
def test_responses_text_reaches_existing_consumers(serve, monkeypatch, consumer):
    from arknights_mower.agent import navigation_process as worker
    from arknights_mower.agent.missed_order import summarize_missed_order_result
    from arknights_mower.agent.schedule_error import analyze_schedule_error
    from arknights_mower.agent.tools.captcha_ocr_match import match_captcha_order
    from arknights_mower.utils import path as paths

    monkeypatch.setattr(agent.config.conf, "ai_base_url", "https://relay.example/v1")
    monkeypatch.setattr(agent.config.conf, "ai_api_protocol", "responses")
    requests = []
    answer = (
        "[0]"
        if consumer == "captcha"
        else '{"indices":[0]}'
        if consumer == "navigation"
        else "模型分析结果"
    )

    def respond(path, body):
        requests.append(path)
        assert path == "/v1/responses" and "tools" not in body
        return responses_text(answer)

    serve(respond)
    if consumer == "schedule":
        assert analyze_schedule_error({"message": "排班失败"}, [], "test-key") == answer
    elif consumer == "captcha":
        assert match_captcha_order("开", [{"word": "开"}], "test-key") == [0]
    elif consumer == "missed_order":
        result = {}
        assert answer in summarize_missed_order_result(
            result, agent.build_llm("test-key")
        )
        assert result["summary_source"] == "llm"
    else:
        settings = agent.config.conf.model_dump()
        channel = Mock()
        # Restore the worker's module-level configuration after this direct invocation.
        monkeypatch.setattr(agent.config, "conf", agent.config.conf)
        worker._model_worker(
            channel,
            settings,
            "test-key",
            [{"role": "user", "content": "rank"}],
            5,
            {name: getattr(paths, name) for name in worker._PATH_FIELDS},
        )
        assert json.loads(channel.send_bytes.call_args.args[0]) == {"text": answer}
        channel.close.assert_called_once()
    assert requests == ["/v1/responses"]


@pytest.mark.parametrize("protocol", ["responses", "chat-completions"])
@pytest.mark.parametrize(
    "registered", [False, True], ids=["unknown-tool", "missing-progress-label"]
)
def test_tool_without_progress_label_keeps_stream_alive(
    serve, monkeypatch, protocol, registered
):
    monkeypatch.setattr(agent.config.conf, "ai_api_protocol", protocol)
    name = "fixture_unlabelled_tool"
    tool = Mock(return_value="tool result")
    if registered:
        monkeypatch.setitem(agent.tool_func_map, name, tool)
    expected = "tool result" if registered else f"未知工具: {name}"
    requests = []

    def respond(path, body):
        requests.append(body)
        assert body["stream"]
        first = len(requests) == 1
        if protocol == "responses":
            assert path == "/v1/responses"
            if first:
                return event_stream(
                    {
                        "type": "response.output_item.added",
                        "output_index": 0,
                        "item": {
                            "type": "function_call",
                            "id": "fc_unknown",
                            "call_id": "call_unknown",
                            "name": name,
                            "arguments": "{}",
                        },
                    }
                )
            result = body["input"][-1]
            assert result["type"] == "function_call_output"
            assert result["call_id"] == "call_unknown" and result["output"] == expected
            return event_stream(
                {
                    "type": "response.output_text.delta",
                    "item_id": "msg_final",
                    "output_index": 0,
                    "content_index": 0,
                    "delta": "final answer",
                }
            )
        assert path == "/v1/chat/completions"
        if first:
            delta = {
                "tool_calls": [
                    {
                        "index": 0,
                        "type": "function",
                        "id": "call_unknown",
                        "function": {"name": name, "arguments": "{}"},
                    }
                ]
            }
        else:
            result = body["messages"][-1]
            assert result["role"] == "tool"
            assert (
                result["tool_call_id"] == "call_unknown"
                and result["content"] == expected
            )
            delta = {"content": "final answer"}
        return event_stream(
            {
                "id": "chatcmpl-fixture",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "fixture-model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", **delta},
                        "finish_reason": "tool_calls" if first else "stop",
                    }
                ],
            }
        )

    serve(respond)
    assert list(agent.ask_llm("Check tools", api_key="test-key")) == ["final answer"]
    assert len(requests) == 2
    if registered:
        tool.assert_called_once_with()
    else:
        tool.assert_not_called()
