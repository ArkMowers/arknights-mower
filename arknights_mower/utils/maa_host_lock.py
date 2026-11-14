"""Coordinate one MAA installation even across different Mower data roots.

POSIX locks the existing directory read-only. Windows uses named kernel mutexes;
each shared reader owns one slot and an installer owns every slot. OS ownership
releases crashed readers without polling or a persistent counter file.
"""

import os
import threading

from arknights_mower.utils.maa_storage import installation_key

MAX_READERS = 64


def host_lease(target, *, exclusive=False, purpose="installation"):
    if os.name == "nt":
        return _WindowsLease(target, exclusive=exclusive, purpose=purpose)
    import fcntl

    # Separate byte-range locks are not available on directories. Navigation's
    # per-data-root lock already isolates its own writable cache.
    if purpose != "installation":
        from contextlib import ExitStack

        return ExitStack()
    descriptor = os.open(target, os.O_RDONLY)
    try:
        fcntl.flock(
            descriptor, fcntl.LOCK_NB | (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        )
    except BaseException:
        os.close(descriptor)
        raise
    from contextlib import ExitStack

    lease = ExitStack()
    lease.callback(os.close, descriptor)
    return lease


class _WindowsLease:
    def __init__(self, target, *, exclusive, purpose):
        self._release = threading.Event()
        ready = threading.Event()
        outcome = []

        def own():
            from contextlib import ExitStack

            try:
                with ExitStack() as stack:
                    kernel, attributes = _mutex_api(stack)
                    key = installation_key(target)
                    for slot in range(MAX_READERS if purpose == "installation" else 1):
                        name = f"Global\\Mower.MAA.{key}.{purpose}.{slot}"
                        handle = kernel.CreateMutexW(attributes, False, name)
                        if not handle:
                            import ctypes

                            raise ctypes.WinError(ctypes.get_last_error())
                        stack.callback(kernel.CloseHandle, handle)
                        status = kernel.WaitForSingleObject(handle, 0)
                        if status in (0, 0x80):
                            stack.callback(kernel.ReleaseMutex, handle)
                            if not exclusive:
                                break
                        elif status == 0x102:
                            if exclusive:
                                raise BlockingIOError("MAA 正在被其他实例使用")
                        else:
                            import ctypes

                            raise ctypes.WinError(ctypes.get_last_error())
                    else:
                        if not exclusive:
                            raise BlockingIOError("MAA 并发实例已达到上限")
                    outcome.append(None)
                    ready.set()
                    self._release.wait()
            except BaseException as error:
                outcome.append(error)
                ready.set()

        # Mutex ownership belongs to a thread. This owner also allows close()
        # from scheduler, cleanup and finalizer threads without leaking a mutex.
        self._thread = threading.Thread(target=own, daemon=True)
        self._thread.start()
        if not ready.wait(5):
            self.close()
            raise TimeoutError("取得 MAA 主机锁超时")
        if outcome[0] is not None:
            self.close()
            raise outcome[0]

    def close(self):
        self._release.set()
        self._thread.join(5)
        if self._thread.is_alive():
            raise TimeoutError("释放 MAA 主机锁超时")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _mutex_api(stack):
    import ctypes
    from ctypes import wintypes

    from arknights_mower.utils.windows_permissions import current_user_sid

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    security = ctypes.WinDLL("advapi32", use_last_error=True)

    class SecurityAttributes(ctypes.Structure):
        _fields_ = [
            ("length", wintypes.DWORD),
            ("descriptor", wintypes.LPVOID),
            ("inherit", wintypes.BOOL),
        ]

    convert = security.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        wintypes.LPVOID,
    ]
    convert.restype = wintypes.BOOL
    descriptor = wintypes.LPVOID()
    # An elevated creator must not exclude the same account's medium token.
    sddl = f"D:P(A;;GA;;;SY)(A;;GA;;;{current_user_sid()})S:(ML;;NW;;;ME)"
    if not convert(sddl, 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    kernel.LocalFree.argtypes = [wintypes.LPVOID]
    kernel.LocalFree.restype = wintypes.LPVOID
    stack.callback(kernel.LocalFree, descriptor)
    attributes = SecurityAttributes(
        ctypes.sizeof(SecurityAttributes), descriptor, False
    )
    for name, args, result in (
        (
            "CreateMutexW",
            [ctypes.POINTER(SecurityAttributes), wintypes.BOOL, wintypes.LPCWSTR],
            wintypes.HANDLE,
        ),
        ("WaitForSingleObject", [wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        ("ReleaseMutex", [wintypes.HANDLE], wintypes.BOOL),
        ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
    ):
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
    return kernel, ctypes.pointer(attributes)
