# UI 多语言译名查找与来源

本页说明维护英文、日文与繁体中文界面时如何核对游戏名称和社区用法。来源核对日期为 2026-10-27；以下内容记录译名来源和显示资源的核对方式；界面语言不表示 Mower 支持对应地区的游戏客户端。本试验的实际翻译范围、设置入口和保存行为见 [Arknights Mower Web 访问子系统说明的界面语言规则](../subsystems/web-access.md#ui-language)。

[Arknights Mower 项目术语表](../../CONTEXT.md)及其[中文版](../../CONTEXT.zh.md)定义本项目的业务概念。翻译仍沿用其中的含义；游戏内显示名称与 Mower 自有操作需要分别核对。

## 查找一个译名

1. 先确定文字指向的对象：游戏内设施、干员或物品，Mower 的排班与恢复操作，或普通软件操作。不要仅按中文字符串相同就合并翻译。
2. 游戏内对象优先按相同资源 ID 核对中英文游戏表。检查两个版本是否都存在该对象；缺少官方名称的专有名词保留原名，通用选项和效果说明按当前中文含义翻译，不把项目译文标为官方译名。
3. 使用 MAA 的英文界面文件和 Arknights Toolbox 的语言文件核对社区习惯，再用 Arknights Terra Wiki 检查玩家常用的名称和简称。来源不一致时，回到游戏表和本项目的实际含义确认。
4. 按本项目的完整操作独立编写帮助与提示，记录所参考的来源和版本。不要把其他工具的操作说明直接换项目名后使用。
5. 检查语言切换前后的请求、配置和条件表达式。只改变显示文字；干员名、设施名等已有内部值继续用于读取、保存和业务判断。

## 已核验的游戏名称

MAA 当前英文界面中的 `Infrast.Room.*` 使用下表九种设施名称，与英文游戏表一致。参考 [MAA 英文语言文件](https://github.com/MaaAssistantArknights/MaaAssistantArknights/blob/877f3e235e9f7ca47d5b3fc5033d6b4fa3faf265/src/MaaWpfGui/Res/Localizations/en-us.xaml#L1353)；游戏表的同 ID 对照见[英文 building_data.json](https://github.com/ArknightsAssets/ArknightsGamedata/blob/a6d4731c10edc58a70ee71b0b77b9f687af13d59/en/gamedata/excel/building_data.json)与[中文 building_data.json](https://github.com/ArknightsAssets/ArknightsGamedata/blob/a6d4731c10edc58a70ee71b0b77b9f687af13d59/cn/gamedata/excel/building_data.json)。这些镜像用于开发时核对；运行时读取本地打包的显示资源，不请求镜像。

| 中文显示名 | 英文显示名 | 游戏表中的房间类型 |
| :--- | :--- | :--- |
| 控制中枢 | Control Center | `CONTROL` |
| 发电站 | Power Plant | `POWER` |
| 制造站 | Factory | `MANUFACTURE` |
| 贸易站 | Trading Post | `TRADING` |
| 宿舍 | Dormitory | `DORMITORY` |
| 加工站 | Workshop | `WORKSHOP` |
| 办公室 | Office | `HIRE` |
| 训练室 | Training Room | `TRAINING` |
| 会客室 | Reception Room | `MEETING` |

基建界面可使用 Base，干员与心情的玩家常用显示词分别为 Operator 和 Morale。Arknights Toolbox 的[通用英文语言文件](https://github.com/arkntools/arknights-toolbox/blob/9b22e35d2bd5857894ccf8792301b180e2ccb91d/src/locales/us/common.json)包含后两项；MAA 的[英文基建说明](https://docs.maa.plus/en-us/manual/introduction/infrastructure.html)使用基建与换班的相应用法。项目内部概念仍按术语表的 [Operator Mood](../../CONTEXT.md#operator-mood) 理解，`mood` 等真实代码标识保持不变。

Arknights Terra Wiki 的[基建页面](https://arknights.wiki.gg/wiki/Base)和[办公室页面](https://arknights.wiki.gg/wiki/HR_Office)可用于检查玩家用法。后者的页面标题是 Human Resources Office，并说明 Office 是常用简称；界面不必因页面标题更长就替换游戏内短名称。本次 Wiki 正文直连返回 HTTP 403，只通过检索结果核对到相应内容，因此设施表优先采用直接读取的游戏表和 MAA 源码。

同一次游戏数据核对中，中文表包含 `RECYCLE`，英文表不包含该类型。因此不能仅凭该中文条目为回收站指定一个“已核实的英文客户端名称”。后续翻译应重新检查对应版本，而不是从其他设施的命名规律推断。

## Mower 自有界面文字

任务设置中的 MAA 选项沿用同一版本[英文语言文件中的集成战略主题](https://github.com/MaaAssistantArknights/MaaAssistantArknights/blob/877f3e235e9f7ca47d5b3fc5033d6b4fa3faf265/src/MaaWpfGui/Res/Localizations/en-us.xaml#L1644)与[生息演算选项](https://github.com/MaaAssistantArknights/MaaAssistantArknights/blob/877f3e235e9f7ca47d5b3fc5033d6b4fa3faf265/src/MaaWpfGui/Res/Localizations/en-us.xaml#L2397)：生息演算使用 Tales Within the Sand 与 RELAUNCH ANCHOR，隐秘战线使用 Hidden Front。集成战略主题改用完整的官方名称：Phantom & Crimson Solitaire、Mizuki & Caerula Arbor、Expeditioner's Jǫklumarkar、Sarkaz's Furnaceside Fables 和 Sui's Garden of Grotesqueries。后两项可分别核对[官方预告片](https://www.youtube.com/watch?v=BXT-fn7NvX8)和[官方专题页](https://arknights.global/gardenofgrotesqueries/)，不再将 MAA 的简称作为完整游戏名称。对应中文配置值及主题 ID 保持不变；较新内容仍显示全部选项；已核验的官方名称优先，缺少官方名称时区分保留的专有名词与独立编写的项目译文。

排班表按术语表已有的 [Scheduling Plan](../../CONTEXT.md#scheduling-plan) 含义翻译，描述换班动作时可使用社区常见的 shift change。运行日志的界面标签可使用 Logs；[Arknights Mower 养成规划子系统说明](../subsystems/growth-planning.md)说明干员养成目标的范围，英文界面按其中的 Operator Growth Planning 理解。这些界面措辞不能因为出现在游戏工具中，就标成游戏官方功能名称。

MAA 和 Arknights Toolbox 能提供通用操作、游戏名称和玩家用法参考，但 Mower 的主班、副表、救急和恢复条件仍由本项目定义。翻译提示前，应阅读调用者和负责该行为的子系统说明，保留原有条件、限制和失败结果。

## 后续查找干员与材料名称

对于干员和材料，先使用相同的 `char_id` 或 `itemId` 对齐不同语言的记录，不按中文名称猜测、拼音转换或逐词翻译。当前[多地区游戏数据镜像](https://github.com/ArknightsAssets/ArknightsGamedata/tree/a6d4731c10edc58a70ee71b0b77b9f687af13d59)同时包含 `cn` 和 `en` 等目录；可在本地查词时读取所需字段。仓库只包含界面使用的显示字段，来源版本保存在相应 JSON 中；完整游戏表和查词缓存不加入仓库，也不接入运行时更新。

实际核验的例子是 `itemId=3003`：中文为赤金，英文为 Pure Gold；`itemId=4001` 对应龙门币与 LMD。对照来源为[中文 item_table.json](https://github.com/ArknightsAssets/ArknightsGamedata/blob/a6d4731c10edc58a70ee71b0b77b9f687af13d59/cn/gamedata/excel/item_table.json)和[英文 item_table.json](https://github.com/ArknightsAssets/ArknightsGamedata/blob/a6d4731c10edc58a70ee71b0b77b9f687af13d59/en/gamedata/excel/item_table.json)。

企鹅物流的[物品接口](https://penguin-stats.io/PenguinStats/api/v2/items)也为每个物品提供 `itemId` 和 `name_i18n`。当次请求返回 155 项，包含上述赤金的中英对照；这个结果可用于材料名交叉核对，不能据此假定它覆盖所有游戏物品。接口使用条件以[企鹅物流 API 说明](https://developer.penguin-stats.io/public-api)为准。

旧的 [Kengxxiao/ArknightsGameData_YoStar](https://github.com/Kengxxiao/ArknightsGameData_YoStar) 已于 2025-12-25 归档，适合核对历史版本，不能假定它持续提供最新英文内容。

## 日文、繁中与显示数据

日服的基地、製造所、貿易所、発電所、オペレーター及理性可对照[日服基地更新公告](https://arknights.jp/news/478)。其余设施在同版本 `jp` 游戏表中依次为制御中枢、宿舎、活動室、加工所、事務室、訓練室和応接室。繁中设施从 `tw` 的相同房间类型核对，不直接使用日服名称。

[游戏名称显示适配](../../ui/src/i18n/gameNames.js)按同一 `charId`、`itemId` 或 `skillId` 对齐简中、英文、日文和繁中。只提取名称；配置中的中文值、图像路径、筛选值和后端请求保持原值。缺少对应地区记录或存在同名歧义时保留原名。游戏技能说明另按相同干员与 `buffId` 核对当前规则；规则一致时可以复用官方译文，其他地区尚未实装或效果不同的条目则独立翻译当前中文效果，并记录为项目译文。不得因缺少某地区记录而隐藏条目，也不得随界面语言替换技能数值、作用对象或生效条件。资源更新后，未知的中文规则仍须先补译，不能套用旧说明。

[模组名称显示适配](../../ui/src/i18n/moduleNames.js)按同一 `uniequipId` 对齐各语言的名称，来源为相同版本的 [uniequip_table.json](https://github.com/ArknightsAssets/ArknightsGamedata/blob/a6d4731c10edc58a70ee71b0b77b9f687af13d59/cn/gamedata/excel/uniequip_table.json)。显示名不改变模组 ID、养成目标和材料计算；缺少对应名称时保留原名，同名且存在歧义的条目不按名称猜测。

同步测试需要同时覆盖有数据与无数据：`/basement-skill/operators` 的空快照提示、`/cultivate-fetch` 的成功与失败消息，以及最优路线计算在同步失败后停止请求的分支。固定操作提示属于界面文案，应通过显示适配翻译；后端原始响应、快照和日志保持原样，未知诊断只翻已知包装前缀。不要仅用成功的离线示例判断这些分支已完成翻译。

Vue I18n 的现有简中和英文资源按功能存放在 `ui/src/i18n/messages/`；新增语言资源在 `ui/src/i18n/locales/ja-JP/` 与 `zh-TW/`。繁中基础文案使用 OpenCC `s2twp` 在开发阶段转换，并核对介面、儲存、設定檔、視窗等用语；转换工具不进入前端运行时。维护时检查所有语言的键、占位参数和消息语法一致，再检查真实页面的按钮、筛选、图表和长说明。OpenCC 的词组转换不能替代官方名称核对，例如职业名称须使用游戏中的「重裝」。养成页原有的英文小标题属于视觉设计，不将这些装饰文字列为漏译；功能按钮、条件说明和错误提示仍按所选语言显示。

## 参考实现与文件复用

Arknights Toolbox 的[国际化入口](https://github.com/arkntools/arknights-toolbox/blob/9b22e35d2bd5857894ccf8792301b180e2ccb91d/src/i18n.js)按功能组织语言文件，并在缺少译文时回退中文。可参考这种组织方式；它使用的 Vue 接口和打包方式不直接适用于本仓库。

Mower 的帮助与操作文案独立编写，没有整包复制社区语言文件或 Wiki 正文。游戏资源只提取界面需要的名称和已核对规则的基建技能显示字段，完整游戏表保留在开发临时目录。若后续需要引入外部文件，应先核对该文件所属的许可、来源和署名方式：

- Arknights Toolbox 的[仓库许可](https://github.com/arkntools/arknights-toolbox/blob/9b22e35d2bd5857894ccf8792301b180e2ccb91d/LICENSE)为 MIT；复制其软件或实质部分时需保留相应版权与许可声明。
- MAA 的[仓库许可](https://github.com/MaaAssistantArknights/MaaAssistantArknights/blob/877f3e235e9f7ca47d5b3fc5033d6b4fa3faf265/LICENSE)为 AGPL-3.0；参考词汇不能被当成已获准无条件搬入整份语言文件。
- Arknights Terra Wiki 页面声明内容采用 [CC BY-SA 4.0](https://arknights.wiki.gg/wiki/Break_Loose)，另有标注的内容除外；如复用其正文，应按实际页面检查署名及相同方式共享要求。
- 企鹅物流的[API 说明](https://developer.penguin-stats.io/public-api)声明数据采用 CC BY-NC 4.0。程序源码许可与接口数据许可需要分别核对。
- 本次检查的游戏数据镜像[根目录](https://github.com/ArknightsAssets/ArknightsGamedata/tree/a6d4731c10edc58a70ee71b0b77b9f687af13d59)未见独立数据许可文件；公开可读取不等于已经确认了整包再分发许可。


<a id="maintaining-interface-copy"></a>
## 新增或修改界面文案

1. 确定文字的实际显示位置和含义，先检查相应功能的语言资源。含义一致时复用已有键，含义不同则创建新键；通过 Vue I18n 在真实调用处显示，动态选项随当前语言更新。
2. 在同一改动中补齐简中、英文、日文和繁中。按当前资源组织维护 `messages/` 中的四语模块，或简中、英文模块及 `locales/ja-JP/`、`locales/zh-TW/` 对应文件。游戏名称与技能效果按本页的来源和规则匹配方法核对；缺少官方日文干员名时保留中文。
3. 保留选项的内部值、请求内容和用户自定义名称；固定后端操作提示通过显示适配翻译，原始响应、缓存、日志及未知诊断继续使用原文。界面语言不改变区服或功能可用性。
4. 在 `ui/` 执行 `npx vitest run src/i18n/messages.test.js`，并运行受影响组件或工具的定向测试，检查四语键、占位参数和消息语法。该检查不会自动发现新代码中的硬编码文案，代码审查仍需检查真实页面、弹窗和失败分支。
5. 对包含较长译文的控件，在桌面和窄屏切换语言并检查完整标签、按钮和选中标记。测量控件内部边界及整页宽度，确认文字完整显示、选择行为和保存值不变；整页没有横向滚动并不代表控件内部没有溢出。
