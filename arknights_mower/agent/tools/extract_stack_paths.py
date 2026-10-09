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
            "从已有错误堆栈中提取 Python、C#、Java、JavaScript 或 TypeScript 文件位置，"
            "提取出文件路径和可选的行号。适用于错误日志、异常堆栈等情况。"
            "没有堆栈时不要仅因 FAQ 未命中就调用。"
            "返回 JSON 数组，行号可能为空；仅对有效路径和正整数行号调用 get_source_snippet。"
            "多个栈帧按异常关联程度选择，不要求用户逐帧选择；空结果时说明未提取到位置。"
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
