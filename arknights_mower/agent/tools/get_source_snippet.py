import json
import os
from dataclasses import asdict

from arknights_mower.agent.tools.debuginfo import DebugInfo


def get_source_snippet(file_path: str, line_number: int, context: int = 10) -> str:
    """
    提取指定文件中某一行上下文的源代码段，自动基于项目目录修正路径。
    """
    try:
        # 基于项目根路径修正路径（例如运行目录或 app 跟路径）
        project_root = os.path.abspath(os.getcwd())  # 或使用 os.path.dirname(__file__)
        abs_path = file_path

        if not os.path.exists(file_path):
            # 尝试从相对路径恢复绝对路径
            rel_path = os.path.relpath(file_path, start="/")
            candidate = os.path.join(project_root, rel_path)
            if os.path.exists(candidate):
                abs_path = candidate

        with open(abs_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        start = max(0, line_number - context - 1)
        end = min(len(lines), line_number + context)
        snippet = "".join(lines[start:end])

        info = DebugInfo(
            file_path=abs_path, line_number=line_number, source_code=snippet
        )
        return json.dumps(asdict(info))

    except Exception as e:
        info = DebugInfo(
            file_path=file_path,
            line_number=line_number,
            source_code=f"读取失败: {str(e)}",
        )
        return json.dumps(asdict(info))


get_source_snippet_tool_def = {
    "type": "function",
    "function": {
        "name": "get_source_snippet",
        "description": (
            "根据文件路径和行号提取报错行及其上下文的源代码，用于错误定位。"
            "extract_stack_paths 工具提取的文件路径和行号必须调用此工具获取源代码片段。"
            "如果 extract_stack_paths 工具返回多个文件路径和行号，则你自行分析最相关的文件和行号。"
            "该工具不能直接调用，必须在 extract_stack_paths 工具返回结果后调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "出错的源代码文件路径"},
                "line_number": {
                    "type": "integer",
                    "description": "出错行号，基于 1 的索引",
                },
                "context": {
                    "type": "integer",
                    "description": "上下文行数，默认10",
                    "default": 10,
                },
            },
            "required": ["file_path", "line_number"],
        },
    },
}
