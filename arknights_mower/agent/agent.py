import datetime
import json
import re
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

try:
    from langgraph.graph import END, MessageGraph
except ImportError:
    END = "__end__"
    MessageGraph = None

from arknights_mower.agent.missed_order import (
    format_missed_order_list,
    summarize_missed_order_result,
)
from arknights_mower.agent.tools.analyze_missed_order import (
    analyze_missed_order,
    analyze_missed_order_tool_def,
)
from arknights_mower.agent.tools.call_db import call_db, call_db_tool_def
from arknights_mower.agent.tools.extract_stack_paths import (
    extract_stack_paths,
    extract_stack_paths_tool_def,
)
from arknights_mower.agent.tools.faq import faq_tool_def, get_faq
from arknights_mower.agent.tools.get_source_snippet import (
    get_source_snippet,
    get_source_snippet_tool_def,
)
from arknights_mower.agent.tools.submit_issue import submit_issue, submit_issue_tool_def
from arknights_mower.utils import config
from arknights_mower.utils.log import logger

model_name_map = {
    "deepseek": ["deepseek-chat", "https://api.deepseek.com/v1"],
    "deepseek_reasoner": ["deepseek-reasoner", "https://api.deepseek.com/v1"],
    "deepseek_v4_pro": ["deepseek-v4-pro", "https://api.deepseek.com/v1"],
    "deepseek_flash": ["deepseek-chat", "https://api.deepseek.com/v1"],
}

MISS_STATE_MARKER = "MOWER_MISS_STATE"
MISS_CONFIRM_WORDS = ("要", "启用", "分析", "查", "是", "好的", "好", "ok", "yes")
MISS_CANCEL_WORDS = ("不要", "不用", "取消", "算了", "不查", "no")
MISS_TIME_RE = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}:\d{2})")


def get_tools():
    return [
        faq_tool_def,
        submit_issue_tool_def,
        call_db_tool_def,
        extract_stack_paths_tool_def,
        get_source_snippet_tool_def,
        analyze_missed_order_tool_def,
    ]


tool_func_map = {
    "get_faq": get_faq,
    "submit_issue": submit_issue,
    "call_db": call_db,
    "extract_stack_paths": extract_stack_paths,
    "get_source_snippet": get_source_snippet,
    "analyze_missed_order": analyze_missed_order,
}
tool_message_map = {
    "get_faq": "从知识黑洞中召唤最靠谱的废话锦集",
    "submit_issue": "把锅优雅地甩给开发组，顺便附上你的怨念",
    "call_db": "发现一条“我不想被发现”的数据记录",
    "extract_stack_paths": "提取智商2000用户提交的错误堆栈路径",
    "get_source_snippet": "获取某个傻逼写的全是bug的源代码片段",
    "analyze_missed_order": "翻检漏单相关的订单和任务时间线",
}


def build_llm(api_key, with_tools=False):
    kwargs = dict(
        model=model_name_map[config.conf.ai_type][0],
        base_url=model_name_map[config.conf.ai_type][1],
        api_key=api_key,
        temperature=0,
    )
    if config.conf.ai_type == "deepseek_v4_pro":
        kwargs["reasoning_effort"] = "high"
        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    llm = ChatOpenAI(**kwargs)
    if with_tools:
        return llm.bind_tools(tools=get_tools())
    return llm


