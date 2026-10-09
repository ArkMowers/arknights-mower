import sqlite3

from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path


def call_db(query: str):
    """
    执行 SQL 查询并返回结果。
    """
    try:
        database_path = get_path("@app/tmp/data.db")
        print(query)
        conn = sqlite3.connect(database_path)
        cursor = conn.cursor()
        cursor.execute(query)
        logger.debug(f"执行 SQL 查询: {query}")
        # 只返回前 100 行，防止数据量过大
        rows = cursor.fetchmany(100)
        columns = [desc[0] for desc in cursor.description]
        result = [dict(zip(columns, row)) for row in rows]
        cursor.close()
        conn.close()
        if not result:
            return "<p>无查询结果</p>"
        html = (
            "<table border='1'><tr>"
            + "".join(f"<th>{col}</th>" for col in columns)
            + "</tr>"
        )
        for row in result:
            html += (
                "<tr>"
                + "".join(f"<td>{row.get(col, '')}</td>" for col in columns)
                + "</tr>"
            )
        html += "</table>"
        print(html)
        return html
    except Exception as e:
        return f"SQL 执行失败: {e}"


call_db_tool_def = {
    "type": "function",
    "function": {
        "name": "call_db",
        "description": (
            "查询本地 SQLite 数据库。只生成 SELECT 查询，不生成写入、删表或修改结构的 SQL。"
            "返回 HTML 表格、无查询结果或 SQL 执行失败信息；"
            "将表格转成 Markdown 或纯文本，空结果和错误按实际含义说明。"
            "最多返回100行，查询最近记录时显式 ORDER BY 时间 DESC LIMIT N，N 不超过100。\n"
            "表定义和专用规则：\n"
            "1. agent_action表 - 干员基建活动:"
            "   字段: name TEXT,agent_current_room TEXT,current_room TEXT,is_high INTEGER,agent_group TEXT,mood REAL,`current_time` TEXT,related_operator TEXT,mood_event TEXT。"
            "agent_current_room 是更新前位置，current_room 是更新后位置；"
            "current_room 为空表示不在房间，dorm_ 开头表示宿舍。记录是历史观测，不保证代表实时位置。"
            "示例查询: SELECT name AS 干员名称, current_room AS 更新后位置, `current_time` AS 时间 FROM agent_action WHERE current_room LIKE 'dorm_%' ORDER BY `current_time` DESC LIMIT 10;\n"
            "2. trading_history表 - 龙门币交易记录/订单记录:"
            "   字段: time INTEGER PRIMARY KEY,server_date TEXT,type TEXT,price INTEGER"
            "   订单类别/ type：龙舌兰，但书，佩佩，可露希尔，漏单"
            "   规则: 时间查询需转换: strftime('%Y-%m-%d %H:%M:%S', time, 'unixepoch', 'localtime') AS local_time"
            "   示例查询: SELECT strftime('%Y-%m-%d %H:%M:%S', time, 'unixepoch', 'localtime') AS 交易时间, type AS 类型 FROM trading_history WHERE type = '漏单' ORDER BY time DESC LIMIT 10;\n"
            "3. log表 - 系统任务记录/报错记录/日志:"
            "   字段: time INTEGER, task TEXT, level TEXT, message TEXT"
            "   专用: 当用户查询'任务'、'报错'、'错误'、'日志'时必须使用此表"
            "   示例查询: SELECT strftime('%Y-%m-%d %H:%M:%S', time, 'unixepoch', 'localtime') AS 时间, task AS 任务, message AS 错误信息 FROM log WHERE level = 'ERROR' ORDER BY time DESC LIMIT 10;\n"
            "查询规则:"
            "- 任务，日志相关查询必须使用log表，不得使用trading_history表"
            "- 列名必须与用户查询语言一致"
            "- 明确查询原始漏单记录时按用户指定的表查询，仅记录类型有歧义时询问"
            "- 如果用户是要分析漏单原因而不是单纯查表，应优先使用 analyze_missed_order 工具"
            "- agent_action 的 `current_time` 你必须用``包住 例子: Select `current_time` from agent_action"
            "时间处理规则:"
            "- trading_history、log 的 time 是 Unix 秒级时间戳，展示时用上述 SQLite 表达式转换"
            "- 按本地时间筛选可比较 datetime(time, 'unixepoch', 'localtime') 与 'YYYY-MM-DD HH:MM:SS'，不要猜测时间戳"
            "- agent_action的`current_time`已是本地时间"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "针对上述表的 SQLite SELECT 查询，包含明确排序和不超过100行的 LIMIT。",
                }
            },
            "required": ["query"],
        },
    },
}
