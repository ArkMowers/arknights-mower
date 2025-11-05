import ast
import glob
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

from arknights_mower.agent.memory.file_hash import sha256_bytes, sha256_file
from arknights_mower.agent.memory.method_cache import MethodCache
from arknights_mower.utils import config
from arknights_mower.utils.log import logger

try:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI
except Exception:
    ChatOpenAI = None  # type: ignore
    SystemMessage = HumanMessage = None  # type: ignore


_BASE_DIR = os.path.dirname(__file__)
_KB_DIR = os.path.join(_BASE_DIR, "knowledgebase")
_SOURCES_JSON = os.path.join(_KB_DIR, "behavior_sources.json")

_EMBED_MODEL = None


def _get_model():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        _EMBED_MODEL = SentenceTransformer("BAAI/bge-large-zh-v1.5")
    return _EMBED_MODEL


def _load_sources() -> List[str]:
    entries: List[str] = []
    if os.path.exists(_SOURCES_JSON):
        try:
            with open(_SOURCES_JSON, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                entries = [str(x) for x in raw]
        except Exception:
            entries = []

    if not entries:
        pkg_root = Path(_BASE_DIR).parents[2]
        pattern = str(pkg_root / "arknights_mower" / "**" / "*.py")
        entries = [pattern]

    files: List[str] = []
    for e in entries:
        if any(ch in e for ch in ["*", "?", "["]):
            files.extend(glob.glob(e, recursive=True))
        else:
            p = Path(e)
            if p.is_dir():
                files.extend([str(pp) for pp in p.rglob("*.py")])
            elif p.exists():
                files.append(str(p))
    final = []
    seen = set()
    for f in files:
        try:
            pf = str(Path(f).resolve())
        except Exception:
            continue
        if pf in seen:
            continue
        if os.path.isfile(pf):
            seen.add(pf)
            final.append(pf)
    return final


def _embed_texts(texts: List[str]) -> np.ndarray:
    model = _get_model()
    vecs = model.encode(texts, normalize_embeddings=True)
    if not isinstance(vecs, np.ndarray):
        vecs = np.array(vecs, dtype=np.float32)
    return vecs.astype("float32")


def _select_files_fn(question: str, top_k: int = 6) -> List[str]:
    files = _load_sources()
    if len(files) > 800:
        files = files[:800]
    descriptors: List[str] = []
    for fp in files:
        try:
            text = Path(fp).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        doc = None
        try:
            mod = ast.parse(text)
            doc = ast.get_docstring(mod)
        except Exception:
            doc = None
        head = text[:1200]
        mid = text[len(text) // 2 : len(text) // 2 + 600] if len(text) > 3000 else ""
        tail = text[-600:] if len(text) > 2400 else ""
        desc = f"路径:{fp}\n文档:{doc or ''}\n片段:{head}\n{mid}\n{tail}"
        descriptors.append(desc)

    q_vec = _embed_texts([question])
    d_vecs = _embed_texts(descriptors)
    sims = (q_vec @ d_vecs.T)[0]
    idxs = np.argsort(-sims)[: max(1, top_k)]
    seen = set()
    ordered = []
    for i in idxs:
        p = files[int(i)]
        if p in seen:
            continue
        seen.add(p)
        ordered.append(p)
    logger.debug(
        f"behavior_faq: 文件检索完成，候选={len(files)}，选中Top{top_k}={len(ordered)}"
    )
    return ordered


def _split_by_functions(text: str) -> List[Tuple[int, int, str, str]]:
    chunks: List[Tuple[int, int, str, str]] = []
    try:
        module = ast.parse(text)
    except Exception:
        return chunks
    lines = text.splitlines()

    def slice_lines(s: int, e: int) -> str:
        s0 = max(1, s)
        e0 = min(len(lines), e)
        if s0 > e0:
            return ""
        return "\n".join(lines[s0 - 1 : e0])

    for node in module.body:
        if isinstance(node, ast.FunctionDef):
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", None)
            if isinstance(start, int) and isinstance(end, int):
                chunks.append(
                    (start, end, slice_lines(start, end), f"def {node.name}(... )")
                )
        elif isinstance(node, ast.ClassDef):
            for inner in node.body:
                if isinstance(inner, ast.FunctionDef):
                    start = getattr(inner, "lineno", None)
                    end = getattr(inner, "end_lineno", None)
                    if isinstance(start, int) and isinstance(end, int):
                        chunks.append(
                            (
                                start,
                                end,
                                slice_lines(start, end),
                                f"class {node.name}.{inner.name}(... )",
                            )
                        )
    return chunks


def _split_into_chunks_fallback(
    text: str, *, lines_per_chunk: int = 240, overlap: int = 40
) -> List[Tuple[int, int, str, str]]:
    lines = text.splitlines()
    n = len(lines)
    chunks: List[Tuple[int, int, str, str]] = []
    if n == 0:
        return chunks
    step = max(1, lines_per_chunk - overlap)
    start = 0
    while start < n:
        end = min(n, start + lines_per_chunk)
        chunk = "\n".join(lines[start:end])
        label = f"lines {start + 1}-{end}"
        chunks.append((start + 1, end, chunk, label))
        if end == n:
            break
        start += step
    return chunks


def _select_relevant_chunks(
    question: str,
    file_contents: Dict[str, str],
    *,
    top_chunks_per_file: int = 2,
) -> Dict[str, List[Tuple[int, int, str, str]]]:
    q_vec = _embed_texts([question])[0]
    result: Dict[str, List[Tuple[int, int, str, str]]] = {}
    for fp, content in file_contents.items():
        chunks = _split_by_functions(content)
        if not chunks:
            chunks = _split_into_chunks_fallback(content)
        if not chunks:
            result[fp] = []
            continue
        texts = [f"{label}\n{code[:1800]}" for (_, _, code, label) in chunks]
        c_vecs = _embed_texts(texts)
        sims = (np.expand_dims(q_vec, 0) @ c_vecs.T)[0]
        order = np.argsort(-sims)
        picks: List[Tuple[int, int, str, str]] = []
        picked_idx = set()
        for oi in order:
            idx = int(oi)
            if idx in picked_idx:
                continue
            picks.append(chunks[idx])
            picked_idx.add(idx)
            if len(picks) >= max(1, top_chunks_per_file):
                break
        result[fp] = picks
        logger.debug(
            f"behavior_faq: 方法级选片 文件={Path(fp).name} 片段数={len(chunks)} 选中Top{top_chunks_per_file}={len(picks)}"
        )
    return result


def _summarize_method(
    question: str, file_path: str, start: int, end: int, code: str, label: str
) -> str:
    api_key = getattr(config.conf, "ai_key", "") if hasattr(config, "conf") else ""
    ai_type = getattr(config.conf, "ai_type", "") if hasattr(config, "conf") else ""
    if not api_key or ChatOpenAI is None or SystemMessage is None:
        try:
            node = ast.parse(code).body[0]
            doc = ast.get_docstring(node) or ""
        except Exception:
            doc = ""
        brief = doc[:400] if doc else code[:800]
        return f"方法 {label} 行{start}-{end} 概述：\n{brief}"

    model_name_map = {
        "deepseek": ["deepseek-chat", "https://api.deepseek.com/v1"],
        "deepseek_reasoner": ["deepseek-reasoner", "https://api.deepseek.com/v1"],
    }
    if ai_type not in model_name_map:
        return f"方法 {label} 行{start}-{end} 片段：\n{code[:1200]}"

    try:
        llm = ChatOpenAI(
            model=model_name_map[ai_type][0],
            base_url=model_name_map[ai_type][1],
            api_key=api_key,
            temperature=0,
        )
        system_prompt = (
            "你是代码分析助手。请基于给定的方法源码，回答用户问题并给出该方法的职责与关键流程。"
            "要求简洁分条，必要时引用少量关键片段，避免臆测。"
        )
        human_prompt = (
            f"问题：{question}\n"
            f"文件：{file_path}，方法：{label}，行号：{start}-{end}\n"
            f"源码如下：\n{code}"
        )
        msg = llm.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)]
        )
        if (
            hasattr(msg, "content")
            and isinstance(msg.content, str)
            and msg.content.strip()
        ):
            logger.debug(
                f"behavior_faq: LLM总结 方法={label} 行={start}-{end} 文件={Path(file_path).name}"
            )
            return msg.content
    except Exception:
        pass
    return f"方法 {label} 行{start}-{end} 片段：\n{code[:1200]}"


