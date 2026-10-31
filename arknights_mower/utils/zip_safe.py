"""zip 解压安全：拒绝路径穿越（zip-slip）。"""

import re
from pathlib import PurePosixPath

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def is_unsafe_zip_member(name: str) -> bool:
    """zip-slip 防护：拒绝绝对路径、穿越段、Windows 盘符路径。"""
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts:
        return True
    return bool(_WINDOWS_DRIVE_RE.match(name))
