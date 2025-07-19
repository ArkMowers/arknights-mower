from datetime import datetime


def parse_datetime(time_str: str) -> str:
    """
    将格式为 'YYYY-MM-DD HH:MM:SS' 的时间字符串转换为 Unix 时间戳字符串。
    """
    try:
        print(f"解析时间字符串: {time_str}")
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        return str(int(dt.timestamp()))
    except Exception as e:
        print(e)
        return f"无法解析时间格式: {e}"
        
parse_datetime_tool_def = {
    "type": "function",
    "function": {
        "name": "parse_datetime",
        "description": (
            "将用户输入的格式为 'YYYY-MM-DD HH:MM:SS' 的时间字符串转换为 Unix 时间戳字符串。"
            "这个时间戳可以用于查询数据库中 time 字段（INTEGER 类型）的记录。"
            "Example: 输入 '2025-07-04 14:30:00'，输出 '1751639400'。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "time_str": {
                    "type": "string",
                    "description": "格式为 YYYY-MM-DD HH:MM:SS 的时间字符串。",
                }
            },
            "required": ["time_str"]
        }
    }
}
