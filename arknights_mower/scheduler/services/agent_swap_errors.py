"""换班服务的失败信号与队列前置处理。

`AgentSwapError` 是 **BUG-2**（翻页到底静默返回，失败被上报为"成功"）的修复载体。
它必须是一个**普通异常**，原因见类文档 —— 这不是风格选择，而是唯一不死循环的选项。
"""

from __future__ import annotations

from copy import deepcopy


class AgentSwapError(Exception):
    """换班过程中遇到**不可原地重试**的失败（翻页到底 / 超过 `MAX_PAGE`）。

    ⚠️ 为什么不能抛 `StepRetry` / `StepRestart`
    ------------------------------------------
    `AgentSwapService._run_steps` **不是** `AbstractExecutor.run_steps` ——
    它没有 `guard()`，也没有超时兜底。其异常分支的真实后果：

    | 抛出 | 结果 |
    |---|---|
    | `StepRetry` | `continue` → 队列**不推进**（`popleft` 未执行）→ `queue[0]` 仍是同一个 `select` 步骤 → 再抛 → **无限循环，无超时能救** |
    | `StepRestart` | 重置队列 → 重跑 → 同样条件 → **同样无限循环** |
    | **普通异常（本类）** | `except Exception` → `return False` → `ShiftExecutor._do_swap` 抛 `StepRestart` → **外层** `AbstractExecutor.run_steps` 的 `_timeout`（10 分钟）兜底 → `dispatch` 捕获 → `loop.py` 置 `state.error = True` |

    即：**"能上报"与"不死循环"同时成立的唯一路径是普通异常。**
    """


def dedup_agents(agents: list[str]) -> list[str]:
    """把重复出现的定向干员降级为 `Free`（与重构前逐字一致）。

    同名干员在同一房间只能坐一个位置；重复项按"补位候选"处理。
    """
    agents = deepcopy(agents)
    seen: set[str] = set()
    for i, name in enumerate(agents):
        if name in seen and name != "Free":
            agents[i] = "Free"
        seen.add(name)
    return agents
