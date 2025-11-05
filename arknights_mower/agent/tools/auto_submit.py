from arknights_mower.agent.tools.submit_issue import submit_issue


def auto_submit(
    description: str,
    issue_type: str = "Bug",
    start_time: str | None = None,
    end_time: str | None = None,
) -> str:
    """
    Convenience wrapper for submit_issue. If start_time/end_time are provided for Bug, logs will be attached.
    Otherwise, forwards to submit_issue which will ask user to provide missing time range.
    """
    return submit_issue(
        description=description,
        issue_type=issue_type,
        start_time=start_time,
        end_time=end_time,
    )


auto_submit_tool_def = {
    "type": "function",
    "function": {
        "name": "auto_submit",
        "description": "自动上报问题或需求，必要时附带日志（传入时间区间）",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "issue_type": {"type": "string", "default": "Bug"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
            },
            "required": ["description"],
        },
    },
}
