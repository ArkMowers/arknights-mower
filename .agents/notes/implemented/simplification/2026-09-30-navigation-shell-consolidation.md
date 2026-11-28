---
format: decision
title: Navigation Shell Consolidation
status: implemented
category: simplification
date: 2026-09-30
---

# Navigation Shell Consolidation

[中文](2026-09-30-navigation-shell-consolidation.zh.md)

## Problem

Before consolidation, `App.vue` defined navigation three times: the desktop `n-menu` option tree, the eight-tab mobile footer, and two mobile selection modals for settings and records. The copies disagree on labels for the same routes, and the mobile copies omit `/BasementSkill` and both external references.

- **Callers Count**: `provide('sidebar_collapsed')` has zero injectors; `handleMenuClick` acts on one key (`chatbot`) and ignores every other menu key.
- **Duplicate Control**: The window-shell collapse zone duplicates the sider trigger, covers the sider scrollbar, and exposes no keyboard access.
- **Dead Imports**: Seventeen icon imports, `renderIcon`, `h` and `RouterLink` exist only to build these copies.
- **Defective Attribute**: External links carry `rel="noopenner noreferrer"`; browsers ignore the misspelled token.
- **Target File(s)**: `ui/src/App.vue`

---

## Consequences

- **Affected Invariants**: `[INV-UI-04] Single Navigation Definition` replaces the three copies.
- **Behavioral Equivalence**: Route records, `ui/public/frontend-routes.json` and persisted configuration remain unchanged. Every page stays reachable in both layouts; the mobile layout additionally reaches `/BasementSkill` and the external references. The old mobile tabs (日志, 设置 with modal, 排班, 自动专精, 数据图表 with modal, 帮助, 资源, Mower AI 助手) become four tabs (日志, 排班, 养成, 设置) plus a 更多 drawer listing the rest. The 设置 tab routes to `/mowersettings` directly instead of opening a modal. Collapsible submenus (全部设置, 数据图表) become always-open section headings (设置, 数据, 资料). Manual collapse in browser mode now stops auto-collapse; the old show-trigger event never set `userToggledSidebar`.

---

## Decision

1. Sections, labels, icons and the mobile tab subset live in [navigation.js](../../../../ui/src/navigation.js).
2. Render the desktop sider and the mobile page drawer through `ui/src/components/AppSidebar.vue`, and the mobile tab bar through `ui/src/components/MobileTabBar.vue`.
3. Delete the option tree, `renderIcon`, `handleMenuClick`, both selection modals, the collapse zone and its CSS, the unused collapsed layout class, the dead provide and the dead imports from `App.vue`.

---

## Alternatives considered

Keeping three navigation definitions retains the label, page coverage and collapse-control problems above. The original record does not document a separate comparison of other approaches.

## Verification

The original record lists these checks without reporting their execution results.

- Targeted Unit Tests: `npm test -- src/navigation.test.js src/components/NavigationShell.test.js src/composables/useCollapsedTips.test.js src/routes.test.js src/theme/mower.test.js`
- Gate Execution: `python scripts/verify_governance.py`

The [navigation sidebar note](../feature/2026-09-30-navigation-sidebar.md) defines the resulting layout rules.
