"""Lightweight ownership of one desktop instance; no device or image imports."""

import mmap
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from arknights_mower.utils import update_runtime as runtime

RESTART_DELAYS = (2.0, 5.0, 15.0)
COOLDOWN_DELAYS = (60.0, 120.0, 300.0)
RESTART_WINDOW = 900.0
STARTUP_TIMEOUT = 120.0
LOCK_TIMEOUT = 15.0
INTENTIONAL_EXIT_CODE = 73
INTENTIONAL_REASONS = frozenset(("window", "tray", "ctrl_c", "runtime_request"))
_report_lock = threading.RLock()


class AutomaticStartCancelled(RuntimeError):
    """The existing Stop intent rejects an internal automatic start."""


def supervisor_directory(arguments):
    from arknights_mower.utils.path import get_path

    space = arguments[0] if arguments and not arguments[0].startswith("-") else ""
    data = get_path("@app", space=space).resolve()
    return data / "tmp/process-supervision"


instance_lock = runtime.supervision_lock


def _console_options():
    """Keep source logs in an attached console without opening a new one."""
    if sys.platform == "win32" and not runtime.frozen():
        import ctypes

        process_ids = (ctypes.c_ulong * 1)()
        if ctypes.WinDLL("kernel32").GetConsoleProcessList(process_ids, 1):
            return {}
    return runtime.hidden_console_options()


def child_command(arguments, *, executable=None, entry=None, frozen=None):
    executable = executable or sys.executable
    frozen = runtime.frozen() if frozen is None else frozen
    if frozen:
        return [executable, "--supervised-instance", *arguments]
    entry = entry or str(runtime.installation_root() / "webview_ui.py")
    return [executable, entry, "--supervised-instance", *arguments]


def child_report(**values):
    report = os.environ.get("MOWER_SUPERVISOR_CHILD_REPORT")
    generation = os.environ.get("MOWER_SUPERVISOR_GENERATION")
    if not report or not generation:
        return
    with _report_lock:
        previous = runtime.read_json(report, {})
        if previous and previous.get("generation") != generation:
            raise RuntimeError("实例监督记录不属于当前启动")
        previous.update(values, generation=generation, pid=os.getpid())
        runtime.write_json(report, previous, sync=True)


def child_ready(registration, *, desired_running=None):
    from arknights_mower.utils import crash_recovery

    notice = runtime.read_json(
        Path(os.environ.get("MOWER_SUPERVISOR_DIRECTORY", ".")) / "recovery.json", {}
    )
    if not isinstance(notice, dict):
        notice = {}
    wanted = bool(
        registration.record.get("running")
        if desired_running is None
        else desired_running
    )
    if notice.get("active") and type(notice.get("resume_requested")) is bool:
        wanted = notice["resume_requested"]
    elif notice.get("active") and os.environ.get("MOWER_RECOVERY_RUN") in (
        "0",
        "1",
    ):
        wanted = os.environ["MOWER_RECOVERY_RUN"] == "1"
    with _report_lock:
        control = os.environ.get("MOWER_SUPERVISOR_INTENT")
        if control and sys.platform == "win32":
            with mmap.mmap(-1, 1, tagname=control, access=mmap.ACCESS_WRITE) as shared:
                if shared[0] != 255:
                    wanted = bool(shared[0])
        try:
            task_intent(wanted, automatic=True)
        except AutomaticStartCancelled:
            wanted = False
            task_intent(False)
        initialized = crash_recovery.initialize_intent(wanted)
        if initialized != wanted:
            task_intent(initialized, automatic=True)
        child_report(
            ready=True,
            port=registration.record["port"],
            shutdown_request=str(registration.request),
        )


def task_intent(running, *, automatic=False):
    with _report_lock:
        control = os.environ.get("MOWER_SUPERVISOR_INTENT")
        if control and sys.platform == "win32":
            with mmap.mmap(-1, 1, tagname=control, access=mmap.ACCESS_WRITE) as shared:
                if automatic and running and shared[0] == 0:
                    raise AutomaticStartCancelled("用户已停止任务，取消自动启动")
                shared[0] = int(bool(running))
        child_report(desired_running=bool(running))


