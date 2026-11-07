# 活动商店更新

适用于从客户端布局获取商店入口、确认标题，并随资源包更新的版本维护。运行时行为见 [Arknights Mower MAA 集成子系统说明](../../../../docs/subsystems/maa-integration.md#12-activity-shop-redemption)，资源格式及独立加载规则见 [Arknights Mower 资源更新子系统说明](../../../../docs/subsystems/resource-update.md#activity-shop-resources)。本过程不执行兑换，也不修改用户的商店覆盖设置。

## 固定输入

1. 固定 [ArknightsGameData](https://github.com/Kengxxiao/ArknightsGameData) 的国服提交，读取 `activity_table.json` 及生成活动关卡所需的 `stage_table.json`、`zone_table.json`、`story_review_table.json`、`retro_table.json`。记录输入摘要。活动名称和商店开放窗口以 `basicInfo` 为准；商店关闭使用 `rewardEndTime`，不能用战斗关卡结束时间代替。
2. 固定 [ArknightsAssets2](https://github.com/ArknightsAssets/ArknightsAssets2) 的 `cn` 提交，读取 `bundles/hot_update_list.json`。从官方 `network_config` 的 `hu` 字段取得下载根地址，按清单的 `versionId` 下载目标活动包。官方路径编码沿用上游 [资源下载脚本](https://github.com/ArknightsAssets/ArknightsAssets/blob/cn/scripts/download_bundles.sh)：包名的 `/` 改为 `_`、扩展名改为 `.dat`。
3. `.dat` 是 ZIP。`totalSize` 对应下载文件大小；`abSize` 和 `md5` 对应其中解压后的 `.ab`，不能把两者混用。只处理清单声明的目标成员，不将任意归档路径解压进仓库。
4. 从同一固定图片提交查看商店标题原图和入口图。核对 `confirm_text` 是进入商店后实际可见的完整标题，而非活动名称、英文副标题或商品名称。标题可能烘焙在图片中，不能假定存在可直接读取的字符串字段。

本次已核对的入口是 `act55side` 的 `btn_shop`，位于 `dyn/activity/[uc]act55side/prefabs/act55side_activity_stage.prefab`。标题图片路径和来源清单保存在 [生成输入](../../../../arknights_mower/data/event_shop_layouts.json) 的 `source` 中；后续活动必须重新核对，不能沿用本次坐标或标题。

## 导出和计算坐标

该版本活动包采用自定义压缩，普通 UnityPy 解包失败。使用上游 ArknightsStudioCLI 导出字段及完整对象清单；它位于 ArknightsAssets 仓库的 `ArknightsStudioCLI` 目录。固定工具版本，并准备匹配的 .NET 运行时。命令示例在仓库根执行，输入与输出使用本次临时目录：

本次使用 [工具提交](https://github.com/ArknightsAssets/ArknightsAssets/tree/c0be4e4428f79c7e87c6889067a6906361ae979b/ArknightsStudioCLI)中的 `v1.2.1.0`，目标运行时为 .NET 6；本次在 .NET 9 下通过 `DOTNET_ROLL_FORWARD=LatestMajor` 执行。后续提取先核对工具的 `--help` 和实际包格式，不将兼容运行结果推定为所有版本均可用。

```bash
dotnet /tmp/studio/ArknightsStudioCLI.dll /tmp/shop/activity.ab -m dump -t all --load-all -o /tmp/shop/dump
dotnet /tmp/studio/ArknightsStudioCLI.dll /tmp/shop/activity.ab -m info --load-all --export-asset-list xml -o /tmp/shop/list
```

导出前确认真实按钮对象及其所属 prefab。GameObject 重名时，导出文件会带编号后缀；必须通过组件指针及父级关系识别，不能取第一个同名对象。`source-json` 按现有生成输入的 `source` 记录图片仓库及固定 `revision`、清单 `version` 和 `manifest`、官方包 URL、`prefab` 及标题图片路径。然后执行：

```bash
python .agents/skills/mower-version-update/scripts/extract_shop_layout.py \
  --dump /tmp/shop/dump --asset-list /tmp/shop/list/assets.xml \
  --activity-table /tmp/game/activity_table.json --source-json /tmp/shop/source.json \
  --downloaded-asset /tmp/shop/activity.dat --activity-id act55side \
  --container 'dyn/activity/[uc]act55side/prefabs/act55side_activity_stage.prefab' \
  --confirm-text '炮火所掩埋的'
```

脚本校验包大小和摘要，沿完整 RectTransform 父链记录锚点、尺寸、枢轴、偏移与缩放。它按标准 1920×1080 根画面计算按钮范围，将 Unity 向上的 Y 轴转换为屏幕向下的 Y 轴，取中心并四舍五入为点击整数。按钮范围保留在原始布局中，可用 `event_shop_data.button_rect` 重新计算。所有主视觉分支必须给出相同范围；未知旋转、越界、循环父链、缺失对象或分支位置不一致时停止生成，不能猜坐标。

该结果是静态布局在指定画面下的坐标。还需核对动画结束后的布局、画面适配和运行时脚本是否重排按钮；没有画面证据时不能声称经过实机校准。本次两套主视觉的范围均为约 `(1361.28, 205.08)` 至 `(1561.28, 305.08)`，中心为 `(1461.2812532, 255.0799474)`，点击位置为 `(1461, 255)`。

## 生成、验证与交付

- `auto_get_res_new.py` 调用 `write_event_shop_data`，从已核对布局和本次活动表生成 `arknights_mower/data/event_shop.json`。活动表缺少已适配活动或商店 ID 不符时失败，不用空表覆盖有效条目。布局源是生成期输入，不进入资源归档；产物继续使用既有可选资源格式，旧资源缺文件时不借用内置数据。
- 同步生成活动关卡，确认当前活动关卡的导航名称与商店 `activity` 一致，否则日常兑换的周计划准入不能识别该活动。保持用户自定义坐标、标题、黑名单和方案切换选择。
- 在项目 Python 环境运行 `event_shop_generation_tests.py`、`maa_event_shop_tests.py` 和两组资源版本测试；从生成后的实际文件验证商店选择、战斗结束后的领取窗口、过期排除，以及导航点击和标题确认。测试只控制设备 I/O，不执行真实兑换。
- 资源抓取和发布继续使用 MowerResource。核对其游戏表来源是否已包含本活动、图片是否齐全、生成器是否已取到本次代码。发布脚本须收集主仓声明的 `RES_PACKAGE_OPTIONAL_DATA`；实际打开完整 ZIP，确认商店条目可读取、布局源未混入归档，并用真实归档文件集复算内容摘要。仅检查生成目录不能证明已经打包。同步内置内容摘要；不另建定时发布流程。独立资源发布不会自动提交主仓库内置文件。
- 若用户将“活动商店能够更新”作为本次 PR 的合并条件，先完成生成、实际归档读取及最新 head 的必要检查；空表、只写文档或未经核实的坐标均不满足该条件。合并和发布沿用用户的具体授权，不因 skill 自行扩大范围。

更新本 skill 后运行 `skill-creator` 的 `quick_validate.py`、项目结构检查及脚本实际提取验证。交付固定来源、按钮范围和整数坐标、标题、开放窗口、归档与导航验证结果，并区分静态布局验证、设备 I/O 测试和实际设备证据。
