import json
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from arknights_mower.agent.tools.pick_activity_entry import pick_activity_entry
from arknights_mower.utils import config
from arknights_mower.utils.log import logger

model_name_map = {
    "deepseek": ["deepseek-chat", "https://api.deepseek.com/v1"],
    "deepseek_reasoner": ["deepseek-reasoner", "https://api.deepseek.com/v1"],
}


def _normalize_indices(indices, max_len):
    if not isinstance(indices, list):
        return []
    out = []
    seen = set()
    for x in indices:
        if not (isinstance(x, int) or str(x).isdigit()):
            continue
        i = int(x)
        if i < 0 or i >= max_len or i in seen:
            continue
        out.append(i)
        seen.add(i)
        if len(out) >= 5:
            break
    return out


def rank_activity_entries_with_agent(
    target_stage: str,
    stage_meta: dict,
    ocr_items: list[dict],
    api_key: str | None = None,
) -> list[int]:
    """
    使用单次 LLM 调用返回 OCR 候选排序 index 列表。
    """
    if api_key is None:
        api_key = config.conf.resolved_ai_key
    if not api_key or not api_key.strip():
        logger.info("rank_activity_entries_with_agent: missing api_key")
        return []
    if config.conf.ai_type not in model_name_map:
        logger.info(
            f"rank_activity_entries_with_agent: unsupported ai_type={config.conf.ai_type}"
        )
        return []

    start = time.perf_counter()
    logger.info(
        f"rank_activity_entries_with_agent: start stage={target_stage} ocr_count={len(ocr_items or [])}"
    )
    llm = ChatOpenAI(
        model=model_name_map[config.conf.ai_type][0],
        base_url=model_name_map[config.conf.ai_type][1],
        api_key=api_key,
        temperature=0,
    )
    # 本地工具先给出一版稳定排序，作为 LLM 失败时兜底
    fallback_indices = []
    try:
        tool_raw = pick_activity_entry(
            target_stage=target_stage,
            stage_meta_json=json.dumps(stage_meta or {}, ensure_ascii=False),
            ocr_items_json=json.dumps(ocr_items or [], ensure_ascii=False),
        )
        tool_obj = json.loads(tool_raw)
        fallback_indices = _normalize_indices(
            [x.get("index") for x in tool_obj.get("ranked", [])], len(ocr_items or [])
        )
        logger.info(
            f"rank_activity_entries_with_agent: fallback indices={fallback_indices[:5]}"
        )
    except Exception as e:
        logger.info(f"rank_activity_entries_with_agent: fallback build failed: {e}")
    messages = [
        SystemMessage(
            content=(
                "你是导航入口排序器。"
                '最后只返回 JSON: {"indices": [int,...], "reason": "..."}。'
                "indices 按可能性从高到低排序，最多返回 5 个。"
                "排序规则："
                "1) 若候选文本包含“活动已开放/前往章节/进入活动/SIDESTORY，优先级最高；"
                "2) 若 OCR 文本中出现“作战结束时间”，说明大概率在活动主界面，"
                "3) 优先返回活动子标题/入口相关候选，降低“终端/前往上一次作战/TO-DO/MAIN”等导航噪声词优先级，优先 “X天（表示活动倒计时）”"
                "4) 输出 indices 必须是传入 ocr_items 的合法下标；"
                "5) 时间相关文本不是可点击选项，禁止放入 indices。"
                "例如：'作战结束时间2026/03/0303:59'、'剩余16天'、'2月24日16:00:00后开启'。"
                "6) 绝对不要输出 markdown，不要输出代码块。"
            )
        ),
        HumanMessage(
            content=json.dumps(
                {
                    "target_stage": target_stage,
                    "stage_meta": stage_meta or {},
                    "ocr_items": ocr_items or [],
                },
                ensure_ascii=False,
            )
        ),
    ]
    logger.info("rank_activity_entries_with_agent: invoke single-shot")
    try:
        response = llm.invoke(messages)
        text = response.content if isinstance(response.content, str) else ""
        parsed = json.loads(text)
        indices = parsed.get("indices", [])
        parsed_indices = _normalize_indices(indices, len(ocr_items or []))
        if parsed_indices:
            logger.info(
                f"rank_activity_entries_with_agent: parsed indices={parsed_indices[:5]}, elapsed={time.perf_counter() - start:.2f}s"
            )
            return parsed_indices
        logger.info(
            f"rank_activity_entries_with_agent: empty indices, use fallback, elapsed={time.perf_counter() - start:.2f}s"
        )
        return fallback_indices
    except Exception:
        logger.info(
            f"rank_activity_entries_with_agent: response is not strict JSON, use fallback, elapsed={time.perf_counter() - start:.2f}s"
        )
        return fallback_indices
