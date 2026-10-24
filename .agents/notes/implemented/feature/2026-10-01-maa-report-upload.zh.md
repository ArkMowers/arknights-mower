---
title: MAA 掉落数据代发上传
status: implemented
category: feature
date: 2026-10-01
---

# MAA 掉落数据代发上传

[English](2026-10-01-maa-report-upload.md)

`arknights_mower/utils/maa_report.py` 执行 MAA 核心委托给客户端的掉落数据上报，`arknights_mower/solvers/base_schedule.py` 中的 `BaseSchedulerSolver.on_maa_callback` 把每个 `ReportRequest` 负载交给该模块。[子系统规范](../../../../docs/subsystems/maa-integration.md) 规定代发上报契约与回调消费边界。

**[INV-MAA-03] 分离式限时上传**：委托上报在 MAA 回调线程之外运行，采用连接与单次读取的有限期限与有界的尝试次数，并以日志行而非异常的形式汇报结果。

MAA 核心不自行上传掉落数据。它判定本次掉落是否可上报、拼出完整的 HTTP 请求，再通过 `ReportRequest` 回调（AsstMsg `30000`）交给客户端，负载携带 `url`、`headers`、`body` 与 `subtask`。`REPORT_REQUEST = 30000` 在 `maa_callback.py` 中为该消息码命名。

此前的回调处理忽略这次交接：`log_maa` 把负载记入 DEBUG 日志后不做其他动作，而 Fight 任务无条件下发 `"report_to_penguin": True`，因此从未发生上传。本机 `log/runtime.log` 文件中的 DEBUG 记录保存了这些被丢弃的负载，例如发往 `https://penguin-stats.io/PenguinStats/api/v2/report` 的请求，`subtask` 为 `ReportToPenguinStats`，`uuid` 为 `3176499b735f1245`，`User-Agent` 为 `MaaAssistantArknights/6.18.0-beta.1`，`X-Penguin-Idempotency-Key` 为 `MAA1406c368ae984aae0698da55f2480`，请求体携带 `"source":"MaaAssistantArknights"`、`"stageId":"wk_toxic_5"` 与 `"version":"v6.18.0-beta.1"`。没有任何代码执行这次 POST，因此被选中的上报从未到达统计站点。本次上传取代 [MAA 回调日志](2026-09-30-maa-callback-logging.zh.md) 中"请求未被处理"的那段描述。

`upload_report` 接收单个负载，返回是否已启动请求。`url` 或 `body` 缺失、为空或不是字符串时，它记录一条警告并返回 `False`，不启动 POST；`headers` 不是映射时按空处理，`url` 解析不出主机名时同样拒绝。被接受的负载在名为 `maa-report` 的守护线程上启动 POST，因此 MAA 回调线程不会阻塞在网络调用上，也不会观察到上传失败。线程创建抛 `RuntimeError` 时同样只记一条警告并返回 `False`；`on_maa_callback` 对该调用加保护，因此线程起不来时回调也不会抛错。

`_upload` 把请求头合并进以 `Accept: application/json` 打底的 `CaseInsensitiveDict`，再用负载的请求头更新，仅在该键缺失时补上 `Content-Type: application/json; charset=utf-8`。HTTP 头部名不区分大小写，因此负载给出的 `Content-Type` 在任何拼写下都优先。请求体按 UTF-8 编码。目标是负载给出的 URL；仅当 `subtask` 为 `ReportToPenguinStats` 且该 URL 的主机名等于 `penguin-stats.io` 时，额外把同一 URL 换成 `penguin-stats.cn`；其余目标只在自己的域名上尝试。主机名经 `urlparse` 按主机名比较，因此出现在路径或查询串里的域名不会触发备用域名。备用域名存在的原因是主域名在部分网络下不可达。

