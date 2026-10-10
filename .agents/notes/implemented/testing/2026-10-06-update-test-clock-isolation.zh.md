---
title: Update Test Clock Isolation
status: implemented
category: testing
date: 2026-10-06
---

# Update Test Clock Isolation

更新兼容性测试仅替换被测模块的时钟引用。其他线程继续使用标准库时间函数；清理重试和到期断言仅统计被测模块调用。永久占用用例在替换范围内包含一次无关标准库休眠调用。
