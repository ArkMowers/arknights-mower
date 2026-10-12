---
title: MAA 活动导航与作战提交确认
status: implemented
category: bug-fix
date: 2026-10-12
---

# MAA 活动导航与作战提交确认

桌面活动导航写入 `cache/resource/tasks/tasks.json`。MAA 递归加载任务目录；`resource/tasks/` 存在时，忽略同层旧式 `resource/tasks.json`。MaaResource 的 OCR 热修复目录触发该优先规则，目录外的导航因此无法到达核心。导航文件与热修复定义共存，不复制安装目录的任务文件，也不改写其他缓存资源。

简化检查复用 `update_maa_navigation`、其原子 JSON 写入器和现有提交检查。下载导航必须是非空映射，且每个任务定义都是对象；下载、校验或写入失败保留旧文件。Android 保留组件打包和桥接加载使用的原有导航路径。不新增更新器类、资源层或持久化配置。[INV-MAA-08] 约束资源加载和任务提交。

离线测试在已有 OCR 热修复目录时复现目录优先规则和重复任务名拒绝规则。现有提交测试覆盖下载无效、写入失败、Android 加载，以及资源加载、任务提交和启动被拒绝。[MAA 集成契约](../../../../docs/subsystems/maa-integration.md) 是运行行为的权威位置。
