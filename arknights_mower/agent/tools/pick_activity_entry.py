import json
import re


def _safe_json_loads(payload: str):
    try:
        return json.loads(payload) if payload else []
    except Exception:
        return []


def _build_keywords(target_stage: str, stage_meta_json: str):
    keywords = {target_stage}
    meta = _safe_json_loads(stage_meta_json)
    if isinstance(meta, dict):
        for key in ("zoneNameSecond", "zoneNameFirst", "name", "subTitle"):
            val = meta.get(key)
            if val:
                keywords.add(str(val))
    return [k for k in keywords if isinstance(k, str) and k.strip()]


def _score_text(text: str, keywords: list[str], target_stage: str):
    score = 0.0
    lower = text.lower()
    noise_tokens = ["前往上一次作战", "to-do", "attention", "终端"]
    if any(token in lower for token in noise_tokens):
        score -= 6.0
    if re.fullmatch(r"\d+/\d+|\d+天|\d+", text):
        score -= 5.0
    # 时间/日期信息通常是说明文案，不是入口
    if (
        re.search(r"\d{4}/\d{2}/\d{2}", text)
        or re.search(r"\d{1,2}:\d{2}(:\d{2})?", text)
        or re.search(r"\d{1,2}月\d{1,2}日", text)
    ):
        score -= 5.0
    if text in keywords:
        score += 8.0
    for kw in keywords:
        if kw and kw in text:
            score += 4.0
    m = re.match(r"^([A-Z]{1,3})-\d+$", target_stage or "")
    if m:
        prefix = m.group(1)
        if re.match(rf"^{prefix}-\d+$", text):
            score += 2.0
    return score


def pick_activity_entry(target_stage: str, stage_meta_json: str, ocr_items_json: str):
    """
    对 OCR 候选做规则打分，返回排序结果，供 Agent 最终决策。
    """
    items = _safe_json_loads(ocr_items_json)
    keywords = _build_keywords(target_stage, stage_meta_json)
    ranked = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        conf = float(item.get("score", 0) or 0)
        if not text:
            continue
        rule_score = _score_text(text, keywords, target_stage)
        final = rule_score + conf
        ranked.append(
            {
                "index": idx,
                "text": text,
                "score": final,
                "rule_score": rule_score,
                "ocr_score": conf,
            }
        )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    best_index = ranked[0]["index"] if ranked else -1
    return json.dumps(
        {"best_index": best_index, "ranked": ranked[:8]}, ensure_ascii=False
    )


pick_activity_entry_tool_def = {
    "type": "function",
    "function": {
        "name": "pick_activity_entry",
        "description": (
            "Score OCR candidates for activity entry selection. "
            "Input is target stage, stage metadata json, and OCR item list json."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target_stage": {"type": "string"},
                "stage_meta_json": {"type": "string"},
                "ocr_items_json": {"type": "string"},
            },
            "required": ["target_stage", "stage_meta_json", "ocr_items_json"],
        },
    },
}
