---
title: MuMu Pro 手动绑定修复
status: implemented
category: bug-fix
date: 2026-09-30
---

# MuMu Pro 手动绑定修复

[English](2026-09-30-mumu-pro-manual-binding.md) | [中文](2026-09-30-mumu-pro-manual-binding.zh.md)

## 契约

- **[INV-DEV-10] MuMu Pro 手动绑定**：没有已选实例指纹时，`macos.mumu_pro` Device Profile 使用保存的 ADB serial 进行标准预检。目标缺失或不匹配时失败，不采用其他设备。管理工具启动、关闭命令保持不可用。
- 只读检测忽略已保存的安装路径和管理程序路径，因为这些路径不能证明 ADB 目标身份。
- 设备设置界面显示 `last_serial`，已填写 serial 的配置进入预检。用户保存之前，草稿检测不写入配置。
- 手动多开时，ADB serial 是连接依据。实例序号没有经过验证；另一实例日后复用同一 serial 时，仅靠此检测无法区分。[已核验的实例选择](../feature/2026-09-30-mumu-pro-instance-selection.zh.md)提供另一种绑定方式。

## 根因与实现

兼容性预设在 ADB 验证前无条件拒绝预检和会话观察。设置界面隐藏 `last_serial`，并把缺少管理程序路径的配置送到不可用的发现入口。预检和会话现复用精确 serial 检测。旧闲置关机入口拒绝 MuMu Pro 管理命令。[简化审计](../simplification/2026-09-30-reuse-manual-adb-gate.zh.md)记录复用边界。

## 验证

离线测试覆盖已保存和草稿 serial、目标缺失、其他在线设备、会话就绪、HTTP 配置持久化、界面路由和闲置关机防护。[设备契约](../../../../docs/subsystems/device-control.md)规定长期行为。