def _summarize_methods_with_cache(
    question: str, chunks_by_file: Dict[str, List[Tuple[int, int, str, str]]]
) -> str:
    cache = MethodCache()
    candidates: List[
        Tuple[float, str, int, int, str, str]
    ] = []  # (score, fp, s, e, code, label)
    # For presentation order, we can re-score later; here preserve per-file order
    for fp, picks in chunks_by_file.items():
        for s, e, code, label in picks:
            candidates.append((1.0, fp, s, e, code, label))
    if not candidates:
        return "[NO_ANSWER] 未定位到相关方法或实现片段。"
    max_methods = min(6, len(candidates))
    selected = candidates[:max_methods]

    parts: List[str] = []
    for _, fp, s, e, code, label in selected:
        abs_fp = str(Path(fp).resolve())
        try:
            file_digest = sha256_file(abs_fp)
        except Exception:
            file_digest = ""
        method_key = f"{abs_fp}::{label}"
        method_hash = sha256_bytes(code.strip().encode("utf-8"))

        entry = cache.get(method_key, method_hash)
        if entry is not None:
            # backfill embedding if missing
            if not entry.method_embedding:
                m_vec = _embed_texts([f"{label}\n{code[:1800]}"])[0]
                try:
                    cache.put(
                        method_key,
                        method_hash,
                        entry.summary,
                        file_path=abs_fp,
                        file_sha256=file_digest,
                        start_line=s,
                        end_line=e,
                        model=entry.model or "behavior_faq-method",
                        metadata=entry.metadata
                        or {"tool": "behavior_faq", "label": label},
                        method_embedding=m_vec.tolist(),
                    )
                    logger.debug(
                        f"behavior_faq: 向量回填 方法={label} 行={s}-{e} 文件={Path(abs_fp).name}"
                    )
                except Exception:
                    pass
            parts.append(
                f"文件: {abs_fp}\n方法: {label} 行{s}-{e}\n文件SHA256: {file_digest}\n(缓存命中 x{entry.hit_count})\n"
                + entry.summary
            )
            continue

        summary = _summarize_method(question, abs_fp, s, e, code, label)
        m_vec = _embed_texts([f"{label}\n{code[:1800]}"])[0]
        cache.put(
            method_key,
            method_hash,
            summary,
            file_path=abs_fp,
            file_sha256=file_digest,
            start_line=s,
            end_line=e,
            model="behavior_faq-method",
            metadata={"tool": "behavior_faq", "label": label},
            method_embedding=m_vec.tolist(),
        )
        logger.debug(
            f"behavior_faq: 新摘要写入 方法={label} 行={s}-{e} 文件={Path(abs_fp).name}"
        )
        parts.append(
            f"文件: {abs_fp}\n方法: {label} 行{s}-{e}\n文件SHA256: {file_digest}\n"
            + summary
        )

    return "\n\n".join(parts)


