---
title: 共享基建技能数据
status: implemented
category: simplification
date: 2026-10-09
---

# 共享基建技能数据

## 契约

[INV-UPD-07] Shared Skill Data Packaging 将受版本管理的目录数据放在 `arknights_mower/data/building_skill.json`。后端调用方与前端导入共用此数据源。后端读取不依赖前端源码或 WebUI 构建。应用打包随后端数据收集该文件，发布前拒绝缺失或为空的必需数据。

## 边界与简化

`dorm_skills._skill_index` 与 `building_skills.skill_index` 调用 `resource_pkg_path`，不再拼接前端源码路径。前端导入共享数据源，HTTP 路由保持现有文件名。桌面打包移除独立的前端源码收集项，因为正常的后端数据收集已包含目录数据。Android 使用同一目录收集机制。

资源包保留历史目录数据条目，兼容已有客户端与现有发布器。`write_building_skill_data` 只序列化一次，将相同字节写入权威数据源与被忽略的兼容导出。兼容导出是生成的发布输入，不是第二份受版本管理的数据源，也不是应用打包输入。`resource_pkg_path` 仅对所选资源包转换权威路径请求，保持整代资源隔离与缓存失效机制。

目录数据移动后保持历史资源哈希标识，干净检出无需生成兼容文件即可匹配内置版本标记。

目录数据也通过[资源重建边界](../../../../docs/subsystems/resource-update.md#1-resource-ota) 提供 OTA 未变更的起点文件。该调用方保留历史归档标识，同时读取随安装包分发的共享数据源。

[软件更新契约](../../../../docs/subsystems/software-update.md#12-shared-building-skill-data) 定义权威行为。排班规则、配置结构与领域术语保持不变。

## 验证

定向离线测试覆盖生成输出一致性、资源内容哈希、没有任何前端文件时的两个后端调用方、桌面与 Android 应用包内容、缺失或空目录数据拒绝、现有 HTTP 文件名、所选历史资源包优先级与缓存失效。前端生产构建验证共享导入。

干净检出回归在修复前复现资源哈希遗漏目录数据的问题，修复后验证有无兼容导出时哈希一致、LF/CRLF 归一化及内容变更检测。既有内置版本哈希断言通过，`version.json` 保持原文。

OTA 回归在修复前复现安装包起点文件遗漏，修复后从真实桌面数据收集结果与 Android 归档验证完整重建和离线手动安装，目录中没有前端源码。[OTA 决策](../architecture/2026-10-09-resource-ota.md) 记录测试目录与回滚证据。
