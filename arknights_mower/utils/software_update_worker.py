"""Detached software installer; source transactions use only the standard library.

Source deployments copy this module and update_runtime.py outside the checkout.
Frozen deployments run a copy of the complete old runtime outside the install.
The old code, virtualenv and frontend remain available for rollback.
"""

import hashlib
import json
import os
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tarfile
import threading
import time
import traceback
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath

if __package__:
    from .github_download import download_url
    from .update_runtime import (
        detached_options,
        instances,
        launch_environment,
        process_alive,
        read_json,
        submission_lock,
        write_json,
    )
else:
    from github_download import download_url
    from update_runtime import (
        detached_options,
        instances,
        launch_environment,
        process_alive,
        read_json,
        submission_lock,
        write_json,
    )

MAX_PACKAGE_BYTES = 2 * 1024**3
MAX_EXTRACTED_BYTES = 8 * 1024**3
NPM_LOCKFILE = "ui/package-lock.json"


class UpdateCancelled(Exception):
    """Preparation was cancelled before any instance was stopped."""


class SourceChangesError(ValueError):
    """Local checkout edits that can be discarded by an explicit force update."""


def npm_lockfile_without_metadata(content):
    """Compare dependency data while ignoring npm's generated bookkeeping."""
    lockfile = json.loads(content)

    def clean_package(package):
        # These fields do not change the installed dependency graph. Do not
        # strip dependency maps: a dependency can itself be named "peer".
        for key in ("peer", "license", "funding"):
            package.pop(key, None)

    for package in lockfile.get("packages", {}).values():
        clean_package(package)

    def clean_legacy_dependencies(dependencies):
        for package in dependencies.values():
            clean_package(package)
            clean_legacy_dependencies(package.get("dependencies", {}))

    clean_legacy_dependencies(lockfile.get("dependencies", {}))
    return lockfile


def generated_npm_lockfile(git, root, env=None):
    """Return local/committed bytes only for equivalent, regular lockfiles."""
    target = Path(root) / NPM_LOCKFILE
    if target.is_symlink() or not target.is_file():
        return None
    try:
        local = target.read_bytes()
        committed = subprocess.check_output(
            [git, "show", "HEAD:" + NPM_LOCKFILE], cwd=root, env=env, timeout=10
        )
        if npm_lockfile_without_metadata(local) == npm_lockfile_without_metadata(
            committed
        ):
            return local, committed
    except (OSError, ValueError, TypeError, AttributeError, subprocess.SubprocessError):
        pass
    return None


def require_clean_source(git, root, env=None, *, force=False, environment=None):
    """Check source edits without rewriting files; return generated lock changes."""
    # Exclude only untracked runtime files, including custom/nested venv names.
    # Tracked edits inside that directory still require explicit force.
    relative = None
    if environment:
        directory = Path(root) / environment
        if directory.is_relative_to(Path(root)) and directory != Path(root):
            relative = directory.relative_to(root).as_posix()
    changes = subprocess.check_output(
        [
            git,
            "-c",
            "core.quotepath=false",
            "status",
            "--porcelain",
            "--untracked-files=normal",
        ]
        + (["--", ".", ":(exclude,literal)" + relative] if relative else []),
        cwd=root,
        env=env,
        text=True,
        timeout=10,
    )
    if isinstance(changes, bytes):
        changes = changes.decode("utf-8", errors="replace")
    entries = changes.rstrip().splitlines()
    if relative:
        tracked = subprocess.check_output(
            [
                git,
                "-c",
                "core.quotepath=false",
                "status",
                "--porcelain",
                "--untracked-files=no",
                "--",
                ":(literal)" + relative,
            ],
            cwd=root,
            env=env,
            text=True,
            timeout=10,
        )
        entries.extend(tracked.rstrip().splitlines())
    generated = {}
    # Staged edits, deletions, renames and untracked files still require action.
    if " M " + NPM_LOCKFILE in entries:
        content = generated_npm_lockfile(git, root, env)
        if content is not None:
            generated[NPM_LOCKFILE] = content
            entries.remove(" M " + NPM_LOCKFILE)
    if entries and not force:
        preview = "\n".join(entries[:10])
        if len(entries) > 10:
            preview += f"\n……另有 {len(entries) - 10} 项"
        raise SourceChangesError(
            "源码目录有未提交修改或未跟踪文件，可自行处理或使用“强制更新”；"
            "普通更新不会覆盖这些文件：\n" + preview
        )
    return generated


