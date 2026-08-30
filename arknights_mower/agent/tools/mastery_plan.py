from arknights_mower.solvers.mastery import get_char_name
from arknights_mower.utils.mastery_db import (
    add_plan_checked,
    get_all_plans,
    get_route,
    retry_failed_plans,
    save_route,
)


def add_mastery_plan(
    char_id: str, skill_index: int, skill_name: str = "", target_level: int = 3
):
    """Add a new mastery plan for an operator skill."""
    plan_id, reason = add_plan_checked(
        char_id,
        skill_index,
        target_level=target_level,
        skill_name=skill_name or f"技能{skill_index + 1}",
        # #53：补传干员名，否则计划 char_name 为 NULL，邮件读不出练谁
        char_name=get_char_name(char_id),
    )
    if plan_id > 0:
        return f"已添加专精计划: {char_id} 技能{skill_index + 1} 专{target_level}"
    return f"添加专精计划失败: {char_id} 技能{skill_index + 1}（{reason}）"


def list_plans(status_filter: str = ""):
    """List mastery plans, optionally filtered by status (pending/in_progress/completed/failed)."""
    if status_filter:
        plans = [p for p in get_all_plans() if p["status"] == status_filter]
    else:
        plans = get_all_plans()
    if not plans:
        return "<p>无专精计划</p>"
    html = "<table border='1'><tr><th>char_id</th><th>技能</th><th>状态</th><th>等级</th><th>失败原因</th><th>时间</th></tr>"
    for p in plans:
        html += (
            f"<tr><td>{p['char_id']}</td>"
            f"<td>{p.get('skill_name', '技能' + str(p['skill_index'] + 1))}</td>"
            f"<td>{p['status']}</td>"
            f"<td>{p.get('target_level', 1)}</td>"
            f"<td>{p.get('failed_reason', '')}</td>"
            f"<td>{p.get('created_at', '')}</td></tr>"
        )
    html += "</table>"
    return html


def set_route(profession: str, supports_json: str):
    """Save a user-customized mastery route for a profession.

    supports_json 为该职业路线的 supports 数组（[{name, skill_level, efficiency,
    swap, swap_name, match}, ...]）或含 supports 的包装对象；中枢加成/换人缓冲是全局
    设置（POST /mastery-route/settings），不在路线 JSON 里。
    """
    save_route(profession, supports_json, is_default=0)
    return f"已保存 {profession} 路线的专精路线"


def get_route_info(profession: str):
    """Get the mastery route for a given profession."""
    route = get_route(profession)
    if route:
        return f"{profession} 路线: supports={route['supports']}"
    return f"{profession} 无已保存路线"


def retry_plan_tool(char_id: str, skill_index: int):
    """Retry failed mastery plans by resetting them to idle."""
    count = retry_failed_plans()
    if count > 0:
        return f"已重置 {count} 个失败的专精计划为待执行"
    return "没有失败的专精计划需要重试"


add_mastery_plan_tool_def = {
    "type": "function",
    "function": {
        "name": "add_mastery_plan",
        "description": "新增一个干员技能的专精计划",
        "parameters": {
            "type": "object",
            "properties": {
                "char_id": {
                    "type": "string",
                    "description": "干员ID，如 char_103_angel",
                },
                "skill_index": {"type": "integer", "description": "技能索引 0/1/2"},
                "skill_name": {"type": "string", "description": "技能名称（可选）"},
                "target_level": {
                    "type": "integer",
                    "description": "目标专精等级 1/2/3，缺省 3",
                    "enum": [1, 2, 3],
                },
            },
            "required": ["char_id", "skill_index"],
        },
    },
}

list_plans_tool_def = {
    "type": "function",
    "function": {
        "name": "list_plans",
        "description": "列出专精计划，可按状态筛选",
        "parameters": {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "description": "筛选状态: pending/completed/failed/in_progress，留空则全部",
                    "enum": ["", "pending", "in_progress", "completed", "failed"],
                },
            },
            "required": [],
        },
    },
}

set_route_tool_def = {
    "type": "function",
    "function": {
        "name": "set_route",
        "description": "保存某个职业的自定义专精路线",
        "parameters": {
            "type": "object",
            "properties": {
                "profession": {
                    "type": "string",
                    "description": "职业中文名，如 近卫/先锋/术师",
                },
                "supports_json": {
                    "type": "string",
                    "description": "该职业路线的 supports JSON 数组 [{name, skill_level, efficiency, swap, swap_name, match}]",
                },
            },
            "required": ["profession", "supports_json"],
        },
    },
}

get_route_info_tool_def = {
    "type": "function",
    "function": {
        "name": "get_route_info",
        "description": "查询某个职业保存的专精路线",
        "parameters": {
            "type": "object",
            "properties": {
                "profession": {
                    "type": "string",
                    "description": "职业中文名，如 近卫/先锋/术师",
                },
            },
            "required": ["profession"],
        },
    },
}

retry_plan_tool_def = {
    "type": "function",
    "function": {
        "name": "retry_plan_tool",
        "description": "重试一个失败的专精计划",
        "parameters": {
            "type": "object",
            "properties": {
                "char_id": {"type": "string", "description": "干员ID"},
                "skill_index": {"type": "integer", "description": "技能索引 0/1/2"},
            },
            "required": ["char_id", "skill_index"],
        },
    },
}
