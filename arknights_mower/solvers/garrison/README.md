# GarrisonFarm 接入

购买、部署和预设编队使用 [UnknownGlyph/GarrisonFarm](https://github.com/UnknownGlyph/GarrisonFarm) 的对局函数。Mower 优先读取包内的脚本和布局。缺少的文件在首次使用时从[个人 fork 的固定提交](https://github.com/ALEXsun0/GarrisonFarm/tree/fd373c9b1ab1e8fbb52ad78b8da4c461ab325abb)下载并缓存。策略面板按实际通关次数选择，相关行为参考 [GarrisonFarm-Personal](https://github.com/FJH3576/GarrisonFarm-Personal/blob/d345ae2712ff8c3dbf6f86c63b7497217c0f723f/CHANGELOG.md)。

当前赛季的策略表只记录游戏策略名称和标识，用于把已读到的胜场绑定到对应策略。数据取自[国服活动表](https://github.com/Kengxxiao/ArknightsGameData/blob/master/zh_CN/gamedata/excel/activity_table.json)，按赛季 `act3autochess` 筛选允许 `mode_single_funny` 的策略。设备连接、进度和调度见[卫戍协议子系统说明](../../../docs/subsystems/garrison.md)。
