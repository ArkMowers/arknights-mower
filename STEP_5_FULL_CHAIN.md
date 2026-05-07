# Step 5: Full Chain

> 估算: 5 天
> 依赖: Step 4 完成 (Executor/Planner 就绪)

## 目标

把全部新组件连起来: MainLoop 驱动, Hook 链处理外围任务, Services 处理外部集成, Database 替换旧 record.py。

## 交付物

```
scheduler/
├── loop.py               # MainLoop (替代旧 simulate())
├── hooks.py              # LifecycleHook 链

database/
├── core.py               # DatabaseEngine (单例连接池)
├── migration.py          # 迁移系统
├── errors.py             # 数据库异常
└── repositories/         # repository 模式
    ├── base.py
    ├── agent_action.py
    ├── saved_state.py
    └── ...

services/
├── maa_client.py         # MAA 连接 + 任务提交
├── maa_planner.py        # MAA 日常计划
├── daily.py              # 每日任务 (mail/report/visit/skland)
└── depot.py              # 仓库扫描
```

## MainLoop

```python
class MainLoop:
    def __init__(self, state, dispatch, planners, hooks, navigator):
        ...

    def run_forever(self):
        while True:
            self._run_hooks()           # 维护/每日/仓库扫描等
            self._run_planners()        # Planner 观察状态 → 插入任务
            task = self.state.queue.peek()
            if task is None:
                self._idle_cycle()
                continue
            # safe_execute 捕获异常, 失败只记录不崩溃
            self.dispatch.execute(task, self._device)
            self.state.queue.pop()      # 无论成功失败都 pop
```

## Hook 链

| Hook | 触发条件 | 替换自 |
|---|---|---|
| MaintenanceCheckHook | 每次循环 | `__main__.py` 维护检测 |
| DailyTaskHook | 每天首次 | `__main__.py` 每日任务 |
| DepotScanHook | config 定时 | `__main__.py` 仓库扫描 |
| ReclamationHook | 启用时 | `__main__.py` 生息演算 |
| SecretFrontHook | 启用时 | `__main__.py` 隐秘战线 |
| IdleSleepHook | 空闲 > 阈值 | `__main__.py` 休眠逻辑 |
| UpdateCheckHook | config 频率 | `services/updater/` |

## 暂停机制

### 设计

```
PauseController (scheduler/infra/pause_controller.py)
  ├── pause()       → 设置暂停标志
  ├── resume()      → 清除暂停标志
  └── wait_if_paused() → 暂停时阻塞直到 resume

AbstractExecutor.check_pause() → 调用 wait_if_paused(), 供耗时操作周期性检查

TaskDispatch.execute(device, pause_controller) → 传入 PauseController

Server API:
  GET /pause    → pause_controller.pause()   (线程继续运行但阻塞在 check_pause)
  GET /resume   → pause_controller.resume()  (阻塞的线程恢复执行)
```

### 使用流程

```
用户点击暂停 → /pause → PauseController.pause()
  → 当前 executor 的 check_pause() 调用 wait_if_paused() 阻塞
  → 线程不退出, 只是等待

用户点击恢复 → /resume → PauseController.resume()  
  → wait_if_paused() 返回
  → executor 继续执行

用户点击停止 → /stop → 沿用旧 config.stop_mower.set()
  → MowerExit 异常 → 线程完全退出
```

### 与旧 stop 的区别

| | Stop | Pause |
|---|---|---|
| 线程状态 | 退出 | 阻塞等待 |
| 恢复方式 | 重新 start | resume |
| 任务状态 | 丢失 | 从中断点继续 |
| 实现 | `threading.Event` + `MowerExit` | `threading.Event.wait()` 阻塞 |

## 验证

- 全链路端到端 (mock device): MainLoop 完整跑一轮
- `__main__.py` 瘦身到 ~50 行, 只做 DI 组装
- 旧 `simulate()` / `run()` 可切换回退

## 允许的旧代码改动

- `__main__.py` 从 366 行瘦身到 ~50 行
- 旧 `simulate()` 保留为 fallback, 但标记 deprecated
