"""Recover unavailable credentials before importing application configuration."""

import argparse
import hashlib
import json
import os
import re
import secrets
import stat
import threading
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from flask import Flask, jsonify, request

from arknights_mower.utils import credential_store as store
from arknights_mower.utils import update_runtime
from arknights_mower.utils.web_auth import require_token

CONFIRMATION = "重置不可读凭据"
_LIMIT = 32 * 1024 * 1024
_PROFILE = re.compile(r"[a-f0-9]{32}\.secrets\.json\Z")
_WARNING = (
    "重置只处理下面列出的不可读凭据，仍可读取的凭据会保留。"
    "配置、排班、数据库和档案 ZIP 会保留。共享的网络与 AI 凭据会单独列出。"
    "若原私钥已丢失，其他使用该私钥的实例也需要分别恢复。"
)
_NEXT_STEP = (
    "请关闭恢复服务并重新启动 Mower，然后在设置中重新填写凭据或导入口令备份。"
    "桌面未保存访问令牌时仅允许本机访问；Docker 请重新提供 MOWER_TOKEN。"
)


class RecoveryConflict(ValueError):
    pass


def _directory(path):
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise store.CredentialStoreError("凭据恢复目录必须是普通目录，不能是符号链接")


def _raw(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise store.CredentialStoreError("凭据文件必须是普通文件，不能是符号链接")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise store.CredentialStoreError("凭据文件必须是普通文件")
        value = stream.read(_LIMIT + 1)
    if len(value) > _LIMIT:
        raise store.CredentialStoreError("凭据文件超过大小限制，请先手动检查")
    return value


class Recovery:
    def __init__(self, instance, shared):
        self.instance = Path(instance).resolve()
        self.shared = Path(shared).resolve()
        self.lock = threading.RLock()
        self.closed = False

    def close(self):
        with self.lock:
            self.closed = True

    def _candidates(self):
        _directory(self.instance)
        _directory(self.shared)
        paths = [
            (self.instance, name, "当前实例")
            for name in (
                "mower.secrets.json",
                "legacy-mower.secrets.json",
                "yituliu.secrets.json",
            )
        ]
        profiles = self.instance / "config-profiles"
        _directory(profiles)
        if profiles.exists():
            paths.extend(
                (self.instance, f"config-profiles/{path.name}", "当前实例档案")
                for path in sorted(profiles.iterdir())
                if _PROFILE.fullmatch(path.name)
            )
        paths.extend(
            (self.shared, name, "共享设置")
            for name in ("network.secrets.json", "ai.secrets.json")
        )
        return paths

    def inspect(self):
        with self.lock:
            if self.closed:
                raise RecoveryConflict("凭据恢复服务正在关闭")
            return self._inspect()

    def _inspect(self):
        files = []
        for root, name, scope in self._candidates():
            path = root / name
            try:
                raw = _raw(path)
            except FileNotFoundError:
                continue
            except (OSError, store.CredentialStoreError) as error:
                files.append(
                    dict(name=name, scope=scope, state="blocked", error=str(error))
                )
                continue
            item = dict(
                name=name,
                scope=scope,
                digest=hashlib.sha256(raw).hexdigest(),
                state="readable",
            )
            try:
                store.decode_credentials(raw)
            except store.CredentialStoreError as error:
                item.update(state="unreadable", error=str(error))
            files.append(item)
        generation = hashlib.sha256(
            json.dumps(files, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return dict(
            instance=str(self.instance),
            shared=str(self.shared),
            files=files,
            generation=generation,
            warning=_WARNING,
            next_step=_NEXT_STEP,
        )

    def _check_stopped(self, shared):
        try:
            records = update_runtime.instances(timeout=0)
        except update_runtime.InstanceScanError:
            raise RecoveryConflict(
                "无法确认实例是否已退出，请先检查实例运行记录"
            ) from None
        for record in records:
            if record.get("kind") != "instance" or record.get("pid") == os.getpid():
                continue
            data = Path(record.get("data_dir") or self.shared).resolve()
            instance = (data / record.get("space", "")).resolve()
            if instance == self.instance or (shared and data == self.shared):
                raise RecoveryConflict("请先退出使用这些凭据的 Mower 实例，再执行恢复")

    def reset(self, generation, confirmation):
        if confirmation != CONFIRMATION:
            raise ValueError(f"请输入“{CONFIRMATION}”以确认")
        if not isinstance(generation, str) or len(generation) != 64:
            raise ValueError("请先检查受影响的凭据文件")
        with self.lock:
            if self.closed:
                raise RecoveryConflict("凭据恢复服务正在关闭")
            archive_root = self.shared / "credential-recovery"
            _directory(archive_root)
            archive_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            lock_path = archive_root / "instance.lock"
            if lock_path.is_symlink() or (
                lock_path.exists() and not lock_path.is_file()
            ):
                raise store.CredentialStoreError(
                    "凭据恢复锁必须是普通文件，不能是符号链接"
                )
            with ExitStack() as locks:
                try:
                    locks.enter_context(
                        update_runtime.supervision_lock(archive_root, timeout=0)
                    )
                except RuntimeError:
                    raise RecoveryConflict(
                        "另一个凭据恢复操作正在进行，请稍后重试"
                    ) from None
                before = self.inspect()
                if before["generation"] != generation:
                    raise RecoveryConflict("凭据文件已改变，请刷新检查结果后重新确认")
                if any(item["state"] == "blocked" for item in before["files"]):
                    raise RecoveryConflict(
                        "存在无法安全归档的文件，请先处理权限或链接问题"
                    )
                unreadable = {
                    (item["scope"], item["name"]): item
                    for item in before["files"]
                    if item["state"] == "unreadable"
                }
                self._check_stopped(any(scope == "共享设置" for scope, _ in unreadable))
                # Only an explicit reset may repair a missing default private key.
                key = store.recover_private_key()
                identifier = uuid4().hex
                moves = []
                for root, name, scope in self._candidates():
                    original = unreadable.get((scope, name))
                    if original is None:
                        continue
                    source = root / name
                    raw = _raw(source)
                    if hashlib.sha256(raw).hexdigest() != original["digest"]:
                        raise RecoveryConflict(
                            "凭据文件已改变，请刷新检查结果后重新确认"
                        )
                    try:
                        store.decode_credentials(raw)
                    except store.CredentialStoreError:
                        parent = root / "credential-recovery"
                        _directory(parent)
                        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                        folder = parent / identifier
                        folder.mkdir(mode=0o700, exist_ok=True)
                        target = folder / name
                        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                        moves.append((source, target, original["digest"]))
                completed = []
                try:
                    for source, target, digest in moves:
                        if hashlib.sha256(_raw(source)).hexdigest() != digest:
                            raise RecoveryConflict(
                                "凭据文件已改变，请刷新检查结果后重新确认"
                            )
                        os.replace(source, target)
                        completed.append((source, target))
                except (OSError, ValueError, store.CredentialStoreError) as error:
                    retained = []
                    for source, target in reversed(completed):
                        try:
                            os.replace(target, source)
                        except OSError:
                            retained.append(str(target))
                    if retained:
                        raise store.CredentialStoreError(
                            "归档未完成，部分密文无法移回原位置；请先从以下位置手动恢复，"
                            "再启动 Mower：" + "；".join(retained)
                        ) from error
                    raise
                return dict(
                    archived=[str(target) for _, target in completed],
                    key=key,
                    message=_NEXT_STEP,
                )


_PAGE = """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mower 凭据恢复</title><style>
body{font:16px/1.65 system-ui,sans-serif;max-width:850px;margin:32px auto;padding:0 24px;color:#20252b;background:#f5f6f8}
main{background:white;padding:24px;border-radius:12px}h1{font-size:24px}li{overflow-wrap:anywhere;margin:10px 0}
button,input{font:inherit;padding:8px 12px;margin:6px 8px 6px 0}button{cursor:pointer}input{width:240px}
pre{white-space:pre-wrap;overflow-wrap:anywhere}#message{color:#9d2929}button:disabled{cursor:default;opacity:.5}
</style><main><h1>Mower 凭据恢复</h1>
<p>请先检查受影响的文件。如果保留了原私钥，请关闭本窗口并恢复原私钥，再重新启动 Mower。</p>
<p id="warning"></p><pre id="location"></pre><ul id="files"></ul>
<button id="inspect">重新检查</button><p>确定无法恢复原私钥时，请输入“重置不可读凭据”，再执行重置。</p>
<input id="confirmation" autocomplete="off" aria-label="重置确认文字" placeholder="重置不可读凭据">
<button id="reset" disabled>归档并重置不可读凭据</button><p id="message" role="status"></p>
<pre id="result"></pre><p id="next"></p><button id="close">关闭恢复服务</button></main>
<script>
const token=new URLSearchParams(location.hash.slice(1)).get('token')||'';
history.replaceState(null,'',location.pathname+location.search);
let generation='';
const el=id=>document.getElementById(id);
async function api(path,body){
 const response=await fetch(path,{method:body?'POST':'GET',headers:{token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,cache:'no-store'});
 const data=await response.json();if(!response.ok)throw new Error(data.error||'恢复请求失败，请重新打开恢复入口');return data;
}
async function inspect(){
 el('reset').disabled=true;el('message').textContent='';
 try{const data=await api('/recovery/status');generation=data.generation;
 el('warning').textContent=data.warning;el('next').textContent=data.next_step;
 el('location').textContent='当前实例：'+data.instance+'\\n共享设置：'+data.shared;
 el('files').replaceChildren();for(const item of data.files){const row=document.createElement('li');row.textContent=item.scope+' / '+item.name+'：'+({readable:'可读取，将保留',unreadable:'不可读取',blocked:'需要手动处理'}[item.state])+(item.error?'（'+item.error+'）':'');el('files').append(row);}
 if(!data.files.length)el('files').textContent='没有发现已保存的凭据文件';
 el('reset').disabled=data.files.some(item=>item.state==='blocked');
 }catch(error){el('message').textContent=error.message;}
}
el('inspect').onclick=inspect;
el('reset').onclick=async()=>{el('reset').disabled=true;try{
 const data=await api('/recovery/reset',{generation,confirmation:el('confirmation').value});
 el('message').textContent='凭据恢复处理完成';el('result').textContent=data.archived.length?'旧密文已归档：\\n'+data.archived.join('\\n'):'没有需要移除的不可读凭据';
 el('next').textContent=data.message;el('confirmation').value='';
 }catch(error){el('message').textContent=error.message;el('reset').disabled=false;}};
el('close').onclick=async()=>{try{await api('/recovery/close',{});el('message').textContent='恢复服务已关闭，请重新启动 Mower';window.close();}catch(error){el('message').textContent=error.message;}};
inspect();
</script></html>"""


def create_app(instance, shared, *, token=None):
    app = Flask(__name__, static_folder=None)
    app.token = secrets.token_urlsafe(32) if token is None else token
    if not isinstance(app.token, str) or not app.token.strip():
        raise ValueError("凭据恢复服务必须使用非空访问令牌")
    app.config["MAX_CONTENT_LENGTH"] = 4096
    recovery = Recovery(instance, shared)
    app.extensions["credential_recovery"] = recovery
    app.extensions["recovery_stop"] = threading.Event()

    @app.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
        return response

    @app.errorhandler(store.CredentialStoreError)
    @app.errorhandler(ValueError)
    @app.errorhandler(OSError)
    def recovery_error(error):
        return jsonify(error=str(error)), 409 if isinstance(
            error, RecoveryConflict
        ) else 400

    @app.errorhandler(403)
    def denied(error):
        return jsonify(error="恢复访问令牌无效，请重新打开恢复入口"), 403

    @app.get("/")
    def page():
        return _PAGE

    @app.get("/status", provide_automatic_options=False)
    @app.get("/recovery/status", provide_automatic_options=False)
    @require_token
    def status():
        return jsonify(recovery.inspect())

    @app.post("/recovery/reset", provide_automatic_options=False)
    @require_token
    def reset():
        if app.extensions["recovery_stop"].is_set():
            raise RecoveryConflict("凭据恢复服务正在关闭")
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError("恢复请求必须是 JSON 对象")
        return jsonify(recovery.reset(data.get("generation"), data.get("confirmation")))

    @app.post("/recovery/close", provide_automatic_options=False)
    @require_token
    def close():
        app.extensions["recovery_stop"].set()
        return jsonify(ok=True)

    return app


def serve(
    instance,
    shared,
    *,
    host="127.0.0.1",
    port=0,
    desktop=False,
    on_ready=None,
    shutdown_requested=None,
):
    from werkzeug.serving import WSGIRequestHandler, make_server

    class QuietHandler(WSGIRequestHandler):
        def log(self, kind, message, *args):
            pass

    app = create_app(instance, shared)
    http = make_server(host, port, app, threaded=True, request_handler=QuietHandler)
    stop = app.extensions["recovery_stop"]
    worker = threading.Thread(
        target=http.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True
    )
    shown_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    if ":" in shown_host:
        shown_host = f"[{shown_host}]"
    url = f"http://{shown_host}:{http.server_port}/#token={quote(app.token)}"

    def wait_for_close():
        while not stop.wait(0.2):
            if shutdown_requested and shutdown_requested():
                stop.set()

    try:
        worker.start()
        if on_ready:
            on_ready(http.server_port, app.token)
        if desktop:
            try:
                import webview

                window = webview.create_window(
                    "Mower 凭据恢复", url, width=900, height=760
                )
                closed = threading.Event()

                def window_closed():
                    closed.set()
                    stop.set()

                window.events.closed += window_closed

                def close_window():
                    wait_for_close()
                    if not closed.is_set():
                        window.destroy()

                threading.Thread(target=close_window, daemon=True).start()
                webview.start()
            except Exception:
                import webbrowser

                if not webbrowser.open(url):
                    raise RuntimeError(
                        "无法打开凭据恢复窗口，请使用命令行恢复入口"
                    ) from None
                wait_for_close()
        else:
            print(f"凭据恢复入口：{url}", flush=True)
            print(
                "请先停止 Mower 服务；操作完成后关闭恢复服务并重新启动 Mower。",
                flush=True,
            )
            wait_for_close()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if worker.ident is not None:
            http.shutdown()
        app.extensions["credential_recovery"].close()
        http.server_close()
        if worker.ident is not None:
            worker.join(3)
            if worker.is_alive():
                raise TimeoutError("凭据恢复服务未在退出预算内关闭")


def main(argv=None, *, desktop=False):
    parser = argparse.ArgumentParser(description="在正常配置加载前恢复本机凭据")
    parser.add_argument("--instance", help="当前实例目录，默认使用 MOWER_DATA_DIR")
    parser.add_argument(
        "--host", default="127.0.0.1", help="监听地址，默认仅允许本机访问"
    )
    parser.add_argument("--port", type=int, default=0, help="监听端口，默认自动选择")
    parser.add_argument(
        "--headless", action="store_true", help="在终端显示恢复入口，不打开桌面窗口"
    )
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("端口需要在 0 至 65535 之间")
    from arknights_mower.utils.path import get_path

    shared = get_path("@app", space="")
    serve(
        args.instance or get_path("@app"),
        shared,
        host=args.host,
        port=args.port,
        desktop=desktop and not args.headless,
    )


if __name__ == "__main__":
    main()
