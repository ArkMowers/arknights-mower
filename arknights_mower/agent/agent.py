import datetime
import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, MessageGraph

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

model_name_map = {
    "deepseek": ["deepseek-chat", "https://api.deepseek.com/v1"],
    "deepseek_reasoner": ["deepseek-reasoner", "https://api.deepseek.com/v1"],
}


def get_tools():
    return [
        faq_tool_def,
        submit_issue_tool_def,
        call_db_tool_def,
        extract_stack_paths_tool_def,
        get_source_snippet_tool_def,
    ]


tool_func_map = {
    "get_faq": get_faq,
    "submit_issue": submit_issue,
    "call_db": call_db,
    "extract_stack_paths": extract_stack_paths,
    "get_source_snippet": get_source_snippet,
}
tool_message_map = {
    "get_faq": "从知识黑洞中召唤最靠谱的废话锦集",
    "submit_issue": "把锅优雅地甩给开发组，顺便附上你的怨念",
    "call_db": "发现一条“我不想被发现”的数据记录",
    "extract_stack_paths": "提取智商2000用户提交的错误堆栈路径",
    "get_source_snippet": "获取某个傻逼写的全是bug的源代码片段",
}


def build_workflow(api_key):
    llm = ChatOpenAI(
        model=model_name_map[config.conf.ai_type][0],
        base_url=model_name_map[config.conf.ai_type][1],
        api_key=api_key,
        temperature=0,
    )
    model_with_tools = llm.bind_tools(tools=get_tools())
    workflow = MessageGraph()

    def agent_node(state):
        messages = state
        response = model_with_tools.invoke(messages)
        return response

    def tool_node(state):
        messages = state
        last_message = messages[-1]
        tool_calls = last_message.additional_kwargs.get("tool_calls", [])
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
        if "tool_calls" in last_message.additional_kwargs:
            return "action"
        if any(x in last_message.content for x in ["是否解决", "还需要帮助", "要上报"]):
            return "agent"
        return END

    workflow.add_conditional_edges(
        "agent", should_continue, {"action": "action", "agent": "agent", END: END}
    )
    workflow.add_edge("action", "agent")
    return workflow.compile()


def ask_llm(user_input, context=None, api_key=None):
    if api_key is None or not api_key.strip():
        yield "未检测到 API Key，请先在设置中配置你的 AI Key。"
        return
    if context is None:
        context = []
    AI_INTRO = (
        "你是明日方舟Mower助手AI，负责帮助用户排查和解决软件使用中的问题。"
        "你可以：1. 帮助用户上报问题；2. 查询本地数据库记录的数据；3.根据用户问题查询常见FAQ；"
        f"当前本地时间为 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}，请使用24小时制。"
        f"当前软件的使用时区为 {datetime.datetime.now().astimezone().tzinfo}。"
        "工具返回的结果如果是 HTML 表格，请直接返回 HTML 字符串，不要转换为 Markdown 或其他格式。"
        "优先检查用户问题是否属于常见FAQ，如果匹配FAQ则直接回复修复方法。工具名称是 get_faq。"
        "如果用户的问题与当前可用工具无关，请提示用户选择合适的工具，并提供相关问法"
        "请根据用户选择的工具，只用对应工具回答。"
        "常见数据库查询问法：'查询最近10条订单'、'查询某干员的上下班记录'、'查询错误信息包含漏单的任务日志'。"
        "常见问题上报问法：'我要反馈一个bug'、'提交无法启动的问题'。"
        "你可能需要多轮调用不同工具才能得到最终分析结果。"
    )
    messages = [SystemMessage(content=AI_INTRO)]
    for msg in context:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=user_input))

    app = build_workflow(api_key)
    for event in app.stream(messages, stream_mode="messages"):
        if isinstance(event, tuple):
            message_chunk, meta = event
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
