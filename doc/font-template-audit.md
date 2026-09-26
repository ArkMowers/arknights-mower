# 字体生成模板核对（国服 Android 2.7.71）

本次从模拟器安装包的 `sharedassets0`～`sharedassets13` 和
`assets/font/` 提取字体，从 `building/[pack]room.ab`、
`building/ui/common/panel_building_char_select_plugin.ab` 与
`ui/pages/building_char_ctrl_page.ab` 读取 Unity 预制体的 Text 和
`DynFontLoader` 字段，并用 2026-09-26 的 1080p 训练室截图核对像素。
这些静态资源给出字体选择、字号和布局参数；运行时的字体注册和渲染仍由
Unity UI `TextGenerator`/`DynFontLoader` 执行，不能把 Pillow 绘制视为
游戏渲染器的逐像素复刻。

## Mower 文字模板

| 生成函数 | 模型 | 当前字体 | 游戏资源核对 | 处理 |
| --- | --- | --- | --- | --- |
| `load_recruit_template` | `recruit_result.pkl` | `FZDYSK.TTF` 120px | APK 内置字体中未发现同名字体；公招揭晓界面待截图验证 | 保留现有模板 |
| `load_recruit_tag` | `recruit.pkl` | `SourceHanSansCN-Medium.otf` 30px | 公招标签所在预制体尚未定位 | 保留现有模板 |
| `训练在房间内的干员名的模型` | `operator_room.model` | 游戏 `NotoSansHans-Medium` 子集 37px | 房间面板 `text_item_name` 使用 `DynFontLoader` 的 `NotoSansHans-Medium` | 一致 |
| `训练选中的干员名的模型` | `operator_select.model` | 游戏 `NotoSansHans-Medium` 子集，23～31px | 基建选人卡片 `text_name` 使用 `NotoSansHans-Medium`、字号 14、Best Fit；卡片 Canvas 缩放和模板预处理会改变最终像素 | 已替换字体，删除两名干员的截图覆盖 |
| `训练训练室干员名的模型` | `operator_train.model` | 游戏 `NotoSansHans-Medium` 子集，24～30px | 基建选人卡片同上；训练位卡片字号依界面有差异 | 已替换字体，删除两名干员的截图覆盖 |
| `build_mastery_panel_model.py` | `mastery_panel.model` | Source Han Sans 37px，间隔号改用游戏 Noto 子集 | 训练室 `text_item_name` 使用 `NotoSansHans-Medium`，原始字号 25、Best Fit，框宽 356.43；1080p 画面约 1.5 倍 | 修正间隔号字宽并移除分段补偿 |

`operator_select.model` 与 `operator_train.model` 中只有
`凯尔希·思衡托`、`维娜·维多利亚` 两个名字含 `·`。切换到游戏 Noto
字体后移除了旧的逐字偏移代码和四张实机截图覆盖。用删除前的四张截图复核，
新模型在选人、训练位分别取得 `凯尔希·思衡托` 0.819/0.849、
`维娜·维多利亚` 0.899/0.802 的正确识别分数；所有竞争名字最高不超过
0.468，均高于运行时 0.6 的命中门槛。另用日志中的两张完整选人页复核，
普通选人页 12 个姓名与原日志完全一致，训练位选人页 10 个槽位结果也完全一致。
字体子集新增字符集校验，之后有新名字
缺字会让生成任务明确失败，需扩充子集再重建模型。

## 训练室的实测差异

`room.ab` 的 `panel_vault_training/panel_training/panel_items/text_item_name`
文本值初始为 `name`；它由训练室状态组件的 `_nameText` 指向。
同一节点的 `DynFontLoader._fontName` 是 `NotoSansHans-Medium`。
倒计时和计数分别使用 `JovannyLemonad-Bender`，字号 25 和 26。

游戏 Noto 的 `·` 横向 advance 是 574/1000 em；APK 的
`SourceHanSansCN-Medium.ttf` 是 2048/2048 em。按模型字号 37px，
分别为约 21px 和 37px。技能表中希腊字母只出现 `β` 与 `γ`；
它们在两字体中的字宽相同。症结是前面的间隔号使后缀整体右移，
而非游戏缺少 `γ` 字形。

实机 `[极境]支援号令·γ型` 画面中，Source Han 整词技能分数 0.704；
旧版分段补偿为 0.831；使用 Noto 间隔号和 Source Han 其余字形后，
整词分数 0.885，姓名分数 0.886。单独用 Noto 在 Pillow 中绘制，
由于栅格化差异，整词分数反而较低，因此模板保留已验证的 Source Han
字形，仅采用游戏的间隔号字形和字宽。`β` 尚无实机样本。

## 字体资源

APK 的 Unity `sharedassets0`～`sharedassets13` 共含 19 个 `Font` 对象：
`NotoSansHans-Medium`、`Novecentowide-Medium`、
`Novecentowide-Normal`、`Novecentowide-Bold`、
`JovannyLemonad-Bender-Light`、`JovannyLemonad-Bender`、`AEwide`、
`RoHMinSinkStd-UB`、`OSWALD-MEDIUM`、`SourceHanSansCN-Heavy`、
`Nesatho`、`Dosis-Bold`、`Dosis-Regular`、`Arvo-Bold`、`ADDWB__`、
`方正特雅宋_GBK`、`GroovyScript`、`GroovyScriptExtrude`、
`OpenSans-Semibold`。APK 的 `assets/font/` 另含
`SourceHanSansCN-Medium.ttf` 和 `SourceHanSerifCN-Medium.ttf`。
这份清单不覆盖游戏后续下载的所有 AssetBundle。

反编译元数据可见 `DynFontLoader` 的 `_BindToRegistry`、`_AssignFont`
等方法和 `AbFontResourceRegistry` 的 `_ReloadFromConfig`，另有
`premain/abfontconfig` 资源路径。由于当前 IL2CPP 元数据头经过自定义处理，
尚未还原运行时资源映射与 Unity 字体栅格化的完整调用链；上述字体使用结论
来自预制体字段与截图匹配，而非对这些方法行为的推测。
