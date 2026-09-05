"""Release discovery, upload validation and detached update job submission."""

import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import requests

from arknights_mower import __version__
from arknights_mower.utils import github_download, network_settings
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.software_update_worker import (
    MAX_PACKAGE_BYTES,
    SourceChangesError,
    require_clean_source,
)

REPO = "ArkMowers/arknights-mower"
API = f"https://api.github.com/repos/{REPO}"
RELEASES_URL = f"https://github.com/{REPO}/releases"
CHANNELS = [
    {
        "value": "stable",
        "label": "正式版",
        "description": "跟随正式 Release，适合希望减少变动的日常使用者。",
    },
    {
        "value": "beta",
        "label": "公测版",
        "description": "跟随预发布 Release（如 v4.1.6-alpha.3），提前体验修复和功能，可能存在不稳定行为。",
    },
    {
        "value": "dev",
        "label": "开发版（仅源码部署）",
        "description": "跟随 alpha 分支的最新提交，比公测版更新更频繁；需要 Git、Python 虚拟环境和 Node.js。",
    },
]
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?(?:\+.*)?$")
ASSET_RE = re.compile(
    r"^arknights-mower_(\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?)_(windows|linux|macos)_(x64|arm64)\.(zip|tar\.gz|dmg)$"
)
_checks = {}


def get_settings():
    saved = runtime.read_json(runtime.state_dir() / "settings.json", {})
    return {
        "channel": saved.get("channel", "beta" if "-" in __version__ else "stable"),
        "background": saved.get("background", True),
        "auto_check": saved.get("auto_check", False),
        "auto_update": saved.get("auto_update", False),
    }


def save_settings(data):
    if not isinstance(data, dict):
        raise ValueError("请提供软件更新设置")
    settings = get_settings()
    for key in ("background", "auto_check", "auto_update"):
        if key in data:
            if not isinstance(data[key], bool):
                raise ValueError("更新开关必须是布尔值")
            settings[key] = data[key]
    if "channel" in data:
        if data["channel"] not in {item["value"] for item in CHANNELS}:
            raise ValueError("未知更新渠道")
        if data["channel"] == "dev" and runtime.frozen():
            raise ValueError("开发版仅支持源码部署")
        settings["channel"] = data["channel"]
    if settings["auto_update"]:
        settings["auto_check"] = True
    with runtime.submission_lock(runtime.state_dir()):
        runtime.write_json(runtime.state_dir() / "settings.json", settings)
    return {"ok": True, "settings": settings}


def check_on_launch():
    """One installation checks once when several instances start together."""
    if os.environ.get("MOWER_RESTART_JOB"):
        return
    settings = get_settings()
    if not settings["auto_check"]:
        return
    state = runtime.state_dir()
    try:
        with runtime.submission_lock(state):
            if runtime.active_job(state):
                return
            previous = runtime.read_json(state / "auto-check.json", {})
            if time.time() - previous.get("started_at", 0) < 60:
                return
            runtime.write_json(state / "auto-check.json", {"started_at": time.time()})
        result = check(settings["channel"])
        if result["available"] and settings["auto_update"]:
            submit(result["check_id"], settings["background"])
    except Exception as error:
        runtime.write_json(
            state / "last-check.json",
            {
                "ok": False,
                "channel": settings["channel"],
                "message": "自动更新检查未完成：" + str(error),
                "checked_at": time.time(),
            },
        )


def version_key(value):
    match = VERSION_RE.fullmatch(value)
    if not match:
        raise ValueError(f"无法识别版本号：{value}")
    major, minor, patch, stage, number = match.groups()
    return (
        int(major),
        int(minor),
        int(patch),
        {"alpha": 0, "beta": 1, "rc": 2, None: 3}[stage],
        int(number or 0),
    )


def platform_asset():
    system = {"win32": "windows", "darwin": "macos", "linux": "linux"}.get(sys.platform)
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(
        platform.machine().lower()
    )
    if not system or not arch:
        raise ValueError("当前系统或架构没有受支持的 Release 安装包")
    return system, arch


validate_proxy = network_settings.normalize_http_proxy


def github(path, proxy=""):
    proxies = {"http": proxy, "https": proxy} if proxy else None
    response = requests.get(
        API + path,
        timeout=30,
        proxies=proxies,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Mower-Software-Update",
        },
    )
    if response.status_code == 403:
        raise ValueError("GitHub API 暂时限流，请稍后重试，或手动上传 Release 安装包")
    response.raise_for_status()
    return response.json()


def choose_release(releases, channel):
    candidates = [
        r
        for r in releases
        if not r.get("draft")
        and bool(r.get("prerelease")) == (channel == "beta")
        and VERSION_RE.fullmatch(r.get("tag_name", ""))
    ]
    if not candidates:
        raise ValueError("所选渠道暂无已发布版本")
    return max(candidates, key=lambda r: version_key(r["tag_name"]))