def build_workflow(api_key):
    if MessageGraph is None:
        return None
    model_with_tools = build_llm(api_key, with_tools=True)
    workflow = MessageGraph()

    def agent_node(state):
        messages = state
        response = model_with_tools.invoke(messages)
        return response

    def tool_node(state):
        messages = state
        last_message = messages[-1]
        tool_calls = getattr(last_message, "additional_kwargs", {}).get(
            "tool_calls", []
        )
        tool_messages = []
        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_args = json.loads(tool_call["function"]["arguments"])
            if tool_name in tool_func_map:
                result = tool_func_map[tool_name](**tool_args)
            else:
                result = f"未知工具: {tool_name}"
            tool_messages.append(
                ToolMessage(content=result, tool_call_id=tool_call["id"])
            )
        return tool_messages

    workflow.add_node("agent", agent_node)
    workflow.add_node("action", tool_node)
    workflow.set_entry_point("agent")

    def should_continue(state):
        messages = state
        last_message = messages[-1]
        tool_calls = getattr(last_message, "additional_kwargs", {}).get("tool_calls")
        if tool_calls:
            return "action"
        return END

    workflow.add_conditional_edges(
        "agent", should_continue, {"action": "action", "agent": "agent", END: END}
    )
    workflow.add_edge("action", "agent")
    return workflow.compile()


def _run_manual_tool_loop(messages, api_key):
    model_with_tools = build_llm(api_key, with_tools=True)
    working_messages = list(messages)
    streamed = []
    for _ in range(8):
        response = model_with_tools.invoke(working_messages)
        tool_calls = getattr(response, "tool_calls", None) or getattr(
            response, "additional_kwargs", {}
        ).get("tool_calls", [])
        if tool_calls:
            streamed.extend(
                f"Mower助手正在{tool_message_map[call.get('name', '')]}...<br/>"
                for call in getattr(response, "tool_calls", []) or []
                if call.get("name") in tool_message_map
            )
            working_messages.append(response)
            for tool_call in tool_calls:
                if "function" in tool_call:
                    tool_name = tool_call["function"]["name"]
                    tool_args = json.loads(tool_call["function"]["arguments"])
                    tool_id = tool_call["id"]
                else:
                    tool_name = tool_call["name"]
                    tool_args = tool_call.get("args", {})
                    tool_id = tool_call["id"]
                result = tool_func_map.get(
                    tool_name, lambda **_: f"未知工具: {tool_name}"
                )(**tool_args)
                working_messages.append(
                    ToolMessage(content=result, tool_call_id=tool_id)
                )
            continue
        content = response.content if hasattr(response, "content") else str(response)
        if content:
            streamed.append(content)
        break
    return streamed


def _build_ai_intro():
    return (
        "你是明日方舟Mower助手AI，负责帮助用户排查和解决软件使用中的问题。"
        "你可以：1. 帮助用户上报问题；2. 查询本地数据库记录的数据；3. 根据用户问题查询常见FAQ；"
        "4. 分析漏单的时间线和原因。"
        f"当前本地时间为 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}，请使用24小时制。"
        f"当前软件的使用时区为 {datetime.datetime.now().astimezone().tzinfo}。"
        "工具返回的结果如果是 HTML 表格，请直接返回 HTML 字符串，不要转换为 Markdown 或其他格式。"
        "优先检查用户问题是否属于常见FAQ，如果匹配FAQ则直接回复修复方法。工具名称是 get_faq。"
        "当用户问漏单原因时，优先启用 analyze_missed_order，不要自己拼 SQL 推理根因。"
        "如果数据库没有漏单日志，就要求用户直接提供漏单发生时间。"
        "常见数据库查询问法：'查询最近10条订单'、'查询某干员的上下班记录'、'查询错误信息包含漏单的任务日志'。"
        "常见问题上报问法：'我要反馈一个bug'、'提交无法启动的问题'。"
        "你可能需要多轮调用不同工具才能得到最终分析结果。"
    )


def _build_messages(user_input, context=None):
    messages = [SystemMessage(content=_build_ai_intro())]
    for msg in context or []:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=user_input))
    return messages


def _is_missed_order_intent(text: str) -> bool:
    return "漏单" in (text or "")


def _encode_state(text: str, state: dict) -> str:
    payload = json.dumps(state, ensure_ascii=False)
    return f"{text}\n<!--{MISS_STATE_MARKER}:{payload}-->"


