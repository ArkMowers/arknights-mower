# 收益演算维护与验证

## 修改入口

- 前端入口：`ui/src/pages/Plan.vue` 与 `ui/src/components/PlanIncomeDialog.vue`。
- 缓存：`server.py` 的 `/riic/income-cache` 只读共享森空岛快照，`utils/building_skills.py` 筛选练度与库存字段。算法复用 `/report/recycling_settings`，演算前重新读取；切换共享算法只修改对应系数，保留回收站效率。
- 输入与参数：`ui/src/riic/income.js`；默认预热 3 天、统计 28 天。
- 演算：`ui/src/riic/incomeWorker.js`；生命周期：`incomeSession.js`；上次结果存储：`incomeArchive.js`；图片：`incomeImage.js`；甘特图主题适配：`ui/src/components/IncomeTimeline.vue`；图表使用固定源码中的 `components/workbench/ScheduleTimelineGantt.vue`，时间轴使用 `workbench/timeline/`。
- 固定源码：`ui/src/riic/vendor/`，`source.json` 记录来源提交、Mower 参考版本和逐文件 SHA-256。保留目录内已有许可证；来源记录不授予其他许可证。
- 原图片接口：`server.py` 的 `/dialog/save/img`，可使用显式排班快照；导入继续走 `/import` 和 `arknights_mower/utils/qrcode.py`。

## 同步固定源码

从明确的计算器提交读取所需模块及全部相对依赖，不依赖另一份本地检出路径。比对主副表、组绑定、库存、宿舍与菲亚梅塔相关行为；记录上游与当前 Mower 调度之间的差异。计算器引用版本不等于当前本体版本。

现有包只有计算桥接、排班转换、诊断和相关依赖。保留所需 JSON 数据与 Mower 来源许可。同步后逐文件更新摘要，并从仓库根目录运行 `python .agents/skills/mower-riic/scripts/verify_calculator.py`；不要把源码目录格式化成与来源不一致却仍保留旧摘要。生成物构建须包含 Worker 和数据，不能只测试 Vite 开发服务。新增运行依赖需要纳入前端锁文件。

结果窗口声明缓存、手填或满配练度及库存来源、初始心情、保存的设施等级及未设置时的推断值、理想跑单、读房时钟及忽略的点击耗时、种子、无人机目标与资源口径。库存副表必须使用有限库存，预热和统计之间不能补充资源。日均收益除以实际统计天数，预热和初始库存不得算入收入；赤金产量、消耗与净增分别报告，并在窗口展示初始、统计开始与期末余额。龙门币净值扣除采样期制造支出；潜在模式的成本事件只供报告观察，不改变账本或生产。导出图在原排班上方显示日均收益、日均产物小图标和注明演算、预热及采样天数的验证章；名称仅用于文件名。产物复用现有图片，回收站复用房间识别模板中的标志。赤金、龙门币分别只保留净值；无人机标记使用本次结果和原图设施位置。赤金透支默认开启，只允许订单交付产生赤金负余额，不能解除其他材料限制。回收站只统计产出次数，不生成随机材料或价值。公招刷新按办公室实际演算区间的驻员、心情及已解锁技能统计，预热进度延续而完成次数剔除；假设及时使用次数，不模拟存满停工，不折算收益。图标使用办公室识别模板中的标志；来源和边界见[公招刷新产出](../../../../docs/subsystems/plan-editor.md#recruitment-refresh-production)。

甘特图直接复用固定计算器的组件与时间轴模块，保留相对路径和来源摘要。Mower 包装组件只适配主题、控件间距和窄窗口布局，不修改时间轴数据或源码交互。Worker 记录源码的采样驻员区间并生成设施、干员分道；横轴从采样起点计时，不包含预热。图表默认折叠、窗口为 24 小时，筛选、时间导航、事件标记及分卷导出均沿用源码。原始区间完整保留，密集切换仅在显示时合并。新成功记录一并保存演算报告与时间轴；旧记录缺少时间轴时提示重新演算，仍允许查看收益和导出原排班收益图。不再复用实测心情页或记录另一份心情曲线。

## 定向验证

从 `ui/` 执行修改范围对应的文件：

```bash
npm test -- src/riic/income.test.js src/riic/incomeSession.test.js src/riic/incomeArchive.test.js src/components/PlanIncomeDialog.test.js src/riic/incomeTimeline.test.js src/riic/vendor/workbench/timeline/timelineModel.spec.ts src/riic/vendor/workbench/timeline/timelineDisplay.spec.ts
```

图片传递从仓库根目录执行：

```bash
pytest arknights_mower/tests/config_backup_tests.py -k 'income or recycling_plan_json_and_image_round_trip'
```

AI 知识与试排修改执行 `arknights_mower/tests/riic_assistant_tests.py`，涉及真实工具注册或调用再加入 `ai_feature_tests.py`。按需要运行前端生产构建一次，确认独立 Worker 产物；不要在快速迭代中反复构建。

核对甘特图采样起点、设施及干员分道、窗口导航、筛选和图片导出，并用相同输入比较区间记录开启和关闭时的产出。核对完成后不自动下载、手动导出使用冻结结果，以及取消、创建失败、消息反序、页面卸载和导出失败重试；核对关闭、刷新后恢复上次成功演算，存储失败保留旧记录、旧窗口保存不覆盖新结果，排班变更后仍导出原快照，以及浅深主题下加高图片的完整二维码回导。用可手算场景验证数量，用代表性完整窗口验证调度和资源。测试通过不能证明真实设备收益。

设施等级在排班编辑器保存为 `facility_levels`，主副表共用；无需在收益窗口再次配置。右侧会客室、加工站、办公室、训练室和回收站未设置时默认三级，空房也计入建筑耗电，显式等级优先。维护时遵循[设施等级与电量规则](../../../../docs/subsystems/plan-editor.md#saved-facility-levels)，核对自动保存、未驻员建筑耗电、主副表容量、二维码往返及采样区间中的实际心情恢复速率。宿舍按当前等级满氛围，不能用任意速率覆盖掩盖等级传递问题。
