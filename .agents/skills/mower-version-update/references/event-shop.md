# 当期 SS 活动更新

适用于 SS 活动更替、章节开放和活动商店导航维护。运行行为见 [Arknights Mower MAA 集成子系统说明](../../../../docs/subsystems/maa-integration.md#12-activity-shop-redemption)，资源格式见 [Arknights Mower 资源更新子系统说明](../../../../docs/subsystems/resource-update.md#activity-shop-resources)。终端自动识别活动入口，商店入口由导航代码按活动期次维护固定坐标。

## 固定输入

从同一固定的 [ArknightsGameData](https://github.com/Kengxxiao/ArknightsGameData) 提交读取国服 `zh_CN/gamedata/excel/`，记录仓库、commit 及各输入文件的 SHA-256。

| 输入 | 必需数据 | 用途 |
| --- | --- | --- |
| `activity_table.json` | `basicInfo` 的活动 ID、名称、`hasStage`、`templateShopId`、`startTime`、`endTime`、`rewardEndTime`；`zoneToActivity` | 识别当前开放且有商店的 SS，绑定章节，区分活动结束和奖励领取截止 |
| `zone_table.json` | `zones` 中所属区域的 ID、名称和章节顺序 | 提供普通、EX、S 章节名称和活动入口关键词，不能只读取已经有作战关卡的区域 |
| `stage_table.json` | `stages` 的 `code`、`zoneId`、`stageDropInfo.displayDetailRewards`；生成完整关卡数据时仍保留有效期和掉落 | 关联实际关卡与章节，提取 `ACTIVITY_ITEM` 代币 ID |
| `item_table.json` | `items` 中代币对应的 `iconId` | 查找复刻代币实际使用的图标 |
| MAA 物品资源 | 与代币 ID 或图标 ID 对应的 `resource/template/items/ID.png`，以及实际安装使用的增量资源 | 在终端定位活动代币图标 |

SS ID 识别沿用生成器中的 `act数字side` 和复刻 `act数字sre`。同时要求存在关卡和商店。新活动改变这些约定时，修正生成器和测试，不能将小游戏、签到或其他类型商店当成 SS。

生成前对照[活动商店资源约定](../../../../docs/subsystems/resource-update.md#activity-shop-resources)核对当期和下一期 SS。遇到预载更新时，检查同一资源包能否在活动开始前识别当期 SS，并在复刻开放后识别复刻 SS。商店奖励领取截止沿用 `rewardEndTime`。

在标准 1920×1080 活动首页核对商店按钮的点击位置。按活动 ID 与作战开始时间在 [`SHOP_ENTRANCE_POINTS`](../../../../arknights_mower/solvers/event_shop.py) 登记坐标，复刻和再次开放时分别核对对应期次的画面。

## 生成导航数据

`auto_get_res_new.py` 调用 `write_event_shop_data` 生成 `arknights_mower/data/event_shop.json`。局部生成可在仓库根运行以下代码。

```python
import json
from pathlib import Path
from arknights_mower.utils.event_shop_data import write_event_shop_data

source = Path("/tmp/game")
activity = json.loads((source / "activity_table.json").read_text("utf-8"))
zones = json.loads((source / "zone_table.json").read_text("utf-8"))["zones"]
stages = json.loads((source / "stage_table.json").read_text("utf-8"))["stages"]
items = json.loads((source / "item_table.json").read_text("utf-8"))["items"]
write_event_shop_data(activity, zones=zones, stages=stages, items=items)
```

核对产物中的 `activity_id`、`activity`、`start_ts`、`end_ts`、`reward_end_ts`、`entry_names`、`chapters` 和 `token_ids`，以及实际用于模板查找的 `token_icon_ids`。同步活动关卡的导航名称。`chapters` 使用 `normal`、`ex`、`s`。

章节优先按实际关卡编号和区域关联分类。标准三区式 SS 的后续 EX、S 关卡可能尚未进入关卡表，但 `zone2`、`zone3` 的名称已经存在于区域表；生成器保留这两区的标题。逐期核对公告、区域表和实际菜单的对应关系。不同布局、同类多个区域或无法确认的分类不能靠名称猜测；完善解析后再以关卡编号前缀确认目标地图。

活动名称、区域名称和 OCR 文本统一去除全部空白再比较，包括首尾、内部空格、制表符和全角空白。例如复刻名称中的空格或 OCR 插入的空格不应让图片匹配的备用路径失效。入口提示只检测所属活动或章节名称关键词，不依赖引号和“已开放”等整句文案。

## 验证共用导航

导航实现位于 [`activity_navigation.py`](../../../../arknights_mower/solvers/activity_navigation.py)。`NavigationSolver` 的活动关卡导航和 `EventShopNavigation` 的商店导航共用活动首页定位；大型任务自动作业继续通过 `NavigationSolver.run(关卡编号)` 调用同一路径。这是 Python 内部调用，不要求新增 HTTP 接口。

- 终端左侧搜索目标活动代币图标，点击检测到的位置。缺图或未匹配时回退名称关键词。复刻时核对代币物品 ID 和 `iconId`，并确认配置的 MAA 安装或增量资源含对应模板。
- 关卡导航进入活动后确认目标活动页面。普通、EX、S 章节进入后须出现对应关卡编号前缀；未解锁章节或错误地图不能算成功，也不能仅凭画面变化开始作业。
- 商店导航选中活动后，在 5 秒观察预算内确认活动首页。截图 I/O 和共享 OCR 使用剩余时间。进程内 OCR 的同步推理可能在截止后才返回，超时结果会被丢弃。新画面须同时显示目标活动名或章节名，以及「作战结束时间」，确认后点击该期次的固定坐标。背景动画可以继续播放。未登记坐标或首页确认失败时跳过兑换。商店页面同时确认关闭或兑换截止信息及商品库存、售罄或已拥有标记。只见到活动首页、代币数量或专有标题不能证明已经进入可兑换页面。
- MAA 的 `SS@Store@Begin` 负责标准当期活动商店的货架和支付流程，不能推定其他特殊商店也支持。Mower 仅在页面确认后提交该固定任务；黑名单与原有方案切换条件保持独立。

在已有项目 Python 环境中运行针对性离线验证：

```bash
python -m pytest arknights_mower/tests/event_shop_generation_tests.py arknights_mower/tests/activity_navigation_tests.py arknights_mower/tests/activity_banner_navigation_tests.py arknights_mower/tests/maa_event_shop_tests.py arknights_mower/tests/maa_large_task_navigation_tests.py arknights_mower/tests/event_shop_defaults_tests.py
python -m pytest arknights_mower/tests/res_version_tests.py arknights_mower/tests/resource_version_tests.py
npm --prefix ui test -- src/components/MaaEventShop.test.js src/stores/maaProtocolSync.test.js
```

商店准入仍要求当前理智周计划包含关卡数据中已收录的当期活动关卡，不额外推断尚未收录的 EX、S 关卡归属。即使章节资源已提供 EX、S 标题，仅有这些未收录关卡的周计划也应跳过商店；关卡导航继续支持使用章节信息进入 EX、S。

覆盖没有 SS、预载后尚未开始、复刻开放切换、已经结束、只有其他类型活动、当前 SS 不在周计划、多个同期开启候选、代币位置与缩放变化、空白文本、错误地图和旧配置兼容。没有当期 SS 时断言不启动导航和 MAA 商店任务。

用户要求实机验证时，先确认目标实例及自动任务状态。固定 ADB 目标，仅验证活动首页、已开放章节和商店的进入结果，不因验证导航而购买商品或开始作战。未开放的 S 章记录为未进入，并用离线测试验证其正常分支。区分实际设备画面、离线识别和未验证的购买流程；不能把一次活动的成功扩大为所有活动均已实测。

## 打包与交付

沿用 MowerResource 的资源生成和发布流程，确认它使用包含本次生成器的版本。实际读取完整 ZIP，核对 `event_shop.json` 的活动、章节和代币数据，再用 `package_file_paths` 和 `content_hash` 复算归档摘要。局部更新主仓内置文件时同步 `data/version.json` 的内容摘要，保留日期前缀及其他来源字段。

交付固定输入版本与摘要、当前 SS 判定、章节和代币信息、实际归档检查、导航验证及未验证范围。仅请求更新技能不构成发布资源、部署软件或操作实例的授权；实际提交、发布和实机验证沿用用户当次要求。更新本技能后运行 `skill-creator` 的 `quick_validate.py` 和项目文档结构检查。
