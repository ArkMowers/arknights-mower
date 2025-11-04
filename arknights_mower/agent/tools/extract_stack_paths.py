import json
import re
from dataclasses import asdict

from arknights_mower.agent.tools.debuginfo import DebugInfo


def extract_stack_paths(text: str) -> str:
    print("正在提取栈追踪信息...", text)
    pattern = re.compile(
        r"(?:File|at)\s+['\"]?(.*?\.(?:py|cs|java|js|ts))['\"]?(?:[:,\s]+line\s+)?(\d+)?",
        re.IGNORECASE,
    )
    matches = pattern.findall(text)
    debug_objects = [
        DebugInfo(file_path=m[0], line_number=int(m[1]) if m[1] else None)
        for m in matches
    ]
    return json.dumps([asdict(d) for d in debug_objects])


extract_stack_paths_tool_def = {
    "type": "function",
    "function": {
        "name": "extract_stack_paths",
        "description": (
            "从用户提供的文本中提取python的栈追踪信息，"
            "提取出文件路径和可选的行号。适用于错误日志、异常堆栈等情况。"
            "如果get_faq工具输出 {[FAQ未命中] 未找到相关常见问题，请尝试其他工具。} 必须调用此工具进行进一步分析。"
            "如果get_faq工具输出的结果你判断相关性不大，你也可以直接调用此工具。"
            "如果结果不为空则调用get_source_snippet工具获取源代码片段。"
            "如果结果为多个而且报错不一样，则你需要返回报错信息以及相关内容给用户让用户确认其中一条"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "包含错误日志或异常栈追踪的完整文本",
                }
            },
            "required": ["text"],
        },
    },
}
