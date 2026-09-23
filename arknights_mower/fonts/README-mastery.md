# 训练室面板模板字体

`SourceHanSansCN-Medium-mastery.ttf` 是从明日方舟国服 Android 2.7.71
安装包内 `SourceHanSansCN-Medium.ttf` 提取的字体生成的字符子集。
只保留当前 `skill_data.json` 中 4–6 星干员姓名与技能名所需字符；
子集的字符清单在 `mastery-charset.txt`。该字体按 SIL Open Font License 1.1
授权，许可文本见 `LICENSE-OFL-1.1.txt`。

`build_mastery_panel_model.py` 使用子集离线生成 `mastery_panel.model`。
游戏更新引入子集之外的字符时，生成会明确失败；用新版游戏字体重建子集，
或以 `--font` / `MOWER_MASTERY_FONT` 提供完整游戏字体后重新生成。
运行时只加载压缩模型，不加载此字体。
