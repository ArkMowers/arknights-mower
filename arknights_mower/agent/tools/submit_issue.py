from datetime import datetime
from typing import Optional

from arknights_mower.utils.email import Email
from arknights_mower.utils.log import get_log_by_time


def submit_issue(
    description: str,
    issue_type: str = "Bug",
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
):
    """
    上报用户未解决的问题给开发组，可附带日志
    """
    try:
        log_files = []

        if issue_type == "Bug":
            if not (start_time and end_time):
                return "请提供问题发生的起止时间（start_time 和 end_time，毫秒时间戳），以便附加日志。"
            st = datetime.fromtimestamp(start_time / 1000.0)
            et = datetime.fromtimestamp(end_time / 1000.0)
            print(
                f"Submitting issue: {description}, type: {issue_type}, start_time: {st}, end_time: {et}"
            )
            log_files = get_log_by_time(et)
            if not log_files:
                return "未找到对应时间的日志文件，无法上报。"
            body = f"<p>Bug 发生时间区间:{st}--{et}</p><br><p>{description}</p>"
        else:
            body = description
        email = Email(
            body,
            "Mower " + issue_type,
            None,
            attach_files=None if issue_type != "Bug" else log_files,
        )
        email.send(["354013233@qq.com"])
        return "问题已成功上报，感谢您的反馈！"
    except Exception as e:
        print(e)
        return f"反馈发送失败，请确保邮箱功能正常使用\n{e}"


submit_issue_tool_def = {
    "type": "function",
    "function": {
        "name": "submit_issue",
        "description": (
            "Attach log with issue description to developer team's email. "
            "If reporting a bug, you must ensure the user specified the time range (start_time and end_time, both as float milliseconds since epoch, max 15 mins apart). "
            "If not provided, ask the user for the time range. "
            "If user provides a time range greater than 15 minutes, return an error message."
            "Return the function result directly to the user."
            "You have to convert the time range to float milliseconds since epoch before calling the function."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "Issue or feature request description, minimum 20 characters.",
                    "default": "",
                },
                "issue_type": {
                    "type": "string",
                    "description": "Bug or feature request",
                    "default": "Bug",
                },
                "start_time": {
                    "type": "number",
                    "description": "Start time of the issue (float, milliseconds since epoch). Required for bug report.",
                    "default": None,
                },
                "end_time": {
                    "type": "number",
                    "description": "End time of the issue (float, milliseconds since epoch). Required for bug report. Must be within 15 minutes of start_time.",
                    "default": None,
                },
            },
            "required": ["description"],
        },
    },
}
