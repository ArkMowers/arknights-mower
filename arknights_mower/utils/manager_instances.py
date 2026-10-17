"""Stopped-process configuration and lifecycle operations for the manager."""

import copy
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from time import monotonic
from uuid import uuid4

import yaml
from yamlcore import CoreDumper, CoreLoader

from . import update_runtime as runtime
from .path import get_path


def instance_directory(space):
    return get_path("@app", space=space).resolve()


def instance_key(space):
    return os.path.normcase(str(instance_directory(space)))


def read_instance_config(space):
    destination = instance_directory(space) / "config/conf.yml"
    source = (
        destination if destination.exists() else destination.parent.parent / "conf.yml"
    )
    raw = (
        yaml.load(source.read_text(encoding="utf-8"), Loader=CoreLoader)
        if source.exists()
        else {}
    )
    if raw is None:
        raw = {}
    if not isinstance(raw, dict) or not isinstance(raw.get("webview", {}), dict):
        raise ValueError("实例配置格式不正确，请检查 conf.yml")
    return destination, raw


def read_webview(space):
    destination, raw = read_instance_config(space)
    settings = raw.get("webview", {})
    token = settings.get("token", "")
    port = settings.get("port", 0)
    assistant = raw.get("ai_assistant_enabled")
    updates = raw.get("updates_enabled", False)
    if not isinstance(token, str):
        raise ValueError("Token 必须是文本")
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("端口必须是 1 至 65535 的整数，或留空")
    if assistant is not None and type(assistant) is not bool:
        raise ValueError("Mower AI 助手开关必须是布尔值")
    if type(updates) is not bool:
        raise ValueError("允许更新开关必须是布尔值")
    return (
        destination,
        raw,
        {
            "token": token,
            "port": port or None,
            "ai_assistant_enabled": assistant is True,
            "updates_enabled": updates,
        },
    )


def validate_settings(settings, *, partial=False):
    allowed = {"token", "port", "ai_assistant_enabled", "updates_enabled"}
    if (
        not isinstance(settings, dict)
        or not settings
        or set(settings) - allowed
        or (not partial and not {"token", "port"} <= set(settings))
    ):
        raise ValueError("不支持的实例配置项")
    result = dict(settings)
    if "token" in result and not isinstance(result["token"], str):
        raise ValueError("Token 必须是文本")
    if "port" in result:
        if result["port"] in (None, ""):
            result["port"] = 0
        if type(result["port"]) is not int or not 0 <= result["port"] <= 65535:
            raise ValueError("端口必须是 1 至 65535 的整数，或留空")
    if (
        "ai_assistant_enabled" in result
        and type(result["ai_assistant_enabled"]) is not bool
    ):
        raise ValueError("Mower AI 助手开关必须是布尔值")
    if "updates_enabled" in result and type(result["updates_enabled"]) is not bool:
        raise ValueError("允许更新开关必须是布尔值")
    return result


