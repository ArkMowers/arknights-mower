# Step 1-7 重构: 未完成项目

## Step 3: Recognition 拆分 (部分完成)

已完成:
- `utils/recognize/` package 结构
- `utils/recognize/constants.py` — COLOR, TEMPLATE_MATCHING, TEMPLATE_MATCHING_SCORE, FEATURE_MATCH_RES
- `utils/recognize/__init__.py` — 不再内联 dict, 从 constants.py 导入
- Old `utils/recognize.py` → bridge import

待完成:
- `utils/recognize/find_color.py` — color 匹配独立 class
- `utils/recognize/find_template.py` — template_matching 独立 class
- `utils/recognize/find_feature.py` — ORB+SVM 独立 class
- `utils/recognize/scene.py` — get_scene() 场景表
- 全场景回归测试 (新旧 find() 结果一致)

## Step 4: Business Logic Migration (仅框架)

创建了所有 executor/planner 文件骨架, 但均为 NotImplementedError:
- 8 个 executor: clue, correction, fiammetta, workshop, skill, run_order, exhaust, shift
- 9 个 planner: idle, shift, order, fiammetta, workshop, exhaust, skill, clue, backup

待完成 (从 `solvers/base_schedule.py` 4474 行中逐条迁移):
- 每个 executor 的具体业务逻辑
- 每个 planner 的规划逻辑
- AgentSelectionFSM 状态机 (8 状态)
- RoomManager UI 原语
- MoodScanner
- 截图回放验证每个 executor

## Step 5: Full Chain (仅框架)

创建了 MainLoop skeleton, 待:
- loop.py 主循环逻辑 (从 `__main__.py:simulate()` 迁)
- hooks.py LifecycleHook 链实现
- database/ 完整持久化层 (repository 模式)
- services/ 外部集成 (MAA, 每日任务, 仓库扫描)
- `__main__.py` 瘦身到 ~50 行

## Step 6: Copilot (仅框架)

创建了 copilot/__init__.py + combat_plan.py stub, 待完整实现:
- combat_plan.py — CombatPlan/Stage/Group/Action 数据类
- loader.py — MAA JSON 作战计划加载
- executor.py — 指令执行主循环
- battle_state.py — 战场状态追踪
- deployer.py — 部署/撤退操作
- skill_mgr.py — 技能管理
- tile.py — Tile 坐标转换
- 战斗截图识别 (复用 utils/recognize)

参考: F:\Git\MaaAssistantArknights (MAA copilot JSON format)

## Step 7: Android (仅规划, 无代码)

待实现:
- android/ Kotlin app (MediaProjection + AccessibilityService)
- Chaquopy Python integration
- utils/device/screencap/android.py
- utils/device/control/android.py
- utils/device/app/android.py

参考: https://github.com/Fate-Grand-Automata/FGA (同技术栈)
- OpenCV for image recognition
- MediaProjection for screenshots
- AccessibilityService for tapping
- Kotlin-based native Android app
