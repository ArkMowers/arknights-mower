"""Outbound Mower relay: dispatch to this Flask application, never a target port."""

import asyncio
import base64
import hmac
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Empty, Full, Queue
from threading import BoundedSemaphore, Event, Lock, Thread

from simple_websocket import ConnectionClosed
from werkzeug.security import check_password_hash

from arknights_mower.utils.log import logger
from arknights_mower.utils.mower_relay import settings
from arknights_mower.utils.mower_relay.protocol import (
    CONNECT_URL,
    MAX_BODY,
    MAX_FRAME,
    MAX_PENDING,
    MAX_SOCKETS,
    SOCKETS,
    VERSION,
    allowed_request,
    decode_body,
    public_origin,
    validate_response,
)


class RelaySocket:
    def __init__(self, send):
        self.queue = Queue(maxsize=32)
        self.send_message = send
        self.connected = True

    def send(self, data):
        if (
            not self.connected
            or not isinstance(data, str)
            or len(data.encode()) > 65536
        ):
            raise ConnectionClosed()
        self.send_message(data)

    def receive(self, timeout=None):
        if not self.connected:
            raise ConnectionClosed()
        try:
            value = self.queue.get(timeout=timeout)
        except Empty:
            return None
        if value is None:
            raise ConnectionClosed()
        return value

    def feed(self, data):
        try:
            self.queue.put_nowait(data)
        except Full:
            self.close()

    def close(self, reason=None, message=None):
        self.connected = False
        try:
            self.queue.put_nowait(None)
        except Full:
            pass


