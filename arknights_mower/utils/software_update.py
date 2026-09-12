"""Release discovery, upload validation and detached update job submission."""

import hashlib
import importlib.util
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from threading import RLock, Thread, current_thread
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
        "description": "跟随 GitHub 标记为 Latest 的正式 Release，适合希望减少变动的日常使用者。",
    },
    {
        "value": "beta",
        "label": "公测版",
        "description": "跟随预发布 Release（如 v4.1.6-alpha.3），提前体验修复和功能，可能存在不稳定行为。",
    },
    {
        "value": "dev",
        "label": "开发版（仅源码部署）",
        "description": "跟随所选源码分支（默认 alpha）的最新提交，比公测版更新更频繁；需要 Git、Python 和 Node.js。",
    },
]
VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?(?:\+.*)?$")
_checks = {}
_auto_check_lock = RLock()
_auto_check_thread = None
_auto_check_revision = 0


def remember_check(plan):
    # A branch preview must not invalidate an update checked in another tab.
    for key, previous in list(_checks.items()):
        if time.time() - previous["created_at"] > 1800:
            _checks.pop(key, None)
    while len(_checks) >= 32:
        _checks.pop(next(iter(_checks)), None)
    check_id = uuid4().hex
    _checks[check_id] = plan
    return check_id


def normalize_source_ref(value):
    if not isinstance(value, str):
        raise ValueError("请填写分支、提交 SHA 或 tag")
    value = value.strip()
    if (
        not value
        or len(value) > 255
        or value.startswith(("-", "/", "."))
        or any(
            ord(char) <= 32 or ord(char) == 127 or char in "~^:?*[\\" for char in value
        )
        or any(part in value for part in ("..", "//", "@{"))
        or any(
            part.startswith(".") or part.endswith((".", ".lock"))
            for part in value.split("/")
        )
        or value.endswith("/")
        or value == "@"
    ):
        raise ValueError("请填写有效的分支、提交 SHA 或 tag，不接受 URL 或 Git 命令")
    return value