`_attempt_domain` 在单个域名上最多尝试 `REPORT_ATTEMPTS`（3）次，每次尝试的连接与单次读取各受 `REPORT_TIMEOUT`（15 秒）约束。只有 5xx 响应会重试，间隔先为 `REPORT_BACKOFF`（3 秒），再乘 `REPORT_BACKOFF_FACTOR`（1.5，即 4.5 秒）。成功严格限定为状态码 `200`，因此重定向或其他 2xx 变体都按该目标失败处理。网络异常立即结束该域名，不再重试。企鹅上报在两个域名上都失败时最多发出六次 POST，每个域名两次退避睡眠，因此当六次尝试都撞上连接期限时，单次上报约占用其工作线程 105 秒。该期限按阶段而非按次计算：`requests` 把它分别用于连接与每次读取，两者都不覆盖域名解析。

`_post` 保护整个函数体。线程内逃逸的异常只到达 `threading.excepthook`，不会在运行时日志里留下任何记录，因此所有失败都必须在此处转成日志行，而不能向外传播。

成功记录一条 INFO 行并说明目的站点，即 `企鹅物流上报成功` 或 `一图流上报成功`。企鹅上报失败记录一条 WARNING 行，说明目的站点并放弃本次上报。其他目的站点的失败以 DEBUG 记录同样文案，与客户端对一图流刻意保持安静的做法一致；但本进程内首次此类失败会升级为 WARNING，因为 WebSocket 日志页面只承载 INFO 及以上，否则一个持续失败的目的站点在界面上完全不可见。

`SUBTASK_TEXT` 把 `ReportToPenguinStats` 映射为企鹅物流、`ReportToYituliu` 映射为一图流；`report_label` 依次取该名称、原始 `subtask` 字符串，或在 `subtask` 不是字符串时取 `MAA`。标签只决定措辞，未知子任务仍然上传。

上传日志经项目共享的 `from arknights_mower.utils.log import logger` 记录，而不是模块内的 `logging.getLogger(__name__)`，因此每条日志都到达终端、`runtime.log` 与 WebSocket 日志页面。

网络参数、成功判定、退避节奏与备用域名照搬 MAA 桌面客户端的 `GameDataReportService.PostWithRetryAsync` 与 `HttpService.BuildHttpClient`（分支 `dev-v2`，提交 `4a2084f2dad2740d388ad71305a3d5beac7fa498`）：每次尝试的连接与单次读取各 15 秒、每域名 3 次、仅 5xx 重试、3000 毫秒退避乘 1.5、严格 `200`，并以 `https://penguin-stats.cn` 作为备用。三项客户端行为被有意排除：客户端对 `txwy` 客户端跳过企鹅上传，而 `_maa_client_type` 只返回 `Official` 或 `Bilibili`，因此该分支在此没有可达情形；客户端在 PC 连接模式下跳过上报，而本后端没有该模式；客户端通过 `x-penguin-set-penguinid` 把返回的 id 写回配置，而由后台上传线程改写持久化配置不在本次改动范围内。另有三处差异源自移植本身：客户端用单一期限覆盖整次尝试，而 `requests` 分别约束连接与每次读取；客户端用 URL 子串匹配选择备用域名，而此处按主机名比较；客户端在域名内最后一次 5xx 之后仍会再睡一次。

上报改为可选。`Conf.maa_report_to_penguin` 默认为 `False`，Fight 任务下发 `"report_to_penguin": conf.maa_report_to_penguin` 取代原先硬编码的 `True`，`maa_penguin_id` 的说明改为"仅在开启上报时有效"，与既有的 `maa_yituliu_id` 一致。`ui/src/components/MaaWeekly.vue` 渲染"上报至企鹅物流"复选框，未勾选时其 id 输入框保持禁用，与一图流那一行保持一致；帮助文案说明两个站点都只在勾选后上传，id 留空则匿名上传。`ui/src/stores/config.js` 让新的 ref 贯通加载、保存与导出。

`log_maa` 更名为 `on_maa_callback`，因为它现在执行上传而不只是记录日志；当 `msg == REPORT_REQUEST` 时调用 `upload_report(d)`，随后照旧记录转换后的日志行。该调用加保护，`upload_report` 抛出的异常记为一条警告，而不会变成无法抛出的异常。

