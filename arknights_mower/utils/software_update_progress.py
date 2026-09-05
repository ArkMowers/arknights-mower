"""Small stdlib progress service that survives replacement of the application.

It temporarily reuses registered instance ports, preserving their token hashes
and listening addresses. No extra port or reverse-proxy route is required.
"""

import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

if __package__:
    from . import update_runtime as runtime
else:
    import update_runtime as runtime


def read_status(state):
    state = Path(state)
    result = runtime.read_json(
        state / "status.json", {"status": "idle", "message": "尚未执行软件更新"}
    )
    if result.get("status") == "running" and not runtime.active_job(state):
        result.update(
            status="failed", message="更新程序意外退出，请查看日志和备份后再试"
        )
    result["cancellable"] = (
        result.get("status") == "running"
        and result.get("cancellable", False)
        and not (state / "active/installing.json").exists()
        and not (state / "active/cancel.json").exists()
    )
    if log_path := result.get("log_path"):
        try:
            with Path(log_path).open("rb") as log:
                log.seek(max(0, log.seek(0, 2) - 16000))
                result["log"] = log.read().decode("utf-8", errors="replace")
        except OSError:
            pass
    return {
        "ok": True,
        **result,
        "last_check": runtime.read_json(state / "last-check.json", {}),
    }


def cancel_update(state, job_id):
    state = Path(state)
    with runtime.submission_lock(state):
        owner = runtime.read_json(state / "active/owner.json", {})
        if not job_id or owner.get("id") != job_id or not runtime.active_job(state):
            raise ValueError("该更新任务已经结束，请刷新状态")
        if (state / "active/installing.json").exists():
            raise ValueError("已开始替换程序，请等待安装和重启完成")
        runtime.write_json(state / "active/cancel.json", {"id": job_id})
    return {"ok": True, "message": "正在取消更新，等待下载或构建进程退出"}


# Public static shell only. Credentials arrive in the URL fragment, are removed
# immediately, and are sent only in the existing token header to same-origin APIs.
PROGRESS_HTML = r"""<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><title>Mower 更新进度</title>
<style>
:root{color-scheme:light dark;font:15px/1.65 system-ui,sans-serif;-webkit-font-smoothing:antialiased}
body{margin:0;padding:24px;background:light-dark(#f5f6f8,#18181c)}
main{max-width:880px;margin:24px auto;padding:24px;border-radius:12px;background:light-dark(white,#242428);box-shadow:0 2px 14px #0001}
h1{font-size:22px;margin:0 0 12px}p{overflow-wrap:anywhere}pre{max-height:55vh;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 ui-monospace,monospace}
button,a{display:inline-block;box-sizing:border-box;min-height:40px;padding:8px 14px;border-radius:6px;font:inherit}
button{cursor:pointer}button:disabled{cursor:default;opacity:.5}#bytes{font-variant-numeric:tabular-nums}#connection{opacity:.65}
</style><main><h1>Mower 更新进度</h1>
<p id="message" role="status" aria-live="polite">正在读取更新状态…</p><p id="bytes"></p>
<p id="connection"></p><button id="cancel" disabled>取消更新</button> <a id="return" href="/mowersettings#software-update">返回 Mower</a>
<details open><summary>安装日志</summary><pre id="log"></pre></details></main>
<script>
const parameters = new URLSearchParams(location.hash.slice(1));
let token = parameters.get('token') ?? sessionStorage.getItem('mower-update-token') ?? '';
if (parameters.has('token')) sessionStorage.setItem('mower-update-token', token);
history.replaceState(null, '', location.pathname);
const headers = {'token':token, 'X-Mower-Update':'1', 'Content-Type':'application/json'};
const message = document.getElementById('message'), log = document.getElementById('log');
const cancel = document.getElementById('cancel'), connection = document.getElementById('connection');
document.getElementById('return').href = '/?'+new URLSearchParams({token}).toString();
let job = null, cancelling = false;
async function poll(){
  try {
    const response = await fetch('/software-update/status', {headers, cache:'no-store', signal:AbortSignal.timeout(5000)});
    if (!response.ok) throw new Error(response.status === 403 ? '认证失败，请从 Mower 重新打开更新进度。' : '更新服务正在交接，稍后自动重试。');
    const data = await response.json();
    if (!data.ok) throw new Error(data.message);
    job = data; message.textContent = data.message; log.textContent = data.log || '';
    document.getElementById('bytes').textContent = data.current ? '已下载 '+(data.current/1048576).toFixed(1)+' MiB'+(data.total ? ' / '+(data.total/1048576).toFixed(1)+' MiB' : '') : '';
    connection.textContent = '';
    cancel.disabled = !data.cancellable || cancelling;
    if (['succeeded','failed','cancelled'].includes(data.status)) return;
  } catch(error) { connection.textContent = error.message || '更新服务正在交接，稍后自动重试。'; }
  setTimeout(poll, 1000);
}
cancel.onclick = async () => {
  if (!job?.cancellable || cancelling) return;
  cancelling = true; cancel.disabled = true;
  try {
    const response = await fetch('/software-update/cancel', {method:'POST', headers, body:JSON.stringify({id:job.id}), signal:AbortSignal.timeout(5000)});
    const data = await response.json();
    connection.textContent = data.message;
    if (!data.ok) cancelling = false;
  } catch { cancelling = false; connection.textContent = '取消请求未送达，请稍后重试。'; }
};
poll();
</script></html>"""


