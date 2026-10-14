# 收益演算维护与验证

## 修改入口

- 前端入口：`ui/src/pages/Plan.vue` 与 `ui/src/components/PlanIncomeDialog.vue`。
- 缓存：`server.py` 的 `/riic/income-cache` 只读共享森空岛快照，`utils/building_skills.py` 筛选练度与库存字段。算法复用 `/report/recycling_settings`，演算前重新读取；切换共享算法只修改对应系数，保留回收站效率。
- 输入与参数：`ui/src/riic/income.js`；默认预热 3 天、统计 28 天。
- 演算：`ui/src/riic/incomeWorker.js`；生命周期：`incomeSession.js`；图片：`incomeImage.js`。
- 固定源码：`ui/src/riic/vendor/`，`source.json` 记录来源提交、Mower 参考版本和逐文件 SHA-256。保留目录内已有许可证；来源记录不授予其他许可证。
- 原图片接口：`server.py` 的 `/dialog/save/img`，可使用显式排班快照；导入继续走 `/import` 和 `arknights_mower/utils/qrcode.py`。

## 同步固定源码

从明确的计算器提交读取所需模块及全部相对依赖，不依赖另一份本地检出路径。比对主副表、组绑定、库存、宿舍与菲亚梅塔相关行为；记录上游与当前 Mower 调度之间的差异。计算器引用版本不等于当前本体版本。

现有包只有计算桥接、排班转换、诊断和相关依赖。保留所需 JSON 数据与 Mower 来源许可。同步后逐文件更新摘要，并从仓库根目录运行 `python .agents/skills/mower-riic/scripts/verify_calculator.py`；不要把源码目录格式化成与来源不一致却仍保留旧摘要。生成物构建须包含 Worker 和数据，不能只测试 Vite 开发服务。新增运行依赖需要纳入前端锁文件。

报告声明缓存、手填或满配练度及库存来源、初始心情、推断设施等级、理想跑单、读房时钟及忽略的点击耗时、种子、无人机目标与资源口径。库存副表必须使用有限库存，预热和统计之间不能补充资源。日均收益除以实际统计天数，预热和初始库存不得算入收入；赤金产量、消耗与净增分别报告，并展示初始、统计开始与期末余额。赤金透支默认开启，只允许订单交付产生赤金负余额，不能解除其他材料限制。回收站只统计产出次数，不生成随机材料或价值。

## 定向验证

从 `ui/` 执行修改范围对应的文件：

```bash
npm test -- src/riic/income.test.js src/riic/incomeSession.test.js src/components/PlanIncomeDialog.test.js
```

图片传递从仓库根目录执行：

```bash
pytest arknights_mower/tests/config_backup_tests.py -k 'income or recycling_plan_json_and_image_round_trip'
```

AI 知识与试排修改执行 `arknights_mower/tests/riic_assistant_tests.py`，涉及真实工具注册或调用再加入 `ai_feature_tests.py`。按需要运行前端生产构建一次，确认独立 Worker 产物；不要在快速迭代中反复构建。

核对取消、创建失败、消息反序、页面卸载和导出失败重试；核对旧排班变更后仍导出原快照，以及浅深主题下加高图片的完整二维码回导。用可手算场景验证数量，用代表性完整窗口验证调度和资源。测试通过不能证明真实设备收益。