def choose_asset(release):
    system, arch = platform_asset()
    version = release["tag_name"].lstrip("v")
    extension = {"windows": "zip", "linux": "tar.gz", "macos": "dmg"}[system]
    name = f"arknights-mower_{version}_{system}_{arch}.{extension}"
    asset = next((a for a in release.get("assets", []) if a["name"] == name), None)
    if not asset:
        raise ValueError(
            f"此 Release 没有适配当前平台的 {name}；macOS 旧版 ZIP 请手动安装"
        )
    digest = asset.get("digest") or ""
    if not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest):
        raise ValueError("Release 缺少 SHA-256 校验值；请下载安装包后手动上传")
    url = asset["browser_download_url"]
    if not url.startswith(f"https://github.com/{REPO}/releases/download/"):
        raise ValueError("Release 下载地址不属于官方仓库")
    return {
        "name": name,
        "url": url,
        "size": asset["size"],
        "sha256": digest[7:].lower(),
    }


def source_tool_path():
    paths = os.environ.get("PATH", os.defpath).split(os.pathsep)
    if sys.platform == "darwin":
        # Finder/desktop launches do not inherit the interactive shell's PATH.
        paths.extend(("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"))
    return os.pathsep.join(dict.fromkeys(path for path in paths if path))


def source_tools(root):
    if not (root / ".git").exists():
        raise ValueError(
            "自动源码更新需要 Git 检出目录；下载的 Source code 压缩包不支持 Git 更新"
        )
    venv = Path(sys.prefix).resolve()
    if venv.parent != root.resolve() or venv.name not in (".venv", "venv"):
        raise ValueError("请使用安装目录内 .venv 或 venv 的 Python 启动 Mower 后更新")
    tool_path = source_tool_path()
    git, npm, node = (
        shutil.which(name, path=tool_path) for name in ("git", "npm", "node")
    )
    if not git or not npm or not node:
        raise ValueError(
            "未找到 "
            + "、".join(
                name
                for name, found in (("Git", git), ("npm", npm), ("Node.js", node))
                if not found
            )
            + "，请安装对应工具并检查启动环境的 PATH"
        )
    origin = (
        subprocess.check_output(
            [git, "remote", "get-url", "origin"], cwd=root, text=True, timeout=10
        )
        .strip()
        .removesuffix(".git")
        .rstrip("/")
        .lower()
    )
    if origin not in (
        f"https://github.com/{REPO}".lower(),
        f"git@github.com:{REPO}".lower(),
        f"ssh://git@github.com/{REPO}".lower(),
    ):
        raise ValueError("源码更新仅支持 origin 指向 ArkMowers/arknights-mower 的安装")
    return {
        "git": git,
        "npm": npm,
        "tool_path": tool_path,
        "python": sys.executable,
        "base_python": getattr(sys, "_base_executable", sys.executable),
        "venv_dir": venv.name,
    }


def info():
    root = runtime.installation_root()
    deployment = "release" if runtime.frozen() else "source"
    blockers = []
    source_changes = ""
    if deployment == "source":
        try:
            tools = source_tools(root)
            require_clean_source(tools["git"], root)
        except SourceChangesError as exc:
            source_changes = str(exc)
        except Exception as exc:
            blockers.append(str(exc))
    elif not os.access(root.parent, os.W_OK) or not os.access(root, os.W_OK):
        blockers.append(
            "安装位置不可写；请先将程序移至可写目录（macOS 请移出 DMG 后运行）"
        )
    registered = runtime.instances()
    if not any(r["pid"] == os.getpid() and r["kind"] == "instance" for r in registered):
        blockers.append(
            "请通过 webview_ui.py / Mower 桌面程序启动；直接运行 Flask 或容器请使用原部署工具更新"
        )
    settings = get_settings()
    return {
        "ok": True,
        "version": __version__,
        "deployment": deployment,
        "platform": sys.platform,
        "root": str(root),
        "channels": CHANNELS,
        "settings": {
            **settings,
            "proxy": network_settings.get_effective_settings()["http_proxy"],
        },
        "last_check": runtime.read_json(runtime.state_dir() / "last-check.json", {}),
        "blockers": blockers + ([source_changes] if source_changes else []),
        "source_changes": source_changes,
        "force_supported": deployment == "source" and not blockers,
        "instances": [
            {"name": r["name"] or "默认实例", "running": r["running"]}
            for r in registered
            if r["kind"] == "instance"
        ],
        "releases_url": RELEASES_URL,
        "manual_supported": deployment == "release",
    }