def http_probe(port, timeout):
    """Check HTTP responsiveness independently of scheduler logs and sleeps."""
    from urllib.request import ProxyHandler, build_opener

    try:
        with build_opener(ProxyHandler({})).open(
            f"http://127.0.0.1:{int(port)}/status", timeout=timeout
        ) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def child_exit(reason):
    child_report(intentional=reason in INTENTIONAL_REASONS, exit_reason=reason)


class WindowsInstanceJob:
    """Prove launcher descendants without taking ownership of shared services."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes = ctypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        for name, args, result in (
            ("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            (
                "AssignProcessToJobObject",
                [wintypes.HANDLE, wintypes.HANDLE],
                wintypes.BOOL,
            ),
            (
                "IsProcessInJob",
                [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)],
                wintypes.BOOL,
            ),
            ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
        ):
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = args, result
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.resume = ctypes.WinDLL("ntdll").NtResumeProcess
        self.resume.argtypes, self.resume.restype = [wintypes.HANDLE], wintypes.LONG

    def start(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, process._handle):
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        if self.resume(process._handle):
            raise OSError("无法启动自有实例进程")

    def contains(self, handle):
        from ctypes import wintypes

        included = wintypes.BOOL()
        if not self.kernel.IsProcessInJob(
            handle, self.handle, self.ctypes.byref(included)
        ):
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        return bool(included.value)

    def close(self):
        # No KILL_ON_JOB_CLOSE: ADB and the selected simulator retain their lifecycle.
        self.kernel.CloseHandle(self.handle)


class OwnedWindowsProcess:
    """Keep an exact registered child handle when a Python launcher re-execs."""

    def __init__(self, pid, job):
        import ctypes
        from ctypes import wintypes

        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.handle = self.kernel.OpenProcess(0x00100000 | 0x0001 | 0x1000, False, pid)
        if not self.handle:
            if ctypes.get_last_error() == 87:
                raise ProcessLookupError("自有实例已退出")
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not job.contains(self.handle):
                raise RuntimeError("实例登记进程不属于自有启动进程，保留该进程")
        except BaseException:
            self.close()
            raise

    def poll(self):
        import ctypes
        from ctypes import wintypes

        result = self.kernel.WaitForSingleObject(self.handle, 0)
        if result == 258:
            return None
        if result != 0:
            raise OSError("无法确认自有实例进程是否退出")
        code = wintypes.DWORD()
        if not self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)):
            raise OSError("无法读取自有实例进程退出结果")
        return code.value

    def stop(self):
        if self.kernel.WaitForSingleObject(self.handle, 0) == 0:
            return
        if not self.kernel.TerminateProcess(self.handle, 1):
            raise OSError("终止自有实例进程失败")
        if self.kernel.WaitForSingleObject(self.handle, 5000) != 0:
            raise TimeoutError("自有实例进程未在预算内结束")

    def close(self):
        self.kernel.CloseHandle(self.handle)


def supervise(
    command,
    directory,
    *,
    delays=RESTART_DELAYS,
    cooldowns=COOLDOWN_DELAYS,
    window=RESTART_WINDOW,
    startup_timeout=STARTUP_TIMEOUT,
    poll_interval=0.2,
    environment=None,
    health_interval=10.0,
    health_timeout=3.0,
    health_failure_window=120.0,
    health_probe=http_probe,
):
    """Restore established-process exits; never infer dispatch progress or replay."""
    directory = Path(directory)
    exits = []
    base_environment = dict(os.environ if environment is None else environment)
    state = runtime.state_dir()
    recovery_path = directory / "recovery.json"

    def recovery_suppressed(report):
        request = report.get("shutdown_request")
        return (
            report.get("intentional") is True
            or (request and Path(request).exists())
            or runtime.active_job(state)
        )

    def retry(report, code, desired):
        nonlocal exits
        request = report.get("shutdown_request")
        if code == INTENTIONAL_EXIT_CODE or recovery_suppressed(report):
            return False
        if not report.get("ready"):
            runtime.write_json(
                directory / "failure.json",
                {
                    "reason": report.get("failure_reason", "startup_exit"),
                    "exit_code": code,
                    "message": "实例启动暂未完成，后台退避后自动重试",
                },
            )
        now = time.monotonic()
        exits = [item for item in exits if now - item < window]
        exits.append(now)
        attempts = len(exits)
        previous = runtime.read_json(recovery_path)
        wanted = desired
        if wanted is None and type(report.get("desired_running")) is bool:
            wanted = report["desired_running"]
        if (
            wanted is None
            and isinstance(previous, dict)
            and type(previous.get("resume_requested")) is bool
        ):
            wanted = previous["resume_requested"]
        if wanted is None:
            for variable in ("MOWER_RECOVERY_RUN", "MOWER_RESUME_RUN"):
                if base_environment.get(variable) in ("0", "1"):
                    wanted = base_environment[variable] == "1"
                    break
        if wanted is None and base_environment.get("MOWER_RESUME_MODE") in (
            "0",
            "1",
        ):
            wanted = True
        if (
            not recovery_path.exists()
            or isinstance(previous, dict)
            and type(previous.get("active")) is bool
        ):
            notice = {
                "active": True,
                "phase": "waiting",
                "exit_code": code,
                "attempt": attempts,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "reason": report.get("failure_reason", "process_exit"),
                "message": "主实例意外退出或服务持续无响应；后台正在恢复服务，重新观察后自动接续已保存任务。",
            }
            if wanted is not None:
                notice["resume_requested"] = wanted
            if isinstance(previous, dict):
                if previous.get("reset_observation_pending"):
                    notice["start_type"] = "2"
                    notice["reset_observation_pending"] = True
                elif previous.get("active") is True:
                    notice["start_type"] = previous.get("start_type", "0")
            runtime.write_json(recovery_path, notice, sync=True)
        if wanted is None:
            base_environment.pop("MOWER_RECOVERY_RUN", None)
        else:
            base_environment["MOWER_RECOVERY_RUN"] = "1" if wanted else "0"
        runtime.write_json(
            directory / "supervisor.json",
            {
                "pid": os.getpid(),
                "generation": generation,
                "phase": "backoff",
                "attempt": attempts,
            },
        )
        delay = (
            delays[attempts - 1]
            if attempts <= len(delays)
            else cooldowns[min(attempts - len(delays) - 1, len(cooldowns) - 1)]
        )
        until = time.monotonic() + delay
        while time.monotonic() < until:
            if runtime.active_job(state) or (request and Path(request).exists()):
                return False
            time.sleep(min(poll_interval, max(0, until - time.monotonic())))
        # A replacement launch must not inherit update-resume intent from an old job.
        for variable in ("MOWER_RESUME_MODE", "MOWER_RESUME_RUN", "MOWER_RESTART_JOB"):
            base_environment.pop(variable, None)
        if report.get("port"):
            base_environment["MOWER_RESTART_PORT"] = str(report["port"])

        return True

    while True:
        generation = uuid4().hex
        report_path = directory / f"child-{generation}.json"
        child_environment = base_environment.copy()
        child_environment.update(
            MOWER_SUPERVISOR_DIRECTORY=str(directory),
            MOWER_SUPERVISOR_CHILD_REPORT=str(report_path),
            MOWER_SUPERVISOR_GENERATION=generation,
        )
        intent = None
        desired = None
        windows_job = None
        process = None
        report = {}
        runtime.write_json(
            directory / "supervisor.json",
            {"pid": os.getpid(), "generation": generation, "phase": "starting"},
        )
        options = _console_options()
        try:
            if sys.platform == "win32":
                control_name = f"Local\\MowerRecoveryIntent_{generation}"
                intent = mmap.mmap(
                    -1, 1, tagname=control_name, access=mmap.ACCESS_WRITE
                )
                intent[0] = 255
                child_environment["MOWER_SUPERVISOR_INTENT"] = control_name
                windows_job = WindowsInstanceJob()
                options["creationflags"] = options.get("creationflags", 0) | 0x00000004
            process = subprocess.Popen(
                command,
                env=child_environment,
                stdin=subprocess.DEVNULL,
                **options,
            )
            if windows_job is not None:
                windows_job.start(process)
        except BaseException as error:
            try:
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
            finally:
                if intent is not None:
                    intent.close()
                if windows_job is not None:
                    windows_job.close()
            if not isinstance(error, (OSError, MemoryError)):
                raise
            if not retry(
                {"failure_reason": "process_creation", "creation_error": str(error)},
                1,
                None,
            ):
                return 1
            continue
        owned_leaf = None
        deadline = time.monotonic() + startup_timeout
        probe_at = 0.0
        unavailable_since = None
        try:
            while True:
                observed = runtime.read_json(report_path)
                if (
                    isinstance(observed, dict)
                    and observed.get("generation") == generation
                ):
                    report = observed
                    if sys.platform == "win32" and owned_leaf is None:
                        pid = report.get("pid")
                        if type(pid) is int and pid != process.pid:
                            try:
                                owned_leaf = OwnedWindowsProcess(pid, windows_job)
                            except ProcessLookupError:
                                pass
                # Adopt an already-published leaf before treating wrapper exit
                # as instance exit; a venv/frozen launcher may finish first.
                if process.poll() is not None and (
                    owned_leaf is None or owned_leaf.poll() is not None
                ):
                    break
                if (
                    not report.get("ready")
                    and time.monotonic() >= deadline
                    and not recovery_suppressed(report)
                ):
                    if owned_leaf is not None:
                        owned_leaf.stop()
                    process.terminate()
                    process.wait(timeout=5)
                    runtime.write_json(
                        directory / "failure.json",
                        {
                            "reason": "startup_timeout",
                            "message": "HTTP 服务未在启动预算内就绪，监督已停止",
                        },
                    )
                    report["failure_reason"] = "startup_timeout"
                    break
                now = time.monotonic()
                if (
                    report.get("ready")
                    and report.get("port")
                    and now >= probe_at
                    and not recovery_suppressed(report)
                ):
                    probe_at = now + health_interval
                    if health_probe(report["port"], health_timeout):
                        unavailable_since = None
                    elif unavailable_since is None:
                        unavailable_since = now
                    elif now - unavailable_since >= health_failure_window:
                        # A shutdown or replacement can begin during the probe.
                        observed = runtime.read_json(report_path)
                        if (
                            isinstance(observed, dict)
                            and observed.get("generation") == generation
                        ):
                            report.update(observed)
                        if recovery_suppressed(report):
                            unavailable_since = None
                            continue
                        if owned_leaf is not None:
                            owned_leaf.stop()
                        if process.poll() is None:
                            process.terminate()
                            process.wait(timeout=5)
                        report["failure_reason"] = "http_unresponsive"
                        break
                time.sleep(poll_interval)
            code = owned_leaf.poll() if owned_leaf is not None else process.returncode
            observed = runtime.read_json(report_path)
            if isinstance(observed, dict) and observed.get("generation") == generation:
                report.update(observed)
        except BaseException:
            if owned_leaf is not None:
                owned_leaf.stop()
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            raise
        finally:
            if intent is not None:
                desired = None if intent[0] == 255 else bool(intent[0])
                intent.close()
            if owned_leaf is not None:
                owned_leaf.close()
            if windows_job is not None:
                windows_job.close()
            report_path.unlink(missing_ok=True)
        if not retry(report, code, desired):
            return code


def run_launcher(arguments):
    directory = supervisor_directory(arguments)
    with instance_lock(directory):
        # A surviving child retains exclusivity even after supervisor termination.
        with instance_lock(directory, timeout=0, child=True):
            pass
        return supervise(child_command(arguments), directory)


wait_for_release = runtime.wait_for_supervisor_release
