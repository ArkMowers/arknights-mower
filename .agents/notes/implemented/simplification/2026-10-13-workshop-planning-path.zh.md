---
format: decision
title: 合成规划路径
status: implemented
category: simplification
date: 2026-10-13
---

# 合成规划路径

配置生成与状态查询共用当前养成投影，执行检查返回结构化阻塞原因。本决策配合[响应调度](../feature/2026-10-13-workshop-responsive-dispatch.zh.md)；[养成规则](../../../../docs/subsystems/growth-planning.md)定义当前行为。

## 问题

两套无正式调用的旧生成器仍被测试直接使用，无法证明当前多项目备料路径的行为。状态接口也需要与真实合成使用同一计算。

## 决策

`calculate_workshop_plan` 调用 `growth_workshop_config`，后者使用按序项目备料和 `next_recipe`。状态查询提供单份库存快照并使用同一投影。入队与诊断共用 `workshop_admission_block`；调人前保留材料和干员检查。提示由结构化结果生成，不解析日志。

仓库调用审计后移除无调用的 `compute_workshop_config`、`compute_default_workshop_config`、`_workshop_lookahead_active` 和 `_workshop_training_reserve`。四个函数合计 348 行源代码，不含导入和测试调整。`_remaining_mastery_materials` 仍被专精调度正式调用，因此保留。不引入第二套规划器、事件历史、工作线程或队列。

## 覆盖与兼容

适用的旧辅助函数测试改为验证真实养成投影和配置路由。直接分配器测试使用显式配方夹具。目标成本、训练预约、材料保护、BOX 数据缺失、专长分配和手动恢复保留覆盖。移除已被替代的单技能前瞻断言；按序多项目测试定义当前规则。间接原料测试循环选择 `next_recipe` 并应用已确认增量，验证精确总产量。

后端定向回归通过 830 项测试，包含迁移后的加工和专精测试。仓库 Python 导入不再引用已删除函数。未发现受移除影响的正式调用方；未记录的外部导入仍是兼容性限制。



## 考虑过的替代方案

保留旧生成器作为测试入口会继续验证另一套算法；将测试改为真实养成投影，使材料预约和路由行为成为直接验证对象。生产仍调用的已付款阶段辅助函数不能随生成器一起删除。

## 后果

配置与状态共用规划路径，测试不再依赖旧生成器。未记录的外部导入可能失效；本次不提供兼容包装，重新引入前需要明确的外部调用证据。
