"""Windows kernel ownership for the JPEG worker and its launcher descendants."""

import os
import subprocess
import sys
import time
from threading import RLock


class WindowsJpegProcess:
    """Create the child inside a noninherited kill-on-close Job, before resuming."""

    def __init__(self, command, *, cwd, env, **options):
        if options.keys() - {"stdin", "stdout", "stderr", "creationflags"}:
            raise TypeError("截图编码启动包含不支持的选项")
        if any(
            options.get(name, subprocess.DEVNULL) != subprocess.DEVNULL
            for name in ("stdin", "stdout", "stderr")
        ):
            raise ValueError("截图编码子进程不接收标准流")
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", ctypes.c_uint64 * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        class StartupInfo(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD),
                ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD),
                ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD),
                ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE),
            ]

        class StartupInfoEx(ctypes.Structure):
            _fields_ = [
                ("StartupInfo", StartupInfo),
                ("lpAttributeList", ctypes.c_void_p),
            ]

        class ProcessInfo(ctypes.Structure):
            _fields_ = [
                ("hProcess", wintypes.HANDLE),
                ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD),
            ]

        class Accounting(ctypes.Structure):
            _fields_ = [
                ("TotalUserTime", ctypes.c_int64),
                ("TotalKernelTime", ctypes.c_int64),
                ("ThisPeriodTotalUserTime", ctypes.c_int64),
                ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                ("TotalPageFaultCount", wintypes.DWORD),
                ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD),
                ("TotalTerminatedProcesses", wintypes.DWORD),
            ]

        class ProcessIds(ctypes.Structure):
            _fields_ = [
                ("NumberOfAssignedProcesses", wintypes.DWORD),
                ("NumberOfProcessIdsInList", wintypes.DWORD),
                ("ProcessIdList", ctypes.c_size_t * 64),
            ]

        self._ctypes = ctypes
        self._Accounting = Accounting
        self._ProcessIds = ProcessIds
        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._job = self._handle = None
        self._members = {}
        self._lock = RLock()
        self.returncode = None
        self.args = command
        self.owner_pid = os.getpid()
        for name, arguments, result in (
            ("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            (
                "SetInformationJobObject",
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
                wintypes.BOOL,
            ),
            (
                "InitializeProcThreadAttributeList",
                [ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p],
                wintypes.BOOL,
            ),
            (
                "UpdateProcThreadAttribute",
                [
                    ctypes.c_void_p,
                    wintypes.DWORD,
                    ctypes.c_size_t,
                    ctypes.c_void_p,
                    ctypes.c_size_t,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                ],
                wintypes.BOOL,
            ),
            ("DeleteProcThreadAttributeList", [ctypes.c_void_p], None),
            (
                "CreateProcessW",
                [
                    wintypes.LPCWSTR,
                    wintypes.LPWSTR,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    wintypes.BOOL,
                    wintypes.DWORD,
                    ctypes.c_void_p,
                    wintypes.LPCWSTR,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                ],
                wintypes.BOOL,
            ),
            ("ResumeThread", [wintypes.HANDLE], wintypes.DWORD),
            (
                "OpenProcess",
                [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD],
                wintypes.HANDLE,
            ),
            (
                "IsProcessInJob",
                [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)],
                wintypes.BOOL,
            ),
            ("TerminateJobObject", [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            (
                "QueryInformationJobObject",
                [
                    wintypes.HANDLE,
                    ctypes.c_int,
                    ctypes.c_void_p,
                    wintypes.DWORD,
                    ctypes.c_void_p,
                ],
                wintypes.BOOL,
            ),
            ("WaitForSingleObject", [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            (
                "GetExitCodeProcess",
                [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)],
                wintypes.BOOL,
            ),
            ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
        ):
            function = getattr(self._kernel, name)
            function.argtypes, function.restype = arguments, result

        attributes = None
        initialized = False
        thread = None
        try:
            self._job = self._kernel.CreateJobObjectW(None, None)
            self._check(self._job)
            limits = ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
            self._check(
                self._kernel.SetInformationJobObject(
                    self._job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
                )
            )
            size = ctypes.c_size_t()
            self._kernel.InitializeProcThreadAttributeList(
                None, 1, 0, ctypes.byref(size)
            )
            attributes = ctypes.create_string_buffer(size.value)
            self._check(
                self._kernel.InitializeProcThreadAttributeList(
                    attributes, 1, 0, ctypes.byref(size)
                )
            )
            initialized = True
            jobs = (wintypes.HANDLE * 1)(self._job)
            # Windows 10 JOB_LIST assigns ownership atomically in CreateProcess.
            self._check(
                self._kernel.UpdateProcThreadAttribute(
                    attributes, 0, 0x0002000D, jobs, ctypes.sizeof(jobs), None, None
                )
            )
            startup = StartupInfoEx()
            startup.StartupInfo.cb = ctypes.sizeof(startup)
            startup.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
            process = ProcessInfo()
            environment = ctypes.create_unicode_buffer(
                "\0".join(f"{key}={value}" for key, value in sorted(env.items())) + "\0"
            )
            flags = options.get("creationflags", 0) | 0x00000400 | 0x00080000 | 4
            self._check(
                self._kernel.CreateProcessW(
                    str(command[0]),
                    ctypes.create_unicode_buffer(subprocess.list2cmdline(command)),
                    None,
                    None,
                    False,
                    flags,
                    environment,
                    str(cwd),
                    ctypes.byref(startup),
                    ctypes.byref(process),
                )
            )
            self.pid = process.dwProcessId
            self._handle, thread = process.hProcess, process.hThread
            self.capture_members()
            self._check(self._kernel.ResumeThread(thread) != 0xFFFFFFFF)
        except BaseException:
            self.kill()
            if self._handle is not None:
                self.wait(timeout=0.2)
            raise
        finally:
            if thread is not None:
                self._kernel.CloseHandle(thread)
            if initialized:
                self._kernel.DeleteProcThreadAttributeList(attributes)

    def _check(self, result):
        if not result:
            raise self._ctypes.WinError(self._ctypes.get_last_error())

    def poll(self):
        with self._lock:
            return self._poll()

    def _poll(self):
        self.capture_members()
        if self.returncode is None:
            from ctypes import wintypes

            result = self._kernel.WaitForSingleObject(self._handle, 0)
            if result == 0xFFFFFFFF:
                self._check(False)
            if result == 0:
                code = wintypes.DWORD()
                self._check(
                    self._kernel.GetExitCodeProcess(
                        self._handle, self._ctypes.byref(code)
                    )
                )
                self.kill()
                self.returncode = code.value
                self._kernel.CloseHandle(self._handle)
                self._handle = None
        if self.returncode is not None and self._job is not None:
            accounting = self._Accounting()
            self._check(
                self._kernel.QueryInformationJobObject(
                    self._job,
                    1,
                    self._ctypes.byref(accounting),
                    self._ctypes.sizeof(accounting),
                    None,
                )
            )
            if accounting.ActiveProcesses:
                return None
            for handle in self._members.values():
                result = self._kernel.WaitForSingleObject(handle, 0)
                if result == 0xFFFFFFFF:
                    self._check(False)
                if result != 0:
                    return None
            for handle in self._members.values():
                self._kernel.CloseHandle(handle)
            self._members.clear()
            self._check(self._kernel.CloseHandle(self._job))
            self._job = None
        return self.returncode

    def wait(self, timeout=None):
        deadline = None if timeout is None else time.monotonic() + max(0, timeout)
        while self.poll() is None:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                raise subprocess.TimeoutExpired(self.args, timeout)
            # poll owns the handle lock; stats may close a signaled handle afterward.
            time.sleep(0.001 if remaining is None else min(0.001, remaining))
        return self.returncode

    def kill(self):
        with self._lock:
            self._kill()

    def _kill(self):
        # Keep the Job handle to verify every descendant exits within the caller budget.
        if self._job is not None and self.owner_pid == os.getpid():
            self.capture_members()
            self._check(self._kernel.TerminateJobObject(self._job, 1))

    def capture_members(self):
        """Retain confirmed Job member handles before termination can hide their PIDs."""
        with self._lock:
            self._capture_members()

    def _capture_members(self):
        if self._job is None:
            return
        from ctypes import wintypes

        members = self._ProcessIds()
        self._check(
            self._kernel.QueryInformationJobObject(
                self._job,
                3,
                self._ctypes.byref(members),
                self._ctypes.sizeof(members),
                None,
            )
        )
        for pid in members.ProcessIdList[: members.NumberOfProcessIdsInList]:
            if pid in self._members:
                continue
            handle = self._kernel.OpenProcess(0x00100000 | 0x1000, False, pid)
            if not handle:
                if self._ctypes.get_last_error() == 87:  # Already gone.
                    continue
                self._check(False)
            try:
                belongs = wintypes.BOOL()
                self._check(
                    self._kernel.IsProcessInJob(
                        handle, self._job, self._ctypes.byref(belongs)
                    )
                )
                if not belongs.value:
                    raise RuntimeError("截图编码进程成员所有权无法核实")
                self._members[pid] = handle
                handle = None
            finally:
                if handle is not None:
                    self._kernel.CloseHandle(handle)

    def __del__(self):
        if getattr(self, "owner_pid", None) == os.getpid():
            if self._job is not None:
                self._kernel.CloseHandle(self._job)
            if self._handle is not None:
                self._kernel.CloseHandle(self._handle)
            for handle in self._members.values():
                self._kernel.CloseHandle(handle)


def launch_jpeg_process(command, **options):
    if sys.platform == "win32":
        return WindowsJpegProcess(command, **options)
    return subprocess.Popen(command, **options)
