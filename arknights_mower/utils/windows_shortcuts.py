import base64
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_CREATE_SHORTCUTS = r"""
$ErrorActionPreference = 'Stop'
$root = $env:MOWER_SHORTCUT_ROOT
$shell = New-Object -ComObject WScript.Shell
foreach ($name in @('mower', '多开管理器')) {
    $target = Join-Path $root ($name + '.exe')
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { continue }
    $destination = Join-Path $root ($name + '（管理员启动）.lnk')
    if (Test-Path -LiteralPath $destination) {
        $existing = $shell.CreateShortcut($destination)
        $bytes = [IO.File]::ReadAllBytes($destination)
        if ($existing.TargetPath -eq $target -and
            $existing.WorkingDirectory -eq $root -and
            $bytes.Length -ge 76 -and
            ([BitConverter]::ToUInt32($bytes, 20) -band 0x2000)) { continue }
    }
    $temporary = Join-Path $env:MOWER_SHORTCUT_TEMP ($name + '.lnk')
    $shortcut = $shell.CreateShortcut($temporary)
    $shortcut.TargetPath = $target
    $shortcut.WorkingDirectory = $root
    $shortcut.IconLocation = $target + ',0'
    $shortcut.Description = '以管理员身份运行 ' + $name
    $shortcut.Save()
    $bytes = [IO.File]::ReadAllBytes($temporary)
    # MS-SHLLINK LinkFlags.RunAsUser requests elevation on explicit launch.
    $flags = [BitConverter]::ToUInt32($bytes, 20) -bor 0x2000
    [BitConverter]::GetBytes([uint32]$flags).CopyTo($bytes, 20)
    [IO.File]::WriteAllBytes($temporary, $bytes)
    Move-Item -LiteralPath $temporary -Destination $destination -Force
}
"""


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
