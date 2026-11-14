"""Delete selected storage files through stable filesystem handles."""

import os
import stat
from contextlib import ExitStack
from pathlib import Path


def delete_file(path, root, cutoff=None):
    """Return deleted bytes, or None when the selected file must be retained."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    if not relative.parts or ".." in relative.parts:
        return None
    if os.name == "nt":
        return _delete_windows_file(path, root, cutoff)
    with ExitStack() as stack:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        parent = os.open(root.anchor, flags)
        stack.callback(os.close, parent)
        for part in (*root.parts[1:], *relative.parts[:-1]):
            parent = os.open(part, flags, dir_fd=parent)
            stack.callback(os.close, parent)
        info = os.stat(relative.name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            return None
        if cutoff is not None and info.st_mtime >= cutoff:
            return None
        os.unlink(relative.name, dir_fd=parent)
        return info.st_size


def _delete_windows_file(path, root, cutoff):
    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel32.CreateFileW
    create.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create.restype = wintypes.HANDLE
    final_path = kernel32.GetFinalPathNameByHandleW
    final_path.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    final_path.restype = wintypes.DWORD
    dispose = kernel32.SetFileInformationByHandle
    dispose.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    dispose.restype = wintypes.BOOL
    close = kernel32.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL

    # DELETE | FILE_READ_ATTRIBUTES, share read/write but forbid rename/delete.
    # OPEN_REPARSE_POINT opens the leaf itself, never its symbolic-link target.
    handle = create(str(path), 0x10080, 3, None, 3, 0x200000, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close(handle)
        raise
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or (
            info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            return None
        if cutoff is not None and info.st_mtime >= cutoff:
            return None
        buffer = ctypes.create_unicode_buffer(32768)
        length = final_path(handle, buffer, len(buffer), 0)
        if not length:
            raise ctypes.WinError(ctypes.get_last_error())
        if length >= len(buffer):
            raise OSError("文件路径过长，无法确认清理范围")
        resolved = buffer.value
        if resolved.startswith("\\\\?\\UNC\\"):
            resolved = "\\\\" + resolved[8:]
        elif resolved.startswith("\\\\?\\"):
            resolved = resolved[4:]
        if not Path(resolved).is_relative_to(root):
            return None
        delete = ctypes.c_bool(True)
        if not dispose(handle, 4, ctypes.byref(delete), ctypes.sizeof(delete)):
            raise ctypes.WinError(ctypes.get_last_error())
        return info.st_size
    finally:
        os.close(descriptor)