def _extract_state_from_text(text: str) -> Optional[dict]:
    if not text:
        return None
    pattern = rf"<!--{MISS_STATE_MARKER}:(.*?)-->"
    matches = re.findall(pattern, text, re.DOTALL)
    if not matches:
        return None
    try:
        return json.loads(matches[-1])
    except json.JSONDecodeError:
        return None


def _latest_miss_state(context) -> Optional[dict]:
    for msg in reversed(context or []):
        if msg.get("role") != "assistant":
            continue
        state = _extract_state_from_text(msg.get("content", ""))
        if state and state.get("flow") == "missed_order":
            return state
    return None


def _looks_like_confirm(text: str) -> bool:
    return any(word in text for word in MISS_CONFIRM_WORDS)


def _looks_like_cancel(text: str) -> bool:
    return any(word in text for word in MISS_CANCEL_WORDS)


def _extract_datetime_string(text: str) -> Optional[str]:
    match = MISS_TIME_RE.search(text or "")
    if not match:
        return None
    return match.group(1).replace("/", "-").replace("T", " ")


def _extract_index_selection(text: str) -> Optional[int]:
    match = re.search(r"\b(\d{1,2})\b", text or "")
    if not match:
        return None
    return int(match.group(1))


def _log_missed_order_flow(step: str, **details):
    logger.debug(
        "[missed_order_flow] %s",
        json.dumps({"step": step, **details}, ensure_ascii=False, default=str),
    )