class ProgressServers:
    def __init__(self, state, records):
        self.state = state
        self.records = records
        self.servers = []

    def handler(self, token_hash):
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, code, body, content_type="application/json; charset=utf-8"):
                content = (
                    body.encode("utf-8")
                    if isinstance(body, str)
                    else json.dumps(body, ensure_ascii=False).encode("utf-8")
                )
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(content)

            def authorized(self):
                supplied = hashlib.sha256(
                    self.headers.get("token", "").encode()
                ).hexdigest()
                return hmac.compare_digest(supplied, token_hash)

            def do_GET(self):
                path = urlparse(self.path).path
                if path in ("/software-update/progress", "/", "/mowersettings"):
                    return self.reply(200, PROGRESS_HTML, "text/html; charset=utf-8")
                if not self.authorized():
                    return self.reply(403, {"ok": False})
                if path != "/software-update/status":
                    return self.reply(404, {"ok": False})
                self.reply(200, read_status(state))

            def do_POST(self):
                origin = self.headers.get("Origin")
                if (
                    not self.authorized()
                    or self.headers.get("X-Mower-Update") != "1"
                    or (origin and urlparse(origin).netloc != self.headers.get("Host"))
                ):
                    return self.reply(403, {"ok": False})
                if self.path != "/software-update/cancel":
                    return self.reply(404, {"ok": False})
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 1024:
                        raise ValueError("无效的取消请求")
                    self.connection.settimeout(5)
                    data = json.loads(self.rfile.read(length))
                    result = cancel_update(state, data.get("id"))
                except (ValueError, OSError, AttributeError) as exc:
                    return self.reply(400, {"ok": False, "message": str(exc)})
                self.reply(200, result)

        return Handler

    def start(self):
        seen = set()
        for record in self.records:
            # Older launchers did not publish auth information. Never guess
            # their token or replace a remote listener with an open service.
            port, host, token_hash = (
                record.get(key) for key in ("port", "listen_host", "token_hash")
            )
            if (
                record.get("kind") != "instance"
                or not port
                or not token_hash
                or host not in ("127.0.0.1", "0.0.0.0")
                or port in seen
            ):
                continue
            seen.add(port)
            try:
                server = ThreadingHTTPServer((host, port), self.handler(token_hash))
            except OSError as exc:
                print(f"更新进度端口 {port} 无法接管：{exc}", flush=True)
                continue
            thread = threading.Thread(
                target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True
            )
            thread.start()
            self.servers.append((server, thread))

    def close(self):
        for server, thread in self.servers:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.servers.clear()