def _summarize_fn(question: str, file_contents: Dict[str, str]) -> str:
    cache = MethodCache()

    def _cos(a: np.ndarray, b: np.ndarray) -> float:
        an = np.linalg.norm(a)
        bn = np.linalg.norm(b)
        if an == 0 or bn == 0:
            return -1.0
        return float(np.dot(a, b) / (an * bn))

    def _embed_method_text(label: str, code: str) -> np.ndarray:
        text = f"{label}\n{code[:1800]}"
        return _embed_texts([text])[0]

    files = list(file_contents.keys())
    if not files:
        return "[NO_ANSWER] 未提供相关源码。"
    q_vec = _embed_texts([question])[0]

    # Fast path: use cached method embeddings
    cached_entries = cache.list_by_files(files, only_with_embedding=True)
    scored_cached: List[Tuple[float, object]] = []
    for e in cached_entries:
        try:
            emb = np.array(e.method_embedding, dtype=np.float32)
        except Exception:
            continue
        scored_cached.append((_cos(q_vec, emb), e))
    scored_cached.sort(key=lambda x: x[0], reverse=True)

    max_methods = 6
    selected_parts: List[str] = []
    selected_keys = set()
    for score, e in scored_cached[:max_methods]:
        mk = (e.file_path, e.method_key)
        selected_keys.add(mk)
        try:
            file_digest = sha256_file(e.file_path) if e.file_path else ""
        except Exception:
            file_digest = ""
        selected_parts.append(
            f"文件: {e.file_path}\n方法: {e.method_key.split('::', 1)[-1]} 行{e.start_line}-{e.end_line}\n文件SHA256: {file_digest}\n(缓存方法向量命中 x{e.hit_count + 1})\n"
            + e.summary
        )
    if selected_parts:
        logger.debug(
            f"behavior_faq: 快速命中已缓存方法向量 数量={len(selected_parts)} 文件数={len(files)}"
        )
        # Fast-path return to avoid downstream failures blocking output
        return "\n\n".join(selected_parts)

    remaining = max_methods - len(selected_parts)
    if remaining > 0:
        # Augment with uncached methods via AST chunking
        chunks_by_file = _select_relevant_chunks(
            question, file_contents, top_chunks_per_file=2
        )
        picks_flat: List[
            Tuple[float, str, int, int, str, str]
        ] = []  # (sim, fp, s, e, code, label)
        for fp, picks in chunks_by_file.items():
            for s, e, code, label in picks:
                mk = (str(Path(fp).resolve()), f"{label}")
                if mk in selected_keys:
                    continue
                m_vec = _embed_method_text(label, code)
                sim = _cos(q_vec, m_vec)
                picks_flat.append((sim, str(Path(fp).resolve()), s, e, code, label))
        picks_flat.sort(key=lambda x: x[0], reverse=True)

        for sim, fp, s, e, code, label in picks_flat[:remaining]:
            try:
                file_digest = sha256_file(fp)
            except Exception:
                file_digest = ""
            method_key = f"{fp}::{label}"
            method_hash = sha256_bytes(code.strip().encode("utf-8"))
            existing = cache.get(method_key, method_hash)
            if existing is not None:
                selected_parts.append(
                    f"文件: {fp}\n方法: {label} 行{s}-{e}\n文件SHA256: {file_digest}\n(缓存命中 x{existing.hit_count})\n"
                    + existing.summary
                )
                logger.debug(
                    f"behavior_faq: 摘要缓存命中 方法={label} 行={s}-{e} 文件={Path(fp).name}"
                )
                continue
            summary = _summarize_method(question, fp, s, e, code, label)
            m_vec = _embed_method_text(label, code)
            cache.put(
                method_key,
                method_hash,
                summary,
                file_path=fp,
                file_sha256=file_digest,
                start_line=s,
                end_line=e,
                model="behavior_faq-method",
                metadata={"tool": "behavior_faq", "label": label, "sim": float(sim)},
                method_embedding=m_vec.tolist(),
            )
            logger.debug(
                f"behavior_faq: 新摘要写入 方法={label} 行={s}-{e} 文件={Path(fp).name} sim={sim:.3f}"
            )
            selected_parts.append(
                f"文件: {fp}\n方法: {label} 行{s}-{e}\n文件SHA256: {file_digest}\n"
                + summary
            )

    if selected_parts:
        logger.debug(f"behavior_faq: 返回聚合摘要 数量={len(selected_parts)}")
        return "\n\n".join(selected_parts)
    return "[NO_ANSWER] 未定位到相关方法或实现片段。"


def _embed_fn(text: str) -> List[float]:
    v = _embed_texts([text])[0]
    return v.tolist()


def behavior_faq(question: str, top_k: int = 6) -> str:
    files = _select_files_fn(question, top_k=top_k)
    contents: Dict[str, str] = {}
    for p in files:
        try:
            contents[str(Path(p).resolve())] = Path(p).read_text(
                encoding="utf-8", errors="ignore"
            )
        except Exception:
            contents[str(Path(p).resolve())] = ""
    return _summarize_fn(question, contents)


behavior_faq_tool_def = {
    "type": "function",
    "function": {
        "name": "behavior_faq",
        "description": (
            "根据用户对软件功能/行为的提问，检索预设核心源代码文件并返回行为总结。"
            "总结包含文件路径、修改时间、哈希与结构化预览（模块/类/函数文档），"
            "可重复调用以获取最新代码下的更新总结（基于文件哈希自动失效）。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "用户的问题（功能/行为）",
                },
                "top_k": {
                    "type": "integer",
                    "description": "检索的相关文件数量",
                    "default": 6,
                },
            },
            "required": ["question"],
        },
    },
}