class RelayClient:
    def __init__(self, app):
        self.app = app
        self._closing = False
        self._lock = Lock()
        self._thread = None
        self._loop = None
        self._changed = None
        self._work_slots = BoundedSemaphore(MAX_PENDING)
        self._socket_slots = BoundedSemaphore(MAX_SOCKETS)
        self._state = "stopped"
        self._message = "尚未连接"

        self._origin = ""
        self._requested_credential = None

    @property
    def token_ready(self):
        from arknights_mower.utils import config

        token = config.conf.webview.token
        return bool(
            token
            and token == getattr(self.app, "token", None)
            and not self.app.config.get("WEBVIEW_LOCAL_ONLY_NO_TOKEN")
        )

    def status(self):
        with self._lock:
            return {"state": self._state, "message": self._message, "url": self._origin}

    def _set(self, state, message, *, origin="", credential=None):
        with self._lock:
            if origin and credential != self._requested_credential:
                return
            self._state, self._message, self._origin = state, message, origin

    def start(self):
        try:
            data = settings.load()
            enabled = data["enabled"] and self.token_ready
        except (OSError, ValueError):
            self._set("error", "读取中转设置失败")
            return
        with self._lock:
            if self._closing:
                return
            self._requested_credential = data["credential"] if enabled else None
            self._origin = ""
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._changed.set)
            if enabled and not (self._thread and self._thread.is_alive()):
                self._thread = Thread(target=self._run, name="mower-relay", daemon=True)
                self._thread.start()

    def close(self):
        with self._lock:
            self._closing = True
            thread = self._thread
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._changed.set)
        if thread:
            thread.join(timeout=5)

    def dispatch(self, message, origin, *, token_changed=None):
        if not getattr(self.app, "token", ""):
            raise ValueError("当前启动方式没有实例 token，请使用桌面入口启动")
        method, path = message.get("method"), message.get("path")
        if not allowed_request(method, path):
            raise ValueError("不支持该 Mower 操作")
        body = decode_body(message.get("body", ""))
        supplied = message.get("headers", {})
        if not isinstance(supplied, dict):
            raise ValueError("请求头无效")
        headers = {
            key: value
            for key, value in supplied.items()
            if key
            in {
                "token",
                "content-type",
                "x-mower-config-generation",
                "x-mower-settings",
            }
            and isinstance(value, str)
        }
        headers["Origin"] = origin
        # The gateway password never substitutes for the instance token.
        environ = {"mower.relay": True}
        if token_changed is not None:
            environ["mower.relay_token_changed"] = token_changed
        with self.app.test_client() as client:
            with client.open(
                path,
                method=method,
                base_url=origin,
                headers=headers,
                data=body,
                environ_overrides=environ,
            ) as response:
                result = bytearray()
                for chunk in response.response:
                    result.extend(chunk)
                    if len(result) > MAX_BODY:
                        raise ValueError("响应超过中转大小限制，请在本机下载")
                mime = response.mimetype
                data = bytes(result)
                if response.status_code >= 400 and mime == "text/html":
                    mime, data = (
                        "application/json",
                        json.dumps({"error": response.status}).encode(),
                    )
                if (
                    mime == "text/html"
                    and len(data) <= 65536
                    and b"<" not in data
                    and b">" not in data
                ):
                    mime = "text/plain"
                if method == "HEAD":
                    data = b""
                validate_response(path, response.status_code, mime, data, method=method)
                return {
                    "op": "response",
                    "id": message["id"],
                    "status": response.status_code,
                    "mime": mime,
                    "body": base64.b64encode(data).decode(),
                }

    def _run(self):
        try:
            asyncio.run(self._main())
        except ModuleNotFoundError as exc:
            logger.error("中转客户端缺少依赖 %s", exc.name)
            self._set("error", "请安装包含中转网络依赖的完整 Mower 版本")
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.error("Mower 中转连接已结束，请检查配置后重新连接")
            self._set("error", "连接已结束，请检查配置后重新连接")

    def authenticate(self, message):
        data = settings.load()
        username, password = message.get("username"), message.get("password")
        ok = (
            data["enabled"]
            and isinstance(username, str)
            and isinstance(password, str)
            and len(username) <= 64
            and bool(password)
            and hmac.compare_digest(username.encode(), data["username"].encode())
            and bool(data["password_hash"])
            and check_password_hash(data["password_hash"], password)
        )
        return {"op": "authenticated", "id": message["id"], "ok": bool(ok)}

    async def _main(self):
        import aiohttp

        changed = asyncio.Event()
        with self._lock:
            self._loop = asyncio.get_running_loop()
            self._changed = changed
        executor = ThreadPoolExecutor(
            max_workers=MAX_PENDING, thread_name_prefix="relay-api"
        )
        try:
            while not self._closing:
                changed.clear()
                data = settings.load()
                if not data["enabled"] or not self.token_ready:
                    self._set(
                        "stopped",
                        "中转已关闭"
                        if not data["enabled"]
                        else "请先配置访问 Token 并重启实例",
                    )
                    await changed.wait()
                    continue
                try:
                    marker = Path(self.app.static_folder) / "relay-ui.json"
                    build = json.loads(marker.read_bytes())["build"]
                    if not isinstance(build, str) or not re.fullmatch(
                        r"[0-9a-f]{64}", build
                    ):
                        raise ValueError("前端构建标识无效")
                except (OSError, KeyError, TypeError, ValueError):
                    self._set("error", "请安装或重新构建含中转标识的 Mower 前端")
                    await changed.wait()
                    continue
                self._set("connecting", "正在连接中转服务")
                connection = asyncio.create_task(self._session(data, executor, build))
                reload_settings = asyncio.create_task(changed.wait())
                try:
                    await asyncio.wait(
                        (connection, reload_settings),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if changed.is_set():
                        continue
                    try:
                        await connection
                    except aiohttp.WSServerHandshakeError as exc:
                        if exc.status in {401, 403, 409}:
                            self._set(
                                "error",
                                "请核对中转凭据，并确认没有其他实例占用连接",
                            )
                            await changed.wait()
                            continue
                    except (aiohttp.ClientError, OSError, ValueError, TimeoutError):
                        pass
                    self._set("reconnecting", "连接已断开，稍后重新连接")
                    try:
                        await asyncio.wait_for(changed.wait(), timeout=5)
                    except TimeoutError:
                        pass
                finally:
                    for task in (connection, reload_settings):
                        task.cancel()
                    await asyncio.gather(
                        connection, reload_settings, return_exceptions=True
                    )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            with self._lock:
                self._loop = self._changed = None
            self._set("stopped", "中转已关闭")

    async def _session(self, data, executor, build):
        import aiohttp

        tasks = set()
        sockets = {}
        try:
            timeout = aiohttp.ClientTimeout(total=15, sock_connect=10)
            async with aiohttp.ClientSession(
                timeout=timeout, trust_env=False
            ) as session:
                async with session.ws_connect(
                    CONNECT_URL,
                    headers={
                        "Authorization": f"Bearer {data['credential']}",
                    },
                    heartbeat=20,
                    max_msg_size=MAX_FRAME,
                    timeout=aiohttp.ClientWSTimeout(ws_receive=None, ws_close=1),
                ) as ws:
                    await ws.send_json(
                        {"op": "hello", "version": VERSION, "ui_build": build}
                    )
                    frame = await ws.receive(timeout=10)
                    if frame.type != aiohttp.WSMsgType.TEXT:
                        raise ConnectionError("网关未确认前端版本")
                    ready = json.loads(frame.data)
                    if not isinstance(ready, dict):
                        raise ValueError("网关响应无效")
                    origin = public_origin(ready.pop("subdomain", None))
                    if ready != {
                        "op": "ready",
                        "version": VERSION,
                        "ui_build": build,
                    }:
                        raise ValueError("协议版本不兼容")
                    self._set(
                        "connected",
                        "中转已连接",
                        origin=origin,
                        credential=data["credential"],
                    )
                    async for frame in ws:
                        if self._closing:
                            break
                        if frame.type != aiohttp.WSMsgType.TEXT:
                            break
                        message = json.loads(frame.data)
                        identity = message.get("id")
                        if not isinstance(identity, str) or len(identity) > 64:
                            raise ValueError("消息编号无效")
                        op = message.get("op")
                        if op in {"request", "authenticate"}:
                            if len(
                                tasks
                            ) >= MAX_PENDING or not self._work_slots.acquire(
                                blocking=False
                            ):
                                await ws.send_json({"op": "error", "id": identity})
                                continue

                            task = asyncio.create_task(
                                self._reply(ws, executor, message, origin)
                            )
                            tasks.add(task)

                            def finished(done):
                                tasks.discard(done)
                                if not done.cancelled():
                                    done.exception()

                            task.add_done_callback(finished)
                        elif op == "ws_open":
                            path = message.get("path")
                            if (
                                path not in SOCKETS
                                or len(sockets) >= MAX_SOCKETS
                                or identity in sockets
                                or not self._socket_slots.acquire(blocking=False)
                            ):
                                await ws.send_json({"op": "ws_close", "id": identity})
                                continue

                            self._open_socket(ws, sockets, identity, path, origin)
                        elif op in {"ws_data", "ws_close"} and identity in sockets:
                            adapter = sockets[identity]
                            if op == "ws_close":
                                adapter.close()
                            elif (
                                isinstance(message.get("data"), str)
                                and len(message["data"].encode()) <= 65536
                            ):
                                adapter.feed(message["data"])
                            else:
                                adapter.close()
        finally:
            for adapter in list(sockets.values()):
                adapter.close()
            sockets.clear()
            if tasks:
                _, pending = await asyncio.wait(tasks, timeout=2)
                for task in pending:
                    task.cancel()

    async def _reply(self, ws, executor, message, origin):
        token_changed = Event()

        def work():
            try:
                if message["op"] == "authenticate":
                    return self.authenticate(message)
                return self.dispatch(message, origin, token_changed=token_changed.set)
            finally:
                self._work_slots.release()

        try:
            reply = await asyncio.shield(
                asyncio.get_running_loop().run_in_executor(executor, work)
            )
        except Exception:
            reply = {"op": "error", "id": message["id"]}
        try:
            if not ws.closed:
                await ws.send_json(reply)
        finally:
            if token_changed.is_set():
                self.start()

    def _open_socket(self, ws, sockets, identity, path, origin):
        loop = asyncio.get_running_loop()

        def send_frame(op, **fields):
            if loop.is_closed() or ws.closed:
                raise ConnectionClosed()
            future = asyncio.run_coroutine_threadsafe(
                ws.send_json({"op": op, "id": identity, **fields}), loop
            )
            try:
                future.result(timeout=5)
            except TimeoutError:
                future.cancel()
                raise

        adapter = RelaySocket(lambda value: send_frame("ws_data", data=value))
        sockets[identity] = adapter

        def forget():
            if sockets.get(identity) is adapter:
                sockets.pop(identity)

        def serve():
            try:
                with self.app.test_request_context(
                    path, base_url=origin, headers={"Origin": origin}
                ):
                    self.app.view_functions[SOCKETS[path]].__wrapped__(adapter)
            except (ConnectionClosed, OSError, TimeoutError):
                pass
            finally:
                adapter.close()
                try:
                    send_frame("ws_close")
                except (ConnectionClosed, OSError, RuntimeError, TimeoutError):
                    pass
                finally:
                    self._socket_slots.release()
                    if not loop.is_closed():
                        loop.call_soon_threadsafe(forget)

        Thread(target=serve, name="relay-websocket", daemon=True).start()
