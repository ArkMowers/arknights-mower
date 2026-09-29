---
title: ${TITLE_ZH}
status: proposed
category: simplification
date: ${DATE}
---

# ${TITLE_ZH}

## 1. 背景与过度设计分析
说明在 `arknights_mower` 或 `ui` 中定位到的过度设计目标。
阐述其属于单一调用点包装类、投机性泛化抽象还是历史废弃兼容代码。

- **调用方计数**：${CALLER_COUNT}（经 grep/AST 校验）
- **目标源码位置**：`arknights_mower/...`

---

## 2. 不变式与安全评估
- **关联不变式**：引用涉及的不变式（`[INV-01]` 至 `[INV-06]`）。
- **等价性保证**：论述移除或内联该模块为何不会破坏对外契约与用户持久化配置。

---

## 3. 简化步骤
1. 从 `${TARGET_FILE}` 中移除 `${TARGET_SYMBOL}`。
2. 将核心逻辑直接内联至唯一调用处。
3. 清理已无实际意义的孤立单元测试或更新 Mock。

---

## 4. 验证方案
- 目标轻量测试：`pytest arknights_mower/tests/...`
- 治理门禁验证：`python scripts/verify_governance.py`
