# Mower 文档导航

从当前任务选择入口，再沿链接阅读负责该行为的文档。完整规则放在所属子系统说明；操作步骤和历史原因各有自己的位置。

| 当前任务 | 阅读入口 |
| :--- | :--- |
| 了解系统和查找实现、测试 | [系统架构与任务入口](architecture.md#2-find-the-implementation-and-verification)、[后端源码地图](../arknights_mower/README.md) |
| 设备绑定、准备、截图、输入或恢复 | [设备控制规范](subsystems/device-control.md)、[设备故障排查](cookbook/device-troubleshooting.md) |
| 基建排班、心情、宿舍或换班状态 | [基建调度规范](subsystems/base-scheduler.md)、[solver 导航](../arknights_mower/solvers/README.md) |
| 其他功能边界 | [子系统说明目录](subsystems/) |
| 开发与排查步骤 | [操作手册目录](cookbook/) |
| 理解历史故障与修复理由 | [事故复盘目录](postmortem/)；从所属子系统说明的直接链接追踪相关决策 |
| 创建、修改或迁移决策记录 | [Agent Note 归属与生命周期模板](../.agents/notes/README.md) |

文档修改遵守本目录的 [AGENTS.md](AGENTS.md)。概念定义查阅 [CONTEXT.md](../CONTEXT.md)；定义、行为规则和操作步骤的归属见[放置规则](../.agents/skills/mower-doc/references/doc-hierarchy.md#routing-rules)。
