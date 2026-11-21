---
title: Cache Save Log Visibility
status: implemented
category: bug-fix
date: 2026-10-03
---

# 缓存保存日志显示

缓存保存成功使用 DEBUG，现有 INFO 级别的 WebHandler 不向用户日志显示该记录。诊断文件继续保留记录。SQLite 失败仍按 [INV-DIAG-06] 使用 ERROR。

简化：复用现有处理器级别，不增加过滤器、设置或持久化行为。验证与双轴审查：保存结果和事务不变；核验处理器级别、Ruff 与治理检查，确认仅修改日志级别。不新增重复验证现有日志配置的单元测试。
