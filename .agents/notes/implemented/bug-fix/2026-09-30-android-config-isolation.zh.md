---
title: Android 配置隔离
status: implemented
category: bug-fix
date: 2026-09-30
---

# Android 配置隔离

## 契约

[INV-DEV-12] Android Configuration Ownership 要求 Android 托管的连接、截图、输入、原生外观、截图历史和服务端点设置在载入、导入、部分更新及保存回读时保持权威。桌面 Device Profile 的值不能覆盖这些设置。用户的游戏服务器和通用任务设置保持可编辑。

## 边界与简化

`Conf.migrate_legacy_keys` 复用已安装 Android 适配层的 `normalize` 契约，在配置校验前移除传入的桌面 Device Profile。`Conf.migrate_device_profile` 从已校验的原生字段派生 Device Profile，保留服务器字段的类型转换。`Conf.updated` 将 Android 编辑交回同一构造入口，不先执行桌面实例绑定校验。不引入第二套平台设置注册表、发现适配层或恢复循环。现有 Android 适配层无需更新配置结构。

显式 `package_type` 选择服务器。仅含配置档的导入在旧服务器字段缺失时保留受支持的 `game_package`。通用设置不被整套平台默认配置替换。

`config_backup._validate_configuration` 在序列化前使用已校验的 Android 配置覆盖导入配置。导入落盘和后续导出保存原生设置与规范的 Device Profile，不在磁盘中残留桌面值。主排班与备用排班、周计划和通用任务设置保持可编辑，支持导出再导入的完整往返。未知备份字段保持保留，桌面备份的序列化行为不变。

## 验证

离线测试固定旧 Android 配置归一化契约，覆盖桌面配置档导入、格式异常的桌面专属字段、部分更新、原生设置、游戏服务器选择、通用任务设置、导入导出、保存回读和未改变的桌面行为。独立兼容性检查组合当前 Android 适配层与更新后的主仓库，不连接设备。
