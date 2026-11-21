"""诊断导出与反馈共用的当前程序版本校验。"""

import unicodedata


class MissingMowerVersionError(ValueError):
    """当前程序没有可用于诊断的有效版本。"""


def require_mower_version(version):
    version = version.strip() if isinstance(version, str) else ""
    if (
        not version
        or len(version) > 128
        or version.casefold() in {"unknown", "未知", "none", "null", "n/a"}
        or any(unicodedata.category(char).startswith("C") for char in version)
    ):
        raise MissingMowerVersionError("未取得有效 Mower 版本")
    return version
