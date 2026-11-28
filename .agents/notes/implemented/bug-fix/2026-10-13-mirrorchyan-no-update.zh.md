---
format: decision
title: Mirror酱无需更新结果
status: implemented
category: bug-fix
date: 2026-10-13
---

# Mirror酱无需更新结果

[English](2026-10-13-mirrorchyan-no-update.md)

## 问题

提交的已安装版本为最新版时，Mirror酱可能成功返回版本号且不提供下载地址。原更新器在比较版本前要求下载地址，因此把有效结果误报为下载信息不完整。[Mirror酱集成指南](https://github.com/MirrorChyan/docs#响应数据结构)定义响应字段。

## 决策

更新器完成服务错误与 CDK 过期检查后，先比较版本，再要求下载资源。`MaaRelease.runtime` 允许为空，使现有元数据传递路径可以表示无需更新。检查接口不返回检查标识，安装器返回 `updated=false`，后台任务提示无需更新并保留已加载核心。[MAA 集成子系统说明](../../../../docs/subsystems/maa-integration.md#mirrorchyan-no-update)定义行为规则与接口结果。

## 考虑过的替代方案

响应已提供比较所需的版本号，因此无需第二次请求。虚构下载地址会错误表示安装包存在。新增异常分支会把成功的协议结果转入错误处理；现有发布元数据可以直接传递这一结果。

## 后果

无需更新时保留安装目录、备份与已加载核心。新版本和首次安装仍要求有效的 HTTPS 下载地址，CDK 错误仍报错。调用方须接受无需更新元数据中的空运行库安装包。本修复不恢复此前损坏的资源缓存，也不改变术语定义。

## 验证

离线[更新测试](../../../../arknights_mower/tests/maa_update_tests.py)与[接口测试](../../../../arknights_mower/tests/maa_update_route_tests.py)共 76 项通过，1 项 Windows 模块查询测试在 macOS 上跳过。测试覆盖同版本及较旧版本不带下载地址、新版本及首次安装缺少地址、CDK 拒绝、保留安装目录与备份、检查结果及后台任务行为。治理单元测试共 80 项通过，Ruff 检查通过。未执行 Windows GUI 操作与真实 CDK 下载。
