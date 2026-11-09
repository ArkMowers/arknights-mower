"""Read-only loopback snapshots for a local MowerHUD client."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread


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

    class LocalServer(HTTPServer):
        def get_request(self):
            sock, address = super().get_request()
            sock.settimeout(2)
            return sock, address

    server = LocalServer(("127.0.0.1", 0), Handler)
    worker = Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.2},
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
            server.shutdown()
            server.server_close()
            worker.join(3)
            if worker.is_alive():
                raise TimeoutError("本地 HUD 服务线程未在退出预算内结束")

    return Service()
