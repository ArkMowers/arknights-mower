"""T1.2 — C5 回归实机验收（S5；**零点击、不连设备**）。

验收目标（§10.3「S13 分片执行」T1.2）
------------------------------------
用**真实** `conf.yml` / `plan.json` 配置，在 `backup_plans=[]` 下构造
`SchedulerState`，**不得**抛 `ConfigError(宿舍优先级和当前宿舍不匹配)`。

三条硬性规约的落实
------------------
| 规约 | 落实方式 |
|---|---|
| 2 反向对照不可省 | 故意把 `config.conf.dorm_order` 设为错配值（`dormitory_9_9`），**必须仍然抛** `ConfigError`。测完在内存里还原 |
| 2 结论不得空洞 | 另加**证伪对照**：用子类复现 C5 修复前的分支（`_backup_plans` 为空时不调 `swap_plan`），该场景**必须**抛错 —— 证明这条判据真能变红 |
| 3 不得写用户 `conf.yml` | 全程把 `config.save_conf` 换成计数器；`dorm_order == ""` 分支会命中它，正是该守卫的必要性证据 |

用法（项目根目录）
------------------
    .venv\\Scripts\\python.exe tests\\live\\t1_2_c5_regression.py
    .venv\\Scripts\\python.exe tests\\live\\t1_2_c5_regression.py --seconds 120

安全边界
--------
- **不连接任何设备**，**不 tap / swipe**，不启动 MainLoop
- 只读 `conf.yml` / `plan.json`；`config.conf.dorm_order` 的改动只存在于本进程内存
- `finally` 里 `request_stop()`，`Ctrl+C` 可安全中断
"""

import argparse
import sys
from pathlib import Path

# 直接执行（python tests/live/xxx.py）时 sys.path[0] 是 tests/live/，仓库根不在其中，
# 连 `tests` 这个包都还解析不到。这里**不硬算层数**，改为向上找 tests/_bootstrap.py 锚点；
# 真正的路径引导一律由 tests._bootstrap 负责。
for _parent in Path(__file__).resolve().parents:
    if (_parent / "tests" / "_bootstrap.py").is_file():
        sys.path.insert(0, str(_parent))
        break

# 副作用：把仓库根写入 sys.path
from tests._bootstrap import REPO_ROOT  # noqa: E402,F401

from tests.live.t1_common import (  # noqa: E402
    WallClockStop,
    no_save_conf,
    quiet_logs,
    sha256_file,
)

# 规约 2 指定的错配哨兵值（不是阈值，是"必定不匹配"的构造值）
MISMATCH_DORM_ORDER = "dormitory_9_9"
MISMATCH_MESSAGE = "宿舍优先级和当前宿舍不匹配"


def _load_state(global_plan, state_cls=None):
    """构造 SchedulerState，返回 (state, error_message)。

    不在此处捕获 `BaseException`：只把 `ConfigError` 与其它异常分开，
    以便把"校验拒绝"和"代码崩了"区分开。
    """
    from arknights_mower.scheduler.errors import ConfigError

    cls = state_cls
    if cls is None:
        from arknights_mower.scheduler.state import SchedulerState

        cls = SchedulerState
    try:
        return cls(global_plan=global_plan), None
    except ConfigError as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001 - 探测脚本需区分"崩了"与"校验拒绝"
        return None, f"<{type(exc).__name__}> {exc}"


def _make_pre_fix_state_class():
    """复现 C5 修复前的分支：`_backup_plans` 为空时**不**调 `swap_plan`。

    修复前 `state.py` 的写法是 `if self._backup_plans: self.swap_plan(...)`。
    本子类把该条件加回 `swap_plan`，其余逻辑完全沿用当前实现 —— 因此
    "该场景必须抛错"就等价于"C5 修复本身是必要且可证伪的"。
    """
    from arknights_mower.scheduler.state import SchedulerState

    class _PreFixState(SchedulerState):
        def swap_plan(self, condition, refresh=False):
            if not self._backup_plans:
                return None
            return super().swap_plan(condition, refresh)

    return _PreFixState