`arknights_mower/tests/maa_report_tests.py` 提供 25 个离线测试。它们用内联假线程替换 `threading.Thread` 并打桩 `time.sleep`，让上传与退避同步执行，覆盖：`url` 或 `body` 缺失或非字符串时拒绝且不发生任何 POST、`url` 解析不出主机名时在起线程前拒绝、线程创建抛 `RuntimeError` 时只记录而不抛出、工作线程中逃逸的异常转成日志行、`requests.post` 的精确参数（含 `Accept`、默认 `Content-Type` 与在三种拼写下覆盖它的负载取值）、`headers` 缺失或非映射的容忍、严格的 `200` 判定、5xx 按 3 秒与 4.5 秒退避重试后放弃、4xx 不在同域名内重试、网络异常结束所属域名、企鹅备用域名、一图流、外来 URL 以及仅出现在查询串里的企鹅域名都不使用备用域名、一图流首次失败的 WARNING 与后续的 DEBUG 行、两种标签，以及调度器接线——证明 `30000` 到达 `upload_report`、其他消息码不会，且上传失败绝不逃出回调。`maa_stage_inventory_scheduler_tests.py` 的企鹅测试按可选默认值改写，既有测试仍然通过。

接口依据：[MAA 回调协议](https://docs.maa.plus/zh-cn/protocol/callback-schema.html)、[MAA 桌面客户端回调处理](https://github.com/MaaAssistantArknights/MaaAssistantArknights/blob/dev-v2/src/MaaWpfGui/Main/AsstProxy.cs) 与客户端的[提交 `4a2084f2`](https://github.com/MaaAssistantArknights/MaaAssistantArknights/commit/4a2084f2dad2740d388ad71305a3d5beac7fa498)。

## 规范检查

通过：上传立即离开 MAA 回调线程并在守护线程上运行，因此网络等待不会到达回调，待完成的上传也不拖住进程退出。工作线程把每个 HTTP 与网络异常转换为日志行，`_post` 保护整个函数体，因此逃出内层处理的异常也会变成日志行，而不是一次静默的 `threading.excepthook` 报告。重试预算受两重限制——每域名 `REPORT_ATTEMPTS` 次、连接与单次读取各受 `REPORT_TIMEOUT` 约束——且只对 5xx 重试，客户端错误不会放大请求量，这正是 [INV-MAA-03] 所固定的内容。负载与 URL 校验在任何线程启动之前完成，`on_maa_callback` 对交接加保护，因此被拒绝的负载或失败的线程创建都不会从 C 回调边界抛出。日志经项目共享 logger 记录，因此沿用服务终端、`runtime.log` 与 WebSocket 日志页面的运行日志策略。新配置字段沿用相邻字段的 pydantic 默认值与文档字符串约定，UI 行照搬既有一图流控件而不引入新模式。未改动设备配置、排班表或术语定义；`CONTEXT.md` 与 `CONTEXT.zh.md` 保持原样。

## 功能检查

通过：本次改动实现 MAA 协议定义的交接分工——核心判定可上报性并拼出请求，客户端负责发送——`on_maa_callback` 把 `30000` 的负载原样交给 `upload_report`。网络策略与照搬的客户端行为逐项一致：每次尝试的连接与单次读取各 15 秒、每域名 3 次、仅 5xx 重试并按 3 秒与 4.5 秒退避、严格 `200`、企鹅备用域名，以及非企鹅失败留在 DEBUG——仅首次升级为 WARNING，以便 WebSocket 日志页面承载它。三项被排除的客户端行为——`txwy` 跳过、PC 连接模式跳过、`x-penguin-set-penguinid` 写回——都记录了原因，移植本身引入的三处差异同样记录在案。不可用或解析不出主机名的负载的拒绝、`headers` 缺失或非映射的容忍、负载 `Content-Type` 在任何拼写下的优先、备用域名按主机名比较、未知子任务仍上传的回落标签，以及终结静默丢弃的可选默认值，都符合既定契约与[子系统规范](../../../../docs/subsystems/maa-integration.md)。离线测试覆盖上述全部边界；向统计站点的实机上传不在测试范围内。
