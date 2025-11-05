import json
import os
import time
from typing import List

import faiss
from sentence_transformers import SentenceTransformer

from arknights_mower.utils.log import logger

_BASE_DIR = os.path.dirname(__file__)
_KB_DIR = os.path.join(_BASE_DIR, "knowledgebase")
_INDEX_PATH = os.path.join(_KB_DIR, "skill_faiss.index")
_META_PATH = os.path.join(_KB_DIR, "skill_faiss_meta.json")



def _load_index_and_meta():
    if not (os.path.exists(_INDEX_PATH) and os.path.exists(_META_PATH)):
        raise FileNotFoundError(
            f"FAISS index/meta not found. Build with build_skill_faiss.py into {_KB_DIR}"
        )
    index = faiss.read_index(_INDEX_PATH)
    with open(_META_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)
    try:
        logger.debug(f"base_skill_faq: 索引加载完成 entries={len(meta)}")
    except Exception:
        pass
    return index, meta


_faiss_index, _meta = None, None
_model = None


def _get_index():
    global _faiss_index, _meta
    if _faiss_index is None or _meta is None:
        _faiss_index, _meta = _load_index_and_meta()
    return _faiss_index, _meta


def _get_model():
    global _model
    if _model is None:
        t0 = time.time()
        _model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
        try:
            logger.debug(
                f"base_skill_faq: 模型加载完成 cost={int((time.time() - t0) * 1000)}ms"
            )
        except Exception:
            pass
    return _model


def base_skill_faq(query: str, top_k: int = 3) -> str:
    index, meta = _get_index()
    model = _get_model()
    t0 = time.time()
    vec = model.encode([query], normalize_embeddings=True).astype("float32")
    t1 = time.time()
    # 检索更多候选以便后续重排过滤
    search_k = max(top_k, 10)
    D, I = index.search(vec, search_k)
    try:
        scores = [round(float(x), 4) for x in D[0].tolist()]
        idxs = I[0].tolist()
        logger.debug(
            f"base_skill_faq: 检索 q='{query}' top_k={top_k} encode={int((t1 - t0) * 1000)}ms search={int((time.time() - t1) * 1000)}ms scores={scores} idx={idxs}"
        )
    except Exception:
        pass
    # 根据查询词对候选进行重排：优先名称/术语包含查询词的条目
    q_core = (query or "").replace("技能", "").replace("术语", "").strip()

    def compute_boost(m: dict) -> float:
        b = 0.0
        name = m.get("op_name") or m.get("term_name") or ""
        desc = m.get("desc") or m.get("Description") or ""
        if q_core and name and q_core in name:
            b += 0.6
        if q_core and name and name in q_core:
            b += 0.3
        if q_core and q_core in desc:
            b += 0.2
        return b

    seen = set()
    candidates = []  # (final_score, meta_idx)
    for pos, ridx in enumerate(I[0]):
        try:
            base = float(D[0][pos])
        except Exception:
            base = 0.0
        meta_idx = int(ridx)
        if not (0 <= meta_idx < len(meta)) or meta_idx in seen:
            continue
        seen.add(meta_idx)
        m = meta[meta_idx]
        candidates.append((base + compute_boost(m), meta_idx))

    candidates.sort(key=lambda x: x[0], reverse=True)
    chosen = candidates[:top_k]

    results: List[str] = []
    for _, meta_idx in chosen:
        m = meta[meta_idx]
        if "op_name" in m and "skills" in m:
            # New grouped schema: list all skills
            lines = [f"干员：{m.get('op_name', '')}"]
            for s in m.get("skills") or []:
                lines.append(
                    f"- 技能：{s.get('skillname', '')} {s.get('phase_level', '')}\n  描述：{s.get('desc', '')}"
                )
            results.append("\n".join(lines) + "\n")
        elif "op_name" in m:
            results.append(
                f"干员：{m.get('op_name', '')} 技能：{m.get('skillname', '')}\n描述：{m.get('desc', '')}\n"
            )
        elif "term_name" in m:
            term_line = f"术语：{m.get('term_name', '')}"
            if m.get("term_id") or m.get("termId"):
                term_line += f" (ID: {m.get('term_id') or m.get('termId')})"
            results.append(
                term_line + f"\n描述：{m.get('desc') or m.get('Description', '')}\n"
            )
        else:
            txt = m.get("text") or m.get("desc") or ""
            results.append(txt[:400])
    if results:
        try:
            logger.debug(
                f"base_skill_faq: 向量检索命中 count={len(results)}, top_result='{results[0][:30]}...'"
            )
            logger.debug("base_skill_faq: 返回结果:\n" + "\n".join(results))
        except Exception:
            pass

    # Fallback: if nothing relevant appears, try substring match in meta
    def fmt(m) -> str:
        if "op_name" in m:
            return f"干员：{m.get('op_name', '')} 技能：{m.get('skillname', '')}\n描述：{m.get('desc', '')}\n"
        if "term_name" in m:
            term_line = f"术语：{m.get('term_name', '')}"
            if m.get("term_id") or m.get("termId"):
                term_line += f" (ID: {m.get('term_id') or m.get('termId')})"
            return term_line + f"\n描述：{m.get('desc') or m.get('Description', '')}\n"
        txt = m.get("text") or m.get("desc") or ""
        return txt[:400]

    if not results:
        try:
            logger.debug("base_skill_faq: 触发兜底子串匹配")
        except Exception:
            pass
        q = query.strip()
        q_alt = q.replace("技能", "")
        tokens = [t for t in {q, q_alt} if t]
        fallback = []
        for m in meta:
            s = (
                m.get("op_name", "")
                + " "
                + m.get("skillname", "")
                + " "
                + m.get("desc", "")
                + " "
                + m.get("term_name", "")
                + " "
                + m.get("Description", "")
            ).strip()
            if any(tok and (tok in s) for tok in tokens):
                fallback.append(fmt(m))
                if len(fallback) >= top_k:
                    break
        if fallback:
            return "\n".join(fallback)
        return "未找到相关技能信息"
    return "\n".join(results)


base_skill_faq_tool_def = {
    "type": "function",
    "function": {
        "name": "base_skill_faq",
        "description": "根据用户问题检索干员技能相关信息，返回最相关的技能描述",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "用户关于干员技能的提问"},
                "top_k": {"type": "integer", "default": 3},
            },
            "required": ["query"],
        },
    },
}
