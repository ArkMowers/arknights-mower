# 房间干员姓名字体

`NotoSansHans-Medium-room.otf` 是游戏内 `NotoSansHans-Medium` 字体的字符子集，
只保留 `arknights_mower/data/agent.json` 中姓名用到的 576 个字符。
来源为明日方舟国服 Android 2.7.71 的 Unity `sharedassets1.assets` Font 对象。
完整字体的 SHA-256 为
`25033438cfa41f1873d4902b8555956557b765117756bcef96406e023e49578c`；
子集的 SHA-256 为
`1d37059018af543e3b18b27e0d0a85fb10a67a95a6ae8567f35da9707298c395`。

该字体的内嵌版权信息为 Adobe Systems Incorporated (2014)，
使用 Apache License 2.0；许可文本见 `LICENSE-APACHE-2.0.txt`。
`auto_get_res_new.py` 的房间干员姓名模型生成函数使用此子集。
选人和训练位干员姓名模型也使用同一子集，不再靠带 `·` 名字的截图覆盖。
`room-charset.txt` 用于在新增干员名时检查子集是否缺字；缺字时需从新版
游戏字体扩充子集并更新字符集文件。