def check(channel, proxy=None):
    if channel not in {c["value"] for c in CHANNELS}:
        raise ValueError("未知更新渠道")
    network_settings.apply_http_proxy()
    proxy = (
        validate_proxy(proxy)
        if proxy is not None
        else network_settings.get_effective_settings()["http_proxy"]
    )
    deployment = "release" if runtime.frozen() else "source"
    plan = {
        "deployment": deployment,
        "channel": channel,
        "proxy": proxy,
        "created_at": time.time(),
    }
    if channel == "dev":
        if deployment != "source":
            raise ValueError("开发版仅支持源码部署")
        commit = github("/commits/alpha", proxy)
        plan.update(
            ref="refs/heads/alpha",
            commit=commit["sha"],
            version="alpha@" + commit["sha"][:7],
            notes=commit["commit"]["message"],
            url=f"https://github.com/{REPO}/commits/alpha",
        )
    else:
        # Fetch pages until both channel types have a candidate (not /latest,
        # which deliberately omits prereleases). Keep pagination bounded.
        releases = []
        for page in range(1, 6):
            batch = github(f"/releases?per_page=100&page={page}", proxy)
            releases.extend(batch)
            if (
                any(
                    not r.get("draft")
                    and bool(r.get("prerelease")) == (channel == "beta")
                    for r in batch
                )
                or len(batch) < 100
            ):
                break
        release = choose_release(releases, channel)
        plan.update(
            version=release["tag_name"],
            notes=release.get("body") or "暂无更新说明",
            url=release["html_url"],
        )
        if deployment == "source":
            commit = github("/commits/" + quote(release["tag_name"], safe=""), proxy)
            plan.update(ref="refs/tags/" + release["tag_name"], commit=commit["sha"])
        else:
            plan["asset"] = choose_asset(release)
    if deployment == "source":
        current = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=runtime.installation_root(),
            text=True,
            timeout=10,
        ).strip()
        available = current != plan["commit"] and (
            channel == "dev" or version_key(plan["version"]) > version_key(__version__)
        )
    else:
        available = version_key(plan["version"]) > version_key(__version__)
    check_id = uuid4().hex
    plan["available"] = available
    plan["force_available"] = deployment == "source" and (
        available or current == plan["commit"]
    )
    _checks.clear()
    _checks[check_id] = plan
    result = {
        "ok": True,
        "check_id": check_id if available or plan["force_available"] else "",
        "available": available,
        "version": plan["version"],
        "notes": plan["notes"],
        "url": plan["url"],
        "message": "发现可用更新"
        if available
        else "当前版本已是所选渠道最新版本，或比该渠道更新",
    }
    runtime.write_json(
        runtime.state_dir() / "last-check.json",
        {
            **{key: value for key, value in result.items() if key != "check_id"},
            "channel": channel,
            "checked_at": time.time(),
        },
    )
    return result


def submit(check_id, background=False, *, force=False):
    plan = _checks.get(check_id)
    if not plan or time.time() - plan["created_at"] > 1800:
        raise ValueError("版本检查已过期，请重新检查更新")
    if not force and not plan.get("available", True):
        raise ValueError("当前没有可用更新")
    if force and not plan.get("force_available", True):
        raise ValueError("强制更新不支持切换到更旧的发布版本")
    return start_job(plan, background, force=force)


def start_job(plan, background=False, uploaded=None, *, force=False):
    with runtime.submission_lock(runtime.state_dir()):
        return _start_job(plan, background, uploaded, force=force)


