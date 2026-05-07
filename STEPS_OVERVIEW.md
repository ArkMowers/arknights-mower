# 7 步重构总览

## 依赖关系图

```
Step 1: Architecture Redesign
  ├── Step 2: Graph / Navigation
  │     └── Step 3: Recognition 简化
  │           └── Step 4: Business Logic Migration
  │                 └── Step 5: Full Chain
  │                       └── Step 7: Android
  └── Step 6: Copilot (可与 Step 3-4 并行)
```

## 时间线

| 周 | Step | 里程碑 |
|----|------|--------|
| 1 | 1 | 领域骨架就绪, DevicePort 可 import |
| 1-2 | 2 | SceneGraph + Navigator 完成, 能导航到任意页面 |
| 2-3 | 3 | recognize.py 砍到 ~500 行, 只剩 template_matching |
| 3-7 | 4 | 所有 Executor/Planner 迁移完毕, 每步截图回放验证 |
| 4-5 | 6 | Copilot 独立完成 (与 Step 4 并行) |
| 7-8 | 5 | MainLoop + Hooks + Services + Database 联调 |
| 8-9 | 7 | Android Chaquopy 打包 + Google Store 提审 |

## 验证策略

| Step | 验证方式 |
|------|----------|
| 1 | pytest 单元测试 + 手动 import 各模块 |
| 2 | 截图回放: 旧 graph vs 新 Navigator, 输出相同 tap 序列 |
| 3 | 全场景回归: 180 个 find() 调用, 匹配结果一致 |
| 4 | 每个 Executor 独立跑通完整流程 |
| 5 | 全链路端到端 (mock device) |
| 6 | JSON 战斗计划重放, 输出指令序列一致 |
| 7 | Android 真机 (MediaProjection + AccessibilityService) 跑通基建 |

## 跨步骤注意事项

- 所有新代码只依赖 `scheduler/device_port.py` 的 `DevicePort` 抽象, 不依赖 `utils/device/Device`
- Step 3 不要在 Step 4 进行中做, 避免连锁回归
- Step 6 可与 Step 3-4 并行开发, 最后 Step 5 合并
