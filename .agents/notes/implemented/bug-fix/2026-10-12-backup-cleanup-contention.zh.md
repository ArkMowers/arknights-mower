---
title: 备份清理锁竞争
status: implemented
category: bug-fix
date: 2026-10-12
---

# 备份清理锁竞争

## 决策

启动清理共享安装范围内的非阻塞锁。维护竞争属于正常跳过本轮，更新提交仍向调用方报告锁占用。[INV-UPD-10] 在[软件更新契约](../../../../docs/subsystems/software-update.md#16-backup-cleanup-contention)中注册这一区分。

`LockBusyError` 保持更新调用方的 `ValueError` 兼容性，并区分原生锁竞争与其他获取失败。清理仅在获取锁时捕获该异常，待清理记录保留供后续启动重试。

## 简化与概念影响

调用方审查覆盖运行时启动、已验证更新器清理及更新提交。现有锁和清理循环继续负责协调与删除，不新增协调器、重试循环、依赖或持久化字段。既有决策三件套没有维护锁竞争的记录。排班、设备和配置概念保持不变，词汇表无需修改。

## 验证

`pytest -q arknights_mower/tests/update_runtime_tests.py arknights_mower/tests/update_backup_tests.py arknights_mower/tests/software_update_tests.py arknights_mower/tests/verify_governance_tests.py` 在 macOS 上通过，结果为 143 passed、3 个平台相关跳过。测试使用真实竞争进程，覆盖应用诊断与复制出的独立更新器、待清理记录保持不变、释放锁后清理、模拟 POSIX 与 Windows 锁错误，以及执行体异常后释放锁。既有测试覆盖已验证备份、删除被拒、文件被替换、无关数据及更新提交兼容性。本地尚未验证 Windows 原生执行。

Ruff 检查与 `python scripts/verify_governance.py` 通过。治理检查报告两项未改变的归档引用兼容警告。

## 规范轴审查

通过：保留现有非阻塞锁及确定释放行为，清理保留原始文件系统失败与现有应用日志注入或独立输出。领域概念与持久化格式保持不变。

## 需求轴审查

通过：仅获取锁时的竞争静默结束；跳过的进程保留备份与记录，后续进程在释放锁后完成清理。既有重启验证、路径和身份保护继续生效。
