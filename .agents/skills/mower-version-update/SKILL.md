---
name: mower-version-update
description: 更新 Arknights Mower 游戏版本数据与配套资源，核对新干员、演算与心情、自动合成、专精协助者及活动商店的生成和验证；不用于同步用户练度或只改排班。
---

# 游戏版本更新

从固定的游戏表和图片快照生成本次版本受影响的数据及资源。新增干员时，以同一上游提交更新共享目录，补齐受影响的演算、自动合成和专精协助者规则，保留既有干员顺序、技能解锁条件及用户配置。

版本更新按实际变化核对干员数据、图片与姓名识别、养成数据、活动关卡和商店。涉及商店入口、名称或坐标时，读取[活动商店更新](references/event-shop.md)，使用附带脚本从客户端布局生成 1920×1080 坐标；未经核实的布局不能作为已完成适配交付。

## 确定来源与影响

- 先核对数据包上游：`.gitmodules` 中的 `ArknightsGameResource`、生成器 `auto_get_res_new.py` 和上游版本文件。资源图片仓库可能晚于游戏表；需要更新的数据尚未进入该仓库时，可使用 [ArknightsGameData](https://github.com/Kengxxiao/ArknightsGameData) 的国服表，固定 commit 后读取 `zh_CN/gamedata/excel/`。不要把资源包日期当成游戏表版本。
- 同一快照读取 `character_table.json`、`building_data.json`、`data_version.txt`，记录仓库、commit 及文件摘要。当前随软件发布的来源保存在 `arknights_mower/data/riic/operators.json` 的 `sourceVersion` 和 `source`。比较新增、删除及既有干员技能变更，不能只查新增姓名。
- 按[共享干员目录说明](../../../docs/subsystems/resource-update.md#shared-operator-catalog)维护数据。游戏定义、用户持有和练度各有自己的来源；缺少个人练度不能补成满练，未取得图片或完整资源时不能声称已更新完整资源包。

## 自动生成与人工适配

| 对象 | 既有生成路径 | 需要人工核对或修复的情况 |
| --- | --- | --- |
| 姓名、职业、技能描述、解锁条件及完整养成数据 | 游戏表经 `auto_get_res_new.py` 生成共享目录、兼容导出和 `skill_data.json` | 输入表不齐或仅局部生成时，逐项说明未更新内容；不能从训练规则更新推定技能真名、材料和耗时已更新 |
| 头像、技能图标及姓名识别产物 | MowerResource 抓取图片，生成姓名模板和识别模型 | 上游缺图、字体缺字或游戏显示变化导致生成或识别失败时，修复对应来源和生成步骤；不逐人手填生成文件 |
| 收益、心情、加工和专精技能机制 | 已支持的机制由已有规则处理 | 新条件、叠加关系、技能语法、分支或成员范围需要扩展解析和计算规则，并从实际入口验证 |
| 加工优先级、默认专精路线和固定名单 | 现有策略读取 `workshop_recipes.py`、`workshop_selection.py`、`mastery.py` 和 `mastery_support_types.py` 等维护配置 | 新技能改变策略时核对是否调整；例如特殊加工优先级和 `CONTROL_TRAINERS`，不能因角色表新增就假定已同步 |

共享目录和配套演算、原生心情代码随软件发布；资源 OTA 不替换这些计算输入。MowerResource 自动出包不代表主仓库内置文件或软件规则已自动提交更新。

## 生成与适配

- 用 [`compile_operator_catalog`、`write_operator_catalog`](../../../arknights_mower/utils/operator_data.py) 从快照生成共享目录及姓名、职业兼容导出。`order` 传入旧目录的 `charId` 顺序；新干员追加，不手填技能槽或复制最终技能数组。写入实际 `sourceVersion`，保留可追溯的 `source`。前端从技能槽派生满练技能，不更新已不被读取的固定旧目录。
- 基建展示复用 `auto_get_res_new.py` 的 `获得干员基建描述`；自动合成复用 [`compile_workshop_data`](../../../arknights_mower/utils/workshop_rules.py)，专精协助者规划复用 [`compile_training_data`](../../../arknights_mower/utils/mastery_rules.py)。新干员更新同时核对 `skill_data.json` 的 `workshop` 和 `training`，不能只更新姓名或加工站数据。局部生成时只替换有完整输入的部分，保留其他内容及紧凑 JSON 格式；完整养成数据和头像按实际输入沿用资源生成流程。
- 逐条核对新增与变更技能的设施、解锁阶段、对象、条件和叠加规则，再检查 `ui/src/riic/vendor/engine/`、`incomeClues.js` 与 `incomeRecruitment.js`。相同机制复用已有分支；未知技能不编造效率。群回先计算该技能的完整值，再在群回之间取最高；不能把其中的人数加成另叠加一次。技能术语明确的成员名单不能替换成国籍判断。
- 加工站核对 `workshop_rules.py`、`workshop_selection.py`、`workshop_recipes.py` 和实际分配入口。新增干员须同时满足持有、已解锁、未被排班占用、配方范围和心情条件。特殊副产品可能需要明确的优先级和材料范围，按用户要求与[养成规划说明](../../../docs/subsystems/growth-planning.md)确定；不能仅凭固定概率把该干员放入通用排序。培养参考、默认候选和实际执行副本须一致，旧手动配置不得被重写。
- 专精协助者核对 `mastery_rules.py`、`mastery_support_data.py` 和 `mastery_support.py`，从实际 `plan_supports` 与职业路线预览验证持有、解锁阶段、非训练室排班排除和目标职业、分支条件。只有条件加成的技能不能把上游 `efficiency` 当作无条件加成；多个可选分支各自匹配且只生效一次，通用职业路线不假定具体分支。生成规则保留既有资源读取格式；新干员作为被训练者也须能进入规划。更新训练规则不代表已补齐专精材料、技能真名或其他养成数据，需分别核对实际来源。
- 修改固定演算源码后更新 `ui/src/riic/vendor/source.json` 中对应 `localPatches` 摘要及理由，保留原始来源摘要。共享心情规则或目录变化后执行 `node scripts/build_mood_runtime.mjs`，软件附带的规则和数据一起更新；资源 OTA 不替换演算目录。
- 资源抓取、完整生成和发布沿用 [MowerResource](https://github.com/ArkMowers/MowerResource) 的流程；`auto_get_res_new.py` 在生成结束时自动写入资源版本，不另建一套发布或定时更新流程。若本次只在主仓库局部更新资源文件，提交前用 `res_version.py` 的 `package_file_paths` 与 `content_hash` 同步 `arknights_mower/data/version.json` 的内容摘要，保留原有日期前缀、上游版本、活动和卡池字段。不能因为没有发布完整资源包，就保留与实际内置文件不符的摘要。

## 定向验证与交付

从真实入口验证新干员可被读取、技能阶段切换、正常效果及失效条件。收益演算至少覆盖实际 `calculateIncome` 调用；自动合成覆盖推荐、分配、排班排除及旧配置执行范围；专精协助者覆盖实际方案、条件加成与通用职业路线的区别，不能只验证姓名存在或自己调用自己生成期望值。

按改动选择入口，在已激活的项目 Python 环境中运行，工作目录为仓库根：

```bash
pytest arknights_mower/tests/operator_data_tests.py arknights_mower/tests/workshop_rules_tests.py
pytest arknights_mower/tests/mastery_operator_update_tests.py arknights_mower/tests/mastery_support_rules_tests.py arknights_mower/tests/mastery_support_optimizer_tests.py arknights_mower/tests/mastery_support_preview_tests.py
pytest arknights_mower/tests/bundled_operator_resources_tests.py arknights_mower/tests/resource_version_tests.py arknights_mower/tests/res_version_tests.py
npm --prefix ui test -- src/riic/operatorCatalog.test.js src/riic/incomeOperatorUpdate.test.js
python .agents/skills/mower-riic/scripts/verify_calculator.py
node scripts/build_mood_runtime.mjs --check
```

再加入实际改动的合成、线索、招募、心情或演算回归；仅运行相关离线测试。生产构建检查 Worker 和共享数据产物。新增或更新本 skill 后运行 skill-creator 的 `quick_validate.py` 及项目结构检查。交付上游提交、数据版本、技能覆盖、实际检查及未验证范围；提交或发布沿用用户授权，不自动合并 PR 或发布资源包。
