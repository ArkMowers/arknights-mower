# tests/ —— 全项目唯一测试根目录

> 契约来源：`重构流程.md` §10.2。旧路径 `arknights_mower/tests/` **已废弃**，不要再引用。

## 门禁命令（4 条，全部必跑）

在仓库根执行：

```powershell
$env:PYTHONIOENCODING="utf-8"     # Windows 控制台中文必需，否则日志乱码
$py = ".venv\Scripts\python.exe"

# G1 单测（基线 35 passed, exit 0）
& $py -m unittest discover -s tests -t . -p "*_tests.py"

# G2 编译（基线 exit 0）
& $py -m compileall -q arknights_mower/scheduler

# G3 Lint（判据是错误数 ≤38，不是 exit code —— 有错误时 ruff 必然 exit 1）
& $py -m ruff check arknights_mower/scheduler --output-format=concise

# G4 导入自检（基线 exit 0；会打印一行 screenshot_cleanup 日志，不是错误）
& $py -c "import arknights_mower.scheduler.bootstrap"
```

**取 G3 错误数（报告里贴这个）**

```powershell
& $py -m ruff check arknights_mower/scheduler --output-format=concise 2>&1 |
    Select-String "^\S+:\d+:\d+:" | Measure-Object | Select-Object -ExpandProperty Count
```

> `-t .` 是**必需**的，否则 `tests/` 的顶层包会被解析成 `unit` 而不是 `tests`，
> 测试模块以 `unit.xxx` 加载，而同一批文件又以 `tests.xxx` 被 import —— **同一个
> 文件被加载成两个模块对象**（实测：`tests.unit.logic_expression_tests` 与
> `unit.logic_expression_tests` 同时存在于 `sys.modules`，`is` 比较为 `False`）。
> 后果是模块级状态、单例、`isinstance` 判定全部失准，且用例可能被重复执行。
> CI 里两个 workflow 用的是同一条命令。

## 新用例放哪

| 我要测什么 | 放哪 | 例子 |
|---|---|---|
| `arknights_mower/scheduler/services/` 的纯逻辑 | `tests/unit/scheduler/services/`（按需新建） | `agent_swap_x_tests.py` |
| `arknights_mower/scheduler/infra/` 的 UI 原语 | `tests/unit/scheduler/infra/` | `navigator_tests.py` |
| 旧 `solvers/` / `utils/` 的既有行为 | `tests/unit/` 平铺 | `logic_expression_tests.py` |
| 实机脚本（连真机，不入门禁） | `tests/live/` | `verify_xxx_live.py` |
| 实机探测回来的真实读数（只读） | `tests/fixtures/*.json` | 面板顺序、房间构成 |

`tests/unit/scheduler/` 是 `arknights_mower/scheduler/` 的**目录结构镜像**；
新建子目录时**必须**同时新建 `__init__.py`（见下方陷阱）。

## ⚠️ 最危险的失败模式：静默漏收

`unittest discover` **不会递归进入没有 `__init__.py` 的子目录**。

实测（本目录，S0 验收标准 2）：

| # | 场景 | G1 结果 |
|---|---|---|
| A | `tests/unit/scheduler/` 只有 `__init__.py`（基线） | **Ran 35 tests** |
| B | 放入临时用例 `tests/unit/scheduler/_recursion_proof_tests.py` | **Ran 36 tests** ✅ 递归生效 |
| C | 临时用例**仍在**，但删掉 `tests/unit/scheduler/__init__.py` | **Ran 35 tests** ← 用例被静默漏收 |
| D | 恢复 `__init__.py` | **Ran 36 tests** |
| E | 删除临时用例 | **Ran 35 tests** |

A / C / E 全部是 `OK`、exit 0 —— **门禁"通过"了，但那个用例根本没跑**。
C 是本次最关键的证据：**漏收不报错，只让数字少 1**。
（B 与 A 的差，是"递归收集是否生效"的唯一可靠信号。）

