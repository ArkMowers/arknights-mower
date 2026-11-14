---
title: Windows Desktop Elevation
status: archived
category: feature
date: 2026-10-11
---

# Windows 桌面程序提权

[English](2026-10-11-windows-desktop-elevation.md)

此历史决定由 [Windows 桌面程序继承启动者权限](../../implemented/feature/2026-10-16-windows-desktop-launcher-permissions.zh.md)取代：强制提权使没有管理员凭据的用户无法启动 Mower。下文保留原实现的理由与验证记录。

简化审查确认 Windows PyInstaller 包含两个可执行文件，`Api.start` 已直接创建实例进程。原生可执行文件清单提供启动授权，不增加重新启动辅助函数、逐实例的 Shell 提权或持久化权限设置。已有决策未覆盖此提权策略。领域概念的含义保持不变，无须修改术语表。

[INV-UPD-08] 要求两个打包桌面程序均在启动前取得管理员权限。已提权管理器沿用现有 `Popen` 路径启动实例，子进程继承其进程令牌。取消 UAC 授权时程序不启动；提权不绕过文件 ACL，也不修复缺失或损坏的资源。源码部署保持 Python 进程的权限。

旧更新器无法从普通权限令牌创建新的提权进程。首次升级因此须从已提权的旧版执行，或手动安装完整包；当时的软件更新子系统说明与打包步骤明确记载此迁移限制。

[Arknights Mower 软件更新子系统说明](../../../../docs/subsystems/software-update.md#14-windows-desktop-elevation)现在定义替代后的启动行为。原有离线测试检查两个可执行文件声明及管理器启动参数。Windows 发布流程在打包前检查实际生成的清单；交互式 UAC 和原生令牌继承仍需 Windows 验证。

规范轴与需求轴审查确认两个 Windows 入口采用相同的原生提权策略，已有管理器启动保留参数、工作目录与实例管理环境。发布工作流及管理器定向测试通过。清单检查接受管理员清单，拒绝清单缺失、执行权限声明缺失及任一可执行文件请求普通权限。结构治理通过；macOS 开发环境未提供原生构建和 Windows 交互验证证据。
