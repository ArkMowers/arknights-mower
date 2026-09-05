"""Detached, standard-library-only software installer.

Source deployments copy this module and update_runtime.py outside the checkout.
Frozen deployments run a copy of the complete old runtime outside the install.
The old code, virtualenv and frontend remain available for rollback.
"""

import hashlib
import os
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import threading
import time
import traceback
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

if __package__:
    from .github_download import download_url
    from .update_runtime import (
        detached_options,
        instances,
        launch_environment,
        process_alive,
        read_json,
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
        write_json,
    )

MAX_PACKAGE_BYTES = 2 * 1024**3
MAX_EXTRACTED_BYTES = 8 * 1024**3


def require_clean_source(git, root, env=None):
    changes = subprocess.check_output(
        [
            git,
            "-c",
            "core.quotepath=false",
            "status",
            "--porcelain",
            "--untracked-files=normal",
        ],
        cwd=root,
        env=env,
        text=True,
        timeout=10,
    )
    if changes:
        if isinstance(changes, bytes):
            changes = changes.decode("utf-8", errors="replace")
        entries = changes.rstrip().splitlines()
        preview = "\n".join(entries[:10])
        if len(entries) > 10:
            preview += f"\n……另有 {len(entries) - 10} 项"
        raise ValueError(
            "源码目录有未提交修改或未跟踪文件，请先提交或备份后清理；"
            "更新不会强制覆盖这些文件：\n" + preview
        )


def extract_archive(archive, destination):
    """Extract official zip/tar layouts; no absolute paths or escaping links."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            members = source.infolist()
            if sum(m.file_size for m in members) > MAX_EXTRACTED_BYTES:
                raise ValueError("安装包解压后过大")
            for member in members:
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
                        shutil.copyfileobj(src, dst)
                    mode = (member.external_attr >> 16) & 0o777
                    if mode:
                        target.chmod(mode)
    else:
        with tarfile.open(archive, "r:gz") as source:
            if sum(m.size for m in source.getmembers()) > MAX_EXTRACTED_BYTES:
                raise ValueError("安装包解压后过大")
            source.extractall(destination, filter="data")


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
        self.needs_lfs = False

    def report(self, phase, message, status="running"):
        self.status.update(
            phase=phase, message=message, status=status, updated_at=time.time()
        )
        write_json(self.state / "status.json", self.status)
        print(message, flush=True)

    def run_command(self, args, cwd=None, timeout=1800):
        # Commands and arguments are fixed by the installer. Never use shell=True.
        print("执行：" + " ".join(map(str, args)), flush=True)
        process = subprocess.Popen(
            list(map(str, args)),
            cwd=cwd or self.root,
            env=self.env,
            stdin=subprocess.DEVNULL,
            **detached_options(),
        )
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
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
        require_clean_source(self.job["git"], self.root, self.env)
        self.old_commit = self.git_output("rev-parse", "HEAD")
        self.old_branch = self.git_output("branch", "--show-current")
        write_json(
            self.work / "recovery.json",
            {
                "root": str(self.root),
                "old_commit": self.old_commit,
                "old_branch": self.old_branch,
                "backups": [
                    {
                        "target": str(self.root / relative),
                        "backup": str(
                            self.work / (relative.replace("/", "-") + ".backup")
                        ),
                    }
                    for relative in (self.venv_dir, "ui/node_modules", "ui/dist")
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
            proxy = self.job.get("proxy")
            handler = (
                urllib.request.ProxyHandler({"http": proxy, "https": proxy})
                if proxy
                else urllib.request.ProxyHandler()
            )
            opener = urllib.request.build_opener(handler)
            request = urllib.request.Request(
                download_url(asset["url"], self.job.get("github_proxy", "")),
                headers={"User-Agent": "Mower-Software-Update"},
            )
            with (
                opener.open(request, timeout=60) as response,
                package.open("wb") as out,
            ):
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_PACKAGE_BYTES:
                        raise ValueError("安装包超过 2 GiB 限制")
                    out.write(chunk)
                    self.status.update(current=size, total=asset.get("size", 0))
        if not manual:
            digest = hashlib.sha256()
            with package.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != asset["sha256"]:
                raise ValueError("SHA-256 校验失败，未安装")
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
                shutil.copytree(app, payload_dir / "mower.app", symlinks=True)
            finally:
                self.run_command(
                    ["/usr/bin/hdiutil", "detach", mount], cwd=self.work, timeout=120
                )
        else:
            extract_archive(package, payload_dir)
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
        shutil.copytree(payload, self.prepared, symlinks=True)
        if self.root.suffix == ".app":
            self.verify_macos_signature(self.prepared)

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
        require_clean_source(self.job["git"], self.root, self.env)
        if self.git_output("rev-parse", "HEAD") != self.old_commit:
            raise ValueError("更新准备期间源码发生变化，已取消安装")
        self.report("installing", "切换源码，保留原版本、虚拟环境和前端用于失败恢复")
        for relative in (self.venv_dir, "ui/node_modules", "ui/dist"):
            target = self.root / relative
            if target.exists():
                backup = self.work / (relative.replace("/", "-") + ".backup")
                shutil.move(str(target), backup)
                self.backups.append((target, backup))
        self.switched = True
        self.run_command([self.job["git"], "switch", "--detach", self.job["commit"]])
        if self.needs_lfs:
            self.run_command([self.job["git"], "lfs", "checkout"])
        self.report("dependencies", "创建虚拟环境并安装 Python 依赖")
        self.run_command(
            [self.job["base_python"], "-m", "venv", self.root / self.venv_dir]
        )
        self.run_command(
            [self.job["python"], "-m", "pip", "install", "-r", "requirements.in"]
        )
        self.report("building", "安装前端依赖并构建页面")
        npm_command = (
            "ci" if (self.root / "ui/package-lock.json").is_file() else "install"
        )
        self.run_command([self.job["npm"], npm_command], cwd=self.root / "ui")
        self.run_command([self.job["npm"], "run", "build"], cwd=self.root / "ui")

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

    def command_for(self, record):
        if self.job["deployment"] == "source":
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
                    self.command_for(record),
                    cwd=self.root,
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
            else:
                self.prepare_package()
            self.stop_instances()
            if self.job["deployment"] == "source":
                self.install_source()
            else:
                self.install_package()
            self.restart(self.original)
            self.report("done", "更新成功，实例已恢复", "succeeded")
        except Exception as exc:
            traceback.print_exc()
            message = str(exc)
            try:
                # Refuse rollback over a new process still using the replacement.
                if any(p.poll() is None for p in self.new_processes):
                    raise RuntimeError(
                        "新实例仍在运行，未覆盖程序；请查看备份和 restart.log 后手动恢复"
                    )
                self.rollback()
                self.restart(self.stopped, verify=False)
            except Exception as recovery_error:
                traceback.print_exc()
                message += f"；恢复需要处理：{recovery_error}"
            self.report("failed", message, "failed")
        finally:
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
