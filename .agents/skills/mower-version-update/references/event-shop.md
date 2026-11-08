# 当期 SS 活动更新

适用于 SS 活动更替、章节开放和活动商店导航维护。运行行为见 [Arknights Mower MAA 集成子系统说明](../../../../docs/subsystems/maa-integration.md#12-activity-shop-redemption)，资源格式见 [Arknights Mower 资源更新子系统说明](../../../../docs/subsystems/resource-update.md#activity-shop-resources)。活动入口和商店入口均自动定位，不维护用户手填坐标、确认文字或活动选择。

## 固定输入

从同一固定的 [ArknightsGameData](https://github.com/Kengxxiao/ArknightsGameData) 提交读取国服 `zh_CN/gamedata/excel/`，记录仓库、commit 及各输入文件的 SHA-256。

| 输入 | 必需数据 | 用途 |
| --- | --- | --- |
| `activity_table.json` | `basicInfo` 的活动 ID、名称、`hasStage`、`templateShopId`、`startTime`、`endTime`、`rewardEndTime`；`zoneToActivity` | 识别当前开放且有商店的 SS，绑定章节，区分活动结束和奖励领取截止 |
| `zone_table.json` | `zones` 中所属区域的 ID、名称和章节顺序 | 提供普通、EX、S 章节名称和活动入口关键词，不能只读取已经有作战关卡的区域 |
| `stage_table.json` | `stages` 的 `code`、`zoneId`、`stageDropInfo.displayDetailRewards`；生成完整关卡数据时仍保留有效期和掉落 | 关联实际关卡与章节，提取 `ACTIVITY_ITEM` 代币 ID |
| MAA 物品资源 | 与代币 ID 对应的 `resource/template/items/ID.png`，以及实际安装使用的增量资源 | 在终端和活动首页定位代币图标，不复制上一期的点击坐标 |

SS ID 识别沿用生成器中的 `act数字side` 和复刻 `act数字sre`。同时要求存在关卡和商店。新活动改变这些约定时，修正生成器和测试，不能将小游戏、签到或其他类型商店当成 SS。

活动开放期使用 `startTime <= now < endTime`。`rewardEndTime` 仅记录商店奖励领取截止；不能用仍开放的旧商店冒充当期 SS。没有开放的 SS 时，正常产物是 `[]`，兑换开关保留用户选择并在运行时跳过。输入表缺失、章节关联不全或代币 ID 缺失属于生成失败，不能伪装成没有活动。

## 生成导航数据

`auto_get_res_new.py` 将活动表、`zone_table.json` 的 `zones` 和 `stage_table.json` 的 `stages` 交给 `write_event_shop_data`，生成 `arknights_mower/data/event_shop.json`。局部生成可在仓库根运行：

```python
import json
from pathlib import Path
from arknights_mower.utils.event_shop_data import write_event_shop_data

source = Path("/tmp/game")
activity = json.loads((source / "activity_table.json").read_text("utf-8"))
zones = json.loads((source / "zone_table.json").read_text("utf-8"))["zones"]
stages = json.loads((source / "stage_table.json").read_text("utf-8"))["stages"]
write_event_shop_data(activity, zones=zones, stages=stages)
```

核对产物中的 `activity_id`、`activity`、`start_ts`、`end_ts`、`reward_end_ts`、`entry_names`、`chapters` 和 `token_ids`，并同步活动关卡的导航名称。`chapters` 使用 `normal`、`ex`、`s`，不写专有活动名到导航源码。

章节优先按实际关卡编号和区域关联分类。标准三区式 SS 的后续 EX、S 关卡可能尚未进入关卡表，但 `zone2`、`zone3` 的名称已经存在于区域表；生成器保留这两区的标题。逐期核对公告、区域表和实际菜单的对应关系。不同布局、同类多个区域或无法确认的分类不能靠名称猜测；完善解析后再以关卡编号前缀确认目标地图。

活动名称、区域名称和 OCR 文本统一去除全部空白再比较，包括首尾、内部空格、制表符和全角空白。例如复刻名称中的空格或 OCR 插入的空格不应让图片匹配的备用路径失效。入口提示只检测所属活动或章节名称关键词，不依赖引号和“已开放”等整句文案。

## 验证共用导航

导航实现位于 [`activity_navigation.py`](../../../../arknights_mower/solvers/activity_navigation.py)。`NavigationSolver` 的活动关卡导航和 `EventShopNavigation` 的商店导航共用活动首页定位；大型任务自动作业继续通过 `NavigationSolver.run(关卡编号)` 调用同一路径。这是 Python 内部调用，不要求新增 HTTP 接口。

- 终端左侧搜索目标活动代币图标，点击检测到的位置；缺图或未匹配时回退名称关键词。活动首页再搜索同一代币定位商店入口，位置和比例可以不同。核对 MAA 资源中实际存在对应图标及正确加载路径；缺图时更新 MAA 资源，不新增手填窗口。
- 点击后确认目标活动页面。普通、EX、S 章节进入后须出现对应关卡编号前缀；未解锁章节或错误地图不能算成功，也不能仅凭画面变化开始作业。
- 商店页面同时确认关闭或兑换截止信息及商品库存、售罄或已拥有标记。只见到活动首页、代币数量或专有标题不能证明已经进入可兑换页面。
- MAA 的 `SS@Store@Begin` 负责标准当期活动商店的货架和支付流程，不能推定其他特殊商店也支持。Mower 仅在页面确认后提交该固定任务；黑名单与原有方案切换条件保持独立。

在已有项目 Python 环境中运行针对性离线验证：

```bash
python -m pytest arknights_mower/tests/event_shop_generation_tests.py arknights_mower/tests/activity_navigation_tests.py arknights_mower/tests/activity_banner_navigation_tests.py arknights_mower/tests/maa_event_shop_tests.py arknights_mower/tests/maa_large_task_navigation_tests.py arknights_mower/tests/event_shop_defaults_tests.py
python -m pytest arknights_mower/tests/res_version_tests.py arknights_mower/tests/resource_version_tests.py
npm --prefix ui test -- src/components/MaaEventShop.test.js src/stores/maaProtocolSync.test.js
```

关卡导航和周计划商店准入共用 `utils/activity_stage.py` 的活动归属解析。验证周计划只有 EX 或 S 关卡、关卡表只有同活动普通关卡时，仍能用当期章节资源通过准入；缺少章节或编号前缀有歧义时应跳过。商店准入使用已经选中的当期活动数据，不能改用另一个时间点或资源版本判断归属。

覆盖没有 SS、尚未开始、已经结束、只有其他类型活动、当前 SS 不在周计划、多个同期开启候选、代币位置与缩放变化、空白文本、错误地图和旧配置兼容。没有当期 SS 时断言不启动导航和 MAA 商店任务。

用户要求实机验证时，先确认目标实例及自动任务状态。固定 ADB 目标，仅验证活动首页、已开放章节和商店的进入结果，不因验证导航而购买商品或开始作战。未开放的 S 章记录为未进入，并用离线测试验证其正常分支。区分实际设备画面、离线识别和未验证的购买流程；不能把一次活动的成功扩大为所有活动均已实测。

## 打包与交付

沿用 MowerResource 的资源生成和发布流程，确认它使用包含本次生成器的版本。实际读取完整 ZIP，核对 `event_shop.json` 的活动、章节和代币数据，再用 `package_file_paths` 和 `content_hash` 复算归档摘要。局部更新主仓内置文件时同步 `data/version.json` 的内容摘要，保留日期前缀及其他来源字段。

交付固定输入版本与摘要、当前 SS 判定、章节和代币信息、实际归档检查、导航验证及未验证范围。仅请求更新技能不构成发布资源、部署软件或操作实例的授权；实际提交、发布和实机验证沿用用户当次要求。更新本技能后运行 `skill-creator` 的 `quick_validate.py` 和项目文档结构检查。