def get_settings():
    saved = runtime.read_json(runtime.state_dir() / "settings.json", {})
    return {
        "channel": saved.get("channel", "beta" if "-" in __version__ else "stable"),
        "background": saved.get("background", True),
        "auto_check": saved.get("auto_check", False),
        "auto_update": saved.get("auto_update", False),
        "source_branch": saved.get("source_branch", "alpha"),
        "source_remote": saved.get("source_remote", "origin"),
        "source_remote_history": saved.get("source_remote_history", []),
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


def automatic_check_key(settings):
    return {
        key: settings[key]
        for key in (
            "channel",
            "source_branch",
            "source_remote",
            "auto_check",
            "auto_update",
        )
    }


def check_on_launch():
    """One installation checks once when several instances start together."""
    settings = get_settings()
    if not settings["auto_check"]:
        return True
    state = runtime.state_dir()
    try:
        with runtime.submission_lock(state):
            if runtime.active_job(state):
                return False
            previous = runtime.read_json(state / "auto-check.json", {})
            key = automatic_check_key(settings)
            if (
                previous.get("settings") == key
                and time.time() - previous.get("started_at", 0) < 60
            ):
                return True
            runtime.write_json(
                state / "auto-check.json", {"started_at": time.time(), "settings": key}
            )
        result = check(settings["channel"])
        current = get_settings()
        # A settings change while the request was in flight must not install an
        # obsolete channel or ignore a newly disabled automatic-update switch.
        completed = runtime.read_json(state / "status.json", {})
        recent_restart = (
            os.environ.get("MOWER_RESTART_JOB")
            and completed.get("id") == os.environ["MOWER_RESTART_JOB"]
            and completed.get("status") in {"succeeded", "failed", "cancelled"}
            and time.time() - completed.get("updated_at", 0) < 60
        )
        if (
            result["available"]
            and not result.get("downgrade", False)
            and current["auto_update"]
            and automatic_check_key(current) == automatic_check_key(settings)
            and not recent_restart
        ):
            submit(result["check_id"], current["background"])
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
    return True


def request_auto_check():
    """Check on app entry or settings changes; coalesce simultaneous callers."""
    global _auto_check_thread, _auto_check_revision
    if not get_settings()["auto_check"]:
        return {"ok": True, "scheduled": False}

    def run():
        global _auto_check_thread
        try:
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                with _auto_check_lock:
                    revision = _auto_check_revision
                before = get_settings()
                completed = not before["auto_check"] or check_on_launch()
                with _auto_check_lock:
                    if (
                        completed
                        and revision == _auto_check_revision
                        and automatic_check_key(before)
                        == automatic_check_key(get_settings())
                    ):
                        # Clear under the same lock used by new requests, so a
                        # settings save cannot coalesce into an exiting worker.
                        _auto_check_thread = None
                        return
                time.sleep(0.5)
        finally:
            with _auto_check_lock:
                if _auto_check_thread is current_thread():
                    _auto_check_thread = None

    with _auto_check_lock:
        _auto_check_revision += 1
        if _auto_check_thread is None or not _auto_check_thread.is_alive():
            _auto_check_thread = Thread(
                target=run, name="mower-auto-update-check", daemon=True
            )
            _auto_check_thread.start()
    return {"ok": True, "scheduled": True}


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


def github(path, proxy="", *, repo=REPO):
    proxies = {"http": proxy, "https": proxy} if proxy else None
    response = requests.get(
        f"https://api.github.com/repos/{repo}" + path,
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


def source_commit_info(commit, repo=REPO):
    sha = commit.get("sha", "")
    if not isinstance(sha, str) or not re.fullmatch(r"[a-fA-F0-9]{40}", sha):
        raise ValueError("GitHub 返回的提交 SHA 无效")
    details = commit.get("commit", {})
    author = details.get("author") or {}
    return {
        "sha": sha.lower(),
        "message": details.get("message") or "无提交说明",
        "author": author.get("name") or "",
        "date": author.get("date") or "",
        "url": f"https://github.com/{repo}/commit/{sha.lower()}",
    }


def normalize_source_url(value):
    """Accept a GitHub repository URL or owner/repo, never Git command syntax."""
    if not isinstance(value, str) or len(value) > 512:
        raise ValueError("请填写 GitHub 仓库地址或本地远端名称")
    value = value.strip()
    match = re.fullmatch(
        r"(?:(https://github\.com/|git@github\.com:|ssh://git@github\.com/))?"
        r"([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9_][A-Za-z0-9_.-]*)/?",
        value,
        re.I,
    )
    if not match:
        raise ValueError(
            "请填写有效的 GitHub 仓库地址，不接受凭据、其他站点或 Git 命令"
        )
    prefix, owner, name = match.groups()
    name = name.removesuffix(".git")
    if not name or name in (".", ".."):
        raise ValueError("GitHub 仓库名称无效")
    repo = f"{owner}/{name}"
    url = (
        f"git@github.com:{repo}.git"
        if prefix and prefix.lower().startswith(("git@", "ssh://"))
        else f"https://github.com/{repo}.git"
    )
    return {"source_repo": repo, "source_url": url}


def resolve_source_remote(remote=None):
    if runtime.frozen():
        raise ValueError("远端仓库选择仅支持源码部署")
    remote = get_settings()["source_remote"] if remote is None else remote
    if not isinstance(remote, str) or not remote.strip():
        raise ValueError("请选择远端仓库或填写个人 fork 地址")
    remote = remote.strip()
    if re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", remote):
        git = shutil.which("git", path=source_tool_path())
        if not git:
            raise ValueError("未找到 Git，请检查启动环境的 PATH")
        try:
            url = subprocess.check_output(
                [git, "remote", "get-url", remote],
                cwd=runtime.installation_root(),
                text=True,
                encoding="utf-8",
                stderr=subprocess.PIPE,
                timeout=10,
            ).strip()
        except subprocess.CalledProcessError as error:
            raise ValueError(
                "所选本地远端不存在，请选择其他远端或填写 GitHub fork 地址"
            ) from error
    else:
        url = remote
    return {"source_remote": remote, **normalize_source_url(url)}


def source_remotes():
    """Only show defaults and addresses explicitly entered for this installation."""
    return [{"value": "origin", "label": "默认仓库"}] + [
        {"value": url, "label": url} for url in get_settings()["source_remote_history"]
    ]


def remember_source_remote(value):
    if runtime.frozen():
        raise ValueError("远端仓库选择仅支持源码部署")
    selected = normalize_source_url(value)
    url = selected["source_url"]
    with runtime.submission_lock(runtime.state_dir()):
        settings = get_settings()
        history = settings["source_remote_history"]
        settings["source_remote_history"] = [url] + [
            item for item in history if item.lower() != url.lower()
        ][:9]
        runtime.write_json(runtime.state_dir() / "settings.json", settings)
    return {"ok": True, **selected, "remotes": source_remotes()}


def source_repository():
    if runtime.frozen():
        raise ValueError("版本管理仅支持源码部署")
    root = runtime.installation_root()
    git = shutil.which("git", path=source_tool_path())
    if not git or not (root / ".git").exists():
        raise ValueError("版本管理需要 Git 检出目录和 Git 工具")
    current = subprocess.check_output(
        [git, "rev-parse", "HEAD"], cwd=root, text=True, encoding="utf-8", timeout=10
    ).strip()
    branch = subprocess.check_output(
        [git, "branch", "--show-current"],
        cwd=root,
        text=True,
        encoding="utf-8",
        timeout=10,
    ).strip()
    network_settings.apply_http_proxy()
    proxy = network_settings.get_effective_settings()["http_proxy"]
    return current, branch, proxy


def source_history(branch=None, remote=None):
    current, current_branch, proxy = source_repository()
    selected = resolve_source_remote(remote)
    repo = selected["source_repo"]
    branch = normalize_source_ref(
        github("", proxy, repo=repo)["default_branch"]
        if branch == ""
        else branch or get_settings()["source_branch"]
    )
    branches = []
    for page in range(1, 4):
        rows = github(f"/branches?per_page=100&page={page}", proxy, repo=repo)
        branches.extend(row["name"] for row in rows)
        if len(rows) < 100:
            break
    try:
        commits = github(
            "/commits?sha=" + quote(branch, safe="") + "&per_page=20", proxy, repo=repo
        )
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code in (404, 422):
            raise ValueError("远端分支不存在或没有可读取的提交") from error
        raise
    return {
        "ok": True,
        "branch": branch,
        "branches": branches,
        "current_branch": current_branch,
        "current_commit": current,
        "commits": [source_commit_info(commit, repo) for commit in commits],
        **selected,
    }


def check_source_version(reference, branch=None, remote=None):
    reference = normalize_source_ref(reference)
    branch = normalize_source_ref(branch or get_settings()["source_branch"])
    current, _, proxy = source_repository()
    selected = resolve_source_remote(remote)
    repo = selected["source_repo"]
    try:
        github("/branches/" + quote(branch, safe=""), proxy, repo=repo)
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 404:
            raise ValueError("所选远端分支不存在，请刷新分支列表") from error
        raise
    try:
        target = source_commit_info(
            github("/commits/" + quote(reference, safe=""), proxy, repo=repo), repo
        )
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code in (404, 422):
            raise ValueError("未找到该分支、提交 SHA 或 tag，请检查输入") from error
        raise
    try:
        protocol = github(
            "/contents/arknights_mower/utils/update_runtime.py?ref=" + target["sha"],
            proxy,
            repo=repo,
        )
        if protocol.get("type") != "file":
            raise ValueError("目标版本未包含可用的实例恢复模块")
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 404:
            raise ValueError(
                "该版本早于软件更新与实例恢复功能，无法从页面自动切换，请使用 Git 手动部署"
            ) from error
        raise
    plan = {
        "deployment": "source",
        "operation": "source-version",
        **selected,
        "channel": "dev",
        "source_branch": branch,
        "ref": target["sha"],  # Pin the resolved commit, even if the branch/tag moves.
        "commit": target["sha"],
        "version": "commit@" + target["sha"][:7],
        "notes": target["message"],
        "url": target["url"],
        "created_at": time.time(),
        "available": True,
        "force_available": True,
    }
    check_id = remember_check(plan)
    return {
        "ok": True,
        "check_id": check_id,
        "current_commit": current,
        **target,
        **selected,
        "version": plan["version"],
    }


def source_pulls(remote=None):
    _, _, proxy = source_repository()
    selected = resolve_source_remote(remote)
    pulls = []
    for page in range(1, 4):
        rows = github(
            f"/pulls?state=open&per_page=100&page={page}",
            proxy,
            repo=selected["source_repo"],
        )
        pulls.extend(
            {"number": row["number"], "title": row["title"]}
            for row in rows
            if not row.get("draft")
        )
        if len(rows) < 100:
            break
    return {"ok": True, "pulls": pulls, **selected}


def mergeable_source_pull(number, repo, proxy):
    if type(number) is not int or number <= 0:
        raise ValueError("请选择有效的 PR 编号")
    for attempt in range(3):
        pull = github(f"/pulls/{number}", proxy, repo=repo)
        if pull.get("state") != "open" or pull.get("draft"):
            raise ValueError(f"PR #{number} 已关闭、已合并或仍为草稿，无法选择更新")
        if pull.get("mergeable") is not None:
            break
        if attempt < 2:
            time.sleep(0.5 * (attempt + 1))
    if pull.get("mergeable") is False:
        raise ValueError(f"PR #{number} 存在合并冲突，暂不能用于更新")
    if pull.get("mergeable") is not True:
        raise ValueError(f"GitHub 正在计算 PR #{number} 的合并状态，请稍后重新检查")
    return pull


def source_pull_target(pull, repo):
    base = pull["base"]
    return (
        (base.get("repo") or {}).get("full_name", repo).casefold(),
        normalize_source_ref(base["ref"]),
    )


def source_branch_head(branch, repo, proxy):
    result = github("/branches/" + quote(branch, safe=""), proxy, repo=repo)
    return source_commit_info(result["commit"], repo)["sha"]


def source_pull_revision(number, repo, proxy):
    """Resolve GitHub's test merge without downloading Git objects locally."""
    pull = mergeable_source_pull(number, repo, proxy)
    target_repo, branch = source_pull_target(pull, repo)
    if target_repo != repo.casefold():
        raise ValueError("PR 的目标仓库已改变，请重新选择")
    # base.sha in a PR response may lag behind its actual target branch.
    base = source_branch_head(branch, repo, proxy)
    head = source_commit_info(pull["head"], repo)["sha"]
    merge_sha = pull.get("merge_commit_sha")
    pending = (
        f"GitHub 正在准备 PR #{number} 与目标分支最新版本的合并结果，请稍后重新检查"
    )
    if not merge_sha:
        raise ValueError(pending)
    merge_sha = source_commit_info({"sha": merge_sha}, repo)["sha"]
    try:
        # The Git database endpoint omits file diffs, keeping checks lightweight.
        commit = github("/git/commits/" + merge_sha, proxy, repo=repo)
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 404:
            raise ValueError(pending) from error
        raise
    target = source_commit_info({"sha": commit.get("sha"), "commit": commit}, repo)
    if target["sha"] != merge_sha or [
        parent.get("sha") for parent in commit.get("parents", [])
    ] != [base, head]:
        # GitHub refreshes the test merge asynchronously after either side moves.
        # Never silently install an old base or fall back to the PR head alone.
        raise ValueError(pending)
    return {
        "source_pr": number,
        "source_branch": branch,
        "base_commit": base,
        "head_commit": head,
        "ref": f"refs/pull/{number}/merge",
        "commit": merge_sha,
        "notes": f"#{number} {pull['title']}",
        "url": target["url"],
        "author": target["author"],
        "date": target["date"],
    }


def check_source_pull(number, remote=None):
    if type(number) is not int or number <= 0:
        raise ValueError("请选择有效的 PR 编号")
    current, _, proxy = source_repository()
    selected = resolve_source_remote(remote)
    revision = source_pull_revision(number, selected["source_repo"], proxy)
    try:
        protocol = github(
            "/contents/arknights_mower/utils/update_runtime.py?ref="
            + revision["commit"],
            proxy,
            repo=selected["source_repo"],
        )
        if protocol.get("type") != "file":
            raise ValueError("目标版本未包含可用的实例恢复模块")
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 404:
            raise ValueError(
                "目标版本未包含实例恢复模块，请使用 Git 手动部署"
            ) from error
        raise
    plan = {
        "deployment": "source",
        "operation": "source-pr",
        **selected,
        **revision,
        "channel": "dev",
        "created_at": time.time(),
        "available": True,
        "force_available": True,
        "version": "PR@" + revision["commit"][:7],
    }
    return {
        "ok": True,
        "check_id": remember_check(plan),
        "current_commit": current,
        **selected,
        **revision,
        "sha": revision["commit"],
        "version": plan["version"],
        "message": revision["notes"],
    }


def check_source_pulls(numbers, remote=None):
    # Accept a single selection from an older page, never silently discard PRs.
    if not isinstance(numbers, list) or len(numbers) != 1:
        raise ValueError("仅支持选择一个 PR，请刷新页面后重新选择")
    return check_source_pull(numbers[0], remote)


def choose_release(releases, channel):
    candidates = []
    for release in releases:
        if (
            release.get("draft")
            or bool(release.get("prerelease")) != (channel == "beta")
            or not VERSION_RE.fullmatch(release.get("tag_name", ""))
        ):
            continue
        try:
            published = datetime.fromisoformat(release.get("published_at"))
        except (TypeError, ValueError):
            continue
        if published.tzinfo is None:
            continue
        candidates.append((published, version_key(release["tag_name"]), release))
    if not candidates:
        raise ValueError("所选渠道暂无带有效发布时间的已发布版本")
    return max(candidates, key=lambda item: item[:2])[2]


def choose_asset(release):
    system, arch = platform_asset()
    version = release["tag_name"].lstrip("v")
    extension = {"windows": "zip", "linux": "tar.gz", "macos": "dmg"}[system]
    name = f"arknights-mower_{version}_{system}_{arch}.{extension}"
    asset = next((a for a in release.get("assets", []) if a["name"] == name), None)
    if not asset:
        message = f"此 Release 没有适配当前平台的 {name}"
        if system == "macos":
            message += "；macOS 旧版 ZIP 请手动安装"
        raise ValueError(message)
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
    environment = Path(sys.prefix).resolve()
    base_python = getattr(sys, "_base_executable", None) or sys.executable
    # Rebuild a project-owned venv at its existing path, regardless of its name.
    # Other environments are updated through the running interpreter's pip.
    # Never require users to rename, move or recreate their Python environment.
    local_environment = (
        environment != root.resolve()
        and environment.is_relative_to(root.resolve())
        and (environment / "pyvenv.cfg").is_file()
        and not Path(base_python).resolve().is_relative_to(environment)
    )
    system_site_packages = False
    if local_environment:
        system_site_packages = any(
            re.fullmatch(r"include-system-site-packages\s*=\s*true", line.strip(), re.I)
            for line in (environment / "pyvenv.cfg")
            .read_text(encoding="utf-8")
            .splitlines()
        )
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
    pip_available = importlib.util.find_spec("pip") is not None
    uv = (
        shutil.which(
            "uv",
            path=os.pathsep.join(
                (
                    tool_path,
                    str(Path.home() / ".local/bin"),
                    str(Path.home() / ".cargo/bin"),
                )
            ),
        )
        if not pip_available
        else None
    )
    return {
        "git": git,
        "npm": npm,
        "tool_path": tool_path,
        "python": sys.executable,
        "base_python": base_python,
        "original_python": sys.executable,
        "in_place_environment": not local_environment or not pip_available,
        "pip_available": pip_available,
        "uv": uv,
        "system_site_packages": system_site_packages,
        "source_environment": str(environment)
        if environment != root.resolve() and environment.is_relative_to(root.resolve())
        else "",
        "venv_dir": str(environment.relative_to(root.resolve()).as_posix())
        if local_environment
        else "",
    }


def info():
    root = runtime.installation_root()
    deployment = "release" if runtime.frozen() else "source"
    blockers = []
    source_changes = ""
    if deployment == "source":
        try:
            tools = source_tools(root)
            require_clean_source(
                tools["git"], root, environment=tools.get("source_environment")
            )
        except SourceChangesError as exc:
            source_changes = str(exc)
        except Exception as exc:
            blockers.append(str(exc))
    elif not os.access(root.parent, os.W_OK) or not os.access(root, os.W_OK):
        blockers.append(
            "安装位置不可写；请先将程序移至可写目录（macOS 请移出 DMG 后运行）"
        )
    try:
        registered = runtime.instances()
    except runtime.InstanceScanError as exc:
        registered = []
        blockers.append(str(exc))
    else:
        if not any(
            r["pid"] == os.getpid() and r["kind"] == "instance" for r in registered
        ):
            blockers.append(
                "请通过 webview_ui.py / Mower 桌面程序启动；直接运行 Flask 或容器请使用原部署工具更新"
            )
    settings = get_settings()
    remotes = source_remotes() if deployment == "source" else []
    return {
        "ok": True,
        "version": __version__,
        "source_remotes": remotes,
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
        branch = normalize_source_ref(get_settings()["source_branch"])
        selected = resolve_source_remote()
        commit = github(
            "/commits/" + quote(branch, safe=""), proxy, repo=selected["source_repo"]
        )
        plan.update(
            **selected,
            source_branch=branch,
            ref=commit["sha"],
            commit=commit["sha"],
            version=branch + "@" + commit["sha"][:7],
            notes=commit["commit"]["message"],
            url=f"https://github.com/{selected['source_repo']}/commits/"
            + quote(branch, safe=""),
        )
    else:
        if channel == "stable":
            # Respect GitHub's Latest selection instead of comparing legacy
            # calendar versions (2025.x) numerically with current versions (4.x).
            try:
                releases = [github("/releases/latest", proxy)]
            except requests.HTTPError as error:
                if error.response is not None and error.response.status_code == 404:
                    raise ValueError("正式版渠道暂无已发布的 Latest Release") from error
                raise
        else:
            # /latest omits prereleases. Read every page before comparing their
            # publication times; creation time and API order are not sufficient.
            releases = []
            page = 1
            while True:
                batch = github(f"/releases?per_page=100&page={page}", proxy)
                releases.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
        release = choose_release(releases, channel)
        plan.update(
            version=release["tag_name"],
            downgrade=version_key(release["tag_name"]) < version_key(__version__),
            notes=release.get("body") or "暂无更新说明",
            url=release["html_url"],
        )
        if deployment == "source":
            commit = github("/commits/" + quote(release["tag_name"], safe=""), proxy)
            plan.update(
                ref="refs/tags/" + release["tag_name"],
                commit=commit["sha"],
                source_url=f"https://github.com/{REPO}.git",
                source_repo=REPO,
            )
    if deployment == "source":
        current = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=runtime.installation_root(),
            text=True,
            encoding="utf-8",
            timeout=10,
        ).strip()
        available = current != plan["commit"]
    else:
        # A maintainer may withdraw a broken release or move Latest backwards.
        # Follow the selected channel, but never reinstall the same version.
        available = version_key(plan["version"]) != version_key(__version__)
        if available:
            plan["asset"] = choose_asset(release)
    plan["available"] = available
    plan["force_available"] = deployment == "source" and (
        available or current == plan["commit"]
    )
    check_id = remember_check(plan)
    result = {
        "ok": True,
        "channel": channel,
        "checked_at": time.time(),
        "check_id": check_id if available or plan["force_available"] else "",
        "available": available,
        "downgrade": plan.get("downgrade", False),
        "version": plan["version"],
        "notes": plan["notes"],
        "url": plan["url"],
        "message": (
            "发现可回退版本，请确认后安装" if plan.get("downgrade") else "发现可用更新"
        )
        if available
        else "当前版本已与所选渠道一致",
    }
    if deployment == "source":
        result.update(
            {
                key: plan[key]
                for key in ("source_url", "source_repo", "source_branch")
                if key in plan
            }
        )
    runtime.write_json(
        runtime.state_dir() / "last-check.json",
        {key: value for key, value in result.items() if key != "check_id"},
    )
    return result


def require_downgrade_confirmation(plan, confirmed):
    if not isinstance(confirmed, bool):
        raise ValueError("回退确认必须是布尔值")
    if plan.get("downgrade") and not confirmed:
        raise ValueError("回退到旧版本需要二次确认，请确认回退后再安装")


def submit(check_id, background=False, *, force=False, confirm_downgrade=False):
    plan = _checks.get(check_id)
    if not plan or time.time() - plan["created_at"] > 1800:
        raise ValueError("版本检查已过期，请重新检查更新")
    if not force and not plan.get("available", True):
        raise ValueError("当前没有可用更新")
    if force and not plan.get("force_available", True):
        raise ValueError("当前检查结果不支持强制更新")
    require_downgrade_confirmation(plan, confirm_downgrade)
    uploaded = Path(plan["_upload"]) if plan.get("_upload") else None
    if uploaded is None:
        return start_job(
            plan, background, force=force, confirm_downgrade=confirm_downgrade
        )
    try:
        if not uploaded.is_file():
            raise ValueError("已检查的安装包已过期或已使用，请重新上传")
        return start_job(
            plan,
            background,
            uploaded=uploaded,
            force=force,
            confirm_downgrade=confirm_downgrade,
        )
    finally:
        if not uploaded.exists():
            discard_upload(check_id)


def start_job(
    plan, background=False, uploaded=None, *, force=False, confirm_downgrade=False
):
    require_downgrade_confirmation(plan, confirm_downgrade)
    with runtime.submission_lock(runtime.state_dir()):
        return _start_job(plan, background, uploaded, force=force)


def _start_job(plan, background=False, uploaded=None, *, force=False):
    if not isinstance(force, bool):
        raise ValueError("强制更新选项必须是布尔值")
    if force and (plan["deployment"] != "source" or uploaded is not None):
        raise ValueError("强制更新仅支持源码部署")
    if plan.get("source_prs"):
        raise ValueError("已取消多 PR 合并，请刷新页面后重新选择一个 PR")
    if plan.get("source_pr"):
        network_settings.apply_http_proxy()
        revision = source_pull_revision(
            plan["source_pr"],
            plan["source_repo"],
            network_settings.get_effective_settings()["http_proxy"],
        )
        if any(
            revision[key] != plan.get(key)
            for key in ("source_branch", "base_commit", "head_commit", "commit", "ref")
        ):
            raise ValueError("PR 或目标分支已改变，请重新检查并确认更新")
    details = info()
    if details["blockers"] and not (force and details.get("force_supported", False)):
        raise ValueError("；".join(details["blockers"]))
    network_settings.apply_http_proxy()
    root = runtime.installation_root()
    tools = source_tools(root) if plan["deployment"] == "source" else {}
    if tools:
        require_clean_source(
            tools["git"], root, force=force, environment=tools.get("source_environment")
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
    previous_settings = get_settings()
    try:
        job = {
            **{key: value for key, value in plan.items() if key != "_upload"},
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
        settings = {**get_settings(), **{k: job[k] for k in ("channel", "background")}}
        if plan.get("operation") == "source-pr":
            settings["auto_update"] = False
            settings["channel"] = previous_settings["channel"]
        if plan.get("operation") == "source-version":
            settings.update(auto_update=False, source_branch=plan["source_branch"])
            if plan.get("source_url"):
                # Remember the confirmed URL, not a local alias that may be retargeted.
                settings["source_remote"] = plan["source_url"]
        runtime.write_json(state / "settings.json", settings)
        runtime.write_json(
            state / "status.json",
            {
                "id": job_id,
                "status": "running",
                "phase": "preparing",
                "version": plan["version"],
                "message": "正在启动独立更新程序",
                "cancellable": True,
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
                "software_update_progress.py",
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
        runtime.write_json(state / "settings.json", previous_settings)
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
    from arknights_mower.utils.software_update_progress import read_status

    return read_status(runtime.state_dir())


def cancel(job_id):
    from arknights_mower.utils.software_update_progress import cancel_update

    return cancel_update(runtime.state_dir(), job_id)


def manual_plan(package, proxy=""):
    from .software_update_package import inspect_package

    if not runtime.frozen():
        raise ValueError("Release 安装包用于独立包部署；源码部署请使用 Git 更新")
    metadata = inspect_package(package, *platform_asset())
    version = metadata["version"]
    return {
        "deployment": "release",
        "manual": True,
        "available": True,
        "downgrade": version_key(version) < version_key(__version__),
        "channel": "beta" if "-" in version else "stable",
        "proxy": validate_proxy(proxy),
        "version": "v" + version,
        "asset": {"name": "package." + metadata["format"]},
        "created_at": time.time(),
    }


def inspect_upload(upload, proxy=""):
    if not runtime.frozen():
        raise ValueError("Release 安装包用于独立包部署；源码部署请使用 Git 更新")
    if not upload:
        raise ValueError("请选择 Release 安装包")
    uploads = runtime.state_dir() / "uploads"
    uploads.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Clean abandoned previews on the next upload. Active inspections have no
    # ready marker and are not removed while a slow upload is still in progress.
    for previous in uploads.iterdir():
        marker = previous / "ready"
        if marker.is_file() and time.time() - marker.stat().st_mtime > 1800:
            shutil.rmtree(previous, ignore_errors=True)
    directory = uploads / uuid4().hex
    directory.mkdir(mode=0o700)
    package = directory / "package"
    try:
        digest = hashlib.sha256()
        size = 0
        with package.open("wb") as stream:
            while chunk := upload.stream.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_PACKAGE_BYTES:
                    raise ValueError("安装包超过 2 GiB 限制")
                digest.update(chunk)
                stream.write(chunk)
        plan = manual_plan(package, proxy)
        canonical = package.with_name(plan["asset"]["name"])
        package.rename(canonical)
        plan.update(_upload=str(canonical))
        plan["asset"].update(size=size, sha256=digest.hexdigest())
        check_id = remember_check(plan)
        (directory / "ready").touch()
        return {
            "ok": True,
            "check_id": check_id,
            "version": plan["version"],
            "downgrade": plan["downgrade"],
            "manual": True,
            "message": "安装包完整性检查通过，请确认安装",
        }
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


def discard_upload(check_id):
    with runtime.submission_lock(runtime.state_dir()):
        plan = _checks.get(check_id)
        if plan and plan.get("_upload"):
            _checks.pop(check_id, None)
            shutil.rmtree(Path(plan["_upload"]).parent, ignore_errors=True)
    return {"ok": True}


def upload_package(upload, proxy="", background=False, *, confirm_downgrade=False):
    """Compatibility entry point; inspection always precedes installation."""
    result = inspect_upload(upload, proxy)
    try:
        return submit(
            result["check_id"], background, confirm_downgrade=confirm_downgrade
        )
    finally:
        discard_upload(result["check_id"])
