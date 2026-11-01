# 原始材料

来源提交：`7aac30fbf6a89592ffdfbaad0c52e6b64946f81e`。

比较基线：`645464b1ddb7ff20b59621645d78d95eabaef807`，即来源提交的父提交。

本用例在项目仓库内执行。读取两版原文与完整差异：

```text
git diff 645464b1ddb7ff20b59621645d78d95eabaef807 7aac30fbf6a89592ffdfbaad0c52e6b64946f81e
```

对应版本的来源入口：

- `ui/src/routes.js`、`ui/src/App.vue` 与 `ui/src/pages/MasteryRecommendation.vue`：页面身份、干员卡片及加载操作。
- `ui/src/components/GrowthSurveyFilters.vue` 与 `ui/src/utils/growthSurvey.js`：调查来源、展示指标及缺少有效指标时的表现。
- `arknights_mower/utils/mastery_recommendation.py`、`arknights_mower/utils/yituliu_statistics.py` 与 `server.py`：读取的数据、缓存归属、请求事件及校验结果。
- `docs/subsystems/growth-planning.md`、相关前后端测试和差异中的实现记录：行为边界与已有证据。

逐个入口使用 `git show <版本>:<路径>` 读取目标与基线，不能拿当前 HEAD 替代。

不使用旧提交标题或业务说明正文作为写作输入。来源记录中的合成测量、接口观测和检查结果只说明当时取得的证据，不代表本轮实际执行或用户现场已验证。
