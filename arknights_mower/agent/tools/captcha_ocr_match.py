"""
验证码汉字顺序匹配工具

接收题目文字和检测到的汉字列表，使用 LLM 按题目输出点击顺序索引。

复用 agent.py 中已有的 build_llm() 构建 LLM 实例。
"""

from __future__ import annotations

import json
import re
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from arknights_mower.agent.agent import build_llm
from arknights_mower.utils import config
from arknights_mower.utils.log import logger


def match_captcha_order(
    title_text: str,
    click_items: list[dict],
    api_key: Optional[str] = None,
) -> list[int]:
    """
    调用 LLM 按题目顺序匹配点击汉字索引。

    Args:
        title_text: 题目文字，如"开始征程"
        click_items: 检测到的汉字列表，每项含 word 和 coords
        api_key: API Key，不传则使用 config 中的配置

    Returns:
        按题目顺序排列的索引列表，如 [2, 0, 1]；
        失败返回空列表。
    """
    if not click_items:
        return []

    lines = [f"{i}: '{it['word']}'" for i, it in enumerate(click_items)]
    detections_str = "\n".join(lines)

    prompt = f"""题目顺序：{title_text}
识别结果（下标从 0 开始）：
{detections_str}
请按题目顺序输出对应下标。"""

    messages = [
        SystemMessage(
            content="你是一个验证码点击排序助手。\n"
            "任务：根据题目文字和 OCR 识别结果，输出每个汉字在结果中的下标。\n"
            "规则：\n"
            "1. OCR 识别结果可能因翻转/旋转一定角度而与原字不完全一致，请根据字形/偏旁部首合理映射。\n"
            "2. 必须使用排除法找到正确匹配，优先解决字形匹配程度高的。\n"
            "2. 输出数组长度必须与题目字数一致。\n"
            "3. 输出数组元素不可重复。\n"
            "4. 不确定时输出最合理的结果。\n"
            "5. 只输出 JSON 数组，例如 [2,0,1]，不要其他内容。"
        ),
        HumanMessage(content=prompt),
    ]

    key = api_key or config.conf.resolved_ai_key
    if not key:
        logger.error("未配置 API Key，无法进行 LLM 匹配")
        return []

    try:
        llm = build_llm(key, with_tools=False)
        resp = llm.invoke(messages)
        result = resp.content.strip()
        logger.info(f"LLM 返回：{result}")
    except Exception as e:
        logger.error(f"LLM 调用失败：{e}")
        return []

    # 提取 JSON 数组
    match = re.search(r"\[[\d,\s]+\]", result)
    if match:
        try:
            indices = json.loads(match.group(0))
            if isinstance(indices, list):
                return [
                    int(i) for i in indices if isinstance(i, int) or str(i).isdigit()
                ]
        except (ValueError, json.JSONDecodeError):
            pass

    logger.error(f"LLM 返回无法解析：{result}")
    return []
