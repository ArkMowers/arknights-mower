---
format: decision
title: 图标以 ES 模块导入
status: implemented
category: bug-fix
date: 2026-09-30
---

# 图标以 ES 模块导入

## 问题

CommonJS 单图标导入在 Vite 8 开发服务器中显示为空白，生产构建却能正确渲染。

## 决策

受影响的管理器入口为 [MowerManager.vue](../../../../ui/manager/MowerManager.vue)。

前端的每个 `@vicons` 图标都从包内 `es/` 目录导入：`@vicons/<pkg>/es/<Icon>`、`@vicons/<pkg>/es` 汇总入口，或从裸包 `@vicons/<pkg>` 具名导入（其 `module` 字段指向 `es/index.js`）。包根目录与 `lib/` 下的单图标文件是 CommonJS。Vite 8 开发服务器把这类文件的默认导入解析为模块对象而非图标组件，图标因此渲染为空白，并出现 "missing template or render function" 警告。生产构建能正确渲染同样的导入，该缺陷只出现在开发环境。

## 边界

`ui/.eslintrc.cjs` 中的 `no-restricted-imports` 规则拒绝 `es/` 以外的任何 `@vicons/<pkg>/<path>`，同时覆盖 `ui/src` 应用与 `ui/manager` 入口。修复由导入路径承担；Vite 配置保持默认，不添加 `legacy.inconsistentCjsInterop` 或别名。CI 工作流运行 prettier 与 vitest，不运行 ESLint，因此该规则通过 `npm run lint` 与编辑器生效。

## 考虑过的替代方案

修复保留 Vite 默认解析，不添加别名或启用 `legacy.inconsistentCjsInterop`；ES 导入路径直接处理已观察到的模块互操作问题。

## 后果

导入限制覆盖两个 UI 入口，但 Vitest 渲染测试无法发现开发服务器中的此类失败。规则及其开发环境限制如上所述。

## 验证

以下为原记录报告的验证结果。

ESLint 报告本次替换的全部 30 处包根目录单图标导入，并接受 `es/` 单图标导入与两种汇总导入。vitest 会解开 CommonJS 默认导入，渲染测试对两种路径都能通过，无法守护该缺陷。在无后端的开发服务器中，`/`、`/plan-editor`、`/maasettings` 与 `/mowersettings` 在移动端与桌面宽度下的每个 `.n-icon` 都渲染出 svg，且没有 missing template 警告；`ui/manager/MowerManager.vue` 的开发转换结果以普通 ES 模块导入每个图标。[导航侧边栏说明](../feature/2026-09-30-navigation-sidebar.zh.md) 记录了最先出现空白图标的导航外壳。
