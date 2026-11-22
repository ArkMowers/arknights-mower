import json
from dataclasses import asdict
from itertools import islice
from pathlib import Path

from arknights_mower.agent.tools.debuginfo import DebugInfo

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _PACKAGE_ROOT.parent
_SOURCE_SUFFIXES = {".py", ".js", ".ts", ".vue", ".java", ".cs"}
_MAX_SOURCE_SCAN_BYTES = 8 * 1024**2
_MAX_SOURCE_LINE_BYTES = 64 * 1024
_MAX_SNIPPET_BYTES = 24 * 1024
_MAX_CONTEXT = 50


def _allowed_source_path(file_path: str) -> Path:
    if not isinstance(file_path, str) or not file_path or "\0" in file_path:
        raise ValueError("不允许读取此文件")
    supplied = Path(file_path)
    candidates = (
        [supplied]
        if supplied.is_absolute()
        else [
            _PROJECT_ROOT / supplied,
            _PACKAGE_ROOT / supplied,
        ]
    )
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if not resolved.is_file() or resolved.suffix.lower() not in _SOURCE_SUFFIXES:
            continue
        in_package = (
            resolved.is_relative_to(_PACKAGE_ROOT) and resolved.suffix.lower() == ".py"
        )
        in_ui = resolved.is_relative_to(_PROJECT_ROOT / "ui" / "src")
        root_source = resolved in {
            _PROJECT_ROOT / "server.py",
            _PROJECT_ROOT / "webview_ui.py",
        }
        if in_package or in_ui or root_source:
            return resolved
    raise ValueError("不允许读取此文件")


def _bounded_source_lines(stream):
    remaining = _MAX_SOURCE_SCAN_BYTES
    while raw := stream.readline(min(remaining, _MAX_SOURCE_LINE_BYTES) + 1):
        if len(raw) > remaining:
            raise ValueError("源码超过扫描字节上限")
        if len(raw) > _MAX_SOURCE_LINE_BYTES:
            raise ValueError("源码行超过扫描字节上限")
        remaining -= len(raw)
        yield from raw.splitlines(keepends=True)


def get_source_snippet(file_path: str, line_number: int, context: int = 10) -> str:
    """
    提取指定文件中某一行上下文的源代码段，自动基于项目目录修正路径。
    """
    try:
        if type(line_number) is not int or line_number < 1:
            raise ValueError("行号无效")
        if type(context) is not int or not 0 <= context <= _MAX_CONTEXT:
            raise ValueError("上下文行数无效")
        source_path = _allowed_source_path(file_path)
        start = max(0, line_number - context - 1)
        end = line_number + context
        remaining = _MAX_SNIPPET_BYTES
        lines = []
        with source_path.open("rb") as source:
            for raw in islice(_bounded_source_lines(source), start, end):
                remaining -= len(raw)
                if remaining < 0:
                    raise ValueError("源码片段超过返回字节上限")
                lines.append(
                    raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
                )

        info = DebugInfo(
            file_path=str(source_path),
            line_number=line_number,
            source_code="".join(lines),
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
            "使用用户明确提供、extract_stack_paths 提取或 get_riic_knowledge 的 code_diagnosis 实际扫描返回的有效路径和正整数行号，不猜测行号。"
            "仅支持当前安装目录允许的项目源文件，上下文行数为0到50，默认10。"
            "返回包含 source_code 的 JSON；读取失败时如实说明，不声称已读取源码。"
            "多个栈帧优先读取与异常最相关的位置。"
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
