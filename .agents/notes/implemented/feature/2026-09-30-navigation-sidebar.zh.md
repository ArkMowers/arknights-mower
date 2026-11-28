---
format: decision
title: 导航侧栏
status: implemented
category: feature
date: 2026-09-30
---

# 导航侧栏

[English](2026-09-30-navigation-sidebar.md)

## 问题

桌面与移动端分别定义导航，页面覆盖和名称容易不一致；折叠控件还可能遮挡列表滚动条。

## 决策

当前导航规则由[前端指令](../../../../ui/AGENTS.md#2-navigation-shell)维护，定义位于 [navigation.js](../../../../ui/src/navigation.js)。

[INV-UI-04] Single Navigation Definition：桌面侧栏、移动端底栏与移动端页面抽屉均由 `ui/src/navigation.js` 渲染。该定义恰好列出每个正式页面路由一次；仅开发环境可用的任务编排原型不列入正式导航。内部条目解析到已注册路由；外部条目使用规范的 https 地址，在新标签页打开且不授予 opener 访问权。

## 最初布局

本节记录最初布局。当前品牌区域、折叠控件、已保存的页面位置与移动端入口遵循 [Arknights Mower Web 访问子系统说明中的侧栏布局规则](../../../../docs/subsystems/web-access.md#sidebar-layout-and-editing)及[前端导航规则](../../../../ui/AGENTS.md#2-navigation-shell)；统一导航定义的选择继续保留。

侧栏为纵向结构：可滚动的分组列表位于固定底部区之上。底部区放置 Mower AI 助手入口与折叠控件，列表滚动条不会与任何控件重叠。折叠控件是带 `aria-expanded` 与 `aria-controls` 的按钮，在无边框窗口与普通浏览器中行为一致。

折叠时图标列位置不变，名称淡出。折叠状态下的条目在悬停或键盘聚焦时以提示框显示名称。分组标题变为等高分隔线，条目不会移位。当前条目由路由匹配得出（`aria-current="page"`），不依赖存储的选中状态。

宽度小于 680px 时，底栏列出四个常用页面与「更多」按钮。「更多」打开包含完整侧栏的抽屉，并在当前页面不在底栏中时保持高亮。水印只覆盖内容区。折叠状态不持久化；宽度小于 850px 时自动折叠，直到用户手动切换。

## 考虑过的替代方案

已移除的重复导航定义与折叠控件见[导航外壳合并记录](../simplification/2026-09-30-navigation-shell-consolidation.zh.md)。

## 后果

统一定义使正式页面在两种布局中都可访问。移动端访问非常用页面需要打开更多抽屉，折叠状态仍只在当前界面生效。

## 验证

以下为原记录报告的验证结果。

`ui/src/navigation.test.js` 覆盖路由完整性、条目唯一性、外部地址格式、移动端标签子集与「更多」高亮。`ui/src/components/NavigationShell.test.js` 在真实路由表下渲染两个组件，检查每个条目恰有一个链接、外部链接属性、唯一的当前条目、分组标注与折叠控件状态，并检查每个图标都渲染出 svg；[图标以 ES 模块导入说明](../bug-fix/2026-09-30-vicons-esm-imports.zh.md) 记录了图标从 `es/` 文件导入的原因。浏览器预览覆盖两种主题、无边框窗口与普通浏览器模式以及移动端宽度。[合并说明](../simplification/2026-09-30-navigation-shell-consolidation.zh.md) 记录了被移除的副本。
