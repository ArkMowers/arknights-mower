"""Local manager maintenance and read-only configuration previews."""

import copy
import json
import os
import threading
from contextlib import ExitStack
from pathlib import Path
from time import monotonic, time

import yaml
from pydantic import ValidationError

from . import manager_common
from . import update_runtime as runtime
from .device_compatibility import capture_compatibility_error
from .path import resolve_config_path


def _value(raw, key, default=None):
    for part in key.split("."):
        if not isinstance(raw, dict) or part not in raw:
            return default
        raw = raw[part]
    return raw


def _maa_target(raw, common):
    value = common.get("maa_path", raw.get("maa_path", "@app/MAA"))
    if not isinstance(value, str) or not value.strip():
        raise ValueError("MAA 安装目录无效")
    return str(Path(resolve_config_path(value)).expanduser().resolve())


def _files(root, deadline, limit=100000):
    """Walk a bounded tree without following directory or file links."""
    stack = [root]
    count = 0
    while stack:
        folder = stack.pop()
        if folder.is_symlink():
            continue
        try:
            entries = os.scandir(folder)
        except FileNotFoundError:
            continue
        with entries:
            for entry in entries:
                count += 1
                if count > limit or monotonic() >= deadline:
                    raise ValueError("文件过多或扫描超时，请缩小范围后重试")
                if entry.is_symlink():
                    continue
                path = Path(entry.path)
                if entry.is_dir(follow_symlinks=False):
                    stack.append(path)
                elif entry.is_file(follow_symlinks=False):
                    yield path


