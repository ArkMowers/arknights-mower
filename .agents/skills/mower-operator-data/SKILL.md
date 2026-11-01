---
name: mower-operator-data
description: 更新 Arknights Mower 新干员及基建技能数据，核对收益演算和养成规划自动合成的接入；不用于同步用户森空岛练度或只改排班。
---

# 新干员数据接入

以同一上游提交的游戏表更新共享目录，补齐受影响的演算规则和自动合成规则，保留既有干员顺序、技能解锁条件及用户配置。

## 确定来源与影响

- 先核对数据包上游：`.gitmodules` 中的 `ArknightsGameResource`、生成器 `auto_get_res_new.py` 和上游版本文件。资源图片仓库可能晚于游戏表；需要更新的数据尚未进入该仓库时，可使用 [ArknightsGameData](https://github.com/Kengxxiao/ArknightsGameData) 的国服表，固定 commit 后读取 `zh_CN/gamedata/excel/`。不要把资源包日期当成游戏表版本。
- 同一快照读取 `character_table.json`、`building_data.json`、`data_version.txt`，记录仓库、commit 及文件摘要。当前随软件发布的来源保存在 `arknights_mower/data/riic/operators.json` 的 `sourceVersion` 和 `source`。比较新增、删除及既有干员技能变更，不能只查新增姓名。
- 按[共享干员目录说明](../../../docs/subsystems/resource-update.md#shared-operator-catalog)维护数据。游戏定义、用户持有和练度各有自己的来源；缺少个人练度不能补成满练，未取得图片或完整资源时不能声称已更新完整资源包。

## 生成与适配

- 用 [`compile_operator_catalog`、`write_operator_catalog`](../../../arknights_mower/utils/operator_data.py) 从快照生成共享目录及姓名、职业兼容导出。`order` 传入旧目录的 `charId` 顺序；新干员追加，不手填技能槽或复制最终技能数组。写入实际 `sourceVersion`，保留可追溯的 `source`。前端从技能槽派生满练技能，不更新已不被读取的固定旧目录。
- 基建展示复用 `auto_get_res_new.py` 的 `获得干员基建描述`；自动合成复用 [`compile_workshop_data`](../../../arknights_mower/utils/workshop_rules.py)，只更新 `skill_data.json` 中对应的 `workshop` 部分时保留其他内容及紧凑 JSON 格式。需要完整养成、训练或头像更新时，按实际输入使用资源生成流程，不用不完整快照覆盖无关数据。
- 逐条核对新增与变更技能的设施、解锁阶段、对象、条件和叠加规则，再检查 `ui/src/riic/vendor/engine/`、`incomeClues.js` 与 `incomeRecruitment.js`。相同机制复用已有分支；未知技能不编造效率。群回先计算该技能的完整值，再在群回之间取最高；不能把其中的人数加成另叠加一次。技能术语明确的成员名单不能替换成国籍判断。
- 加工站核对 `workshop_rules.py`、`workshop_selection.py`、`workshop_recipes.py` 和实际分配入口。新增干员须同时满足持有、已解锁、未被排班占用、配方范围和心情条件。特殊副产品可能需要明确的优先级和材料范围，按用户要求与[养成规划说明](../../../docs/subsystems/growth-planning.md)确定；不能仅凭固定概率把该干员放入通用排序。培养参考、默认候选和实际执行副本须一致，旧手动配置不得被重写。
- 修改固定演算源码后更新 `ui/src/riic/vendor/source.json` 中对应 `localPatches` 摘要及理由，保留原始来源摘要。共享心情规则或目录变化后执行 `node scripts/build_mood_runtime.mjs`，软件附带的规则和数据一起更新；资源 OTA 不替换演算目录。

## 定向验证与交付

从真实入口验证新干员可被读取、技能阶段切换、正常效果及失效条件。收益演算至少覆盖实际 `calculateIncome` 调用；自动合成覆盖推荐、分配、排班排除及旧配置执行范围，不能只验证姓名存在或自己调用自己生成期望值。

按改动选择入口，在已激活的项目 Python 环境中运行，工作目录为仓库根：

```bash
pytest arknights_mower/tests/operator_data_tests.py arknights_mower/tests/workshop_rules_tests.py
npm --prefix ui test -- src/riic/operatorCatalog.test.js src/riic/incomeOperatorUpdate.test.js
python .agents/skills/mower-riic/scripts/verify_calculator.py
node scripts/build_mood_runtime.mjs --check
```

再加入实际改动的合成、线索、招募、心情或演算回归；仅运行相关离线测试。生产构建检查 Worker 和共享数据产物。新增或更新本 skill 后运行 skill-creator 的 `quick_validate.py` 及项目结构检查。交付上游提交、数据版本、技能覆盖、实际检查及未验证范围；提交或发布沿用用户授权，不自动合并 PR 或发布资源包。