class InstanceController:
    def __init__(self, storage_path=None, ready=None):
        self._ready = ready
        self._lock = threading.RLock()
        self._operation_depth = 0
        self._storage_path = (
            Path(storage_path)
            if storage_path is not None
            else get_path("@app/instances.json", space="")
        )
        self.instances = self._load()

    @property
    def _control_directory(self):
        return runtime.state_dir() / "manager-controls"

    def _load(self):
        try:
            result = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        if not isinstance(result, list) or any(
            not isinstance(i, dict)
            or not isinstance(i.get("name"), str)
            or not isinstance(i.get("path"), str)
            for i in result
        ):
            raise ValueError("实例列表格式不正确，请检查 instances.json")
        return result

    @contextmanager
    def _operation(self):
        with self._lock:
            if self._operation_depth:
                yield
                return
            with runtime.submission_lock(self._control_directory):
                self._operation_depth += 1
                try:
                    self.instances = self._load()
                    yield
                finally:
                    self._operation_depth -= 1

    def _save(self, instances):
        runtime.write_json(self._storage_path, instances, sync=True)
        self.instances = instances

    def _records(self):
        records = runtime.instances(timeout=0)
        for file in self._control_directory.glob("*.json"):
            pending = json.loads(file.read_text(encoding="utf-8"))
            if (
                not isinstance(pending, dict)
                or type(pending.get("pid")) is not int
                or pending["pid"] <= 0
                or not isinstance(pending.get("id"), str)
                or len(pending["id"]) != 32
                or any(c not in "0123456789abcdef" for c in pending["id"])
            ):
                raise ValueError("实例启动记录格式不正确，请检查管理器运行目录")
            if runtime.process_alive(pending["pid"]):
                records.append(pending)
            else:
                file.unlink(missing_ok=True)
                if not any(r.get("id") == pending["id"] for r in records):
                    (runtime.state_dir() / "shutdown" / f"{pending['id']}.json").unlink(
                        missing_ok=True
                    )
        return [r for r in records if r.get("kind") == "instance"]

    def _matching(self, instance, records):
        if not instance["path"]:
            return []
        key = instance_key(instance["path"])
        return [
            r
            for r in records
            if instance_key(
                str(
                    Path(r.get("data_dir") or get_path("@app", space=""))
                    / (r.get("space") or "")
                )
            )
            == key
        ]

    def _editable(self, instance, records):
        if self._matching(instance, records):
            raise ValueError("实例进程运行期间不能修改配置，请先停止实例")
        if runtime.active_job():
            raise ValueError("软件更新或进程操作期间不能修改实例配置")

    def _start_settings(self, instance, records):
        if runtime.active_job():
            raise ValueError("软件更新或进程操作期间无法启动新实例")
        if not instance["path"] or instance["path"].startswith("-"):
            raise ValueError("请先选择实例保存目录")
        if self._matching(instance, records):
            raise ValueError("实例正在运行或启动中，不能重复启动")
        _, _, settings = read_webview(instance["path"])
        if port := settings["port"]:
            if any(r.get("port") == port for r in records):
                raise ValueError(f"端口 {port} 已被其他实例使用")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                if sys.platform == "win32":
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                try:
                    probe.bind(("0.0.0.0" if settings["token"] else "127.0.0.1", port))
                except OSError as error:
                    raise ValueError(f"端口 {port} 已被占用或不可用") from error
        return settings

    def get_instances(self):
        with self._operation():
            records = self._records()
            result = []
            for instance in self.instances:
                item = dict(
                    instance,
                    token="",
                    port=None,
                    ai_assistant_enabled=False,
                    updates_enabled=False,
                    editable=False,
                    can_start=False,
                    can_stop=False,
                    state="stopped",
                    reason="",
                )
                matches = self._matching(instance, records)
                if matches:
                    item["state"] = (
                        "running"
                        if any(r.get("ready") for r in matches)
                        else "starting"
                    )
                    if any(
                        (runtime.state_dir() / "shutdown" / f"{r['id']}.json").exists()
                        for r in matches
                    ):
                        item["state"] = "stopping"
                    item["can_stop"] = (
                        all(r.get("managed") for r in matches)
                        and item["state"] != "stopping"
                    )
                try:
                    self._editable(instance, records)
                    item["editable"] = True
                except (OSError, ValueError) as error:
                    item["reason"] = str(error)
                try:
                    if instance["path"]:
                        _, _, settings = read_webview(instance["path"])
                        item.update(settings)
                    self._start_settings(instance, records)
                    item["can_start"] = True
                except (OSError, ValueError, yaml.YAMLError) as error:
                    item["reason"] = str(error)
                result.append(item)
            return result

    def mark_ready(self):
        if self._ready is not None:
            self._ready.set()

    def add(self, name, path):
        if not isinstance(name, str) or not name.strip() or not isinstance(path, str):
            raise ValueError("实例名称不能为空，保存目录必须是文本")
        with self._operation():
            self._save([*self.instances, {"name": name, "path": path}])

    def remove(self, idx):
        with self._operation():
            self._editable(self.instances[idx], self._records())
            self._save([i for n, i in enumerate(self.instances) if n != idx])

    def rename(self, idx, name):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("实例名称不能为空")
        self._update(idx, {"name": name})

    def _update(self, idx, changes):
        with self._operation():
            records = self._records()
            self._editable(self.instances[idx], records)
            updated = copy.deepcopy(self.instances)
            updated[idx].update(changes)
            self._editable(updated[idx], records)
            self._save(updated)

    def update_settings(self, idx, settings, target=None):
        settings = validate_settings(settings)
        with self._operation():
            if target is not None and (
                type(idx) is not int
                or not 0 <= idx < len(self.instances)
                or target != {key: self.instances[idx][key] for key in ("name", "path")}
            ):
                raise ValueError("实例已变化，请重新打开配置")
            instance = self.instances[idx]
            self._editable(instance, self._records())
            self._write_settings(instance, settings)

    def _write_settings(self, instance, settings):
        if not instance["path"]:
            raise ValueError("请先选择实例保存目录")
        destination, raw = read_instance_config(instance["path"])
        current = {
            key: raw.get(key)
            if key in {"ai_assistant_enabled", "updates_enabled"}
            else raw.get("webview", {}).get(key)
            for key in settings
        }
        if (
            destination.is_file()
            and current == settings
            and all(
                type(current[key]) is type(value) for key, value in settings.items()
            )
        ):
            return False
        connection = {
            key: settings[key] for key in ("token", "port") if key in settings
        }
        if connection:
            raw.setdefault("webview", {}).update(connection)
        if "ai_assistant_enabled" in settings:
            raw["ai_assistant_enabled"] = settings["ai_assistant_enabled"]
        if "updates_enabled" in settings:
            raw["updates_enabled"] = settings["updates_enabled"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=destination.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                yaml.dump(raw, stream, Dumper=CoreDumper, allow_unicode=True)
                stream.flush()
                os.fsync(stream.fileno())
            runtime.replace_with_retry(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return True

    def update_all_settings(self, changes, targets):
        if not isinstance(changes, list) or not changes:
            raise ValueError("请选择需要保存的实例配置")
        selected = {}
        for change in changes:
            if (
                not isinstance(change, dict)
                or set(change) != {"idx", "settings"}
                or type(change["idx"]) is not int
                or change["idx"] < 0
                or change["idx"] in selected
            ):
                raise ValueError("批量实例配置格式不正确")
            selected[change["idx"]] = validate_settings(
                change["settings"], partial=True
            )
        with self._operation():
            current = [
                {"name": item["name"], "path": item["path"]} for item in self.instances
            ]
            if targets != current:
                raise ValueError("实例列表已变化，请重新打开批量配置")
            if any(idx >= len(current) for idx in selected):
                raise ValueError("批量配置包含无效实例")
            results, seen = [], set()
            deadline = monotonic() + 10
            records = self._records()
            blocked = ""
            for position, (idx, settings) in enumerate(sorted(selected.items())):
                instance = self.instances[idx]
                item = {
                    "idx": idx,
                    "name": instance["name"],
                    "status": "failed",
                    "message": "",
                }
                results.append(item)
                if monotonic() >= deadline:
                    blocked = "批量配置已达到时间上限，未执行"
                if blocked:
                    item["message"] = blocked
                    continue
                try:
                    if position:
                        records = self._records()
                except (OSError, ValueError, runtime.InstanceScanError) as error:
                    blocked = f"无法读取实例状态，未执行：{error}"
                    item["message"] = blocked
                    continue
                try:
                    self._editable(instance, records)
                    if not instance["path"]:
                        raise ValueError("未选择实例保存目录")
                    key = instance_key(instance["path"])
                    if key in seen:
                        raise ValueError("保存目录重复，已跳过")
                    seen.add(key)
                except (OSError, ValueError) as error:
                    item.update(status="skipped", message=str(error))
                    continue
                if monotonic() >= deadline:
                    blocked = "批量配置已达到时间上限，未执行"
                    item["message"] = blocked
                    continue
                try:
                    changed = self._write_settings(instance, settings)
                except (OSError, ValueError, yaml.YAMLError) as error:
                    item["message"] = str(error)
                else:
                    item.update(
                        status="updated", message="已更新" if changed else "已符合设置"
                    )
            return {"ok": True, "results": results}

    def start(self, idx):
        try:
            with self._operation():
                instance = self.instances[idx]
                settings = self._start_settings(instance, self._records())
                frozen = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
                executable = Path(sys.executable).resolve().parent / (
                    "mower.exe" if sys.platform == "win32" else "mower"
                )
                command = (
                    [str(executable)]
                    if frozen
                    else [
                        sys.executable,
                        str(runtime.installation_root() / "webview_ui.py"),
                    ]
                )
                command += [instance["path"], instance["name"]]
                launch_id = uuid4().hex
                env = runtime.launch_environment(
                    {"data_dir": os.environ.get("MOWER_DATA_DIR", ""), "managed": True}
                )
                env.update(
                    MOWER_LAUNCH_ID=launch_id,
                    MOWER_MANAGER_PORT=str(settings["port"] or 0),
                )
                process = subprocess.Popen(
                    command,
                    cwd=runtime.installation_root(),
                    env=env,
                    **runtime.hidden_console_options(),
                )
                pending = dict(
                    id=launch_id,
                    pid=process.pid,
                    kind="instance",
                    space=instance["path"],
                    data_dir=env.get("MOWER_DATA_DIR", ""),
                    managed=True,
                    ready=False,
                    port=settings["port"],
                )
                key = hashlib.sha256(
                    instance_key(instance["path"]).encode()
                ).hexdigest()
                try:
                    runtime.write_json(
                        self._control_directory / f"{key}.json", pending, sync=True
                    )
                except BaseException as error:
                    try:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
                    except BaseException as cleanup_error:
                        error.add_note(f"关闭未登记的实例进程失败：{cleanup_error}")
                    raise
                threading.Thread(target=process.wait, daemon=True).start()
            return {"ok": True}
        except (
            OSError,
            ValueError,
            yaml.YAMLError,
            runtime.InstanceScanError,
        ) as error:
            return {"ok": False, "message": str(error)}

    def stop(self, idx):
        try:
            with self._operation():
                matches = self._matching(self.instances[idx], self._records())
                if any(not r.get("managed") for r in matches):
                    raise ValueError("该实例不是由多开管理器启动，请在实例中退出程序")
                for record in matches:
                    runtime.send_instance_command(record, "exit")
            return {"ok": True}
        except (OSError, ValueError, runtime.InstanceScanError) as error:
            return {"ok": False, "message": str(error)}

    def start_all(self):
        return self._bulk("start")

    def stop_all(self):
        return self._bulk("stop")

    def _bulk(self, action):
        with self._operation():
            results = []
            for idx in range(len(self.instances)):
                if action == "start":
                    records = self._records()
                    try:
                        self._start_settings(self.instances[idx], records)
                    except (OSError, ValueError, yaml.YAMLError):
                        continue
                    # 复用 start 的再次检查；大量实例时会增加登记扫描和端口探测开销。
                results.append(getattr(self, action)(idx))
        failures = [r["message"] for r in results if not r["ok"]]
        return {"ok": not failures, "message": "；".join(dict.fromkeys(failures))}