class ManagerTools:
    def _target(self, idx, target):
        if (
            type(idx) is not int
            or not 0 <= idx < len(self.instances)
            or target != {k: self.instances[idx][k] for k in ("name", "path")}
        ):
            raise ValueError("实例已变化，请刷新后重试")
        return self.instances[idx]

    def _raw(self, instance):
        from .manager_instances import read_instance_config

        return read_instance_config(instance["path"])[1]

    def get_mower_update_info(self):
        from . import software_update

        return software_update.info()

    def check_mower_update(self, channel):
        from . import software_update

        return software_update.check(channel)

    def start_mower_update(self, check_id, background):
        from . import software_update

        if not isinstance(check_id, str) or type(background) is not bool:
            raise ValueError("Mower 更新请求无效")
        with self._lock:
            if self._maintenance_job.get("status") == "running":
                raise ValueError("请先等待 MAA 维护完成")
            return software_update.submit(check_id, background)

    def get_mower_update_status(self):
        from . import software_update

        return software_update.status()

    def cancel_mower_update(self, job_id):
        from . import software_update

        return software_update.cancel(job_id)

    def get_network_settings(self):
        from . import network_settings

        try:
            raw = json.loads(
                network_settings.settings_path().read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            raw = {}
        if not isinstance(raw, dict):
            raise ValueError("网络配置格式不正确")
        return {
            "http_proxy": network_settings.normalize_http_proxy(
                raw.get("http_proxy", "")
            ),
            "github_proxy": network_settings.normalize_proxy(
                raw.get("github_proxy", "")
            ),
        }

    def save_network_settings(self, values, original):
        from . import network_settings

        if not isinstance(values, dict) or set(values) != {
            "http_proxy",
            "github_proxy",
        }:
            raise ValueError("网络配置格式不正确")
        with self._operation():
            if self.get_network_settings() != original:
                raise ValueError("网络配置已变化，请重新加载")
            return network_settings.save_settings(values)

    def preview_common_settings(self, values, targets):
        from .config import Conf
        from .manager_instances import instance_directory

        values = manager_common.validate_settings(values)
        with self._operation():
            if targets != [{k: i[k] for k in ("name", "path")} for i in self.instances]:
                raise ValueError("实例列表已变化，请重新打开批量配置")
            document = self._connection_document(persist=False, skip_invalid=True)
            rows = []
            for idx, instance in enumerate(self.instances):
                row = dict(idx=idx, name=instance["name"], warnings=[], fields=[])
                rows.append(row)
                try:
                    if not instance["path"]:
                        raise ValueError("尚未选择保存目录")
                    raw = self._raw(instance)
                    configuration = Conf(**raw)
                    key = manager_common.policy_key(
                        instance_directory(instance["path"])
                    )
                    independent = document["independent_instances"].get(key, False)
                    row["independent_configuration"] = independent
                    proposed = manager_common.instance_values(
                        document, key, values=values
                    )
                    current_values = manager_common.instance_values(document, key)
                    if reason := capture_compatibility_error(
                        proposed.get(
                            "device.preset_id", configuration.device.preset_id
                        ),
                        proposed.get("device.screenshot_backend"),
                    ):
                        row["warnings"].append(reason)
                    current_configuration = configuration.model_dump()
                    for field in manager_common.FIELDS:
                        key = field["key"]
                        if (
                            key in manager_common.MANAGER_ONLY_KEYS
                            or key not in proposed
                        ):
                            continue
                        current = current_values.get(
                            key, _value(current_configuration, key)
                        )
                        # A preview never returns secrets from either source.
                        password = field["kind"] == "password"
                        row["fields"].append(
                            dict(
                                label=field["label"],
                                before="已设置"
                                if password and current
                                else "未设置"
                                if password
                                else current,
                                after="已设置"
                                if password and proposed[key]
                                else "未设置"
                                if password
                                else proposed[key],
                            )
                        )
                except (OSError, ValueError, yaml.YAMLError) as error:
                    row["warnings"].append(
                        "实例配置格式不正确，请检查 conf.yml"
                        if isinstance(error, (ValidationError, yaml.YAMLError))
                        else str(error)
                    )
            return {"rows": rows, "future_instances": True}

    def get_storage_usage(self):
        from .manager_instances import instance_directory, instance_key

        with self._operation():
            rows, seen = [], set()
            records = self._records()
            deadline = monotonic() + 8
            for idx, instance in enumerate(self.instances):
                row = dict(
                    idx=idx,
                    name=instance["name"],
                    path=instance["path"],
                    log=0,
                    screenshot=0,
                    can_clean=False,
                )
                rows.append(row)
                try:
                    if not instance["path"]:
                        continue
                    try:
                        self._editable(instance, records)
                        row["can_clean"] = True
                    except (OSError, ValueError) as error:
                        row["clean_reason"] = str(error)
                    key = instance_key(instance["path"])
                    if key in seen:
                        row["warning"] = "与其他实例共用保存目录，不重复计数"
                        continue
                    seen.add(key)
                    for category in ("log", "screenshot"):
                        root = instance_directory(instance["path"]) / category
                        if root.is_symlink():
                            row["warning"] = "目录是符号链接，已跳过"
                            continue
                        for path in _files(root, deadline):
                            row[category] += path.stat().st_size
                except (OSError, ValueError, yaml.YAMLError) as error:
                    row["warning"] = str(error)
            return {"rows": rows}

    def clean_instance_storage(self, idx, target, categories, older_days):
        from .manager_instances import instance_directory

        if (
            not isinstance(categories, list)
            or not categories
            or any(c not in {"log", "screenshot"} for c in categories)
            or type(older_days) is not int
            or not 0 <= older_days <= 3650
        ):
            raise ValueError("清理范围无效")
        with self._operation():
            instance = self._target(idx, target)
            if not instance["path"]:
                raise ValueError("请先选择实例保存目录")
            self._editable(instance, self._records())
            cutoff = time() - older_days * 86400
            deadline = monotonic() + 8
            deleted = freed = 0
            errors = []
            for category in dict.fromkeys(categories):
                root = instance_directory(instance["path"]) / category
                try:
                    if root.is_symlink():
                        raise ValueError("不能清理符号链接目录")
                    for path in _files(root, deadline):
                        # Recheck ancestry; a path may have been replaced during scanning.
                        if any(
                            p.is_symlink()
                            for p in (path, *path.parents)
                            if p != root.parent
                        ):
                            continue
                        stat = path.stat()
                        if older_days and stat.st_mtime >= cutoff:
                            continue
                        try:
                            path.unlink()
                            deleted += 1
                            freed += stat.st_size
                        except OSError as error:
                            if len(errors) < 10:
                                errors.append(str(error))
                except (OSError, ValueError, yaml.YAMLError) as error:
                    errors.append(str(error))
                    break
            return {"ok": True, "deleted": deleted, "freed": freed, "errors": errors}

    def get_maa_installations(self):
        from .manager_instances import instance_directory

        with self._operation():
            document = manager_common.read_document(self._common_path)
            records = self._records()
            groups = {}
            errors = []
            for instance in self.instances:
                try:
                    if not instance["path"]:
                        continue
                    raw = self._raw(instance)
                    common = manager_common.instance_values(
                        document, instance_directory(instance["path"])
                    )
                    target = _maa_target(raw, common)
                    key = os.path.normcase(target)
                    group = groups.setdefault(
                        key,
                        dict(
                            target=target,
                            instances=[],
                            channels=[],
                            running=False,
                        ),
                    )
                    group["instances"].append(instance["name"])
                    channel = common.get(
                        "maa_update_channel", raw.get("maa_update_channel", "stable")
                    )
                    if channel not in {"stable", "beta"}:
                        raise ValueError("MAA 更新通道无效")
                    if channel not in group["channels"]:
                        group["channels"].append(channel)
                    group["running"] |= bool(self._matching(instance, records))
                except (OSError, ValueError, yaml.YAMLError) as error:
                    errors.append(f"{instance['name']}：{error}")
            return {"groups": list(groups.values()), "errors": errors}

    def _check_maintenance_start(self, instance):
        job = self._maintenance_job
        if job.get("status") == "running" and job.get("action") == "update":
            from .manager_instances import instance_directory

            target = _maa_target(
                self._raw(instance),
                manager_common.instance_values(
                    manager_common.read_document(self._common_path),
                    instance_directory(instance["path"]),
                ),
            )
            if os.path.normcase(target) == os.path.normcase(job["target"]):
                raise ValueError("此实例使用的 MAA 正在更新，请完成后再启动")

    def request_close(self):
        with self._lock:
            return self._maintenance_job.get("status") != "running"

    def get_maintenance_status(self):
        with self._lock:
            return copy.deepcopy(self._maintenance_job)

    def start_maa_maintenance(self, target, channel, component, action):
        if (
            channel not in {"stable", "beta"}
            or component not in {"core", "resource"}
            or action not in {"check", "update"}
        ):
            raise ValueError("MAA 维护请求无效")
        with self._operation():
            if self._maintenance_job["status"] == "running" or runtime.active_job():
                raise ValueError("已有维护操作正在进行中")
            snapshot = self.get_maa_installations()
            group = next((g for g in snapshot["groups"] if g["target"] == target), None)
            if snapshot["errors"] or group is None:
                raise ValueError("MAA 使用范围无法确认，请重新加载")
            if group["running"] and action == "update":
                raise ValueError("请先停止使用此 MAA 目录的实例")
            check = self._maa_check
            if action == "update" and (
                check.get("target") != target
                or check.get("channel") != channel
                or check.get("component") != component
                or not check.get("available")
                or monotonic() - check.get("time", 0) > 600
            ):
                raise ValueError("请先检查更新，发现新版本后再更新")
            self._maintenance_job = dict(
                status="running",
                target=target,
                action=action,
                channel=channel,
                component=component,
                message="正在检查更新" if action == "check" else "正在更新",
            )
            self._maa_check = {}
            thread = threading.Thread(
                target=self._maa_worker,
                args=(target, channel, component, action, copy.deepcopy(check)),
                daemon=True,
            )
            thread.start()
            return {"ok": True}

    def _maa_worker(self, target, channel, component, action, check):
        try:
            with ExitStack() as cleanup:
                state = runtime.state_dir()
                with runtime.submission_lock(state):
                    if runtime.active_job():
                        raise ValueError(
                            "软件更新或进程操作正在进行，请完成后再维护 MAA"
                        )
                    cleanup.enter_context(runtime.manager_maintenance_lock(state))
                self._run_maa_worker(target, channel, component, action, check)
        except Exception as error:
            from .log import logger

            logger.exception("多开管理器 MAA 维护失败")
            with self._lock:
                self._maintenance_job.update(status="failed", message=str(error))

    def _run_maa_worker(self, target, channel, component, action, check):
        from arknights_mower import __system__

        from .maa_resource_update import (
            get_maa_resource_release,
            install_maa_resource_update,
            read_maa_resource_info,
        )
        from .maa_update import (
            get_latest_release,
            has_maa_installation,
            install_latest_maa,
            is_maa_version_newer,
            read_installed_version,
        )

        current = (
            read_installed_version(target, fresh=True)
            if component == "core"
            else read_maa_resource_info(target)["version"]
        )
        if action == "check":
            if component == "core":
                if has_maa_installation(target) and not current:
                    raise ValueError(
                        "无法读取 MAA 本体版本，请检查安装是否完整及目录读取权限"
                    )
                latest = get_latest_release(
                    system=__system__, channel=channel, installed_version=current
                )
                available = not has_maa_installation(target) or bool(
                    current and is_maa_version_newer(latest.tag, current)
                )
                version = latest.tag
            else:
                latest = get_maa_resource_release("github", current_version=current)
                available, version = latest.available, latest.version
            with self._lock:
                self._maa_check = dict(
                    target=target,
                    channel=channel,
                    component=component,
                    available=available,
                    version=version,
                    current=current,
                    time=monotonic(),
                )
            result = dict(current=current, latest=version, available=available)
        else:
            if current != check.get("current"):
                raise ValueError("MAA 安装已变化，请重新检查更新")

            def progress(phase, done, total, message):
                with self._lock:
                    self._maintenance_job.update(
                        message=message, progress=done / total if total else None
                    )

            if component == "core":
                result = install_latest_maa(
                    target, system=__system__, channel=channel, callback=progress
                )
            else:
                result = install_maa_resource_update(
                    target, system=__system__, callback=progress
                )
        with self._lock:
            self._maintenance_job.update(
                status="completed",
                result=result,
                message="检查完成" if action == "check" else "维护完成",
            )
