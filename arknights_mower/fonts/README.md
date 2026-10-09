# 房间干员姓名字体

`NotoSansHans-Medium-room.otf` 是游戏内 `NotoSansHans-Medium` 字体的字符子集，
只保留 `arknights_mower/data/agent.json` 中姓名用到的 579 个字符。
来源为明日方舟国服 Android 2.7.71 的 Unity `sharedassets1.assets` Font 对象。
完整字体的 SHA-256 为
`25033438cfa41f1873d4902b8555956557b765117756bcef96406e023e49578c`；
子集的 SHA-256 为
`be5f1cebcca68bae419ad89940ec98695df33835a9e58bdac4ad9ed2d7bd7cfe`。

该字体的内嵌版权信息为 Adobe Systems Incorporated (2014)，
使用 Apache License 2.0；许可文本见 `LICENSE-APACHE-2.0.txt`。
`auto_get_res_new.py` 的房间干员姓名模型生成函数使用此子集。
选人和训练位干员姓名模型也使用同一子集，不再靠带 `·` 名字的截图覆盖。
`room-charset.txt` 记录子集字符。生成器检查字体实际字符映射；新增姓名缺字时，
`build_font_subsets.py` 从 主仓 `font_sources/NotoSansHans-Medium.otf` 自动扩字，
再加载字体生成模型。完整原字体缺失、指纹不符或没有所需字符时明确失败。
