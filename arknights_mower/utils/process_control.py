"""Restart or stop the calling desktop instance without touching its installation."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

from arknights_mower.utils import update_runtime as runtime


def current_instance():
    return next(
        (
            record
            for record in runtime.instances()
            if record["pid"] == os.getpid() and record["kind"] == "instance"
        ),
        None,
    )


def info():
    record = current_instance()
    return {
        "ok": True,
        "supported": record is not None,
        "name": (record.get("name") or "默认实例") if record else "",
        "message": "" if record else "请通过 Mower 桌面启动器启动实例后使用",
    }


def job_folder(job_id):
    if not isinstance(job_id, str) or UUID(job_id).hex != job_id:
        raise ValueError("无效的进程操作编号")
    return runtime.state_dir() / "control" / job_id


def status(job_id):
    result = runtime.read_json(job_folder(job_id) / "status.json", {})
    if not result:
        raise ValueError("未找到此次进程操作")
    if result["status"] == "running" and not runtime.active_job():
        result.update(status="failed", message="进程操作未完成，请检查日志")
    return {"ok": True, **result}


def request_action(action):
    if action not in ("restart", "stop"):
        raise ValueError("未知进程操作")
    state = runtime.state_dir()
    with runtime.submission_lock(state):
        if runtime.active_job(state):
            raise ValueError("软件更新或进程操作正在进行，请等待完成")
        record = current_instance()
        if record is None:
            raise ValueError("当前服务不是已注册的 Mower 实例")
        job_id = uuid4().hex
        work = job_folder(job_id)
        work.mkdir(parents=True, mode=0o700)
        lock = state / "active"
        shutil.rmtree(lock, ignore_errors=True)
        lock.mkdir()
        runtime.write_json(lock / "owner.json", {"id": job_id, "pid": os.getpid()})
        job = {
            "id": job_id,
            "action": action,
            "record": record,
            "state_dir": str(state),
            "frozen": runtime.frozen(),
        }
        runtime.write_json(work / "job.json", job)
        runtime.write_json(
            work / "status.json",
            {
                "id": job_id,
                "action": action,
                "status": "running",
                "message": "正在等待当前实例正常退出",
            },
        )
        command = [sys.executable]
        if not runtime.frozen():
            command.append(str(runtime.installation_root() / "webview_ui.py"))
        command.extend(["--process-control-worker", str(work / "job.json")])
        try:
            with (work / "process.log").open("ab") as log:
                process = subprocess.Popen(
                    command,
                    cwd=runtime.installation_root(),
                    env=runtime.launch_environment({}),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    **runtime.detached_options(),
                )
            runtime.write_json(lock / "owner.json", {"id": job_id, "pid": process.pid})
        except Exception:
            shutil.rmtree(lock, ignore_errors=True)
            raise
    return {
        "ok": True,
        "id": job_id,
        "action": action,
        "message": "已提交当前实例的进程操作",
    }


def restart_command(record, frozen):
    executable = record["executable"]
    argv = record["argv"]
    return [executable, *argv[1:]] if frozen else [executable, *argv]


def execute(job_path):
    job_path = Path(job_path)
    job = runtime.read_json(job_path)
    state = Path(job["state_dir"])
    record = job["record"]
    request = state / "shutdown" / f"{record['id']}.json"
    result = {"id": job["id"], "action": job["action"], "status": "running"}

    def report(message, status="running"):
        result.update(message=message, status=status)
        runtime.write_json(job_path.parent / "status.json", result)

    try:
        report("正在等待当前实例正常退出")
        runtime.write_json(request, {"job": job["id"]})
        deadline = time.monotonic() + 90
        while runtime.process_alive(record["pid"]):
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "当前实例未能在 90 秒内退出，已取消操作；其他实例不受影响"
                )
            time.sleep(0.25)
        if job["action"] == "stop":
            report("当前实例已结束", "succeeded")
            return
        report("正在恢复当前实例及原启动参数")
        env = runtime.launch_environment(
            record, job["id"], record.get("background", False)
        )
        with (job_path.parent / "restart.log").open("ab") as log:
            child = subprocess.Popen(
                restart_command(record, job["frozen"]),
                cwd=record["cwd"],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                **runtime.detached_options(),
            )
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if any(
                item["pid"] == child.pid
                and item.get("ready")
                and item.get("restart_job") == job["id"]
                for item in runtime.instances(state)
            ):
                report("当前实例已重启，原运行状态将自动恢复", "succeeded")
                return
            if child.poll() is not None:
                break
            time.sleep(0.25)
        raise RuntimeError("重启进程未能就绪，请检查此次操作的 restart.log")
    except Exception as error:
        report(str(error), "failed")
    finally:
        request.unlink(missing_ok=True)
        owner = runtime.read_json(state / "active/owner.json", {})
        if owner.get("id") == job["id"]:
            shutil.rmtree(state / "active", ignore_errors=True)


def worker_main(job_path):
    execute(job_path)
