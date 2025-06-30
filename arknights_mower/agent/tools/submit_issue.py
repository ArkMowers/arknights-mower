from datetime import datetime

from arknights_mower.utils.email import Email
from arknights_mower.utils.log import get_log_by_time, logger


def submit_issue(
    description: str,
    issue_type: str = "Bug",
    start_time: str = None,
    end_time: str = None,
):
    """
    上报用户未解决的问题给开发组，可附带日志
    """
    try:
        log_files = []
        logger.debug(
            f"Submitting issue: {description}, type: {issue_type}, start_time: {start_time}, end_time: {end_time}"
        )
        if issue_type == "Bug":
            if not (start_time and end_time):
                return "请提供问题发生的起止时间（start_time 和 end_time，毫秒时间戳），以便附加日志。"
            # 直接用本地时间戳
            st = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            et = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
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
            "If reporting a bug, you must ensure the user specified the time range (start_time and end_time max 15 mins apart). "
            "User must specify both Issue and expected behavior in the description."
            "If not provided, ask the user for the time range. "
            "If user provides a time range greater than 15 minutes, return an error message."
            "Return the function result directly to the user."
            "If user only provides a time, by default, end_time will be 10 minutes after start_time."
            "If user only provides natual language description for time, convert it to a datetime and ask user for confirmation."
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
                    "type": "string",
                    "description": (
                        "Using the user's local time zone (not UTC). "
                        "The start_date must be provided in the format 'YYYY-MM-DD HH:mm:ss', e.g. '2025-06-29 14:35:00'. "
                        "if milliseconds are not provided, default to 0"
                    ),
                },
                "end_time": {
                    "type": "string",
                    "description": (
                        "Using the user's local time zone (not UTC). "
                        "The date must be provided in the format 'YYYY-MM-DD HH:mm:ss', e.g. '2025-06-29 14:35:00'. "
                        "if milliseconds are not provided, default to 0"
                        "the end_time must be at most 15 minutes after start_time"
                    ),
                },
            },
            "required": ["description"],
        },
    },
}
