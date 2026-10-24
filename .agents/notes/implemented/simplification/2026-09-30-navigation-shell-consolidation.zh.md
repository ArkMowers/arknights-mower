---
format: decision
title: 导航外壳合并
status: implemented
category: simplification
date: 2026-09-30
---

# 导航外壳合并

[English](2026-09-30-navigation-shell-consolidation.md)

## 问题

合并前的 `App.vue` 将导航定义了三遍：桌面端 `n-menu` 选项树、移动端八个标签的底栏，以及设置与数据图表两个移动端选择弹窗。同一路由在各份副本中的名称不一致，移动端副本缺少 `/BasementSkill` 与两个外部参考链接。

- **调用方计数**：`provide('sidebar_collapsed')` 没有任何注入方；`handleMenuClick` 只处理 `chatbot` 一个键，其余菜单键全部忽略。
- **重复控件**：无边框窗口的折叠热区与侧栏自带触发器重复，遮挡侧栏滚动条，且无法通过键盘操作。
- **无用导入**：十七个图标导入以及 `renderIcon`、`h`、`RouterLink` 仅用于构建这些副本。
- **错误属性**：外部链接写为 `rel="noopenner noreferrer"`，浏览器会忽略拼错的值。
- **目标源码位置**：`ui/src/App.vue`

---

## 后果

- **关联不变式**：`[INV-UI-04] Single Navigation Definition` 取代上述三份副本。
- **等价性保证**：路由记录、`ui/public/frontend-routes.json` 与持久化配置均保持不变。两种布局下所有页面仍可到达；移动端布局额外可以到达 `/BasementSkill` 与外部参考链接。旧版移动端标签(日志、设置弹窗、排班、自动专精、数据图表弹窗、帮助、资源、Mower AI 助手)变为四个标签(日志、排班、养成、设置)加一个更多抽屉列出剩余项。设置标签直接路由至 `/mowersettings` 而非打开弹窗。可折叠子菜单(全部设置、数据图表)变为始终展开的分组标题(设置、数据、资料)。浏览器模式下手动折叠现在会停止自动折叠；旧版 show-trigger 事件从未设置 `userToggledSidebar`。

---

## 决策

1. 将分组、名称、图标与移动端标签子集移入 [navigation.js](../../../../ui/src/navigation.js)。
2. 桌面侧栏与移动端页面抽屉由 `ui/src/components/AppSidebar.vue` 渲染，移动端底栏由 `ui/src/components/MobileTabBar.vue` 渲染。
3. 从 `App.vue` 删除选项树、`renderIcon`、`handleMenuClick`、两个选择弹窗、折叠热区及其 CSS、无用的折叠布局类、无注入方的 provide 与无用导入。

---

## 考虑过的替代方案

保留三份导航定义会保留上述名称、页面覆盖和折叠控件问题；原记录未记载其他方案的独立比较。

## 验证

原记录列出以下检查项，未在本记录中报告其执行结果。

- 目标轻量测试：`npm test -- src/navigation.test.js src/components/NavigationShell.test.js src/composables/useCollapsedTips.test.js src/routes.test.js src/theme/mower.test.js`
- 治理门禁验证：`python scripts/verify_governance.py`

[导航侧栏说明](../feature/2026-09-30-navigation-sidebar.zh.md) 定义了合并后的布局规则。
