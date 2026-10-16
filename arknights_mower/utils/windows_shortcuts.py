import base64
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Use the Unicode Shell interface rather than WScript.Shell's legacy path handling.
_SHELL_LINK_TYPE = r"""
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

namespace Mower {
    [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
    class ShellLink { }

    [ComImport, Guid("000214F9-0000-0000-C000-000000000046"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellLinkW {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path,
                     int size, IntPtr findData, uint flags);
        void GetIDList(out IntPtr pidl);
        void SetIDList(IntPtr pidl);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder text, int size);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string text);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int size);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string path);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder text, int size);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string text);
        void GetHotkey(out ushort hotkey);
        void SetHotkey(ushort hotkey);
        void GetShowCmd(out int command);
        void SetShowCmd(int command);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path,
                             int size, out int index);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string path, int index);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string path, uint reserved);
        void Resolve(IntPtr window, uint flags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string path);
    }

    public static class Shortcuts {
        public static void Create(string destination, string target, string directory,
                                  string description) {
            object instance = new ShellLink();
            try {
                IShellLinkW link = (IShellLinkW)instance;
                link.SetPath(target);
                link.SetWorkingDirectory(directory);
                link.SetIconLocation(target, 0);
                link.SetDescription(description);
                ((IPersistFile)instance).Save(destination, true);
            } finally {
                Marshal.FinalReleaseComObject(instance);
            }
        }

        public static string[] Read(string path) {
            object instance = new ShellLink();
            try {
                ((IPersistFile)instance).Load(path, 0);
                IShellLinkW link = (IShellLinkW)instance;
                StringBuilder target = new StringBuilder(32768);
                StringBuilder directory = new StringBuilder(32768);
                link.GetPath(target, target.Capacity, IntPtr.Zero, 4);
                link.GetWorkingDirectory(directory, directory.Capacity);
                return new string[] { target.ToString(), directory.ToString() };
            } finally {
                Marshal.FinalReleaseComObject(instance);
            }
        }
    }
}
"""

_LOAD_SHELL_LINK_TYPE = (
    "$ErrorActionPreference = 'Stop'\nAdd-Type -TypeDefinition @'\n"
    + _SHELL_LINK_TYPE
    + "\n'@\n"
)
_CREATE_SHORTCUTS = (
    _LOAD_SHELL_LINK_TYPE
    + r"""
$root = $env:MOWER_SHORTCUT_ROOT
foreach ($name in @('mower', '多开管理器')) {
    $target = Join-Path $root ($name + '.exe')
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { continue }
    $destination = Join-Path $root ($name + '（管理员启动）.lnk')
    if (Test-Path -LiteralPath $destination) {
        $existing = [Mower.Shortcuts]::Read($destination)
        $bytes = [IO.File]::ReadAllBytes($destination)
        if ($existing[0] -eq $target -and
            $existing[1] -eq $root -and
            $bytes.Length -ge 76 -and
            ([BitConverter]::ToUInt32($bytes, 20) -band 0x2000)) { continue }
    }
    $temporary = Join-Path $env:MOWER_SHORTCUT_TEMP ($name + '.lnk')
    [Mower.Shortcuts]::Create($temporary, $target, $root, ('以管理员身份运行 ' + $name))
    $bytes = [IO.File]::ReadAllBytes($temporary)
    # MS-SHLLINK LinkFlags.RunAsUser requests elevation on explicit launch.
    $flags = [BitConverter]::ToUInt32($bytes, 20) -bor 0x2000
    [BitConverter]::GetBytes([uint32]$flags).CopyTo($bytes, 20)
    [IO.File]::WriteAllBytes($temporary, $bytes)
    Move-Item -LiteralPath $temporary -Destination $destination -Force
}
"""
)


def create_admin_shortcuts():
    """Refresh optional elevated launch links beside the Windows executables."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    root = Path(sys.executable).resolve().parent
    env = os.environ.copy()
    env["MOWER_SHORTCUT_ROOT"] = str(root)
    command = base64.b64encode(_CREATE_SHORTCUTS.encode("utf-16le")).decode("ascii")
    try:
        with tempfile.TemporaryDirectory(
            prefix=".mower-shortcuts-", dir=root
        ) as temporary:
            env["MOWER_SHORTCUT_TEMP"] = temporary
            subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-EncodedCommand",
                    command,
                ],
                cwd=root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=0x08000000,
                timeout=5,
                check=True,
            )
    except (OSError, subprocess.SubprocessError) as error:
        from arknights_mower.utils.log import logger

        logger.warning(
            f"创建管理员启动快捷方式失败（{type(error).__name__}），"
            "可右键 EXE 以管理员身份运行"
        )
