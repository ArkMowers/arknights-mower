---
title: 前端页面导航与 API 分派
status: implemented
category: bug-fix
date: 2026-10-12
---

# 前端页面导航与 API 分派

`/mastery-recommendation` 同时属于 Vue 页面和 JSON API。成功的接口响应绕过现有 404 页面回退，刷新时直接显示 JSON。此前的页面刷新测试排除了这一重名路径。现有有效决策记录没有覆盖此分派边界。

[INV-WEB-04] Frontend Navigation Dispatch 的契约位于 [Web Access 契约](../../../../docs/subsystems/web-access.md#6-frontend-navigation)。已知页面的导航请求在 API 分派前使用现有路由清单解析。API 客户端保留原处理函数，缓存变体区分页面导航与接口请求。

复杂度检查发现 `server.not_found` 中有一处清单读取，没有冗余的公共抽象。共用清单和导航判定函数使新增分派检查与现有 404 回退保持一致。领域概念、配置结构、设备控制和调度均保持原有含义，无需修改术语表。

`arknights_mower/tests/web_routing_tests.py` 的定向验证覆盖清单中的所有页面、重名接口、GET 与 HEAD、查询参数、大小写、末尾斜杠、请求元数据、缓存变体、非读取方法以及保留的 404 响应。原实现未通过页面导航和缓存变体回归测试。修复后的路由测试通过全部 10 项测试，治理测试通过 27 项测试，`npm test -- src/routes.test.js` 通过路由清单一致性测试。`python scripts/verify_governance.py` 通过结构检查，保留两条既有的归档引用警告。

规范审查确认请求判定共用且没有术语表或持久化变更。需求审查确认通过 Flask 实际请求钩子完成分派、保留接口响应，并对全部 17 个清单页面提供定向覆盖。打包后的桌面浏览器刷新仍需手动验证。
