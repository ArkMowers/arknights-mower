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
            "ALWAYS return the HTML table string exactly as received from the tool."
            "Execute a SQL query on the specified database and return the result. "
            "DO NOT reformat the result. "
            "You must generate a valid SQL SELECT statement according to the user's request and the provided table schema. "
            "If the query is not a SELECT, return an error. "
            "If the query is too complex or dangerous, ask the user for confirmation."
            "agent_action(name TEXT,agent_current_room TEXT,current_room TEXT,is_high INTEGER,agent_group TEXT,mood REAL,current_time TEXT) 记录了明日方舟干员进出基建的相关信息，包括干员名称、当前房间、是否在高效状态、干员组、心情值和当前时间。"
            "如果用户查询干员位置，相关信息，请检索 agent_current_room 是干员当前位置然后 current_room是被转移去的房间"
            "如果current_room是空值则表示该干员不在任何房间中, current_room 如果是以 dorm_ 开头则表示该干员在宿舍中，在休息（同样适用于agent_current_room）"
            "如果agent_current_room 是非宿舍房间，current_room 是宿舍，则表示改干员从工作站移到了宿舍中休息（下班）,相反，则表示干员从宿舍中休息回到了工作站（上班）"
            "trading_history(time INTEGER PRIMARY KEY,server_date TEXT,type TEXT,price INTEGER) 记录了所有龙门币订单(跑单，插拔)的相关信息，包括时间、服务器时间、类型和价格。如果用户查询是否有漏单，则 检索 type 为 '漏单' 的记录"
            "如果用户查询 trading_history 并且带有特定的时间（不是日期），则query 的时候需要对应 time 字段转换为本地时间。Example: strftime('%Y-%m-%d %H:%M:%S', time, 'unixepoch', 'localtime') AS local_time, 并且在查询结果中返回 local_time 字段。agent_action 里面的 current_time 字段已经是本地时间了，不需要转换。"
            "If user provides a time for query database convert it to local time"
            "返还条目的表格的列名应该和用户输入的语言相同（生成SQL语句的时候，表格的列名需要转化成对应语言）Example: 如果用户输入 '查询最近10条订单信息 Select 'strftime('%Y-%m-%d %H:%M:%S', time, 'unixepoch', 'localtime') AS 本地时间, server_date AS 服务器时间, type AS 类型, price AS 价格 FROM trading_history ORDER BY time DESC LIMIT 10"
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
