# Step 6: Copilot 自动作战

> 估算: 7 天
> 可并行: 与 Step 3-4 独立

## 目标

新建自动战斗子系统, 支持读取 JSON 作战计划并执行。

## 交付物

```
scheduler/copilot/
├── __init__.py
├── combat_plan.py         # 数据类 (CombatPlan, Stage, Group, Action)
├── loader.py              # JSON 作战计划加载 + 校验
├── executor.py            # 指令执行主循环
├── battle_state.py        # 战场状态追踪 (费用/部署位/干员状态)
├── deployer.py            # 部署/撤退/技能 操作
├── skill_mgr.py           # 技能自动释放管理
└── tile.py                # Tile 坐标 → 像素坐标转换
```

## 数据流

```
JSON 作战计划 (MAA 格式兼容)
  → loader.load() → CombatPlan
  → executor.execute(plan, device_port)
      → battle_state.update(截图识别)
      → deployer.deploy(tile, operator)
      → skill_mgr.auto_skill(battle_state)
```

## 关键设计

### 战场识别

复用 `utils/recognize.py` 的 template_matching 识别干员头像/费用/技能 CD:

```
截图 → crop 费用区域 → digit_reader 读数字
截图 → crop 部署栏 → matchTemplate 匹配干员头像
截图 → crop 技能栏 → matchTemplate 技能状态 (亮/暗/CD)
```

### 坐标系统

使用战斗 Tile 坐标系 (2D grid), 通过 `tile.py` 映射到 1920×1080 像素坐标:

```python
class TileSystem:
    def __init__(self, stage_name: str):
        # 从 JSON 或 stage config 加载 tile 布局
        self._tiles = load_tile_layout(stage_name)

    def tile_to_pixel(self, tile: tuple[int, int]) -> tuple[float, float]:
        """(row, col) → (x, y) 比例坐标 0~1"""
        ...

    def pixel_to_tile(self, x: float, y: float) -> tuple[int, int]:
        """(x, y) 比例坐标 → (row, col)"""
        ...
```

### MAA 兼容

JSON 作战计划格式尽量与 MAA 的 `resource/copilot/` JSON 文件兼容, 方便社区复用:

```json
{
  "stage_name": "OF-1",
  "actions": [
    {"type": "部署", "group": "先锋", "location": [4, 3], "direction": "向上"},
    {"type": "技能", "group": "先锋", "skill": 2, "wait": 30}
  ]
}
```

## 验证

- 加载现有 MAA 作战计划 JSON → 解析正确
- 截图回放: JSON 计划 → 期望 tap 序列 vs 实际 tap 序列
- 简单关卡 (OF-1 / 1-7) 手动测试通过

## 允许的旧代码改动

- 无。纯新建模块。
