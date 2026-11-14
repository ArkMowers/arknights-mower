---
format: decision
title: 抽屉与提示的减弱动效
status: implemented
category: feature
date: 2026-10-01
---

# 抽屉与提示的减弱动效

## 问题

若不覆盖运行时样式，Drawer 与 Tooltip 在用户选择减弱动效后仍执行过渡。

## 决策

样式位于 [mower.css](../../../../ui/src/theme/mower.css)。

在 `prefers-reduced-motion: reduce` 下，naive-ui 的 Drawer 面板、其遮罩与 Tooltip 跳过进入和离开过渡，直接落到结束状态。`ui/src/theme/mower.css` 对它们的 `*-transition-enter-active` 与 `*-transition-leave-active` 类设置 `transition: none !important`。过渡时长为零时，Vue 的 `<Transition>` 在下一帧结束，并照常触发 `after-enter` 与 `after-leave`，Drawer 的焦点陷阱与卸载走正常路径。

## 边界

naive-ui 在运行时把组件样式插到 `mower.css` 之后，同等优先级的规则会被覆盖。`!important` 覆盖 Drawer 滑动与 Tooltip 缩放过渡。遮罩的 `fade-in` 过渡本身带 `!important`，因此其选择器加上 `.n-drawer-container >` 父级，以优先级取胜。两个组件都 teleport 到 `body`，选择器不带 `.provider` 前缀。其他浮层（Modal、Popover、Dropdown、Message）保留各自的过渡。

## 考虑过的替代方案

同等优先级的覆盖规则会被 naive-ui 后插入的样式取代。所选选择器与优先级规则处理这一已观察到的顺序问题。

## 后果

覆盖规则依赖 naive-ui 的过渡类名，仅影响 Drawer 与 Tooltip；其他浮层保留原有过渡。

## 验证

以下为原记录报告的验证结果。

在开发服务器上用无头 Chrome 模拟 `prefers-reduced-motion`，移动端页面抽屉与折叠侧栏的提示在 `enter-active` 期间计算出的 `transition` 为 `none`，并在一帧内到达 `translateX(0)` 与 `scale(1)`、不透明度 1。未开启该偏好时，二者保留 0.3 s 滑动、0.2 s 遮罩淡入与 0.15 s 缩放。