def _handle_missed_order_flow(user_input, context, api_key):
    _log_missed_order_flow("input_received", user_input=user_input)
    state = _latest_miss_state(context)
    if state and state.get("step") == "closed":
        state = None
    if state is None:
        if not _is_missed_order_intent(user_input):
            return None
        _log_missed_order_flow("intent_detected", action="await_confirm")
        reply = (
            "检测到你在问漏单。要不要启用漏单分析？"
            "我会先查 log 表里的漏单日志；如果数据库里没有漏单日志，再让你直接输入漏单时间。"
        )
        return _encode_state(
            reply,
            {"flow": "missed_order", "step": "await_confirm"},
        )

    if state.get("step") == "await_confirm":
        if _looks_like_cancel(user_input):
            _log_missed_order_flow("confirm_cancelled")
            return _encode_state(
                "已取消漏单分析。你如果只想看原始数据，也可以直接让我查数据库。",
                {"flow": "missed_order", "step": "closed"},
            )
        if not (
            _looks_like_confirm(user_input) or _extract_datetime_string(user_input)
        ):
            _log_missed_order_flow("confirm_not_understood", user_input=user_input)
            reply = "要继续的话，直接回复“要”或“启用分析”；如果你已经知道时间，也可以直接发漏单时间。"
            return _encode_state(reply, state)
        _log_missed_order_flow("list_orders_requested")
        orders_raw = analyze_missed_order(mode="list_orders")
        orders_result = json.loads(orders_raw)
        orders = orders_result.get("orders", [])
        _log_missed_order_flow("list_orders_loaded", count=len(orders))
        if orders:
            reply = format_missed_order_list(orders)
            next_state = {
                "flow": "missed_order",
                "step": "await_target",
                "orders": orders,
            }
            return _encode_state(reply, next_state)
        _log_missed_order_flow("list_orders_empty", action="await_target_time")
        reply = "数据库里没有漏单日志记录，请直接回复漏单发生时间，格式如 2026-02-24 11:06:16。"
        next_state = {"flow": "missed_order", "step": "await_target", "orders": []}
        return _encode_state(reply, next_state)

    if state.get("step") == "await_target":
        if _looks_like_cancel(user_input):
            _log_missed_order_flow("target_cancelled")
            return _encode_state(
                "已取消漏单分析。",
                {"flow": "missed_order", "step": "closed"},
            )
        dt_text = _extract_datetime_string(user_input)
        selected_time = None
        selected_signal_type = None
        selected_log_event_time = None
        selected_log_event_ts = None
        selected_room = None
        if dt_text:
            selected_time = dt_text
            mode = "analyze_by_time"
            _log_missed_order_flow(
                "target_selected_by_time",
                selected_time=selected_time,
                mode=mode,
            )
        else:
            selected_index = _extract_index_selection(user_input)
            orders = state.get("orders", [])
            if selected_index and 1 <= selected_index <= len(orders):
                selected_order = orders[selected_index - 1]
                selected_time = (
                    selected_order.get("task_time")
                    or selected_order.get("current_task_time")
                    or selected_order["local_time"]
                )
                selected_signal_type = selected_order.get("signal_type")
                selected_log_event_time = selected_order.get("local_time")
                selected_log_event_ts = selected_order.get("event_utc_time")
                selected_room = selected_order.get("room")
                mode = "analyze_by_order"
                _log_missed_order_flow(
                    "target_selected_by_index",
                    selected_index=selected_index,
                    selected_time=selected_time,
                    selected_signal_type=selected_signal_type,
                    selected_log_event_time=selected_log_event_time,
                    selected_log_event_ts=selected_log_event_ts,
                    selected_room=selected_room,
                    mode=mode,
                )
            else:
                _log_missed_order_flow(
                    "target_not_understood",
                    user_input=user_input,
                    orders_count=len(orders),
                )
                reply = "我没识别到具体是哪一单。请回复编号，或者直接回复完整时间，例如 2026-02-24 11:06:16。"
                return _encode_state(reply, state)
        result_raw = analyze_missed_order(
            mode=mode,
            order_time=selected_time if mode == "analyze_by_order" else None,
            event_time=selected_time if mode == "analyze_by_time" else None,
            signal_type=selected_signal_type if mode == "analyze_by_order" else None,
            log_event_time=selected_log_event_time
            if mode == "analyze_by_order"
            else None,
            log_event_ts=selected_log_event_ts if mode == "analyze_by_order" else None,
            room=selected_room if mode == "analyze_by_order" else None,
        )
        result = json.loads(result_raw)
        _log_missed_order_flow(
            "analysis_completed",
            mode=mode,
            selected_time=selected_time,
            has_error=bool(result.get("error")),
            candidate_room=result.get("candidate_room"),
            target_task_time=result.get("target_task_time"),
            trace_count=len(result.get("analysis_trace") or []),
        )
        if result.get("error"):
            return _encode_state(
                f"漏单分析失败：{result['error']}",
                {"flow": "missed_order", "step": "closed"},
            )
        summary_llm = build_llm(api_key, with_tools=False)
        return _encode_state(
            summarize_missed_order_result(result, llm=summary_llm),
            {"flow": "missed_order", "step": "closed"},
        )

    return None


def ask_llm(user_input, context=None, api_key=None):
    if api_key is None or not api_key.strip():
        yield "未检测到 API Key，请先在设置中配置你的 AI Key。"
        return
    if context is None:
        context = []

    missed_order_reply = _handle_missed_order_flow(user_input, context, api_key)
    if missed_order_reply is not None:
        yield missed_order_reply
        return

    messages = _build_messages(user_input, context)
    app = build_workflow(api_key)
    if app is None:
        for reply in _run_manual_tool_loop(messages, api_key):
            if reply:
                yield reply
        return

    for event in app.stream(messages, stream_mode="messages"):
        if isinstance(event, tuple):
            message_chunk, _meta = event
            if isinstance(message_chunk, ToolMessage):
                continue
            if hasattr(message_chunk, "tool_calls") and message_chunk.tool_calls:
                for call in message_chunk.tool_calls:
                    tool_name = call.get("name")
                    if tool_name:
                        yield f"Mower助手正在{tool_message_map[tool_name]}...<br/>"
            elif hasattr(message_chunk, "content"):
                content = message_chunk.content
                if content:
                    yield content
