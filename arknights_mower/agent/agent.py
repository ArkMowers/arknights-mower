import datetime
import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, MessageGraph

from arknights_mower.agent.tools.readdata import call_db, call_db_tool_def

# from arknights_mower.agent.tools.faq import get_faq
# from arknights_mower.agent.tools.logcheck import check_log
# from arknights_mower.agent.tools.code_search import search_code
# from arknights_mower.agent.tools.dbquery import query_db
# from arknights_mower.agent.tools.issue import submit_issue
from arknights_mower.agent.tools.submit_issue import submit_issue, submit_issue_tool_def
from arknights_mower.utils import config

model_name_map = {"deepseek": ["deepseek-chat", "https://api.deepseek.com/v1"]}


def get_tools():
    return [
        submit_issue_tool_def,
        call_db_tool_def,
        # {
        #     "type": "function",
        #     "function": {
        #         "name": "get_faq",
        #         "description": "查询软件常见问题或名词释义",
        #         "parameters": {
        #             "type": "object",
        #             "properties": {
        #                 "question": {"type": "string", "description": "用户的问题或名词"}
        #             },
        #             "required": ["question"]
        #         }
        #     }
        # },
        # {
        #     "type": "function",
        #     "function": {
        #         "name": "search_code",
        #         "description": "在本地源代码中查找相关实现或特性",
        #         "parameters": {
        #             "type": "object",
        #             "properties": {
        #                 "feature": {"type": "string", "description": "用户想了解的软件特性"}
        #             },
        #             "required": ["feature"]
        #         }
        #     }
        # },
        # {
        #     "type": "function",
        #     "function": {
        #         "name": "query_db",
        #         "description": "查询软件数据库",
        #         "parameters": {
        #             "type": "object",
        #             "properties": {
        #                 "sql": {"type": "string", "description": "SQL语句"}
        #             },
        #             "required": ["sql"]
        #         }
        #     }
        # },
        # {
        #     "type": "function",
        #     "function": {
        #         "name": "submit_issue",
        #         "description": "将用户未解决的问题上报给开发组",
        #         "parameters": {
        #             "type": "object",
        #             "properties": {
        #                 "description": {"type": "string", "description": "用户遇到的问题描述"}
        #             },
        #             "required": ["description"]
        #         }
        #     }
        # }
    ]


tool_func_map = {
    # "check_log": check_log,
    # "get_faq": get_faq,
    # "search_code": search_code,
    # "query_db": query_db,
    "submit_issue": submit_issue,
    "call_db": call_db,
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
        return "未检测到 API Key，请先在设置中配置你的 AI Key。"
    if context is None:
        context = []
    # 系统提示词，定义AI身份和流程
    AI_INTRO = (
        "你是明日方舟Mower助手AI，负责帮助用户排查和解决软件使用中的问题。"
        "你可以：1. 帮助用户上报问题；2. 查询本地数据库记录的数据"
        f"当前本地时间为 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}，请使用24小时制。"
        f"当前软件的使用时区为 {datetime.datetime.now().astimezone().tzinfo}。"
        "工具返回的结果如果是 HTML 表格，请直接返回 HTML 字符串，不要转换为 Markdown 或其他格式。举例 <table><tr><th>列名1</th><th>列名2</th></tr><tr><td>数据1</td><td>数据2</td></tr></table> 你可以在这部分前后加入你的分析或者判断，但是不要修改表格的htem string。"
        "请根据用户选择的工具，只用对应工具回答。"
        "常见数据库查询问法：'查询最近10条订单'、'查询某干员的上下班记录'。"
        "常见问题上报问法：'我要反馈一个bug'、'提交无法启动的问题'。"
        "如果用户的问题与当前可用工具无关，请提示用户选择合适的工具，并提供相关问法"
    )
    messages = [SystemMessage(content=AI_INTRO)]
    for msg in context:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=user_input))
    workflow = build_workflow(api_key)
    final_state = workflow.invoke(messages)
    return final_state[-1].content