def run_checks() -> bool:
    from arknights_mower.utils import config
    from arknights_mower.utils.operators import build_global_plan

    conf_path = Path(REPO_ROOT) / "conf.yml"
    before_sha = sha256_file(conf_path)
    print(f"[0] conf.yml 运行前 SHA256 = {before_sha}")

    original_dorm_order = config.conf.dorm_order
    print(f"[0] 真实 dorm_order = {original_dorm_order!r}")

    results: list[tuple[str, bool]] = []

    def record(name: str, ok: bool) -> None:
        results.append((name, ok))
        print(f"    -> {'PASS' if ok else 'FAIL'}  {name}")

    # ---------- 正向：真实配置 + backup_plans=[] ----------
    print("\n[1] 正向：真实配置 + backup_plans=[] 构造 SchedulerState")
    with no_save_conf() as save_calls:
        plan = build_global_plan()
        plan["backup_plans"] = []
        state, error = _load_state(plan)
        intercepted = len(save_calls)

    if state is None:
        print(f"    抛错：{error}")
    else:
        print(f"    plan 房间数 = {len(state.plan)}")
        print(f"    干员数     = {len(state.operators)}")
        print(f"    config set = {state.config is not None}")
        print(f"    宿舍数     = {len(state.dormitories)}")
        print(f"    backup_plans 长度 = {len(state.backup_plans)}")
    print(f"    save_conf 被拦截次数 = {intercepted}（>0 证明该守卫是必要的）")

    record("正向不抛 ConfigError", state is not None)
    record("正向 plan 非空", state is not None and bool(state.plan))
    record("正向 config 非 None", state is not None and state.config is not None)
    record(
        "正向错误信息不含宿舍优先级不匹配",
        error is None or MISMATCH_MESSAGE not in error,
    )

    # ---------- 反向对照：错配 dorm_order 必须仍抛 ConfigError ----------
    print(f"\n[2] 反向对照：dorm_order = {MISMATCH_DORM_ORDER!r}（错配）")
    try:
        config.conf.dorm_order = MISMATCH_DORM_ORDER
        with no_save_conf():
            plan = build_global_plan()
            plan["backup_plans"] = []
            state_rev, error_rev = _load_state(plan)
    finally:
        config.conf.dorm_order = original_dorm_order
    print(f"    抛错信息 = {error_rev!r}")
    print(f"    已还原 dorm_order = {config.conf.dorm_order!r}")

    record("反向对照仍抛错", state_rev is None and error_rev is not None)
    record(
        "反向对照错误信息含宿舍优先级不匹配",
        error_rev is not None and MISMATCH_MESSAGE in error_rev,
    )

    # ---------- 证伪对照：复现 C5 修复前分支 ----------
    print("\n[3] 证伪对照：复现 C5 修复前分支（backup_plans 为空时不 swap_plan）")
    with no_save_conf():
        plan = build_global_plan()
        plan["backup_plans"] = []
        state_fix, error_fix = _load_state(plan, _make_pre_fix_state_class())
    print(f"    抛错信息 = {error_fix!r}")

    record("修复前分支确实抛错（判据可证伪）", state_fix is None)
    record(
        "修复前分支错误信息含宿舍优先级不匹配",
        error_fix is not None and MISMATCH_MESSAGE in error_fix,
    )

    # ---------- 证伪对照：dorm_order == "" 时守卫确实拦住一次写入 ----------
    print("\n[4] 证伪对照：dorm_order = '' 时是否真的会写 conf.yml")
    try:
        config.conf.dorm_order = ""
        with no_save_conf() as save_calls:
            plan = build_global_plan()
            plan["backup_plans"] = []
            state_empty, error_empty = _load_state(plan)
            empty_calls = len(save_calls)
            written_value = config.conf.dorm_order
    finally:
        config.conf.dorm_order = original_dorm_order
    print(f"    抛错信息 = {error_empty!r}")
    print(f"    save_conf 被拦截次数 = {empty_calls}")
    print(f"    分支写回的 dorm_order = {written_value!r}")

    record("空 dorm_order 分支构造成功", state_empty is not None)
    record("空 dorm_order 分支确实命中 save_conf（守卫必要）", empty_calls > 0)

    # ---------- 只读保证：conf.yml 未被写 ----------
    after_sha = sha256_file(conf_path)
    print(f"\n[5] conf.yml 运行后 SHA256 = {after_sha}")
    record("conf.yml SHA256 未变", before_sha == after_sha)

    # ---------- 内存还原确认 ----------
    record("dorm_order 已还原", config.conf.dorm_order == original_dorm_order)

    passed = sum(1 for _, ok in results if ok)
    print(f"\n[T1.2] {passed}/{len(results)} 项通过")
    return passed == len(results)


def main() -> int:
    parser = argparse.ArgumentParser(description="T1.2 C5 回归（零点击）")
    parser.add_argument("--seconds", type=int, default=120, help="墙钟上限（秒）")
    args = parser.parse_args()

    from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController

    pause = ThreadPauseController()
    clock = WallClockStop(args.seconds, on_timeout=pause.request_stop).start()
    quiet_logs()

    ok = False
    try:
        ok = run_checks()
    except KeyboardInterrupt:
        print("\n    Ctrl+C，正在停止...")
    finally:
        clock.cancel()
        pause.request_stop()

    if clock.timed_out:
        print(f"\n[FAIL] 达到墙钟上限 {args.seconds}s")
        return 1
    print("\n[OK] T1.2 全部通过" if ok else "\n[FAIL] T1.2 存在未通过项")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
