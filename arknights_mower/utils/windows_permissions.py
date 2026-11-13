"""Explicit, account-scoped repair for files left by elevated Windows runs."""

import argparse
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path


def current_user_sid():
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [wintypes.LPVOID]
    kernel.LocalFree.restype = wintypes.LPVOID
    security.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    security.OpenProcessToken.restype = wintypes.BOOL
    security.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    security.GetTokenInformation.restype = wintypes.BOOL
    security.ConvertSidToStringSidW.argtypes = [
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.LPWSTR),
    ]
    security.ConvertSidToStringSidW.restype = wintypes.BOOL
    token = wintypes.HANDLE()
    if not security.OpenProcessToken(
        kernel.GetCurrentProcess(), 8, ctypes.byref(token)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size = wintypes.DWORD()
        security.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not security.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid = ctypes.cast(buffer, ctypes.POINTER(wintypes.LPVOID))[0]
        text = wintypes.LPWSTR()
        if not security.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return text.value
        finally:
            kernel.LocalFree(text)
    finally:
        kernel.CloseHandle(token)


def repair_permissions(roots, sid, *, apply=False):
    """Grant only the selected account; never take ownership or follow links."""
    if not re.fullmatch(r"S-1-(?:\d+-)+\d+", sid):
        raise ValueError("用户 SID 格式无效")
    deadline = time.monotonic() + 120
    executable = Path(os.environ["SystemRoot"]) / "System32/icacls.exe"
    targets = []
    seen = set()
    for root in roots:
        root = Path(os.path.abspath(root))
        if root == Path(root.anchor) or root == Path.home():
            raise ValueError(f"不能修复整个磁盘或用户目录：{root}")
        for ancestor in root.parents:
            info = ancestor.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0)
                & stat.FILE_ATTRIBUTE_REPARSE_POINT
            ):
                raise ValueError(f"权限修复不跟随链接或目录联接：{ancestor}")
        pending = [root]
        while pending:
            if time.monotonic() >= deadline or len(targets) >= 100_000:
                raise TimeoutError(
                    "权限检查超过范围或时间上限，请分别选择具体的 Mower 数据目录"
                )
            path = pending.pop()
            info = path.lstat()
            if path in seen:
                continue
            seen.add(path)
            if (
                stat.S_ISLNK(info.st_mode)
                or getattr(info, "st_file_attributes", 0)
                & stat.FILE_ATTRIBUTE_REPARSE_POINT
            ):
                raise ValueError(f"权限修复不跟随链接或目录联接：{path}")
            directory = stat.S_ISDIR(info.st_mode)
            if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink > 1):
                raise ValueError(f"权限修复不处理特殊文件或硬链接：{path}")
            targets.append((path, directory, info.st_dev, info.st_ino))
            if directory:
                pending.extend(path.iterdir())
    if apply:
        for path, directory, device, inode in targets:
            info = path.lstat()
            if (
                (info.st_dev, info.st_ino) != (device, inode)
                or getattr(info, "st_file_attributes", 0)
                & stat.FILE_ATTRIBUTE_REPARSE_POINT
                or (
                    stat.S_ISLNK(info.st_mode)
                    or stat.S_ISDIR(info.st_mode) != directory
                    or not directory
                    and (not stat.S_ISREG(info.st_mode) or info.st_nlink > 1)
                )
            ):
                raise ValueError(f"目录内容已变化，停止权限修复：{path}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("权限修复超时；已完成的授权保留，可关闭程序后重试")
            permission = "(OI)(CI)M" if directory else "M"
            result = subprocess.run(
                [
                    str(executable),
                    str(path),
                    "/grant",
                    f"*{sid}:{permission}",
                    "/L",
                    "/Q",
                ],
                capture_output=True,
                timeout=min(10, remaining),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode:
                raise PermissionError(
                    f"无法修复权限：{path}；请关闭相关程序并由有权修改该目录权限的账户执行，显式拒绝规则需由系统管理员处理"
                )
    return len(targets)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="检查或修复指定 Mower 数据目录的 Windows 权限；请先关闭相关程序"
    )
    parser.add_argument("directories", nargs="+")
    parser.add_argument(
        "--user-sid",
        help="普通运行账户的 SID；默认当前账户，用其他管理员账户执行时必须指定",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="实际向指定账户授予修改权限；默认仅检查范围",
    )
    args = parser.parse_args(argv)
    try:
        if os.name != "nt":
            raise ValueError("此入口仅用于 Windows 权限修复")
        sid = args.user_sid or current_user_sid()
        count = repair_permissions(args.directories, sid, apply=args.apply)
        message = f"{'已授权' if args.apply else '已检查'} {count} 个文件或目录，账户 SID：{sid}。"
        message += (
            "请退出管理员进程后以普通权限运行验证。"
            if args.apply
            else "添加 --apply 后才会修改权限。"
        )
        code = 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        message, code = str(error), 1
    if getattr(sys, "frozen", False) and os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None, message, "Mower 权限修复", 0x10 if code else 0x40
        )
    else:
        print(message)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
