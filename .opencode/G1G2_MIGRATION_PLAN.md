# G1+G2 迁移计划（精简版）

## 实际缺口

- `build_global_plan()` 产出旧 `utils/plan.py` 对象 → `SchedulerState` 里存的还是旧 Room
- `init_and_validate()` 未调用 → `state.operators/groups/dormitories` 全空

## 改动范围

**只改一个文件**: `scheduler/state.py`

### 1. 旧→新 Plan 转换 (纯计算，放 `SchedulerState`)

```python
def _from_old_plan(self) -> None:
    """把 self._global_plan 里的旧 Plan/Room/PlanConfig 转为新 domain dataclass"""
```

对 `default_plan` 和每个 `backup_plan`:
- 旧 `Room` → 新 `Room` dataclass（字段一一映射）
- 旧 `PlanConfig` → 新 `PlanConfig` dataclass（list 字段直接赋值）
- 旧 `Plan` → 新 `Plan` dataclass（trigger 从 LogicExpression 取 str 表达）
- 更新 `self.plan` / `self.config` / `self._backup_plans`

### 2. init_and_validate 直接写在 `SchedulerState` 里（也放 `state.py`）

- 遍历 `self.plan` 创建 `Operator` → `self.operators`
- 校验规则（干员名、Free/宿舍约束、重复、替换组等）
- 构建 `self.groups`、`self.dormitories`
- 心情阈值初始化
- 跑单房间识别

### 3. 补充 `SchedulerState` 缺失字段

`exhaust_agent`, `exhaust_group`, `workaholic_agent`, `run_order_rooms`, `power_plant_count`, `true_exhaust_room`

### 4. `__init__` 末尾调用

```python
self._from_old_plan()
error = self._init_and_validate()
if error:
    raise ConfigError(error)
```

## 不新建文件

| 原来 | 现在 |
|---|---|
| `新建 operator_service.py` | 不建，逻辑放 `SchedulerState` 内部 |

## 不改

- `utils/plan.py`
- `utils/operators.py`
- 其他 scheduler 文件