**所以：`tests/` 下每一个子目录都必须有 `__init__.py`。** 判别方法：

```powershell
Get-ChildItem tests -Recurse -Directory |
    Where-Object { -not (Test-Path (Join-Path $_.FullName "__init__.py")) } |
    Select-Object FullName      # 输出必须为空
```

## 写法规范

| 项 | 规范 |
|---|---|
| 文件名 | `*_tests.py`（**不要** `test_*.py`，否则不匹配 G1 的 `-p`） |
| 类名 | `XxxTests(unittest.TestCase)` |
| 方法名 | `test_<行为>_<预期>`（英文；中文写在 docstring/注释里） |
| 框架 | `unittest`。**禁止引入 pytest** 或任何新依赖 |
| 结构 | AAA：Arrange / Act / Assert，段间空行 |
| 断言 | **必须能证伪**：改坏实现要能变红。无断言的用例一律打回 |
| 回归保护 | 修复类用例在 docstring 写明"修复前行为" |

## 夹具（`tests/harness/`）

**单测里禁止构造真实 `Device` / `PCDevicePort`，禁止真实截图，禁止真实等待。**

```python
from tests.harness.mock_device import MockDevicePort
from tests.harness.mock_recognizer import MockRecognizer
from arknights_mower.scheduler.scene import Scene

device = MockDevicePort(screencap_factory=lambda n: frame)  # n 是第几次截图
recog = MockRecognizer(scenes=[Scene.INFRA_MAIN, Scene.INFRA_DETAILS])

device.tap_named("CLEAR_ALL", *INFRA_CLEAR_ALL)  # 具名点击
service.run(...)
assert device.tap_names() == ["CLEAR_ALL", "SLOT0", "SLOT1"]
assert device.call_names() == ["screencap", "tap", "tap", "tap"]  # 全量按序
```

- `MockDevicePort` **继承** `scheduler/device_port.py` 的 `DevicePort`：
  协议一旦漂移（新增/改名抽象方法），实例化就 `TypeError`，不会静默跑在假实现上。
- `MockRecognizer` 的成员名与真实 `Recognizer` 逐一对齐（`update` / `get_scene` /
  `img` / `gray` / `find` / `set_scene_whitelist` / `check_announcement`），
  实现里一旦改名，用例立刻 `AttributeError`。
- 夹具自检（9 个用例，不入门禁，改动 harness 后手跑）：

  ```powershell
  & $py -m unittest tests.harness.selftest
  ```

## 实机脚本（`tests/live/`）

不参与 G1。规范见 §10.2「实机脚本规范」。共同要求：

- **默认只读**，会点击的必须显式 `--run` 或明确参数
- 必须有 `--seconds` 墙钟上限（默认 ≤300），`finally` 里 `request_stop()`
- 路径引导统一走 `tests/_bootstrap.py`，**不要**用 `parent.parent` 硬算仓库根
- 开头 `logger.setLevel(INFO)`（`utils/log.py` 硬编码 DEBUG）

运行（两种方式等价）：

```powershell
& $py tests\live\verify_scheduler_live.py          # 只读探测，exit 0
& $py -m tests.live.verify_shift_live --room room_1_1 --seconds 120
```

## 路径引导（`tests/_bootstrap.py`）

`python tests/live/xxx.py` 与 `python -m tests.live.xxx` 的 `sys.path[0]` **不同**
（分别是 `tests/live/` 和仓库根），只有一种方式能解析到 `arknights_mower`。
`tests/_bootstrap.py` 把仓库根插进 `sys.path`，让两种调用方式等价。

实机脚本头部需要一小段 prelude（向上找 `tests/_bootstrap.py` 锚点，
**不硬算层数**），之后才是：

```python
from tests._bootstrap import REPO_ROOT  # noqa: E402,F401
```

`tests/harness/` 与 `tests/unit/` 里的模块**不要** import 它 —— 它们随 `tests`
包一起被正确解析。