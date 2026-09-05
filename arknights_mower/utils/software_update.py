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
from arknights_mower.utils.software_update_worker import MAX_PACKAGE_BYTES

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
        "description": "跟随 alpha 分支的最新提交，比公测版更新更频繁；需要 Git、Git LFS、Python 虚拟环境和 Node.js。",
    },
]
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?(?:\+.*)?$")
ASSET_RE = re.compile(
    r"^arknights-mower_(\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?)_(windows|linux|macos)_(x64|arm64)\.(zip|tar\.gz|dmg)$"
)
_checks = {}


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


def source_tools(root):
    if not (root / ".git").exists():
        raise ValueError(
            "自动源码更新需要 Git 检出目录；下载的 Source code 压缩包不支持 Git 更新"
        )
    venv = Path(sys.prefix).resolve()
    if venv.parent != root.resolve() or venv.name not in (".venv", "venv"):
        raise ValueError("请使用安装目录内 .venv 或 venv 的 Python 启动 Mower 后更新")
    git, npm = shutil.which("git"), shutil.which("npm")
    if not git or not npm:
        raise ValueError(
            "未找到 Git 或 npm，请安装 Git、Git LFS 和 Node.js 并检查启动环境的 PATH"
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
    subprocess.run(
        [git, "lfs", "version"], cwd=root, capture_output=True, check=True, timeout=10
    )
    return {
        "git": git,
        "npm": npm,
        "python": sys.executable,
        "base_python": getattr(sys, "_base_executable", sys.executable),
        "venv_dir": venv.name,
    }


def info():
    root = runtime.installation_root()
    deployment = "release" if runtime.frozen() else "source"
    blockers = []
    if deployment == "source":
        try:
            tools = source_tools(root)
            if subprocess.check_output(
                [tools["git"], "status", "--porcelain", "--untracked-files=normal"],
                cwd=root,
                timeout=10,
            ):
                blockers.append(
                    "源码目录有未提交修改或未跟踪文件，请先提交或自行备份；不会执行强制重置"
                )
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
    settings = runtime.read_json(runtime.state_dir() / "settings.json", {})
    return {
        "ok": True,
        "version": __version__,
        "deployment": deployment,
        "platform": sys.platform,
        "root": str(root),
        "channels": CHANNELS,
        "settings": {
            "channel": settings.get(
                "channel", "beta" if "-" in __version__ else "stable"
            ),
            "proxy": network_settings.get_effective_settings()["http_proxy"],
            "background": settings.get("background", True),
        },
        "blockers": blockers,
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
    _checks.clear()
    _checks[check_id] = plan
    return {
        "ok": True,
        "check_id": check_id if available else "",
        "available": available,
        "version": plan["version"],
        "notes": plan["notes"],
        "url": plan["url"],
        "message": "发现可用更新"
        if available
        else "当前版本已是所选渠道最新版本，或比该渠道更新",
    }


def submit(check_id, background=False):
    plan = _checks.get(check_id)
    if not plan or time.time() - plan["created_at"] > 1800:
        raise ValueError("版本检查已过期，请重新检查更新")
    return start_job(plan, background)


def start_job(plan, background=False, uploaded=None):
    with runtime.submission_lock(runtime.state_dir()):
        return _start_job(plan, background, uploaded)


def _start_job(plan, background=False, uploaded=None):
    details = info()
    if details["blockers"]:
        raise ValueError("；".join(details["blockers"]))
    network_settings.apply_http_proxy()
    root = runtime.installation_root()
    tools = source_tools(root) if plan["deployment"] == "source" else {}
    if tools:
        dirty = subprocess.check_output(
            [tools["git"], "status", "--porcelain", "--untracked-files=normal"],
            cwd=root,
            timeout=10,
        )
        if dirty:
            raise ValueError(
                "源码目录有未提交修改或未跟踪文件，请先提交或自行备份；不会执行强制重置"
            )
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
            "github_proxy": github_download.get_proxy(),
            "proxy": network_settings.get_effective_settings()["http_proxy"],
        }
        if uploaded:
            shutil.move(str(uploaded), work / plan["asset"]["name"])
        job_path = work / "job.json"
        runtime.write_json(job_path, job)
        runtime.write_json(
            state / "settings.json",
            {k: job[k] for k in ("channel", "proxy", "background")},
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
    return {"ok": True, **result}


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
