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
            # 基本规则
            "ALWAYS return the HTML table string exactly as received from the tool."
            "Execute a SQL query on the specified database and return the result. "
            "DO NOT reformat the result. "
            "You must generate a valid SQL SELECT statement according to the user's request and the provided table schema. "
            "If the query is not a SELECT, return an error. "
            "If the query is too complex or dangerous, ask the user for confirmation."
            "表定义和专用规则："
            "1. agent_action表 - 干员基建活动:"
            "   字段: name TEXT,agent_current_room TEXT,current_room TEXT,is_high INTEGER,agent_group TEXT,mood REAL,current_time TEXT"
            "   规则: 如果current_room是空值则表示该干员不在任何房间中; dorm_开头表示在宿舍"
            "   示例查询: SELECT name AS 干员名称, current_room AS 当前位置 FROM agent_action WHERE agent_current_room LIKE 'dorm_%'"
            "2. trading_history表 - 龙门币交易记录/订单记录:"
            "   字段: time INTEGER PRIMARY KEY,server_date TEXT,type TEXT,price INTEGER"
            "   订单类别/ type：龙舌兰，但书，佩佩，漏单"
            "   规则: 时间查询需转换: strftime('%Y-%m-%d %H:%M:%S', time, 'unixepoch', 'localtime') AS local_time"
            "   示例查询: SELECT strftime('%Y-%m-%d %H:%M:%S', time, 'unixepoch', 'localtime') AS 交易时间, type AS 类型 FROM trading_history WHERE type = '漏单'"
            "3. log表 - 系统任务记录/报错记录/日志:"
            "   字段: time INTEGER, task TEXT, level TEXT, message TEXT"
            "   专用: 当用户查询'任务'、'报错'、'错误'、'日志'时必须使用此表"
            "   示例查询: SELECT strftime('%Y-%m-%d %H:%M:%S', time, 'unixepoch', 'localtime') AS 时间, task AS 任务, message AS 错误信息 FROM log WHERE level = 'ERROR'"
            # 强制规则
            "强制规则:"
            "- 任务，日志相关查询必须使用log表，不得使用trading_history表"
            "- 如果错误选择了表，必须立即纠正"
            "- 列名必须与用户查询语言一致"
            "- 用户查询‘漏单’时候你需要向用户确认是想查询任务记录还是查询账单/龙门币记录"
            # 时间处理
            "时间处理规则:"
            "- trading_history,log 的时间字段需转换 需要调用 parse_datetime 工具"
            "- agent_action的current_time已是本地时间"
            "- 不确定时向用户确认"
            "- 在以下情况必须暂停执行，向用户确认后再继续:"
            "- 查询漏单的时候，如果用户没有规定是订单还是任务记录，则必须暂停执行，向用户确认"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A valid SQL SELECT statement to execute, e.g. 'SELECT * FROM users WHERE id=1'.",
                }
            },
            "required": ["query"],
        },
    },
}
