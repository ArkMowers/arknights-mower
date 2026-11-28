"""Keep navigation model I/O, including DNS, inside one disposable process."""

import json
import multiprocessing
import os
import time
from types import SimpleNamespace

from arknights_mower.utils.device.owned import close_process

MAX_REPLY_BYTES = 4000
CLEANUP_TIMEOUT = 0.03
_PATH_FIELDS = ("_data_dir", "_internal_dir", "_install_dir", "global_space")
_unreaped = []


class _ReplySlot:
    def __init__(self, buffer):
        self._buffer = buffer

    @property
    def closed(self):
        return self._buffer is None

    def send_bytes(self, payload):
        if not 0 < len(payload) <= MAX_REPLY_BYTES:
            raise ValueError("导航模型回复长度无效")
        self._buffer[4 : 4 + len(payload)] = payload
        self._buffer[:4] = len(payload).to_bytes(4, "big")

    def recv_bytes(self, maximum):
        size = int.from_bytes(bytes(self._buffer[:4]), "big")
        if not 0 < size <= min(maximum, MAX_REPLY_BYTES):
            raise EOFError("导航模型工作进程未返回完整回复")
        return bytes(self._buffer[4 : 4 + size])

    def close(self):
        self._buffer = None


def _close_worker(process, channel, owner_pid, *, join_timeout=CLEANUP_TIMEOUT):
    if owner_pid == os.getpid():
        try:
            process.pid
        except ValueError:
            channel.close()
            return
    try:
        if owner_pid == os.getpid() and process.pid is not None and process.is_alive():
            process.kill()
        close_process(process, owner_pid, timeout=join_timeout)
    except Exception:
        entry = (process, channel, owner_pid)
        if entry not in _unreaped:
            _unreaped.append(entry)
        raise
    else:
        channel.close()


def _model_worker(channel, settings, api_key, messages, timeout, paths):
    try:
        from arknights_mower.utils import path

        for name in _PATH_FIELDS:
            setattr(path, name, paths[name])
        from arknights_mower.agent.agent import build_llm
        from arknights_mower.utils import config

        config.conf = SimpleNamespace(**settings)
        llm = build_llm(api_key, with_tools=False, timeout=timeout, max_retries=0)
        try:
            response = llm.invoke(messages)
            text = response.content if isinstance(response.content, str) else ""
            payload = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
            if len(payload) > MAX_REPLY_BYTES:
                raise ValueError("导航模型回复过长")
        finally:
            llm.root_client.close()
    except Exception as error:
        payload = json.dumps({"error": type(error).__name__}).encode("ascii")
    try:
        channel.send_bytes(payload)
    finally:
        channel.close()


def _start_worker(settings, api_key, messages, timeout):
    from arknights_mower.utils import path

    paths = {name: getattr(path, name) for name in _PATH_FIELDS}
    context = multiprocessing.get_context("spawn")
    reply = _ReplySlot(context.RawArray("B", MAX_REPLY_BYTES + 4))
    process = None
    try:
        process = context.Process(
            target=_model_worker,
            args=(reply, settings, api_key, messages, timeout, paths),
            daemon=True,
        )
        process.start()
    except BaseException:
        if process is None:
            reply.close()
        else:
            _close_worker(process, reply, os.getpid())
        raise
    return process, reply


def invoke_navigation_model(api_key, messages):
    from arknights_mower.utils import config
    from arknights_mower.utils.csleep import MowerExit
    from arknights_mower.utils.device.io_budget import io_timeout
    from arknights_mower.utils.log import logger

    budget = io_timeout(90)
    cleanup_budget = min(0.1, budget / 2)
    deadline = time.monotonic() + budget - cleanup_budget

    def remaining():
        if config.stop_mower.is_set():
            raise MowerExit
        seconds = io_timeout(min(90, deadline - time.monotonic()))
        if seconds <= 0:
            raise TimeoutError("导航模型请求超时")
        return seconds

    # A failed cleanup retains ownership and prevents another worker starting.
    for process, channel, owner_pid in list(_unreaped):
        remaining()
        _close_worker(
            process,
            channel,
            owner_pid,
            join_timeout=min(CLEANUP_TIMEOUT, cleanup_budget / 3),
        )
        _unreaped.remove((process, channel, owner_pid))

    settings = {
        key: getattr(config.conf, key)
        for key in (
            "ai_type",
            "ai_deepseek_model",
            "ai_model",
            "ai_base_url",
            "ai_api_protocol",
        )
    }
    process, channel = _start_worker(settings, api_key, messages, remaining())
    owner_pid = os.getpid()
    error = None
    try:
        while process.is_alive():
            process.join(timeout=min(0.05, remaining()))
        remaining()
        # Worker exit precedes reading the completed shared reply.
        response = json.loads(channel.recv_bytes(MAX_REPLY_BYTES))
        remaining()
        if "error" in response:
            raise RuntimeError("导航模型工作进程失败：" + response["error"])
        return SimpleNamespace(content=response["text"])
    except BaseException as exc:
        error = exc
        raise
    finally:
        try:
            _close_worker(
                process,
                channel,
                owner_pid,
                join_timeout=min(CLEANUP_TIMEOUT, cleanup_budget / 3),
            )
        except Exception as cleanup_error:
            if error is None:
                raise
            error.add_note(f"导航模型工作进程清理失败：{cleanup_error}")
            logger.exception("导航模型工作进程清理失败")
