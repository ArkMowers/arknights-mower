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

from . import manager_common
from . import update_runtime as runtime
from .manager_tools import ManagerTools
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
    updates = raw.get("updates_enabled", True)
    extra_settings = raw.get("extra_settings_visible", False)
    if type(extra_settings) is not bool:
        raise ValueError("显示额外设置开关必须是布尔值")
    automatic = raw.get("start_automatically", False)
    if type(automatic) is not bool:
        raise ValueError("启动后自动开始任务必须是布尔值")
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
            "start_automatically": automatic,
            "extra_settings_visible": extra_settings,
        },
    )


def validate_settings(settings, *, partial=False):
    allowed = {
        "token",
        "port",
        "ai_assistant_enabled",
        "updates_enabled",
        "start_automatically",
        "extra_settings_visible",
    }
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
    if (
        "start_automatically" in result
        and type(result["start_automatically"]) is not bool
    ):
        raise ValueError("启动后自动开始任务必须是布尔值")
    if (
        "extra_settings_visible" in result
        and type(result["extra_settings_visible"]) is not bool
    ):
        raise ValueError("显示额外设置开关必须是布尔值")
    return result


class InstanceTargetChangedError(ValueError):
    """The submitted instance identity no longer matches the shared list."""


class InstanceController(ManagerTools):
    def __init__(self, storage_path=None, ready=None):
        self._ready = ready
        self._lock = threading.RLock()
        self._operation_depth = 0
        self._maintenance_job = {"status": "idle"}
        self._maa_check = {}
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
        self._check_maintenance_start(instance)
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
                    updates_enabled=True,
                    start_automatically=False,
                    extra_settings_visible=False,
                    editable=False,
                    can_start=False,
                    can_stop=False,
                    can_open_browser=False,
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
                    item["can_open_browser"] = item["state"] == "running" and all(
                        r.get("managed") for r in matches
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

    @property
    def _common_path(self):
        return self._storage_path.parent / "config/manager-common.json"

    def get_common_settings(self):
        with self._operation():
            document = self._connection_document()
            return {
                "values": document["values"],
                "fields": manager_common.fields(),
            }

    def _connection_document(self, *, persist=True, skip_invalid=False):
        from .config import Conf
        from .config.device_profile import LEGACY_PROFILE_FIELDS

        document = manager_common.read_document(self._common_path)
        configurations = []
        missing_shared = (
            manager_common.SHARED_CONNECTION_KEYS - document["values"].keys()
        )
        shared = manager_common.SHARED_CONNECTION_KEYS
        legacy_paths = {"device.installation_path", "device.manager_path"}
        legacy_patch = {}
        if document["version"] == 0 and legacy_paths & document["values"].keys():
            for name, selected in document["values"].items():
                if name in manager_common.MANAGER_ONLY_KEYS:
                    continue
                if "." in name:
                    parent, child = name.split(".", 1)
                    legacy_patch.setdefault(parent, {})[child] = selected
                else:
                    legacy_patch[name] = selected
        bindings = {}
        for instance in self.instances:
            if not instance["path"]:
                continue
            key = manager_common.policy_key(instance_directory(instance["path"]))
            if document["version"] == 1 and key in document["independent_instances"]:
                if not missing_shared or document["independent_instances"][key]:
                    continue
            try:
                destination, raw = read_instance_config(instance["path"])
                configuration = Conf(**raw)
                upgrading_shared = (
                    document["version"] == 1
                    and key in document["independent_instances"]
                )
                if upgrading_shared:
                    configuration = manager_common.apply_settings(
                        configuration, document["values"]
                    )
            except (OSError, ValueError, yaml.YAMLError):
                if skip_invalid:
                    continue
                raise
            explicit = (
                set(manager_common.TEMPLATE_KEYS) | {"waiting_scene"}
                if upgrading_shared or document["version"] == 0
                else set()
            )
            for field in shared:
                current = raw
                for part in field.split("."):
                    if not isinstance(current, dict) or part not in current:
                        break
                    current = current[part]
                else:
                    explicit.add(field)
            for path, targets in LEGACY_PROFILE_FIELDS.items():
                current = raw
                for part in path:
                    if not isinstance(current, dict) or part not in current:
                        break
                    current = current[part]
                else:
                    explicit.update(
                        f"device.{name}"
                        for name in targets
                        if f"device.{name}" in shared
                    )
            if "low_frame_rate_mode" in raw:
                explicit.add("performance_mode")
            if "enable" in raw.get("tap_to_launch_game", {}):
                explicit.add("tap_to_launch_game.mode")
            configurations.append(
                (key, configuration, explicit, destination, raw, upgrading_shared)
            )

        def value(configuration, path):
            for part in path.split("."):
                configuration = getattr(configuration, part)
            return (
                configuration.model_dump(mode="json")
                if hasattr(configuration, "model_dump")
                else configuration
            )

        changed = (
            document["version"] == 0 or bool(configurations) or bool(missing_shared)
        )
        if document["version"] == 0 or missing_shared:
            baseline = Conf()
            for _, candidate, _, _, _, _ in configurations:
                try:
                    manager_common.validate_settings(
                        {name: value(candidate, name) for name in shared}
                    )
                except ValueError:
                    continue
                baseline = candidate
                break
            template_baseline = (
                baseline.updated(legacy_patch) if legacy_patch else baseline
            )
            for key in sorted(shared):
                source = (
                    template_baseline
                    if key in manager_common.TEMPLATE_KEYS
                    else baseline
                )
                document["values"].setdefault(key, value(source, key))
            document["version"] = 1
        for (
            key,
            configuration,
            explicit,
            destination,
            raw,
            upgrading_shared,
        ) in configurations:
            if legacy_patch:
                previous = configuration.updated(legacy_patch)
                data = configuration.model_dump()
                for name, selected in previous.device.model_dump().items():
                    if (
                        f"device.{name}" not in shared
                        or f"device.{name}" in manager_common.TEMPLATE_KEYS
                    ):
                        data["device"][name] = selected
                configuration = Conf(**data)
                explicit -= legacy_paths & document["values"].keys()
            independent = any(
                value(configuration, field) != document["values"][field]
                for field in explicit
            )
            try:
                manager_common.validate_settings(
                    {name: value(configuration, name) for name in shared}
                )
                manager_common.apply_settings(
                    configuration, document["values"], independent=independent
                )
            except ValueError:
                independent = True
            document["independent_instances"][key] = independent
            if independent and (legacy_patch or upgrading_shared):
                from . import managed_device

                preserved = copy.deepcopy(raw)
                values = (
                    managed_device.snapshot(configuration)
                    if upgrading_shared
                    else {
                        name: configuration.model_dump()[name]
                        for name in ("device", "simulator", "adb", "package_type")
                    }
                )
                for name, selected in values.items():
                    preserved[name] = (
                        {**preserved[name], **selected}
                        if isinstance(preserved.get(name), dict)
                        and isinstance(selected, dict)
                        else selected
                    )
                if preserved != raw:
                    bindings[destination] = preserved
        if changed:
            manager_common.validate_settings(document["values"])
            if persist:
                originals = {
                    path: path.read_bytes() if path.exists() else None
                    for path in (*bindings, self._common_path)
                }
                attempted = []
                try:
                    for path, raw in bindings.items():
                        attempted.append(path)
                        self._write_config(path, raw)
                    attempted.append(self._common_path)
                    runtime.write_json(self._common_path, document, sync=True)
                except BaseException:
                    failures = []
                    for path in reversed(attempted):
                        try:
                            original = originals[path]
                            if original is None:
                                path.unlink(missing_ok=True)
                            elif not path.exists() or path.read_bytes() != original:
                                self._write_config_bytes(path, original)
                        except OSError as error:
                            failures.append(error)
                    if failures:
                        raise OSError(
                            "配置迁移失败且无法完整恢复，请检查文件权限"
                        ) from failures[0]
                    raise
        return document

    def _connection_state(self, instance, raw, document):
        from .config import Conf

        key = manager_common.policy_key(instance_directory(instance["path"]))
        independent = document["independent_instances"].get(key, False)
        shared_values = {
            name: value
            for name, value in document["values"].items()
            if name in manager_common.SHARED_CONNECTION_KEYS
        }
        effective = manager_common.apply_settings(
            Conf(**raw), shared_values, independent=independent
        )
        policy = dict(
            independent_configuration=independent, shared_values=shared_values
        )
        return effective, independent, policy

    def add(self, name, path, targets=None):
        if not isinstance(name, str) or not name.strip() or not isinstance(path, str):
            raise ValueError("实例名称不能为空，保存目录必须是文本")
        with self._operation():
            self._check_targets(targets)
            self._save([*self.instances, {"name": name, "path": path}])

    def _check_targets(self, targets):
        if targets is not None and targets != [
            {key: item[key] for key in ("name", "path")} for item in self.instances
        ]:
            raise InstanceTargetChangedError("实例列表已变化，请刷新列表后重试")

    def _target_instance(self, idx, target=None):
        if target is not None and (
            type(idx) is not int
            or not 0 <= idx < len(self.instances)
            or target != {key: self.instances[idx][key] for key in ("name", "path")}
        ):
            raise InstanceTargetChangedError("实例已变化，请刷新列表后重试")
        return self.instances[idx]

    def remove(self, idx, target=None):
        with self._operation():
            instance = self._target_instance(idx, target)
            self._editable(instance, self._records())
            self._save([i for n, i in enumerate(self.instances) if n != idx])

    def rename(self, idx, name, target=None):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("实例名称不能为空")
        self._update(idx, {"name": name}, target)

    def set_path(self, idx, path, target=None):
        if not isinstance(path, str) or not path.strip():
            raise ValueError("实例保存目录不能为空")
        if not Path(path).is_absolute():
            raise ValueError("请填写 Mower 所在主机上的完整目录路径")
        self._update(idx, {"path": path}, target)

    def _update(self, idx, changes, target=None):
        with self._operation():
            instance = self._target_instance(idx, target)
            records = self._records()
            self._editable(instance, records)
            updated = copy.deepcopy(self.instances)
            updated[idx].update(changes)
            self._editable(updated[idx], records)
            self._save(updated)

    def update_settings(self, idx, settings, target=None):
        settings = validate_settings(settings)
        with self._operation():
            instance = self._target_instance(idx, target)
            self._editable(instance, self._records())
            self._write_settings(instance, settings)

    def _write_settings(self, instance, settings):
        if not instance["path"]:
            raise ValueError("请先选择实例保存目录")
        destination, raw = read_instance_config(instance["path"])
        current = {
            key: raw.get(key)
            if key
            in {
                "ai_assistant_enabled",
                "updates_enabled",
                "start_automatically",
                "extra_settings_visible",
            }
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
        if "start_automatically" in settings:
            raw["start_automatically"] = settings["start_automatically"]
        if "extra_settings_visible" in settings:
            raw["extra_settings_visible"] = settings["extra_settings_visible"]
        self._write_config(destination, raw)
        return True

    def _write_config(self, destination, raw):
        self._write_config_bytes(
            destination,
            yaml.dump(raw, Dumper=CoreDumper, allow_unicode=True).encode("utf-8"),
        )

    def _write_config_bytes(self, destination, content):
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            runtime.replace_with_retry(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def get_device_settings(self, idx, target):
        from . import managed_device

        with self._operation():
            instance = self._target(idx, target)
            self._editable(instance, self._records())
            if not instance["path"]:
                raise ValueError("请先选择实例保存目录")
            document = self._connection_document()
            _, raw = read_instance_config(instance["path"])
            configuration, independent, policy = self._connection_state(
                instance, raw, document
            )
            return {
                "values": managed_device.snapshot(configuration),
                "fields": managed_device.fields(),
                "independent_configuration": independent,
                "original_policy": policy,
                "shared_keys": sorted(manager_common.SHARED_CONNECTION_KEYS),
            }

    def update_device_settings(self, idx, changes, target, original, policy=None):
        from . import managed_device
        from .config import Conf

        if policy is not None and (
            not isinstance(policy, dict)
            or set(policy) != {"independent_configuration", "original_policy"}
            or type(policy["independent_configuration"]) is not bool
        ):
            raise ValueError("独立连接配置格式不正确")
        patch = managed_device.validate_patch(changes) if changes else {}
        if not changes and policy is None:
            raise ValueError("请选择需要保存的设备配置")
        derived = managed_device.DERIVED_IDENTITY_FIELDS
        submitted_identity = {
            key: value
            for key, value in patch.get("device", {}).items()
            if key in derived
        }
        candidates = None
        if any(submitted_identity.values()):
            discovery_changes = {
                key: value
                for key, value in changes.items()
                if key not in {f"device.{name}" for name in derived}
            }
            candidates = self.discover_device_settings(
                idx,
                discovery_changes,
                target,
                original,
                policy,
            ).get("candidates", [])
        with self._operation():
            instance = self._target(idx, target)
            self._editable(instance, self._records())
            if not instance["path"]:
                raise ValueError("请先选择实例保存目录")
            document = self._connection_document()
            destination, raw = read_instance_config(instance["path"])
            current, independent, current_policy = self._connection_state(
                instance, raw, document
            )
            if original != managed_device.snapshot(current):
                raise ValueError("设备配置已变化，请重新打开编辑器")
            if policy is not None and policy["original_policy"] != current_policy:
                raise ValueError("独立连接配置已变化，请重新打开编辑器")
            desired = (
                independent if policy is None else policy["independent_configuration"]
            )
            if not desired and set(changes) & (
                manager_common.SHARED_CONNECTION_KEYS | {"device.last_serial"}
            ):
                raise ValueError("共享连接参数只能在公共配置中修改，请先启用独立配置")
            baseline = (
                current
                if desired
                else manager_common.apply_settings(
                    Conf(**raw), current_policy["shared_values"]
                )
            )
            if "instance_name" in patch.get("device", {}) and (
                patch["device"]["instance_name"] != baseline.device.instance_name
            ):
                patch["device"]["last_serial"] = ""
                for name in derived:
                    patch["device"].setdefault(name, "")
            proposed = managed_device.snapshot(baseline.updated(patch))
            if submitted_identity:
                ordinary_patch = copy.deepcopy(patch)
                for key in derived:
                    ordinary_patch.get("device", {}).pop(key, None)
                automatic = baseline.updated(ordinary_patch).device.model_dump()
                if any(proposed["device"][key] != automatic[key] for key in derived):
                    if not candidates or not any(
                        (desired or candidate.get("shared_template_matches") is True)
                        and all(
                            proposed["device"].get(key) == value
                            for key, value in candidate.get("binding", {}).items()
                            if key not in {"last_serial", "game_package_confirmed"}
                        )
                        and all(
                            key in candidate.get("binding", {})
                            for key, value in submitted_identity.items()
                            if value
                        )
                        for candidate in candidates
                    ):
                        raise ValueError(
                            "实例识别信息由检测结果维护，请重新检测并选择实例"
                        )
            if not desired:
                # Validate the binding against shared launch values, but retain
                # local connection values and their synchronized legacy aliases.
                stored = managed_device.snapshot(Conf(**raw))
                for name in (
                    manager_common.SHARED_CONNECTION_KEYS - manager_common.TEMPLATE_KEYS
                ):
                    parts = name.split(".")
                    source, destination_values = stored, proposed
                    for part in parts[:-1]:
                        source, destination_values = (
                            source[part],
                            destination_values[part],
                        )
                    destination_values[parts[-1]] = source[parts[-1]]
                proposed = managed_device.snapshot(Conf(**proposed))
            # Preserve unknown private fields while synchronizing legacy aliases.
            for key, value in proposed.items():
                raw[key] = (
                    {**raw[key], **value}
                    if isinstance(raw.get(key), dict) and isinstance(value, dict)
                    else value
                )
            original_bytes = destination.read_bytes() if destination.exists() else None
            self._write_config(destination, raw)
            if desired != independent:
                key = manager_common.policy_key(instance_directory(instance["path"]))
                document["independent_instances"][key] = desired
                try:
                    runtime.write_json(self._common_path, document, sync=True)
                except BaseException:
                    if original_bytes is None:
                        destination.unlink(missing_ok=True)
                    else:
                        self._write_config_bytes(destination, original_bytes)
                    raise
            return {"ok": True}

    def discover_device_settings(self, idx, changes, target, original, policy=None):
        from . import managed_device

        if policy is not None and (
            not isinstance(policy, dict)
            or set(policy) != {"independent_configuration", "original_policy"}
            or type(policy["independent_configuration"]) is not bool
        ):
            raise ValueError("独立连接配置格式不正确")
        patch = managed_device.validate_patch(changes) if changes else {}
        with self._operation():
            instance = self._target(idx, target)
            self._editable(instance, self._records())
            if not instance["path"]:
                raise ValueError("请先选择实例保存目录")
            document = self._connection_document()
            _, raw = read_instance_config(instance["path"])
            current, independent, current_policy = self._connection_state(
                instance, raw, document
            )
            if original != managed_device.snapshot(current):
                raise ValueError("设备配置已变化，请重新打开编辑器")
            if policy is not None and policy["original_policy"] != current_policy:
                raise ValueError("独立连接配置已变化，请重新打开编辑器")
            desired = (
                independent if policy is None else policy["independent_configuration"]
            )
            if not desired and set(changes) & (
                manager_common.SHARED_CONNECTION_KEYS | {"device.last_serial"}
            ):
                raise ValueError("共享连接参数只能在公共配置中修改，请先启用独立配置")
            baseline = (
                current
                if desired
                else manager_common.apply_settings(
                    current, current_policy["shared_values"]
                )
            )
            configuration = baseline.updated(patch)
        result = managed_device.discover(configuration)
        if not desired:
            result = managed_device.project_shared_candidates(
                result, current_policy["shared_values"]
            )
        with self._operation():
            self._editable(self._target(idx, target), self._records())
        return result

    def update_all_settings(self, changes, targets, common=None):
        if not isinstance(changes, list) or (not changes and common is None):
            raise ValueError("请选择需要保存的实例配置")
        if common is not None:
            if not isinstance(common, dict) or set(common) != {"values", "original"}:
                raise ValueError("公共配置格式不正确")
            common_values = manager_common.validate_settings(common["values"])
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
                raise InstanceTargetChangedError("实例列表已变化，请重新打开批量配置")
            if any(idx >= len(current) for idx in selected):
                raise ValueError("批量配置包含无效实例")
            if common is not None:
                if runtime.active_job():
                    raise ValueError("软件更新或进程操作期间不能修改公共配置")
                if (
                    manager_common.read_settings(self._common_path)
                    != common["original"]
                ):
                    raise ValueError("公共配置已变化，请重新打开批量配置")
            results, seen = [], set()
            deadline = monotonic() + 10
            records = self._records()
            if common is not None:
                document = manager_common.read_document(self._common_path)
                if document["version"] == 1:
                    document = self._connection_document()
                    for key in manager_common.SHARED_CONNECTION_KEYS:
                        common_values.setdefault(key, document["values"][key])
                    document["values"] = common_values
                    runtime.write_json(self._common_path, document, sync=True)
                else:
                    runtime.write_json(self._common_path, common_values, sync=True)
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
            return {"ok": True, "results": results, "common_saved": common is not None}

    def start(self, idx, target=None):
        try:
            with self._operation():
                instance = self._target_instance(idx, target)
                settings = self._start_settings(instance, self._records())
                self._connection_document()
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
                common_settings = manager_common.read_settings(self._common_path)
                env = runtime.launch_environment(
                    {"data_dir": os.environ.get("MOWER_DATA_DIR", ""), "managed": True},
                    background=common_settings.get("startup_mode") == "background",
                )
                for name in tuple(env):
                    if name.startswith("MOWER_SUPERVISOR_") or name in (
                        "MOWER_RECOVERY_RUN",
                        "MOWER_RESUME_MODE",
                    ):
                        env.pop(name)
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

    def stop(self, idx, target=None):
        try:
            with self._operation():
                instance = self._target_instance(idx, target)
                matches = self._matching(instance, self._records())
                if any(not r.get("managed") for r in matches):
                    raise ValueError("该实例不是由多开管理器启动，请在实例中退出程序")
                for record in matches:
                    runtime.send_instance_command(record, "exit")
            return {"ok": True}
        except (OSError, ValueError, runtime.InstanceScanError) as error:
            return {"ok": False, "message": str(error)}

    def open_browser(self, idx, target):
        return self._open_instance_page(idx, target, action="browser")

    def open_instance_page(self, idx, target, mode=None, remember=False):
        return self._open_instance_page(idx, target, mode=mode, remember=remember)

    def _ready_instance_page(self, instance, records):
        matches = self._matching(instance, records)
        if not matches or any(not r.get("managed") for r in matches):
            raise ValueError("请先通过多开管理器启动此实例")
        if any(
            (runtime.state_dir() / "shutdown" / f"{r['id']}.json").exists()
            for r in matches
        ):
            raise ValueError("实例正在停止，无法打开网页")
        ready = next((r for r in matches if r.get("ready")), None)
        if ready is None:
            raise ValueError("实例尚未就绪，请稍后重试")
        return ready

    def _page_mode(self, mode, remember):
        if type(remember) is not bool:
            raise ValueError("记住打开方式必须是布尔值")
        if remember and mode is None:
            raise ValueError("请选择需要记住的实例页面打开方式")
        if mode is not None:
            manager_common.validate_settings({"instance_page_mode": mode})
        document = manager_common.read_document(self._common_path)
        return document, mode or document["values"].get("instance_page_mode")

    def _remember_page_mode(self, document, mode):
        if document["values"].get("instance_page_mode") == mode:
            return
        updated = copy.deepcopy(document)
        updated["values"]["instance_page_mode"] = mode
        runtime.write_json(
            self._common_path,
            updated if updated["version"] == 1 else updated["values"],
            sync=True,
        )

    def _open_instance_page(
        self, idx, target, *, action=None, mode=None, remember=False
    ):
        try:
            with self._operation():
                if (
                    type(idx) is not int
                    or not 0 <= idx < len(self.instances)
                    or target
                    != {key: self.instances[idx][key] for key in ("name", "path")}
                ):
                    raise ValueError("实例已变化，请刷新后重试")
                ready = self._ready_instance_page(self.instances[idx], self._records())
                if action is None:
                    document, selected_mode = self._page_mode(mode, remember)
                    if selected_mode is None:
                        return {
                            "ok": False,
                            "needs_mode": True,
                            "message": "请选择实例页面打开方式",
                        }
                    if remember:
                        self._remember_page_mode(document, selected_mode)
                    action = "show" if selected_mode == "webview" else "browser"
                runtime.send_instance_command(ready, action)
            return {"ok": True}
        except (OSError, ValueError, runtime.InstanceScanError) as error:
            return {"ok": False, "message": str(error)}

    def open_instance_pages(self, targets, mode=None, remember=False):
        try:
            with self._operation():
                if targets is None:
                    raise ValueError("请提供当前实例列表")
                self._check_targets(targets)
                document, selected_mode = self._page_mode(mode, remember)
                deadline = monotonic() + 10
                records = self._records()
                available = []
                for idx, instance in enumerate(self.instances):
                    try:
                        self._ready_instance_page(instance, records)
                        available.append(idx)
                    except ValueError:
                        pass
                if available and selected_mode is None:
                    return {
                        "ok": False,
                        "needs_mode": True,
                        "message": "请选择实例页面打开方式",
                    }
                results, blocked, remembered = [], "", False
                for idx, instance in enumerate(self.instances):
                    item = dict(
                        idx=idx, name=instance["name"], status="skipped", message=""
                    )
                    results.append(item)
                    if blocked or monotonic() >= deadline:
                        blocked = (
                            blocked or "打开实例页面已达到时间上限，请检查结果后重试"
                        )
                        item.update(status="failed", message=blocked)
                        continue
                    try:
                        records = self._records()
                    except (OSError, ValueError, runtime.InstanceScanError) as error:
                        blocked = str(error)
                        item.update(status="failed", message=blocked)
                        continue
                    try:
                        ready = self._ready_instance_page(instance, records)
                    except ValueError as error:
                        item["message"] = str(error)
                        continue
                    if selected_mode is None:
                        item["message"] = "尚未选择实例页面打开方式，请重试"
                        continue
                    if monotonic() >= deadline:
                        blocked = "打开实例页面已达到时间上限，请检查结果后重试"
                        item.update(status="failed", message=blocked)
                        continue
                    if remember and not remembered:
                        try:
                            self._remember_page_mode(document, selected_mode)
                            remembered = True
                        except (OSError, ValueError) as error:
                            blocked = str(error)
                            item.update(status="failed", message=blocked)
                            continue
                    if monotonic() >= deadline:
                        blocked = "打开实例页面已达到时间上限，请检查结果后重试"
                        item.update(status="failed", message=blocked)
                        continue
                    try:
                        runtime.send_instance_command(
                            ready, "show" if selected_mode == "webview" else "browser"
                        )
                        item["status"] = "opened"
                    except (OSError, ValueError) as error:
                        item.update(status="failed", message=str(error))
                return {
                    "ok": all(item["status"] != "failed" for item in results),
                    "results": results,
                }
        except (OSError, ValueError, runtime.InstanceScanError) as error:
            return {"ok": False, "message": str(error)}

    def start_all(self, targets=None):
        return self._bulk("start", targets=targets)

    def stop_all(self, targets=None):
        return self._bulk("stop", targets=targets)

    def _bulk(self, action, *, targets=None):
        with self._operation():
            self._check_targets(targets)
            results = []
            indices = range(len(self.instances))
            for idx in indices:
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
