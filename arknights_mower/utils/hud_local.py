"""Read-only loopback snapshots for a local MowerHUD client."""

import io
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import BoundedSemaphore, Lock, Thread
from time import monotonic

_HEADER_TIMEOUT = 2
_MAX_CONNECTIONS = 4
_SHUTDOWN_TIMEOUT = 3


class _IncompleteHeaders(Exception):
    pass


class _DeadlineSocketReader(io.RawIOBase):
    def __init__(self, connection, deadline):
        self.connection = connection
        self.deadline = deadline

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError("HTTP 请求头接收超时")
        self.connection.settimeout(remaining)
        return self.connection.recv_into(buffer)


class _HeaderReader(io.BufferedReader):
    def readline(self, size=-1):
        line = super().readline(size)
        if monotonic() >= self.raw.deadline:
            raise TimeoutError("HTTP 请求头接收超时")
        if not line or (not line.endswith(b"\n") and (size < 0 or len(line) < size)):
            raise _IncompleteHeaders
        return line


def _task_summary(task):
    task_type = task.get("type") or {}
    plan = task.get("plan")
    presentation = task.get("presentation")
    result = {
        "time": task.get("time"),
        "type": {
            "display_value": task_type.get("display_value", ""),
            "priority": task_type.get("priority", 0),
        },
        "meta_data": task.get("meta_data", ""),
        "display_name": task.get("display_name"),
        "plan": {room: [] for room in plan} if isinstance(plan, dict) else None,
    }
    if isinstance(presentation, dict):
        result["presentation"] = {
            "title": presentation.get("title", ""),
            "rooms": [
                {"id": room["id"], "label": room["label"]}
                for room in presentation.get("rooms", [])
            ],
            "targets": [
                {"id": target["id"], "label": target["label"]}
                for target in presentation.get("targets", [])
            ],
        }
    return result


def start_hud_local_server(app, instance_id, mower_port, name):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.rfile.close()
            deadline = self.server.request_deadline(self.connection)
            self.rfile = _HeaderReader(_DeadlineSocketReader(self.connection, deadline))

        def handle(self):
            try:
                super().handle()
            except (_IncompleteHeaders, ConnectionError):
                pass
            except OSError:
                if not self.server.stopping:
                    raise

        def parse_request(self):
            if not super().parse_request() or self.server.stopping:
                return False
            self.connection.settimeout(_HEADER_TIMEOUT)
            return True

        def log_message(self, _format, *args):
            pass

        def _send(self, status, body=b""):
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self):
            if self.path != "/mowerhud":
                self._send(404)
                return
            forbidden = {"origin", "referer", "forwarded", "x-real-ip"}
            if (
                self.client_address[0] != "127.0.0.1"
                or self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}"
                or any(
                    key.lower() in forbidden
                    or key.lower().startswith(("x-forwarded-", "sec-fetch-"))
                    for key in self.headers
                )
            ):
                self._send(403)
                return
            try:
                token = getattr(app, "token", "")
                headers = {"token": token} if token else {}
                with app.test_client() as client:
                    status = client.get("/status", headers=headers)
                    tasks = client.get("/task", headers=headers)
                    if status.status_code != 200 or tasks.status_code != 200:
                        self._send(503)
                        return
                    status_data = status.get_json()
                    tasks_data = tasks.get_json()
                snapshot = {
                    "protocol": "mowerhud/1",
                    "id": instance_id,
                    "name": name,
                    "mower_port": mower_port,
                    "status": status_data["status"],
                    "next_task_time": status_data.get("next_task_time"),
                    "tasks": [_task_summary(task) for task in tasks_data[:2]],
                }
                body = json.dumps(snapshot, ensure_ascii=False).encode("utf-8")
                self._send(200, body)
            except (KeyError, TypeError, ValueError):
                self._send(503)

        def do_POST(self):
            self._send(405)

        do_PUT = do_DELETE = do_PATCH = do_POST

    class LocalServer(ThreadingHTTPServer):
        def __init__(self, *args):
            self._lock = Lock()
            self._slots = BoundedSemaphore(_MAX_CONNECTIONS)
            self._connections = {}
            self.stopping = False
            super().__init__(*args)

        def request_deadline(self, connection):
            with self._lock:
                return self._connections[connection]

        def serve(self):
            try:
                self.serve_forever(poll_interval=0.2)
            except OSError:
                if not self.stopping:
                    raise

        def process_request(self, connection, address):
            with self._lock:
                admitted = not self.stopping and self._slots.acquire(blocking=False)
                if admitted:
                    self._connections[connection] = monotonic() + _HEADER_TIMEOUT
            if not admitted:
                self.shutdown_request(connection)
                return
            try:
                super().process_request(connection, address)
            except BaseException:
                with self._lock:
                    self._connections.pop(connection, None)
                self._slots.release()
                raise

        def process_request_thread(self, connection, address):
            try:
                super().process_request_thread(connection, address)
            finally:
                with self._lock:
                    self._connections.pop(connection, None)
                self._slots.release()

        def stop_requests(self):
            with self._lock:
                self.stopping = True
                connections = tuple(self._connections)
            for connection in connections:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    server = LocalServer(("127.0.0.1", 0), Handler)
    worker = Thread(
        target=server.serve,
        name="mowerhud-local",
        daemon=True,
    )
    try:
        worker.start()
    except BaseException:
        server.server_close()
        raise

    class Service:
        port = server.server_port

        def close(self):
            deadline = monotonic() + _SHUTDOWN_TIMEOUT
            server.stop_requests()
            stopper = Thread(target=server.shutdown, name="mowerhud-stop", daemon=True)
            try:
                stopper.start()
                stopper.join(max(0, deadline - monotonic()))
            finally:
                try:
                    server.socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                server.server_close()
            worker.join(max(0, deadline - monotonic()))
            if stopper.is_alive() or worker.is_alive():
                raise TimeoutError("本地 HUD 服务线程未在退出预算内结束")

    return Service()