def _start_job(plan, background=False, uploaded=None, *, force=False):
    if not isinstance(force, bool):
        raise ValueError("强制更新选项必须是布尔值")
    if force and (plan["deployment"] != "source" or uploaded is not None):
        raise ValueError("强制更新仅支持源码部署")
    details = info()
    if details["blockers"] and not (force and details.get("force_supported", False)):
        raise ValueError("；".join(details["blockers"]))
    network_settings.apply_http_proxy()
    root = runtime.installation_root()
    tools = source_tools(root) if plan["deployment"] == "source" else {}
    if tools:
        require_clean_source(tools["git"], root, force=force)
    state = runtime.state_dir()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = state / "active"
    if lock.exists():
        owner = runtime.read_json(lock / "owner.json", {})
        if not owner or runtime.process_alive(owner.get("pid")):
            raise ValueError("同一安装目录已有更新任务，请等待完成")
        shutil.rmtree(lock)
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise ValueError("其他实例正在提交更新任务") from exc
    job_id = uuid4().hex
    runtime.write_json(lock / "owner.json", {"id": job_id, "pid": os.getpid()})
    work = state / "jobs" / job_id
    work.mkdir(parents=True, mode=0o700)
    try:
        job = {
            **plan,
            **tools,
            "id": job_id,
            "root": str(root),
            "state_dir": str(state),
            "background": bool(background),
            "force": force,
            "github_proxy": github_download.get_proxy(),
            "proxy": network_settings.get_effective_settings()["http_proxy"],
        }
        if uploaded:
            shutil.move(str(uploaded), work / plan["asset"]["name"])
        job_path = work / "job.json"
        runtime.write_json(job_path, job)
        runtime.write_json(
            state / "settings.json",
            {**get_settings(), **{k: job[k] for k in ("channel", "background")}},
        )
        runtime.write_json(
            state / "status.json",
            {
                "id": job_id,
                "status": "running",
                "phase": "preparing",
                "version": plan["version"],
                "message": "正在启动独立更新程序",
                "log_path": str(work / "update.log"),
            },
        )
        if plan["deployment"] == "source":
            # Stage PySocks before moving the old venv. Only pip's subprocess
            # receives this bootstrap module through PYTHONPATH.
            if any(
                value.lower().startswith(("socks5://", "socks5h://"))
                for key, value in os.environ.items()
                if key.lower() in ("http_proxy", "https_proxy", "all_proxy")
            ):
                try:
                    import socks
                except ImportError as exc:
                    raise ValueError(
                        "SOCKS 代理需要 PySocks，请先更新 Python 依赖"
                    ) from exc
                shutil.copy2(socks.__file__, work / "socks.py")
            for name in (
                "software_update_worker.py",
                "update_runtime.py",
                "github_download.py",
            ):
                shutil.copy2(Path(__file__).with_name(name), work / name)
            command = [
                tools["base_python"],
                str(work / "software_update_worker.py"),
                str(job_path),
            ]
        else:
            # Copy only application-owned runtime paths, never portable user data.
            runner = work / "runner" / root.name
            if root.suffix == ".app":
                shutil.copytree(root, runner, symlinks=True)
            else:
                runner.mkdir(parents=True)
                shutil.copytree(root / "_internal", runner / "_internal", symlinks=True)
                shutil.copy2(sys.executable, runner / Path(sys.executable).name)
            executable = runner / Path(sys.executable).resolve().relative_to(root)
            command = [str(executable), "--software-update-worker", str(job_path)]
        with (work / "update.log").open("ab") as log:
            process = subprocess.Popen(
                command,
                cwd=work,
                env=runtime.launch_environment({}),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                **runtime.detached_options(),
            )
        runtime.write_json(lock / "owner.json", {"id": job_id, "pid": process.pid})
        return {"ok": True, "id": job_id, "message": "更新任务已启动"}
    except Exception:
        shutil.rmtree(lock, ignore_errors=True)
        runtime.write_json(
            state / "status.json",
            {
                "id": job_id,
                "status": "failed",
                "phase": "failed",
                "message": "独立更新程序未能启动，请检查安装目录权限和可用磁盘空间",
            },
        )
        raise


def status():
    state = runtime.state_dir()
    result = runtime.read_json(
        state / "status.json", {"status": "idle", "message": "尚未执行软件更新"}
    )
    if result.get("status") == "running" and not runtime.active_job(state):
        result.update(
            status="failed", message="更新程序意外退出，请查看日志和备份后再试"
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


def manual_plan(filename, proxy=""):
    if not runtime.frozen():
        raise ValueError(
            "Release 安装包用于独立包部署；源码部署请选择正式版、公测版或开发版进行 Git 更新"
        )
    match = ASSET_RE.fullmatch(filename or "")
    if not match:
        raise ValueError(
            "请上传官方 Release 安装包，保留原始文件名；不接受热更包、资源包或 Source code 压缩包"
        )
    version, system, arch, extension = match.groups()
    if (system, arch) != platform_asset():
        raise ValueError("安装包的系统或架构与当前运行程序不匹配")
    if extension != {"windows": "zip", "linux": "tar.gz", "macos": "dmg"}[system]:
        raise ValueError("当前系统不支持此安装包格式；macOS 请使用 DMG")
    if version_key(version) <= version_key(__version__):
        raise ValueError("安装包版本不高于当前版本；为保护配置，不支持直接降级")
    return {
        "deployment": "release",
        "manual": True,
        "channel": "beta" if "-" in version else "stable",
        "proxy": validate_proxy(proxy),
        "version": "v" + version,
        "asset": {"name": filename},
        "created_at": time.time(),
    }


def upload_package(upload, proxy="", background=False):
    if not upload:
        raise ValueError("请选择 Release 安装包")
    plan = manual_plan(upload.filename, proxy)
    state = runtime.state_dir()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = state / f"upload-{uuid4().hex}"
    try:
        size = 0
        with temporary.open("wb") as stream:
            while chunk := upload.stream.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_PACKAGE_BYTES:
                    raise ValueError("安装包超过 2 GiB 限制")
                stream.write(chunk)
        plan["asset"]["size"] = size
        return start_job(plan, background, uploaded=temporary)
    finally:
        temporary.unlink(missing_ok=True)
