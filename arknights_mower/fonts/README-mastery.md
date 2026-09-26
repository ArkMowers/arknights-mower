# 训练室面板模板字体

`SourceHanSansCN-Medium-mastery.ttf` 是从明日方舟国服 Android 2.7.71
安装包内 `SourceHanSansCN-Medium.ttf` 提取的字体生成的字符子集。
只保留当前 `skill_data.json` 中 4–6 星干员姓名与技能名所需字符；
子集的字符清单在 `mastery-charset.txt`。该字体按 SIL Open Font License 1.1
授权，许可文本见 `LICENSE-OFL-1.1.txt`。

阿米娅医疗形态技能新增的「恸」「情」字形取自
`ArkMowers/MowerFonts` 的 `fonts/SourceHanSansCN-Medium.otf`
（提交 `e93f499da845e9e9144332db5ad60cebae9e6489`），通过 fontTools 转成
TrueType 轮廓并按字高缩放加入原子集；原有字形未变。

游戏的训练室姓名和技能文本实际使用 `NotoSansHans-Medium`，原始预制体字号 25，
1080p 画面约为 37px，启用 Best Fit。游戏 `NotoSansHans-Medium` 的间隔号
`·` 比 `SourceHanSansCN-Medium` 窄 16px；当前资源字符集中只有这一字的
字宽不同。构建模板时用已收录的 `NotoSansHans-Medium-room.otf` 绘制间隔号，
其余字形沿用与实机像素更接近的 Source Han Sans。`γ` 实机样本的整词匹配分数
由 0.704 提高到 0.885，不再依赖分段字距补偿。

`build_mastery_panel_model.py` 使用两个子集离线生成 `mastery_panel.model`。
游戏更新引入子集之外的字符时，生成会明确失败；用新版游戏字体重建子集，
或以 `--font` / `MOWER_MASTERY_FONT` 提供完整游戏字体后重新生成。
运行时只加载压缩模型，不加载此字体。
