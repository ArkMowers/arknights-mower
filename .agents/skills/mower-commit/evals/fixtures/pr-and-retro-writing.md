# 原始材料

来源提交：`5094013c11240075cd00910cc894148c47d45754`。

本次范围仅为该提交与其父提交的差异。不使用旧提交标题或业务说明正文作为写作输入。

## 历史检查记录

以下记录来自来源提交当时的正文，仅保留检查结果与证据限制，不代表本轮实际执行。

结构检查与十份生成产物的文本扫描通过。五组新旧单轮对照仍有计时关系图、版本定位和局部表述缺项，尚未证明稳定性改善。

## 完整 diff

```diff
diff --git a/.agents/AGENTS.md b/.agents/AGENTS.md
index ee1cc7dfd..621d64228 100644
--- a/.agents/AGENTS.md
+++ b/.agents/AGENTS.md
@@ -44,7 +44,7 @@ Use one primary workflow for each responsibility. Repository skills own reposito
 | Responsibility | Primary repository skill | General-skill relationship |
 | :--- | :--- | :--- |
 | Code review | [mower-code-review](skills/mower-code-review/SKILL.md) | Generic code-review may supply review technique; keep one comparison scope and one report. |
-| Session retrospective | [mower-retro](skills/mower-retro/SKILL.md) | Generic retro supplies retrospective technique; mower-retro owns session evidence, project check reuse and read-only recommendations. |
+| Session or PR delivery retrospective | [mower-retro](skills/mower-retro/SKILL.md) | Generic retro supplies retrospective technique; mower-retro owns original process evidence, project check reuse and read-only recommendations. |
 | Complexity assessment | [mower-find-simplifications](skills/mower-find-simplifications/SKILL.md) | Use diagnosis/design techniques as needed; findings do not automatically create a proposal. |
 | Guarantee and test design | [mower-define-invariant](skills/mower-define-invariant/SKILL.md) | Generic testing skills support observable behavior verification; reuse existing guarantees first. |
 | Document placement | [mower-doc](skills/mower-doc/SKILL.md) | Domain modeling supplies concept analysis; repository routing and approval remain authoritative. |
diff --git a/.agents/skills/mower-pr/SKILL.md b/.agents/skills/mower-pr/SKILL.md
index cbc42afa4..dc92706f4 100644
--- a/.agents/skills/mower-pr/SKILL.md
+++ b/.agents/skills/mower-pr/SKILL.md
@@ -15,11 +15,13 @@ description: 为 Arknights Mower 编写或更新中文 PR 标题和正文，从
 
 先按主要变化整理事实项，将实际对象、修改前的行为或要求、修改后的行为或要求、方案理由、验证结果及来源分别记录。同时记录材料中的既有产物和本次交付的状态，分别确定影响范围与恢复对象。
 
+筛选前从原始材料确认审阅必需的事实：触发条件与现场后果、失败原因、相关版本各自的行为、同输入对照，以及已有状态或数据的影响与恢复条件。只保留与本次判断有关的项目；未提供的关键材料标为缺项。未进入 Git diff 的本地数据修复或外部产物，也按其实际影响判断是否需要交接。
+
 对照文档时，读取两版原文，确认与本次变化有关的具体规定，以及本次补充了哪些原文未规定的要素。文档和工程改动说明使用或维护方式的变化。
 
 文档要求展开为具体格式、内容或操作。格式说明给出实际格式，流程说明给出动作及顺序；原文只提出名称或方向时，记录与本次变化有关的未规定内容。材料只有概括时先补读原文，缺少必要原文时记录缺少的依据。事实项只写核实后的具体内容，概括性原句留在原文中作为来源。
 
-交接前筛选事实，只保留最终变化、必要设计理由、实际验证及重要缺口、真实影响与恢复条件，以及核对这些事实必需的来源。每项说明审阅者据此判断什么；没有审阅用途的工作记录留在聊天或工作区。方案关系另列节点、连线及含义，已有图作为核对来源。
+交接前筛选事实，只保留最终变化、必要设计理由、实际验证及重要缺口、真实影响与恢复条件，以及核对这些事实必需的来源。每项说明审阅者据此判断什么；没有审阅用途的工作记录留在聊天或工作区。再从必需事实反向核对交接，确认精简后仍能判断问题、方案、证据和恢复条件。方案关系另列节点、连线及含义，已有图作为核对来源。
 
 负责写作的 Agent 直接读取 skill 与模板，再重新组织句子。版本与来源单独定位。材料整理完成的条件是每项变化均能说明实际对象怎样改变，以及依据或相关缺项是什么。
 
@@ -43,9 +45,9 @@ description: 为 Arknights Mower 编写或更新中文 PR 标题和正文，从
 
 列表前留空行，每项保留自身的条件和例外，不用逗号或分号把多项独立要点挤在同一段。同一主题可以包含引导段和列表，标签只放在主题开头，列表项不必重复加粗。Summary 和 Evidence 中对应变化使用可相互辨认的主题标签；Merge Danger 使用影响范围和可逆性定位后果与恢复条件。
 
-**Summary** 首段交代原问题和最终变化，后续段落解释方案及必要取舍。小改动可用一段完成。
+**Summary** 首段交代原问题和最终变化，后续段落解释方案及必要取舍。篇幅取决于审阅问题、证据和后果的复杂度；这些内容简单时可用一段完成。
 
-方案包含同一输入到多项输出的对应、组件职责分工或步骤依赖时，用关系图说明，并紧邻整体方案放置。纯文本关系图使用标记为 `text` 的 Markdown 代码块，节点分行，以缩进、分支线和箭头区分并列对应与先后依赖。节点写明实际对象，连线表达已核实的关系；已有图仍符合最终方案时，保留必要节点和呈现结构，按最终事实校正文字。局部代码差异适合用短 diff 展示。
+方案包含同一输入到多项输出的对应、组件职责分工或步骤依赖时，用关系图说明，并紧邻整体方案放置。纯文本关系图使用标记为 `text` 的 Markdown 代码块，节点分行，以缩进、分支线和箭头区分并列对应与先后依赖。节点写明实际对象，连线表达已核实的关系；已有图仍符合最终方案时，保留必要节点和呈现结构，按最终事实校正文字。先确定要解释的关系，再选择最小展示：步骤依赖用关系图，局部代码变化用短 diff，同输入结果比较用对照表。正文仍需解释的职责或依赖关系由关系图呈现，局部 diff 和结果表分别说明变化与证据。
 
 关系图的展示方式参考 HumanLayer 的 [show-me](https://github.com/humanlayer/skills/blob/main/plugins/show-me/skills/show-me/SKILL.md)。
 
@@ -75,12 +77,14 @@ description: 为 Arknights Mower 编写或更新中文 PR 标题和正文，从
 
 ## 5. 回读与交付
 
-负责复核的 Agent 逐项核对完整正文：每项 Summary 变化均能定位到 Evidence 的具体结果、原文差异或缺项；首次出现的对象已解释用途与变化；每个回退对象已说明恢复动作和条件。通读自然段，核对主语、修饰关系、指代和句间关系，确认旧行为、文档要求及检查结果已写出具体内容。
+负责复核的 Agent 做双向核对：从正文逐项确认事实有依据，再从原始材料中的必需事实逐项定位正文落点。后者包含未进入交接或 diff、但影响审阅的事实；省略项需确认其缺失不影响方案、证据或恢复判断。该对应保留在工作区，正式正文只写审阅所需的内容。
+
+每项 Summary 变化均能定位到 Evidence 的具体结果、原文差异或缺项；首次出现的对象已解释用途与变化；每个回退对象已说明恢复动作和条件。按第 3 步的条件核对方案关系及其展示，确认所需关系图、局部 diff 或对照结果已经进入成稿。通读自然段，核对主语、修饰关系、指代和句间关系，确认旧行为、文档要求及检查结果已写出具体内容。
 
 发现概括性表述、对象用途不明或对应事实遗漏时，重新核实相关事实项并重写该段，再按相同场景复核。交付条件是具体内容、证据对应和恢复条件均已落实到成稿。
 
 先对照需求与完整最终 diff 检查标题范围和事实，再脱离正文检查标题是否保留对象种类及必要条件、场景和结果，最后按共享规则检查表达与格式。正文有对应句子只说明有来源，不能证明标题概括完整。再读标签和结论句，核对并列要点、步骤先后、首次文档名称与用途、恢复条件、数量、链接和证据版本，清除模板提示。
 
-发布前将仓库路径转为实际审阅提交的可访问链接，按[正式文本检查入口](../../../scripts/README.md#formal-text-checks)扫描标题与完整正文；每次编辑 PR 元数据也执行检查。按已有授权发布后，回读远端标题、正文和最新提交，重新扫描回读内容，核对成稿一致并检查当前 CI 与评审状态；草稿请求以交付标题和正文结束。
+发布前将仓库路径转为实际审阅提交的可访问链接，按[正式文本检查入口](../../../scripts/README.md#formal-text-checks)扫描标题与完整正文；每次编辑 PR 元数据也执行检查。文本扫描确认格式和指定术语，事实覆盖与展示选择由上述复核确认。用户要求开 PR 时默认发布为可审阅状态；用户明确要求 Draft PR 时使用 Draft。按已有授权发布后，回读远端标题、正文和最新提交，重新扫描回读内容，核对成稿一致并检查当前 CI 与评审状态；只要求文案草稿时以交付标题和正文结束。
 
 [评估用例](evals/evals.json)用于同一请求、相同原始材料下的独立对照。各版本按自己的流程筛选和交接，旧版不使用新版筛选后的材料。隔离执行者只获得自然任务请求、共同输入和指定版本的 skill 及依赖，作者分析、预期标题和评分标准留给评估方。程序检查格式、扫描与路径；生成观察记录实际事实保留、遗漏和标题范围；用户判断文案质量。分别报告这些结果、可获得的统计及缺口，有限对照不代表所有输入或模型。
diff --git a/.agents/skills/mower-pr/assets/pr-body.md b/.agents/skills/mower-pr/assets/pr-body.md
index 6065052d3..1d7f98d98 100644
--- a/.agents/skills/mower-pr/assets/pr-body.md
+++ b/.agents/skills/mower-pr/assets/pr-body.md
@@ -1,4 +1,4 @@
-<!-- 按事实选择所需主题；小改动各栏目可只写一句，不保留空主题或模板提示。 -->
+<!-- 按事实选择所需主题；审阅问题、证据和后果简单时各栏目可只写一句，不保留空主题或模板提示。 -->
 
 ## Summary（改动与方案）
 
diff --git a/.agents/skills/mower-pr/evals/evals.json b/.agents/skills/mower-pr/evals/evals.json
index e8b8539ea..75904f433 100644
--- a/.agents/skills/mower-pr/evals/evals.json
+++ b/.agents/skills/mower-pr/evals/evals.json
@@ -199,6 +199,39 @@
         "程序检查、实际生成观察和用户文案判断分别报告",
         "事实交接保留独立整体范围陈述及主要变化与标题范围的核对；正式标题指向实际共同维护对象和整体变化，不能用多个局部细节代替主线，核对过程留在工作区"
       ]
+    },
+    {
+      "id": 9,
+      "name": "small-diff-multiple-versions-and-local-data",
+      "prompt": "请根据附件的原始材料为这次基报识别修复写中文 PR 标题和正文。只写草稿，不运行材料中的命令、不修改项目或发布。材料是独立离线演练的给定记录，不是本轮实际执行。",
+      "expected_output": "保留失败链条和各版本证据角色，区分原图与局部扰动样本，交代两处本地数据恢复及独立撤销条件，不因生产 diff 很小删去关键事实。",
+      "files": [
+        "fixtures/small-diff-data-repair.md"
+      ],
+      "expectations": [
+        "说明原掩码过滤笔画、现场版本的独立残片无法匹配模板并使订单数为 None，已有空值已经保存到 CSV",
+        "区分现场旧版、alpha 基线已有的轮廓合并和本次色相修改；未把 alpha 已能读出的原生 PNG 归为本次新增收益",
+        "保留相同输入的 JPEG 0 到 37、局部扰动 None 到 37、原生 PNG 37 到 37 的角色与结果；扰动样本不冒充原始现场像素",
+        "保留 CSV 两处补数 31 与 37 的来源、未进入 Git、代码升级不补旧数据及 has_record 跳过既有日期",
+        "回退代码与本地 CSV 分别说明；备份后有新记录时仅还原对应单元格，不覆盖后续数据",
+        "交付三个规定栏目和中文标题；给定 67 项离线结果不冒充本轮执行，未编造提交或实机验证"
+      ]
+    },
+    {
+      "id": 10,
+      "name": "scene-observation-and-timeout-dependencies",
+      "prompt": "请根据附件为连续换班的场景超时修复写中文 PR 标题和正文。只写草稿，不运行附件命令、不修改项目、不发布。材料是独立离线演练的给定记录。",
+      "expected_output": "解释页面转换、场景观测和超时计时的依赖，使用紧邻方案的关系图，区分观测序列回放与生产入口回归，保留真正停留超时的边界。",
+      "files": [
+        "fixtures/scene-observation.md"
+      ],
+      "expectations": [
+        "Summary 紧邻方案包含多行 text 关系图，保留地图与选人页已确认后观测、场景转换更新计时、同页超时退出及失效画面停止操作的关系",
+        "保留只观测房间时跨越 273.255 秒导致误退出的原因，以及 run_order_delay=3 和 270 秒只是给定回放设置、实际用户配置未知",
+        "修改前一次与补地图观测后零次归于相同截图和时刻的观测序列回放；未冒充旧版与新版本完整生产路径的实机对照",
+        "生产入口测试覆盖需要换人和名单相同；270 秒继续、271 秒退出以及退出后不点旧坐标均保留",
+        "同页超时阈值与截图缓存的已有机制有准确说明，给定 242 项与 18 项子测试不冒充本轮执行"
+      ]
     }
   ]
 }
diff --git a/.agents/skills/mower-pr/evals/fixtures/scene-observation.md b/.agents/skills/mower-pr/evals/fixtures/scene-observation.md
new file mode 100644
index 000000000..e3bc6a3d2
--- /dev/null
+++ b/.agents/skills/mower-pr/evals/fixtures/scene-observation.md
@@ -0,0 +1,33 @@
+# 给定演练材料：连续换班场景观测
+
+以下是虚构的完整改动及验证记录，不代表本轮执行。base 与 head 的 SHA 未提供。
+
+## 用户问题和最终 diff
+
+正常连续换班误触发长时间同场景超时，要求修复且保留真正卡住时的检测。生产变化只有两个入口：
+
+```diff
+ # 地图进房：已有识别确认中枢特征后
++if self.scene() != Scene.INFRA_MAIN:
++    self.recog.update()
++    continue  # 沿用原有有界尝试
+ # 普通设施选人：已有识别确认蓝色确认按钮后
++if self.scene() == Scene.UNKNOWN:
++    raise RuntimeError("选人页场景观测已失效")  # 沿用房间重试
+```
+
+其余变化为新增离线回归和两个既有测试补齐 scene 模拟返回值，没有修改计时器或 run_order_delay×90 秒阈值。
+
+## 原始观察和已有机制
+
+原路径仅在每间房结束时观测，连续 14 次均为房间场景，跨越 273.255 秒。截图显示中间已经经历地图、选人页和房间，但没有登记中间观测；计时因此把多间房累计为同一场景停留。Recognizer 在场景编号变化时更新计时，同页持续停留超过阈值则退出游戏并使场景失效。scene() 识别复用已有截图缓存，不强制每次重截。
+
+本次在已确认地图与选人页后补观测，使计时反映页面转换。观测过程中若发生超时退出，进房刷新画面再走原有有界尝试，选人进入现有房间重试，后续不点击旧坐标。
+
+## 给定验证记录
+
+原包没有用户配置。以 run_order_delay=3、阈值 270 秒，使用相同原始截图和日志时刻、最终识别实现，仅改变观测序列：只保留房间观测退出一次；补入截图已出现的地图观测退出零次。这是观测序列回放，不是完整旧版与新版生产路径的对照。
+
+生产入口回归沿用这些时刻，覆盖需要换人和名单相同跳过选人两种情况，均完成安排且不退出。选人页转房间更新计时；房间停留 270 秒继续、271 秒退出；地图一直不变时超时仍退出且不再点击旧坐标。两种已识别页面的离线检查均复用截图缓存。
+
+最终给定 7 个定向测试文件共 242 项及 18 项子测试通过，Ruff、格式和结构检查通过，保留既有归档提示。全部离线，没有实机验证。改动没有持久化数据变化，回退代码恢复原行为。
diff --git a/.agents/skills/mower-pr/evals/fixtures/small-diff-data-repair.md b/.agents/skills/mower-pr/evals/fixtures/small-diff-data-repair.md
new file mode 100644
index 000000000..6ee19cf8c
--- /dev/null
+++ b/.agents/skills/mower-pr/evals/fixtures/small-diff-data-repair.md
@@ -0,0 +1,33 @@
+# 给定演练材料：基报识别与本地数据
+
+以下是虚构的完整小改动及原始观察记录，用于写作评估。没有可引用的 Git SHA，不能虚构提交链接或本轮执行。
+
+## 需求与完整最终改动
+
+用户报告订单数为 None，要求修复并依据截图补齐本地 CSV；仅提交识别修复。最终生产 diff：
+
+```diff
+- img = cv2.inRange(img, (0, 0, 50), (100, 100, 170))
++ # 低饱和度灰字接受完整色相范围。
++ img = cv2.inRange(img, (0, 0, 50), (179, 100, 170))
+```
+
+此外只新增三例离线回归和两个脱敏数字裁剪样本，并在既有双语字段完整性记录补充原因及结果；未修改其他算法和存储规则。
+
+## 原始观察与版本
+
+现场旧版逐轮廓匹配。原生 PNG 的原掩码接收 241 个像素，完整色相接收 251 个；丢失的 10 个像素切断数字 3，缩放后二值图留下 13×7 px 的独立残片，加上下边框后高 27 px，低于 29–31 px 的全部模板，匹配返回 None，整个 37 字段未读取。日志中的其他五字段和定位锚点正常。订单数空单元格已经写入 CSV。
+
+alpha 基线已增加横向相交轮廓合并，在上限 100 时就能读出上述原生 PNG 的 37；本次保留该合并实现，仅改色相。最终分支临时恢复上限 100，其他代码不变，与上限 179 在同输入比较：JPEG 裁剪原色偏样本 0→37；保留明度、将数字局部改为中性灰的扰动样本 None→37；原生 PNG 37→37。两侧合成玉订单数均为 0。扰动是控制输入，不能说明现场具有相同像素。PNG 不缩放，仅裁剪；JPEG 从 1280×720 放大到 1920×1080 后裁剪。模拟设备只提供截图，定位、裁剪、掩码及数字匹配均用生产实现。
+
+给定执行记录：最终版本 67 项定向离线测试通过，含既有 64 例；Ruff、格式及结构检查通过，另有两条既有归档引用警告。没有实机测试。
+
+## 本地数据与恢复
+
+CSV 按采集日期写行，报告画面显示前一天数据。2026-10-11 行的订单数空值按近三天截图的 10.10 报告补为 31；2026-10-13 行按完整 PNG 的 10.12 报告补为 37。只改这两个单元格，其他字节保留，原文件先备份。CSV 与备份不进入 Git。has_record 跳过已有日期，升级不自动补旧数据，不能按金额推算订单数。
+
+代码回退恢复色相上限 100，alpha 已有合并仍保留。本地补数独立撤销：备份后没有新增记录或修改才恢复整个备份；已有后续记录时只将两个订单数字段还原为空，保留后续数据。
+
+## 开发过程记录
+
+临时工具曾遇到编码问题，重跑成功；曾压缩一次聊天总结。它们没有改变最终证据、交付及数据恢复条件。
diff --git a/.agents/skills/mower-retro/SKILL.md b/.agents/skills/mower-retro/SKILL.md
index 6dd488849..cac71d872 100644
--- a/.agents/skills/mower-retro/SKILL.md
+++ b/.agents/skills/mower-retro/SKILL.md
@@ -1,6 +1,6 @@
 ---
 name: mower-retro
-description: 复盘 Arknights Mower 编码会话，提出有会话证据的 Agent 环境改进建议。用户要求总结返工原因或改善导航、检查和工作流程时使用；不用于普通开发、代码评审或文案修改，也不作为每次任务的必做步骤。
+description: 复盘 Arknights Mower 编码会话或 PR 交付过程，提出有原始记录依据的 Agent 环境改进建议。用户要求分析返工、PR 遗漏或指令执行偏差，或改善导航、检查和工作流程时使用；不用于普通开发、代码评审或文案修改，也不作为每次任务的必做步骤。
 compatibility: 依赖 Arknights Mower 仓库及可读取的会话材料；历史会话访问能力由宿主提供。
 metadata:
   credits:
@@ -13,16 +13,18 @@ metadata:
 
 ## 输入与输出
 
-输入为用户指定的编码会话及其原始记录；未指定时使用当前会话。输出为按影响排序的环境改进建议，说明会话证据、成因、最小改进、维护位置和验证方法。默认交付只读报告。
+输入为用户指定的编码会话或 PR 交付过程及其原始记录；未指定时使用当前会话。PR 链接用于定位最终改动和正文，初稿、修订过程、相关会话及当时的指令用于还原交付经过。输出为按影响排序的环境改进建议，说明会话证据、成因、最小改进、维护位置和验证方法。默认交付只读报告。
 
 ## 复盘流程
 
 1. **确定范围。** 读取 [Arknights Mower Agent 工作流程](../../AGENTS.md#1-task-selection)，确定本次复盘与已有授权的范围。使用当前对话、用户提供的材料或宿主可读取的指定会话记录；只查找与该会话有关的内容。报告采用[项目文风规范](../mower-prose-standard/SKILL.md)及其术语来源。
 
-2. **还原关键经过。** 从用户要求、实际命令与输出、改动和评审反馈中定位找错入口、返工、误判、遗漏或重复读取。将已观察的问题与待确认的原因分开。当前源码、最终总结和成功状态不能证明先前执行过某一步；原始记录缺失时说明缺项，缩小结论范围。
+2. **还原关键经过。** 从用户要求、实际命令与输出、改动和评审反馈中定位找错入口、返工、误判、遗漏或重复读取。将已观察的问题与待确认的原因分开。复盘 PR 时对照首次交付、用户或评审反馈与修订稿，定位事实何时丢失、补充依据及发布前检查覆盖。当前源码、最终正文、作者自述和成功状态不能单独证明先前执行过某一步或遗漏原因；原始记录缺失时说明缺项，缩小结论范围。
 
 3. **核对当时的环境。** 检查问题涉及的导航、规则、脚本和 CI。以会话使用的版本、比较范围和工作目录解释结果；必要时用 `git show <commit>:<path>` 读取旧版。已有改进能解释旧问题时，说明它已被覆盖。只有当前文件可读时，保留版本差异的不确定性。
 
+   分别核对指令是否被访问、内容是否完整可见、条件是否被正确判断、关键事实是否在交接中保留，以及发布前检查能否发现遗漏。工具记录显示读取了 skill，只能证明访问；作者对原因的解释需与原始材料和实际产物相互核对。将现有要求未落实与规则或流程缺口分开，再判断需要修复入口、条件表述、交接或完成标准中的哪一处。
+
 4. **选择改进方向。** 按下表检查与已观察问题相关的维度。先检查已有机制的覆盖和执行情况，再决定补充或调整什么。
 
    | 维度 | 判断与项目入口 |
@@ -45,6 +47,6 @@ metadata:
 
 ## 完成
 
-每项建议均能追溯到指定会话，已核对相关现有机制，并有维护位置和可执行的验证方法。资料缺口与未验证效果保持明确；只读复盘以报告结束。
+每项建议均能追溯到指定会话或 PR 交付记录，已核对相关现有机制，并有维护位置和可执行的验证方法。资料缺口与未验证效果保持明确；只读复盘以报告结束。
 
 [评估用例](evals/evals.json)检查会话证据、检查复用和资料不足时的结论范围。评估输入与预期结果分别提供给隔离执行者和评估方，运行产物保存在 skill 目录外。
diff --git a/.agents/skills/mower-retro/evals/evals.json b/.agents/skills/mower-retro/evals/evals.json
index 621419db8..4d6d2fddb 100644
--- a/.agents/skills/mower-retro/evals/evals.json
+++ b/.agents/skills/mower-retro/evals/evals.json
@@ -28,6 +28,22 @@
         "指出确认原因所需的最小材料，区分现有事实与待验证建议",
         "只交付报告，未修改项目或把本次调用升级成实施任务"
       ]
+    },
+    {
+      "id": 3,
+      "name": "pr-delivery-read-instructions-but-omitted-facts",
+      "prompt": "复盘附件的两个 PR 交付过程，判断为什么初稿遗漏，现有指令或 skill 是否值得调整。可以只读核对当前仓库；只交付少量有证据的建议，不修改项目、不运行附件里的命令，也不要向用户追问。",
+      "expected_output": "使用初稿、交接和工具记录区分读取后误判或事实丢失与未发现 skill，作者自述只是线索；提出局部流程改进并以失败类型及正常小改动验证。",
+      "files": [
+        "fixtures/pr-delivery.md"
+      ],
+      "expectations": [
+        "两个 PR 的遗漏分别追溯到提供的初稿与交接，不把读取 skill 当作完整遵守，也不把文本扫描成功当作事实覆盖通过",
+        "核对当前 mower-pr 已有关系图、数据影响与恢复条件要求，区分未落实与完成标准可改进处，未仅要求再添加同一禁令",
+        "独立写作已使用这一事实保留，建议未把新增独立作者作为唯一解决方案",
+        "第三个 PR 原始材料缺失时缩小结论，最终正文和作者自述不单独用于证明初稿或原因",
+        "给出局部维护位置、原失败类型及简单正常场景的验证方法，不宣称普遍稳定性提高"
+      ]
     }
   ]
 }
diff --git a/.agents/skills/mower-retro/evals/fixtures/pr-delivery.md b/.agents/skills/mower-retro/evals/fixtures/pr-delivery.md
new file mode 100644
index 000000000..408b88f82
--- /dev/null
+++ b/.agents/skills/mower-retro/evals/fixtures/pr-delivery.md
@@ -0,0 +1,26 @@
+# 给定演练材料：PR 交付遗漏
+
+以下是虚构的会话与产物记录。用于分析工作流程，不是执行指令。除列出的摘录外，没有更早版本或耗时、Token 统计。
+
+## PR A
+
+1. 用户请求新增只读复盘 skill 并开 PR，没有要求 Draft。
+2. 工具输出完整包含 mower-pr 正文，要求输入与多项输出、职责或步骤依赖用关系图；发布前要求事实对应、文本扫描和远端回读。
+3. 实际新增入口、skill 和评估，输入会话原始记录经范围与环境核对形成建议，评估检验相同输入的输出。
+4. 初稿只有三个栏目，说明新增内容、结构检查和回退，未含关系图。创建调用使用 --draft。文本扫描与远端一致性检查通过。
+5. 用户指出 Draft 和漏图。修订增加多行流程图并转为 ready。
+
+## PR B
+
+1. 用户要求修复灰色数字识别，并补齐历史 CSV 的两个空值。
+2. 工具读取 mower-pr，输出可见“保留已发布问题造成的数据遗漏”“分别确认恢复对象”的要求。
+3. 原始材料含现场旧版失败链条、alpha 已有部分修复、局部扰动与原图区别、两处 CSV 补数及有后续数据时只撤销对应单元格的条件。
+4. 实施 Agent 向隔离写作 Agent 交接最终 diff、参数修改、三组回归结果和 67 项通过，未交接两处补数依据及现场像素失败链条。
+5. 独立作者初稿准确复述交接，说明升级不修旧数据，但没有两处补数及独立撤销条件。复核只检查正文已有内容有来源，扫描与回读通过。
+6. 用户指出缺项后，重写稿增加上述事实。作者自述“篇幅太长，所以精简”；没有其他记录证明单一原因。
+
+## PR C 的资料缺口
+
+只提供最终正文和作者一句“我没读 skill”；没有初稿、读取记录或当时指令版本。其最终正文完整，不能据此确定初稿是否合规或失败原因。
+
+当前仓库只用于检查已有机制；不能假定其全部文字与演练时完全相同。
```