def extract_archive(archive, destination, check_cancelled=lambda: None):
    """Extract official zip/tar layouts; no absolute paths or escaping links."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            members = source.infolist()
            if sum(m.file_size for m in members) > MAX_EXTRACTED_BYTES:
                raise ValueError("安装包解压后过大")
            for member in members:
                check_cancelled()
                name = member.filename
                path = PurePosixPath(name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in name
                    or ":" in name
                    or stat.S_ISLNK(member.external_attr >> 16)
                ):
                    raise ValueError(
                        "安装包包含不支持的路径或符号链接，请使用当前 Release 安装包"
                    )
                target = destination.joinpath(*path.parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source.open(member) as src, target.open("wb") as dst:
                        while chunk := src.read(1024 * 1024):
                            check_cancelled()
                            dst.write(chunk)
                    mode = (member.external_attr >> 16) & 0o777
                    if mode:
                        target.chmod(mode)
    else:
        with tarfile.open(archive, "r:gz") as source:
            if sum(m.size for m in source.getmembers()) > MAX_EXTRACTED_BYTES:
                raise ValueError("安装包解压后过大")
            for member in source.getmembers():
                check_cancelled()
                source.extract(member, destination, filter="data")


class Worker:
    def __init__(self, job_path):
        self.job_path = Path(job_path)
        self.job = read_json(self.job_path)
        self.work = self.job_path.parent
        self.state = Path(self.job["state_dir"])
        self.root = Path(self.job["root"])
        self.env = launch_environment({})
        if self.job.get("tool_path"):
            self.env["PATH"] = self.job["tool_path"]
        if self.job.get("proxy"):
            self.env.update(http_proxy=self.job["proxy"], https_proxy=self.job["proxy"])
        self.status = {
            "id": self.job["id"],
            "status": "running",
            "phase": "preparing",
            "message": "准备更新",
            "version": self.job["version"],
            "log_path": str(self.work / "update.log"),
        }
        self.stopped = []
        self.original = []
        self.backups = []
        self.switched = False
        self.old_commit = None
        self.old_branch = None
        self.bundle_backup = self.root.with_name(
            f"{self.root.name}.backup-{self.job['id']}"
        )
        self.replacements = []
        self.new_processes = []
        self.recovery_processes = []
        self.venv_dir = self.job.get("venv_dir", ".venv")
        self.environment = self.root / self.venv_dir
        self.source_backup_paths = [
            self.root / "ui/node_modules",
            self.root / "ui/dist",
        ]
        if not self.job.get("in_place_environment"):
            self.source_backup_paths.insert(0, self.environment)
        self.dependencies_started = False
        self.needs_lfs = False
        self.cancellable = True
        self.status["cancellable"] = True
        self.source_stage = self.work / "source"
        self.stage_attempted = False
        self.payload_ready = False
        self.dependencies_changed = True
        self.wheels = None
        self.progress_servers = []

    def report(self, phase, message, status="running"):
        self.status.update(
            phase=phase, message=message, status=status, updated_at=time.time()
        )
        write_json(self.state / "status.json", self.status)
        print(message, flush=True)

    def check_cancelled(self):
        if self.cancellable and (self.state / "active/cancel.json").exists():
            raise UpdateCancelled("已取消更新，当前实例继续运行")

    def begin_install(self):
        # Serialize the last cancellation check with the authenticated API.
        deadline = time.monotonic() + 5
        while True:
            try:
                with submission_lock(self.state):
                    self.check_cancelled()
                    self.cancellable = False
                    self.status["cancellable"] = False
                    write_json(
                        self.state / "active/installing.json", {"id": self.job["id"]}
                    )
                    self.report("prepared", "准备完成，开始保存任务并重启全部实例")
                return
            except ValueError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)

    def run_command(self, args, cwd=None, timeout=1800, env=None, cancellable=True):
        if cancellable:
            self.check_cancelled()
        # Commands and arguments are fixed by the installer. Never use shell=True.
        print("执行：" + " ".join(map(str, args)), flush=True)
        process = subprocess.Popen(
            list(map(str, args)),
            cwd=cwd or self.root,
            env=self.env if env is None else env,
            stdin=subprocess.DEVNULL,
            **detached_options(),
        )
        try:
            deadline = time.monotonic() + timeout
            while True:
                if cancellable:
                    self.check_cancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(args, timeout)
                try:
                    code = process.wait(timeout=min(0.25, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
        except (subprocess.TimeoutExpired, UpdateCancelled):
            # Only this command's own child tree is stopped. npm/git can have
            # grandchildren; leaving them running would race with rollback.
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    timeout=15,
                )
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=15)
            raise
        if code:
            raise subprocess.CalledProcessError(code, args)

    def git_output(self, *args):
        return subprocess.check_output(
            [self.job["git"], *args], cwd=self.root, env=self.env, text=True, timeout=60
        ).strip()

    def prepare_source(self):
        require_clean_source(
            self.job["git"],
            self.root,
            self.env,
            force=self.job.get("force", False),
            environment=self.job.get("source_environment", self.venv_dir),
        )
        self.old_commit = self.git_output("rev-parse", "HEAD")
        self.old_branch = self.git_output("branch", "--show-current")
        write_json(
            self.work / "recovery.json",
            {
                "root": str(self.root),
                "old_commit": self.old_commit,
                "old_branch": self.old_branch,
                "original_python": self.job.get(
                    "original_python", self.job.get("python")
                ),
                "python": self.job.get("python"),
                "backups": [
                    {
                        "target": str(target),
                        "backup": str(self.work / f"runtime-{index}.backup"),
                    }
                    for index, target in enumerate(self.source_backup_paths)
                ],
            },
        )
        self.report("downloading", "获取目标源码")
        self.run_command(
            [self.job["git"], "fetch", "--no-tags", "origin", self.job["ref"]]
        )
        if self.git_output("rev-parse", "FETCH_HEAD^{commit}") != self.job["commit"]:
            raise ValueError("远端版本已改变，请重新检查更新")
        try:
            self.git_output(
                "cat-file",
                "-e",
                self.job["commit"] + ":arknights_mower/utils/update_runtime.py",
            )
        except subprocess.CalledProcessError as exc:
            raise ValueError(
                "目标版本尚未包含软件更新与实例恢复功能，请等待包含此功能的版本发布；当前程序未停止"
            ) from exc
        self.needs_lfs = self.target_uses_lfs()
        if self.needs_lfs:
            try:
                self.run_command([self.job["git"], "lfs", "version"], timeout=10)
            except (OSError, subprocess.SubprocessError) as exc:
                raise ValueError(
                    "目标版本使用 Git LFS，请安装 Git LFS 并确保启动环境可以运行 git lfs；当前实例尚未停止"
                ) from exc
            self.run_command(
                [self.job["git"], "lfs", "fetch", "origin", self.job["commit"]]
            )

    def ensure_installer(self):
        if self.job.get("in_place_environment"):
            self.report("preparing", "检查当前 Python 环境的依赖安装工具")
            try:
                if self.job.get("uv"):
                    self.run_command([self.job["uv"], "--version"], timeout=30)
                else:
                    if self.job.get("pip_available") is False:
                        self.run_command(
                            [self.job["python"], "-m", "ensurepip"], timeout=60
                        )
                    self.run_command(
                        [self.job["python"], "-m", "pip", "--version"], timeout=30
                    )
            except (OSError, subprocess.SubprocessError) as exc:
                raise ValueError(
                    "当前 Python 无法使用依赖安装工具，请查看日志，为此解释器安装 pip 或在启动路径中提供 uv；当前实例尚未停止"
                ) from exc

    def prepare_source_payload(self):
        self.report("preparing", "在临时目录准备目标版本，当前实例继续运行")
        self.stage_attempted = True
        self.run_command(
            [
                self.job["git"],
                "worktree",
                "add",
                "--detach",
                self.source_stage,
                self.job["commit"],
            ]
        )
        # Only reuse an environment for unchanged, ordinary index requirements.
        # Local paths, included files and VCS requirements need fresh resolution.
        requirements = self.source_stage / "requirements.in"
        current = self.root / "requirements.in"
        lines = requirements.read_text(encoding="utf-8").splitlines()
        simple = all(
            not line.strip()
            or line.lstrip().startswith("#")
            or (
                not line.lstrip().startswith(("-", ".", "/"))
                and not any(char in line for char in ("/", "@", "\\"))
            )
            for line in lines
        )
        inputs = self.git_output(
            "diff", "--name-only", self.old_commit, self.job["commit"]
        )
        changed_inputs = any(
            Path(name).name in ("pyproject.toml", "setup.py", "setup.cfg", "uv.lock")
            or Path(name).name.startswith("requirements")
            for name in inputs.splitlines()
        )
        self.dependencies_changed = not (
            simple
            and not changed_inputs
            and current.is_file()
            and current.read_bytes() == requirements.read_bytes()
        )
        if self.dependencies_changed:
            self.report("dependencies", "下载并准备 Python 依赖，当前实例继续运行")
            self.ensure_installer()
            python = self.job["python"]
            if self.job.get("uv"):
                temporary_env = self.work / "dependency-tools"
                self.run_command(
                    [self.job["uv"], "venv", "--python", python, temporary_env]
                )
                python = temporary_env / (
                    "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
                )
                # uv has no download command. An isolated environment warms its
                # cache without modifying the currently running interpreter.
                self.run_command(
                    [
                        self.job["uv"],
                        "pip",
                        "install",
                        "--python",
                        python,
                        "-r",
                        "requirements.in",
                    ],
                    cwd=self.source_stage,
                    env=self.pip_environment(),
                )
            else:
                self.wheels = self.work / "wheels"
                self.run_command(
                    [
                        python,
                        "-m",
                        "pip",
                        "wheel",
                        "-r",
                        "requirements.in",
                        "--wheel-dir",
                        self.wheels,
                    ],
                    cwd=self.source_stage,
                    env=self.pip_environment(),
                )
                # Install the resolved wheels offline, including direct-URL
                # requirements, rather than fetching those URLs a second time.
                from email.parser import BytesParser

                resolved = []
                for wheel in self.wheels.glob("*.whl"):
                    with zipfile.ZipFile(wheel) as archive:
                        name = next(
                            name
                            for name in archive.namelist()
                            if name.endswith(".dist-info/METADATA")
                        )
                        metadata = BytesParser().parsebytes(archive.read(name))
                        resolved.append(f"{metadata['Name']}=={metadata['Version']}")
                (self.work / "resolved-requirements.txt").write_text(
                    "\n".join(resolved), encoding="utf-8"
                )
        else:
            self.report("dependencies", "Python 依赖清单未变化，保留当前环境")
        self.report("building", "安装前端依赖并构建页面，当前实例继续运行")
        ui = self.source_stage / "ui"
        self.run_command(
            [
                self.job["npm"],
                "ci" if (ui / "package-lock.json").is_file() else "install",
            ],
            cwd=ui,
        )
        self.run_command([self.job["npm"], "run", "build"], cwd=ui)
        self.payload_ready = True

    def cleanup_preparation(self):
        if self.stage_attempted or self.source_stage.exists():
            try:
                self.run_command(
                    [
                        self.job["git"],
                        "worktree",
                        "remove",
                        "--force",
                        "--force",
                        self.source_stage,
                    ],
                    timeout=120,
                    cancellable=False,
                )
            except Exception:
                traceback.print_exc()
        for path in (
            self.work / "dependency-tools",
            self.work / "wheels",
            self.work / "payload",
            getattr(self, "prepared", None),
        ):
            if path and path.exists():
                shutil.rmtree(path, ignore_errors=True)
        if self.job["deployment"] == "release" and self.status["status"] == "cancelled":
            (self.work / self.job["asset"]["name"]).unlink(missing_ok=True)

    def create_environment(self):
        args = [self.job["base_python"], "-m", "venv"]
        if self.job.get("system_site_packages"):
            args.append("--system-site-packages")
        args.append(str(self.environment))
        self.run_command(args)

    def target_uses_lfs(self):
        commit = self.job["commit"]
        paths = self.git_output("ls-tree", "-r", "--name-only", "-z", commit)
        for path in paths.split("\0"):
            if PurePosixPath(path).name != ".gitattributes":
                continue
            contents = self.git_output("show", f"{commit}:{path}")
            for line in contents.splitlines():
                if (
                    not line.lstrip().startswith("#")
                    and "filter=lfs" in line.split()[1:]
                ):
                    return True
        return False

    def prepare_package(self):
        asset = self.job["asset"]
        package = self.work / asset["name"]
        manual = self.job.get("manual") is True
        self.report(
            "downloading",
            "准备上传的安装包" if manual else "下载 Release 安装包",
        )
        if not package.exists():
            if manual:
                raise ValueError("上传的安装包不存在，请重新上传")
            # Release workers retain the complete old runtime, including SOCKS
            # dependencies. Source workers never execute this branch.
            import requests

            proxy = self.job.get("proxy")
            with (
                requests.get(
                    download_url(asset["url"], self.job.get("github_proxy", "")),
                    headers={"User-Agent": "Mower-Software-Update"},
                    proxies={"http": proxy, "https": proxy} if proxy else None,
                    stream=True,
                    timeout=(10, 10),
                ) as response,
                package.open("wb") as out,
            ):
                response.raise_for_status()
                size = 0
                for chunk in response.iter_content(64 * 1024):
                    self.check_cancelled()
                    size += len(chunk)
                    if size > MAX_PACKAGE_BYTES:
                        raise ValueError("安装包超过 2 GiB 限制")
                    out.write(chunk)
                    self.status.update(current=size, total=asset.get("size", 0))
        if not manual:
            digest = hashlib.sha256()
            with package.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    self.check_cancelled()
                    digest.update(chunk)
            if digest.hexdigest() != asset["sha256"]:
                raise ValueError("SHA-256 校验失败，未安装")
        self.check_cancelled()
        payload_dir = self.work / "payload"
        self.report("extracting", "解压并验证安装包")
        if package.suffix == ".dmg":
            mount = self.work / "mount"
            mount.mkdir()
            try:
                self.run_command(
                    [
                        "/usr/bin/hdiutil",
                        "attach",
                        "-readonly",
                        "-nobrowse",
                        "-mountpoint",
                        mount,
                        package,
                    ],
                    cwd=self.work,
                    timeout=120,
                )
                app = mount / "mower.app"
                if not (app / "Contents/MacOS/mower").is_file():
                    raise ValueError("DMG 中未找到 mower.app")
                shutil.copytree(
                    app,
                    payload_dir / "mower.app",
                    symlinks=True,
                    copy_function=self.copy_package_file,
                )
            finally:
                self.run_command(
                    ["/usr/bin/hdiutil", "detach", mount],
                    cwd=self.work,
                    timeout=120,
                    cancellable=False,
                )
        else:
            extract_archive(package, payload_dir, self.check_cancelled)
        if self.root.suffix == ".app":
            payload = payload_dir / "mower.app"
            executable = payload / "Contents/MacOS/mower"
        else:
            payload = payload_dir / "mower"
            executable = payload / ("mower.exe" if sys.platform == "win32" else "mower")
        if not executable.is_file() or (
            self.root.suffix != ".app" and not (payload / "_internal").is_dir()
        ):
            raise ValueError("安装包结构不受支持：未找到完整 Mower 运行环境")
        package_root = payload / (
            "Contents/Resources" if self.root.suffix == ".app" else "_internal"
        )
        if not (package_root / "arknights_mower/utils/update_runtime.py").is_file():
            raise ValueError(
                "此安装包尚未包含软件更新与实例恢复功能，请手动安装或等待新版；当前程序未停止"
            )
        # Prepare on the same filesystem as the installation for atomic renames.
        self.prepared = self.root.with_name(f"{self.root.name}.new-{self.job['id']}")
        shutil.copytree(
            payload, self.prepared, symlinks=True, copy_function=self.copy_package_file
        )
        if self.root.suffix == ".app":
            self.verify_macos_signature(self.prepared)

    def copy_package_file(self, source, target):
        self.check_cancelled()
        return shutil.copy2(source, target)

    def verify_macos_signature(self, bundle):
        self.report("verifying", "检查 macOS 程序签名完整性")
        try:
            self.run_command(
                ["/usr/bin/codesign", "--verify", "--deep", "--strict", bundle],
                cwd=self.work,
                timeout=120,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError(
                "macOS 安装包签名完整性检查失败，当前实例尚未停止；"
                "请重新下载官方安装包。签名有效也不代表已通过 Apple 公证或 Gatekeeper 信任检查。"
            ) from error

    def stop_instances(self):
        self.report("stopping", "保存任务状态并关闭同一安装目录下的 Mower 实例")
        self.original = instances(self.state)
        if not any(r["kind"] == "instance" for r in self.original):
            raise ValueError("未找到可恢复的实例，请从桌面启动器打开 Mower 后重试")
        write_json(self.work / "instances-before.json", self.original)
        for record in self.original:
            write_json(
                self.state / "shutdown" / f"{record['id']}.json",
                {"job": self.job["id"]},
            )
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            self.stopped = [r for r in self.original if not process_alive(r["pid"])]
            if len(self.stopped) == len(self.original):
                return
            time.sleep(0.5)
        raise RuntimeError(
            "部分实例未能在 90 秒内退出，已取消安装。请检查正在执行的任务后重试"
        )

    def install_source(self):
        # Recheck after shutdown: the checkout may have been edited during fetch.
        force = self.job.get("force", False)
        generated = require_clean_source(
            self.job["git"],
            self.root,
            self.env,
            force=force,
            environment=self.job.get("source_environment", self.venv_dir),
        )
        if self.git_output("rev-parse", "HEAD") != self.old_commit:
            raise ValueError("更新准备期间源码发生变化，已取消安装")
        if not force:
            for relative, (local, committed) in generated.items():
                target = self.root / relative
                if target.is_symlink() or target.read_bytes() != local:
                    raise ValueError(f"更新准备期间 {relative} 发生变化，已取消安装")
                # npm's metadata is regenerated; dependency changes never enter
                # this path. Keep checks and fetch strictly read-only.
                target.write_bytes(committed)
        self.report("installing", "切换源码，保留原提交和前端用于失败恢复")
        for index, target in enumerate(self.source_backup_paths):
            if target == self.environment and not self.dependencies_changed:
                continue
            if target.exists():
                backup = self.work / f"runtime-{index}.backup"
                shutil.move(str(target), backup)
                self.backups.append((target, backup))
        self.switched = True
        if force:
            self.report("installing", "强制更新：覆盖本地源码改动，不备份本地修改")
            # Detach first so resetting does not move the user's original branch.
            # reset --hard also replaces untracked files in the target's way;
            # unrelated untracked/ignored runtime files are not globally cleaned.
            self.run_command([self.job["git"], "switch", "--detach", self.old_commit])
            self.run_command([self.job["git"], "reset", "--hard", self.job["commit"]])
        else:
            self.run_command(
                [self.job["git"], "switch", "--detach", self.job["commit"]]
            )
        if self.needs_lfs:
            self.run_command([self.job["git"], "lfs", "checkout"])
        if self.dependencies_changed:
            self.report("dependencies", "安装已准备的 Python 依赖")
            if not self.job.get("in_place_environment"):
                self.create_environment()
            self.dependencies_started = True
            self.install_dependencies(prepared=self.payload_ready)
        if self.payload_ready:
            self.report("installing", "应用已构建的前端页面")
            for name in ("node_modules", "dist"):
                staged = self.source_stage / "ui" / name
                if staged.exists():
                    shutil.move(str(staged), self.root / "ui" / name)
        else:
            raise RuntimeError("目标版本尚未准备完成")

    def pip_environment(self):
        env = self.env.copy()
        if (self.work / "socks.py").is_file():
            # A fresh venv has pip but no PySocks yet. The staged module lets
            # pip download its own SOCKS dependency without using a direct route.
            env["PYTHONPATH"] = os.pathsep.join(
                filter(None, (str(self.work), env.get("PYTHONPATH")))
            )
        return env

    def install_dependencies(self, *, prepared=False):
        if self.job.get("uv"):
            command = [self.job["uv"], "pip", "install", "--python", self.job["python"]]
        else:
            command = [self.job["python"], "-m", "pip", "install"]
        arguments = ["-r", "requirements.in"]
        if prepared:
            if self.wheels:
                arguments = [
                    "--no-index",
                    "--find-links",
                    self.wheels,
                    "-r",
                    self.work / "resolved-requirements.txt",
                ]
            elif self.job.get("uv"):
                arguments = ["--offline", *arguments]
        self.run_command(command + arguments, env=self.pip_environment())

    def install_package(self):
        self.report("installing", "替换程序，保留用户数据和原版本")
        write_json(
            self.work / "recovery.json",
            {
                "root": str(self.root),
                "backup": str(self.bundle_backup),
                "deployment": "release",
            },
        )
        if self.root.suffix == ".app":
            os.replace(self.root, self.bundle_backup)
            try:
                os.replace(self.prepared, self.root)
            except Exception:
                os.replace(self.bundle_backup, self.root)
                raise
        else:
            # Portable packages contain only these owned paths. Config, databases,
            # instances, MAA and other user directories stay exactly where they are.
            owned = (
                "_internal",
                "mower",
                "mower.exe",
                "多开管理器",
                "多开管理器.exe",
                "manager",
            )
            self.bundle_backup.mkdir()
            for name in owned:
                old = self.root / name
                new = self.prepared / name
                if not old.exists() and not new.exists():
                    continue
                backup = self.bundle_backup / name
                if old.exists():
                    os.replace(old, backup)
                self.replacements.append((old, backup))
                if new.exists():
                    os.replace(new, old)

    def command_for(self, record, *, recovery=False):
        if self.job["deployment"] == "source":
            if recovery and record.get("argv"):
                return [
                    record.get("executable") or self.job["original_python"],
                    *record["argv"],
                ]
            if record.get("argv"):
                return [self.job["python"], *record["argv"]]
            return [
                self.job["python"],
                str(
                    self.root
                    / ("manager.py" if record["kind"] == "manager" else "webview_ui.py")
                ),
            ] + (
                [] if record["kind"] == "manager" else [record["space"], record["name"]]
            )
        directory = (
            self.root / "Contents/MacOS" if self.root.suffix == ".app" else self.root
        )
        name = (
            "mower"
            if record["kind"] == "instance"
            else ("manager" if self.root.suffix == ".app" else "多开管理器")
        )
        if sys.platform == "win32":
            name += ".exe"
        return [str(directory / name)] + (
            [] if record["kind"] == "manager" else [record["space"], record["name"]]
        )

    def restart(self, records, verify=True):
        if self.job.get("operation") == "source-version":
            self.clear_source_runtime_snapshots(records)
        self.report("restarting", "恢复实例，等待网页服务就绪")
        processes = []
        if verify:
            self.new_processes = processes
        else:
            self.recovery_processes = processes
        for record in records:
            if record["kind"] == "manager" and self.job["background"]:
                continue
            env = launch_environment(record, self.job["id"], self.job["background"])
            if self.job.get("tool_path"):
                env["PATH"] = self.job["tool_path"]
            with (self.work / "restart.log").open("ab") as log:
                process = subprocess.Popen(
                    self.command_for(record, recovery=not verify),
                    cwd=record.get("cwd") or self.root,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    **detached_options(),
                )
            processes.append(process)
        if not verify:
            return
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            ready = {
                r["pid"]
                for r in instances(self.state)
                if r.get("ready") and r.get("restart_job") == self.job["id"]
            }
            if all(p.pid in ready for p in processes):
                return
            if any(p.poll() is not None for p in processes):
                break
            time.sleep(1)
        # Do not replace a runtime while a failed new launcher still has it open.
        current = [
            r for r in instances(self.state) if r.get("restart_job") == self.job["id"]
        ]
        for record in current:
            write_json(
                self.state / "shutdown" / f"{record['id']}.json",
                {"job": self.job["id"]},
            )
        deadline = time.monotonic() + 90
        while any(p.poll() is None for p in processes) and time.monotonic() < deadline:
            time.sleep(0.5)
        if any(p.poll() is None for p in processes):
            raise RuntimeError(
                "新实例未就绪且无法退出；原版本备份已保留，请退出实例后按更新日志恢复"
            )
        raise RuntimeError(
            "新版本启动失败或不支持更新恢复协议，准备恢复原版本；详情见 restart.log"
        )

    def clear_source_runtime_snapshots(self, records):
        """Old launchers may resume mode 0; remove only their runtime snapshots."""
        self.report("resetting", "重置实例运行缓存，保留配置、专精计划和数据库记录")
        databases = set()
        for record in records:
            if record.get("kind") != "instance":
                continue
            data = record.get("data_dir")
            base = Path(data).expanduser() if data else self.root
            if not base.is_absolute():
                base = Path(record.get("cwd") or self.root) / base
            database = (base / record.get("space", "") / "tmp/data.db").resolve()
            if database in databases or not database.is_file():
                continue
            databases.add(database)
            with (
                closing(
                    sqlite3.connect(
                        database.as_uri() + "?mode=rw", uri=True, timeout=10
                    )
                ) as connection,
                connection,
            ):
                if connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='saved_state'"
                ).fetchone():
                    connection.execute("DELETE FROM saved_state")

    def rollback(self):
        self.report("rollback", "安装未完成，恢复原版本")
        if self.job["deployment"] == "source":
            if self.switched:
                self.run_command(
                    [self.job["git"], "switch", "--detach", self.old_commit]
                )
                if self.old_branch:
                    self.run_command([self.job["git"], "switch", self.old_branch])
            for target, backup in reversed(self.backups):
                if target.exists():
                    shutil.rmtree(target)
                shutil.move(str(backup), target)
            if self.job.get("in_place_environment") and self.dependencies_started:
                self.report("rollback", "按原版本依赖清单恢复当前 Python 环境")
                self.install_dependencies()
        elif self.root.suffix == ".app" and self.bundle_backup.exists():
            failed = self.root.with_name(f"{self.root.name}.failed-{self.job['id']}")
            if self.root.exists():
                os.replace(self.root, failed)
            os.replace(self.bundle_backup, self.root)
        else:
            for target, backup in reversed(self.replacements):
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
                if backup.exists():
                    os.replace(backup, target)

    def start_progress_servers(self):
        if __package__:
            from .software_update_progress import ProgressServers
        else:
            from software_update_progress import ProgressServers
        self.progress_servers = ProgressServers(self.state, self.original)
        self.progress_servers.start()

    def close_progress_servers(self):
        if self.progress_servers:
            self.progress_servers.close()
            self.progress_servers = []

    def execute(self):
        finished = threading.Event()

        def heartbeat():
            while not finished.wait(1):
                write_json(
                    self.state / "active/owner.json",
                    {"pid": os.getpid(), "id": self.job["id"]},
                )
                write_json(self.state / "status.json", dict(self.status))

        write_json(
            self.state / "active/owner.json", {"pid": os.getpid(), "id": self.job["id"]}
        )
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            if self.job["deployment"] == "source":
                self.prepare_source()
                self.prepare_source_payload()
            else:
                self.prepare_package()
            self.begin_install()
            self.stop_instances()
            self.start_progress_servers()
            if self.job["deployment"] == "source":
                self.install_source()
            else:
                self.install_package()
            self.close_progress_servers()
            self.restart(self.original)
            self.report("done", "更新成功，实例已恢复", "succeeded")
        except Exception as exc:
            cancelled = isinstance(exc, UpdateCancelled) or (
                self.cancellable and (self.state / "active/cancel.json").exists()
            )
            self.cancellable = False
            self.status["cancellable"] = False
            if cancelled:
                self.report("cancelled", "已取消更新，当前实例继续运行", "cancelled")
            else:
                traceback.print_exc()
                message = str(exc)
                try:
                    # Refuse rollback over a process still using the replacement.
                    if any(p.poll() is None for p in self.new_processes):
                        raise RuntimeError(
                            "新实例仍在运行，未覆盖程序；请查看备份和 restart.log 后手动恢复"
                        )
                    if self.original or self.switched or self.replacements:
                        self.rollback()
                        self.close_progress_servers()
                        self.restart(self.stopped, verify=False)
                except Exception as recovery_error:
                    traceback.print_exc()
                    message += f"；恢复需要处理：{recovery_error}"
                self.report("failed", message, "failed")

        finally:
            self.cancellable = False
            self.status["cancellable"] = False
            self.close_progress_servers()
            self.cleanup_preparation()
            finished.set()
            thread.join()
            for record in self.original:
                (self.state / "shutdown" / f"{record['id']}.json").unlink(
                    missing_ok=True
                )
            shutil.rmtree(self.state / "active", ignore_errors=True)
            write_json(self.state / "status.json", self.status)


def main(job_path):
    # Windowed PyInstaller applications may set stdout/stderr to None.
    if sys.stdout is None or sys.stderr is None:
        original_streams = sys.stdout, sys.stderr
        with (Path(job_path).parent / "update.log").open(
            "a", encoding="utf-8", buffering=1
        ) as log:
            try:
                sys.stdout = sys.stderr = log
                Worker(job_path).execute()
            finally:
                sys.stdout, sys.stderr = original_streams
    else:
        Worker(job_path).execute()


if __name__ == "__main__":
    main(sys.argv[1])
