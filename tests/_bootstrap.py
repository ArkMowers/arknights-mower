"""统一引导：把仓库根插入 sys.path，供所有测试与实机脚本 import。

为什么需要它
------------
1. `unittest discover -s tests -t .` 只保证顶层目录 `.` 在 sys.path 上，
   包内的单个测试文件不保证能解析到 `arknights_mower`。
2. `python tests/live/xxx.py` 时 sys.path[0] 是 `tests/live/`，
   **仓库根不在 sys.path 上**；用 `python -m tests.live.xxx` 又恰好相反。
   两种调用方式只能靠显式引导同时成立。

用法
----
`tests/` 下的实机脚本（`tests/live/*.py`）在文件头部**第一个** import 本模块：

    from tests._bootstrap import REPO_ROOT  # noqa: F401

但用 `python tests/live/xxx.py` 直接执行时，`sys.path[0]` 是 `tests/live/`
而不是仓库根，`tests` 这个包本身都还解析不到，上面那行会先 `ModuleNotFoundError`。
所以脚本需要一段极短的 prelude（见 `tests/README.md`），它只做一件事：
把仓库根塞进 `sys.path`，之后 `from tests._bootstrap import REPO_ROOT` 才成立。
本模块内部同样自带这层兜底，保证 `python -m tests.live.xxx` 与直接执行两种方式等价。

包内模块（`tests/harness/*.py`、`tests/unit/**/*.py`）**不要** import 本模块，
它们随 `tests` 包一起被正确解析；只有被当作脚本直接执行时才需要。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
