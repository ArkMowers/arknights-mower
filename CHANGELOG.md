# CHANGELOG

## 4.1.6-alpha.13 - 2026-10-27

### New

- 将仓库页面偏好保存到 gui.yml [PR](https://github.com/ArkMowers/arknights-mower/pull/1657) @NiceAfternoon
- 重组养成规划页面为四视图工作区 [PR](https://github.com/ArkMowers/arknights-mower/pull/1656) @NiceAfternoon
- 支持按计划暂停和停止 Mower [PR](https://github.com/ArkMowers/arknights-mower/pull/1652) @ALEXsun0 @Fui-Reconk
- 逐屏领取多个签到活动的奖励 [PR](https://github.com/ArkMowers/arknights-mower/pull/1648) @NiceAfternoon
- 支持显示或隐藏版本水印 [PR](https://github.com/ArkMowers/arknights-mower/pull/1642) @NiceAfternoon
- 新增游戏内七日活动签到自动领取任务 [PR](https://github.com/ArkMowers/arknights-mower/pull/1640) @NiceAfternoon
- 支持按日期范围查看基建产出与收益 [PR](https://github.com/ArkMowers/arknights-mower/pull/1639) @NiceAfternoon
- 支持开启“实时心情计算调控”后，在有界预测证明能改善后续轮班接续时提前安排普通主班休息。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1634) @ALEXsun0
- 支持自定义运行日志背景图 [PR](https://github.com/ArkMowers/arknights-mower/pull/1637) @NiceAfternoon
- 重建软件更新重启后的普通任务并保留重要任务 [PR](https://github.com/ArkMowers/arknights-mower/pull/1638) @ALEXsun0
- 支持自选日志导出时间范围 [PR](https://github.com/ArkMowers/arknights-mower/pull/1633) @ALEXsun0
- 合并实例的更新授权与维护设置显示开关 [PR](https://github.com/ArkMowers/arknights-mower/pull/1627) @ALEXsun0
- 支持普通基建调度按收益演算规则计算心情 [PR](https://github.com/ArkMowers/arknights-mower/pull/1624) @ALEXsun0
- 集中管理多开实例的设置和维护 [PR](https://github.com/ArkMowers/arknights-mower/pull/1616) @Fui-Reconk @ALEXsun0
- 整合新增任务表单的日常入口并生成关联专精任务 [PR](https://github.com/ArkMowers/arknights-mower/pull/1619) @ALEXsun0
- 重组导航与设置入口并支持实例内配置档案 [PR](https://github.com/ArkMowers/arknights-mower/pull/1609) @NiceAfternoon
- 支持手动安排日常任务和长任务 [PR](https://github.com/ArkMowers/arknights-mower/pull/1615) @ALEXsun0
- 补充排班选人时基建技能提示中的持有和解锁状态。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1594) @ALEXsun0
- 新增“跳过清除已读”选项，开启后领取邮件奖励并保留已读邮件。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1593) @ALEXsun0
- 支持在副表生效条件中嵌套函数 [PR](https://github.com/ArkMowers/arknights-mower/pull/1589) @ALEXsun0
- 自动向一图流上报回收站掉落并补发历史记录 [PR](https://github.com/ArkMowers/arknights-mower/pull/1588) @ALEXsun0
- 支持按筛选一键添加养成计划 [PR](https://github.com/ArkMowers/arknights-mower/pull/1569) @ALEXsun0
- 统一保存心情曲线与工休比报表的查看偏好 [PR](https://github.com/ArkMowers/arknights-mower/pull/1568) @ALEXsun0
- 为 Bug 反馈附加日志调度中的关键截图 [PR](https://github.com/ArkMowers/arknights-mower/pull/1545) @ALEXsun0
- 支持 macOS 和 Linux 桌面窗口使用自绘标题栏 [PR](https://github.com/ArkMowers/arknights-mower/pull/1535) @NiceAfternoon @ALEXsun0
- 支持按分组选择副表 [PR](https://github.com/ArkMowers/arknights-mower/pull/1514) @ALEXsun0
- 将多开实例的更新授权改为默认允许。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1484) @ALEXsun0
- 支持在多开管理器中按实例授权更新 [PR](https://github.com/ArkMowers/arknights-mower/pull/1462) @Fui-Reconk
- 支持 Windows 桌面程序异常后自动接续调度 [PR](https://github.com/ArkMowers/arknights-mower/pull/1397) @NiceAfternoon
- 补充收益导出图片中的订单统计和作者备注 [PR](https://github.com/ArkMowers/arknights-mower/pull/1451) @ALEXsun0
- 多绑组工作主班可填写一列空绑组及对应替班，按自身心情独立轮休，具名组休息时仍优先使用对应替班。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1447) @ALEXsun0
- 收益演算增加会客室驻员搜集的线索数量，并在收益明细和导出图右上角展示。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1444) @ALEXsun0
- 为双 Mower 模式新增信用商店性价比购物 [PR](https://github.com/ArkMowers/arknights-mower/pull/1436) @YuNHz
- 生成 Release Changelog 时优先采用已合并 PR 正文中的 Changelog 段，无法采用时再读取 commit 的 Changelog 段或标题。 @NiceAfternoon
- 同步收益演算排班规则并采用源码甘特图与赤金等价龙门币展示 [PR](https://github.com/ArkMowers/arknights-mower/pull/1435) @ALEXsun0
- 支持赠送板上已有编号的多余自有线索 [PR](https://github.com/ArkMowers/arknights-mower/pull/1432) @YuNHz @ALEXsun0
- 新增基建只读主班试排与支持设施等级配置、结果保存和收益图回导的完整排班演算，并为实测及演算心情曲线提供缩放 [PR](https://github.com/ArkMowers/arknights-mower/pull/1421) @ALEXsun0
- 新增按实例授权的 Mower AI 助手对话开关和实例配置批量编辑表格 [PR](https://github.com/ArkMowers/arknights-mower/pull/1429) @Fui-Reconk
- 为双 Mower 模式提供按需领取信用板 [PR](https://github.com/ArkMowers/arknights-mower/pull/1420) @YuNHz
- 为每日凌晨四点刷新提前安排跑单与专精换人 [PR](https://github.com/ArkMowers/arknights-mower/pull/1424) @ALEXsun0
- 为多开管理器增加实例启停与离线配置管理 [PR](https://github.com/ArkMowers/arknights-mower/pull/1422) @Fui-Reconk
- 在基建技能页整合只读组合与技能效率估算 [PR](https://github.com/ArkMowers/arknights-mower/pull/1417) @ALEXsun0
- 支持按库存与单批心情调度并显示阻塞原因的自动养成合成 [PR](https://github.com/ArkMowers/arknights-mower/pull/1412) @ALEXsun0
- 添加回收站材料统计、共享估值与基报算法设置 [PR](https://github.com/ArkMowers/arknights-mower/pull/1369) @ALEXsun0
- 分离本体与资源自动更新，Windows 启动请求管理员权限 [PR](https://github.com/ArkMowers/arknights-mower/pull/1365) @ALEXsun0
- 接入一图流 OAuth 干员同步并跳过重复上传 [PR](https://github.com/ArkMowers/arknights-mower/pull/1344) @ALEXsun0
- 添加副手与活动室自动切换信赖 [PR](https://github.com/ArkMowers/arknights-mower/pull/1361) @ALEXsun0
- 衔接同干员技能减半并校准中枢换班时间 [PR](https://github.com/ArkMowers/arknights-mower/pull/1356) @ALEXsun0

### Bug Fixes

- 修复普通工作线程异常引起的反复基建观察 [PR](https://github.com/ArkMowers/arknights-mower/pull/1654) @NiceAfternoon
- 修复更新未结束时桌面自动任务启动失败的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1655) @ALEXsun0
- 修复多开实例获准维护后仍无法更新 MAA 的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1653) @ALEXsun0
- 修复显示零心情时忽略工作倒计时而提前下班的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1650) @ALEXsun0
- 修复普通轮班提前下班和菲亚向满心情目标充能的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1647) @ALEXsun0
- 修复库存选关关闭时仍提示跳过关卡、比例选择或本轮不刷取的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1643) @NiceAfternoon
- 修复本体和收益演算中干员未完成休息就回班的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1645) @ALEXsun0
- 点击“一键芯片上限”时自动启用当前方案的库存选关，让芯片上限参与选关。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1644) @ALEXsun0
- 修复副表换班预演中普通纠正错误召回整组、丢失原下班目标并反复上下班的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1641) @ALEXsun0
- 修复桌面窗口最大化启动时先显示普通窗口的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1636) @NiceAfternoon
- 修复回收站材料统计入口显示刷新图标的问题，改用回收图标。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1635) @NiceAfternoon
- 修复多开管理器清理日志和截图时可能沿目录联接或被替换的目录误删外部文件的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1631) @NiceAfternoon
- 修复全部设置中档案操作不一致和重启续接缺失 [PR](https://github.com/ArkMowers/arknights-mower/pull/1632) @NiceAfternoon
- 修复维护工具读取或保存期间切页后，MAA 更新或存储清理误显示没有实例的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1630) @NiceAfternoon
- 修复多开管理器的本实例设置漏存，以及取消本实例启动或页面打开方式后仍显示旧值的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1629) @NiceAfternoon
- 延后实时心情计算模式的下班确认至个人下限 [PR](https://github.com/ArkMowers/arknights-mower/pull/1628) @ALEXsun0
- 修正多开设置可同时选择多个空闲动作、显示无关字段以及自定义截图默认命令固定设备地址的问题，并调整全部设置页布局和手机排班入口。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1625) @ALEXsun0
- 修复心情计算模式的配置继承与单回恢复判定 @ALEXsun0
- 修复点击基建房间后未等进入确认便重试或报错的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1623) @ALEXsun0
- 修复普通替班已有有效心情读数仍重复进房检查，并将正常等待观测记为警告的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1622) @ALEXsun0
- 修复闪断更新提前进入游戏后又被同一公告暂停至公告结束的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1621) @ALEXsun0
- 修复普通换班沿用中途读数安排远期跑单的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1620) @ALEXsun0
- 修复选人时撤换确认弹窗延迟出现导致的职业筛选失败 [PR](https://github.com/ArkMowers/arknights-mower/pull/1614) @NiceAfternoon
- 修复自动切换信赖在联网时提前点击副手导致的检查失败 [PR](https://github.com/ArkMowers/arknights-mower/pull/1613) @NiceAfternoon
- 同步收益演算的替班检查与宿舍恢复规则 [PR](https://github.com/ArkMowers/arknights-mower/pull/1603) @ALEXsun0
- 修复养成材料合成因芯片等资源不足而跳过的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1602) @ALEXsun0
- 恢复通过标准输出采集 MuMu 广告控件 [PR](https://github.com/ArkMowers/arknights-mower/pull/1597) @NiceAfternoon
- 修复回满动态干员占床挤出未恢复干员的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1600) @ALEXsun0
- 停止回收站材料上报失败后的自动重发 [PR](https://github.com/ArkMowers/arknights-mower/pull/1601) @ALEXsun0
- 修复普通替班因缺少工作倒计时被记为错误的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1599) @ALEXsun0
- 修复绑组换班执行名单与核验目标不同步的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1598) @ALEXsun0
- 修复自动专精批量排队并反复读取已有训练的问题，收取后衔接首个就绪技能，受保护训练位可继续自己的专精计划。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1596) @ALEXsun0
- 移除普通在线更新的升降级判断 [PR](https://github.com/ArkMowers/arknights-mower/pull/1595) @ALEXsun0
- 修复副表条件控件逐个竖排和过度拉伸的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1592) @ALEXsun0
- 修复换班预演切换副表后仍将失效的用尽下班预约带入轮休和补床计算的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1591) @ALEXsun0
- 修复进入房间后因标题或房间号暂未确认而过早返回基建地图的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1590) @ALEXsun0
- 修复 macOS 窗口关闭后 GUI 子进程未退出 [PR](https://github.com/ArkMowers/arknights-mower/pull/1587) @ALEXsun0
- 改用快捷置入按钮识别线索板 [PR](https://github.com/ArkMowers/arknights-mower/pull/1586) @ALEXsun0
- 修复贸易站跑单超窗后滞留旧任务的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1585) @ALEXsun0
- 修复跑单原班恢复失败后，巡检因现驻员的心情缓存尚未到刷新时间而跳过实读的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1577) @NiceAfternoon
- 修复单岗位生产房无法取消暂选的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1576) @NiceAfternoon
- 修复 MuMu 返回桌面后因广告控件读取异常而无法恢复游戏前台的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1573) @NiceAfternoon
- 修复跑单选人时提前点击尚未就绪的画面，以及提交后仍显示选人页时重复确认的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1571) @NiceAfternoon
- 限制排班表导入的请求与解析数据量 [PR](https://github.com/ArkMowers/arknights-mower/pull/1572) @ALEXsun0
- 修复回满核验造成的回班和普通纠错阻塞 [PR](https://github.com/ArkMowers/arknights-mower/pull/1570) @ALEXsun0
- 修复训练室无法区分有包含关系的技能名的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1567) @ALEXsun0
- 修复自动恢复重试覆盖首次故障信息、通知无法保留最初原因的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1566) @NiceAfternoon
- 修复主实例重新启动时旧状态覆盖当前运行选择的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1565) @NiceAfternoon
- 修复 Windows 主实例关闭期间连续 Ctrl+C 中断进程关闭和锁清理的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1564) @NiceAfternoon
- 修复进程恢复和缓存重置期间读取房间遇到设备异常时退出工作线程的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1563) @NiceAfternoon
- 修复登录取消弹窗被误判后返回桌面的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1562) @NiceAfternoon
- 修复普通启动首次补床时跳过主班轮休规划的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1561) @NiceAfternoon
- 修复收益演算中主班未回满就离宿后无法继续休息，以及副表切换后整组回班状态丢失的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1560) @YuNHz @ALEXsun0
- 修复回班暂停时跳过本轮源石碎片补货的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1559) @ALEXsun0
- 修复浏览器地址多带客户端名称及桌面修饰键点击内部链接外跳的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1556) @ALEXsun0
- 修复宿舍计划内离宿被误判后触发整组回班纠错的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1558) @ALEXsun0
- 修复 SystemUI 错误弹窗和输入无响应导致的游戏恢复失败 [PR](https://github.com/ArkMowers/arknights-mower/pull/1557) @NiceAfternoon
- 修复自动恢复和配置保存失败提示切换页面后丢失关闭状态的问题，并统一在所有页面右上角显示。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1555) @NiceAfternoon
- 修复等待回班时宿舍补床预演循环及休息位丢失 [PR](https://github.com/ArkMowers/arknights-mower/pull/1553) @ALEXsun0
- 修复清空暂选延迟造成的基建选人遗漏 [PR](https://github.com/ArkMowers/arknights-mower/pull/1554) @ALEXsun0
- 修复贸易站换入前读到窗口外的有效生产倒计时后，后续跑单持续停滞的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1552) @ALEXsun0
- 修复存在过期普通任务时，个人心情上限离宿被错误提前并反复触发清队、重建排班的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1551) @ALEXsun0
- 修复副表含“是否正在训练”条件时收益演算因无法解析条件而终止的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1550) @ALEXsun0
- 修复普通换班连续读取订单和换人时耽误关键任务的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1547) @NiceAfternoon
- 修复离岗未满的回满主班被普通纠错反复安排回班，导致到期换班受阻和普通跑单反复纠错的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1549) @ALEXsun0
- 修复主班恢复期间的提前召回和回班阻塞 [PR](https://github.com/ArkMowers/arknights-mower/pull/1548) @ALEXsun0
- 修复运行日志页的自动恢复和配置保存失败提示挤占截图与日志区域的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1544) @NiceAfternoon
- 修复普通跑单目标干员已驻员时反复纠错，以及空闲主班初始化上岗被错误要求先回满而阻塞过期换班的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1546) @ALEXsun0
- 修复 Windows 从终端启动源码时看不到实例日志的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1543) @NiceAfternoon
- 修复一级回收站按两槽读取导致自动恢复和换班受阻的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1542) @ALEXsun0
- 修复回收站材料被收取提示短暂遮挡时过早记为未知 [PR](https://github.com/ArkMowers/arknights-mower/pull/1540) @ALEXsun0
- 修复普通换班确认贸易站驻员后，继续安排其他房间而延迟读单、延误跑单的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1539) @NiceAfternoon
- 修复入住信息侧栏打开时会客室信息板打不开的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1541) @ALEXsun0
- 修复活动室信赖误读导致的检查中断 [PR](https://github.com/ArkMowers/arknights-mower/pull/1537) @NiceAfternoon
- 修复基建恢复任务反复阻塞独立跑单和纠错的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1536) @ALEXsun0
- 修复普通替班实测心情消耗速率变化后仍沿用旧检查时间的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1532) @NiceAfternoon
- 修复制造站份数误识别导致切产物和搓玉补货失败 [PR](https://github.com/ArkMowers/arknights-mower/pull/1533) @ALEXsun0
- 修复清零初始化先恢复低心情主班、下一轮又安排下班，造成重复换人的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1531) @ALEXsun0
- 修复 Android 安装 Mower 更新后自动刷新页面、清除手动重启提示却仍运行旧版本的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1530) @ALEXsun0
- 修复主班恢复期间的离宿滞留和调度阻塞 [PR](https://github.com/ArkMowers/arknights-mower/pull/1528) @ALEXsun0
- 修复多个普通替班在同一房间工作时，心情检查因整房实读而反复触发的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1527) @NiceAfternoon
- 修复设备启动或恢复时共享 ADB 错误摘要丢失底层原因的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1526) @NiceAfternoon
- 修复漏算替班接岗腾出的床位导致主班无法下班 [PR](https://github.com/ArkMowers/arknights-mower/pull/1525) @ALEXsun0
- 修复基建回班补人受阻后的空房订单刷新循环 [PR](https://github.com/ArkMowers/arknights-mower/pull/1524) @NiceAfternoon
- 保留 Agent 合并 PR 时的 GitHub 默认说明 [PR](https://github.com/ArkMowers/arknights-mower/pull/1521) @NiceAfternoon
- 修复源石碎片生产份数归零后周期补货失败的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1520) @ALEXsun0
- 修复主班缺少实读心情时回班受阻并漏排后续跑单的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1519) @ALEXsun0
- 修复局域网 HTTP 访问时无法创建副表分组的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1518) @ALEXsun0
- 修复限时物品标签遮挡导致仓库扫描失败的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1517) @ALEXsun0
- 修复收益演算中换位后技能未重新暖机的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1513) @ALEXsun0
- 修复主班未到急救线就召回休息组，以及未回满组在普通纠错中阻塞其他主班回班的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1506) @NiceAfternoon
- 修复从宿舍借用干员加工后，因加工任务计划为空而恢复原床位失败的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1509) @NiceAfternoon
- 修复源石碎片因材料不足而只能生产 2–98 份时，切产物补货被误判失败的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1512) @ALEXsun0
- 修复基建报告将相连数字当成一位而读错订单数的问题 @NiceAfternoon
- 修复恢复期限变化后为同一干员重复安排宿舍心情复查的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1504) @NiceAfternoon
- 修复前置换班未完成时反复生成同一回班安排、旧缓存积累重复等待任务的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1500) @NiceAfternoon
- 修复 MuMu 桌面广告阻碍游戏启动的问题，并在普通新画面采集前恢复游戏前台。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1499) @NiceAfternoon
- 修复用尽下班预约误判个人或所属组的回满要求、使用错误提前量的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1498) @NiceAfternoon
- 修复在岗普通替班缺少个人心情下限检查的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1497) @NiceAfternoon
- 修复自动专精忽略协助位记录保存失败的问题 @NiceAfternoon
- 修复换班任务恢复旧目标时调走受保护训练室驻员的问题 @NiceAfternoon
- 修复自动专精读取失败后放弃协助者换人的问题 @NiceAfternoon
- 修复训练室驻员读数不可靠时漏排专精换人任务的问题 @NiceAfternoon
- 修复训练室巡检失败后可能一直沿用旧驻员记录的问题 @NiceAfternoon
- 修复训练室两槽读数未确认就更新驻员状态的问题 @NiceAfternoon
- 修复副表换班后的休息遗漏与共享替班阻塞 [PR](https://github.com/ArkMowers/arknights-mower/pull/1486) @ALEXsun0
- 共享 OCR 服务不再在更新准备期随工作进程回收退出，并先校验连接序言再接收请求。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1485) @NiceAfternoon
- 恢复组内延后回班的额外等待上限 [PR](https://github.com/ArkMowers/arknights-mower/pull/1483) @ALEXsun0
- 修复干员只有有效满心情卡牌预估时无法加入加工队列的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1482) @ALEXsun0
- 修复一图流同步后专三练度无法正确显示，以及大数据养成专精筛选因旧等级统计被丢弃而失效的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1479) @ALEXsun0
- 修复普通制造站加速在无跑单房间时用尽无人机的问题，按配置阈值保留无人机。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1477) @ALEXsun0
- 修复有跑单房间时制造站加速耗尽无人机的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1478) @YuNHz
- 修复宿舍选人反复跳到末页而找不到休息干员的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1467) @NiceAfternoon
- 修复基建换人确认超时重启后无法继续原任务的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1476) @NiceAfternoon
- 修复用尽倒计时未确认时的调度异常和错误预约 [PR](https://github.com/ArkMowers/arknights-mower/pull/1468) @NiceAfternoon
- 修复仓库扫描在画面未就绪时继续识别并保存空结果的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1464) @NiceAfternoon
- 修复基建换人联网等待时误报确认失败的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1466) @NiceAfternoon
- 修复共用安装时活动导航刷新导致 MAA 初始化失败的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1474) @ALEXsun0
- 修复桌面 MAA 更新后仍使用旧核心的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1472) @ALEXsun0
- 修复普通轮休等待被误报为执行失败的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1473) @ALEXsun0
- 修复重启后旧替班占位和召回记录丢失导致的轮休阻塞 [PR](https://github.com/ArkMowers/arknights-mower/pull/1470) @ALEXsun0
- 修复收益演算因宿舍选人与实机不一致而反复报错、主班无法轮休的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1471) @YuNHz
- 修复普通信用购物中“代糖”等名单项误匹配“糖”等商品的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1465) @YuNHz
- 修复会客室信息板打不开和自有重复线索漏送 [PR](https://github.com/ArkMowers/arknights-mower/pull/1463) @YuNHz
- 修复共享替班阻塞轮休和组员错误换班的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1457) @ALEXsun0
- 修复独立切产物与换班同时到期时，干员尚未换班就按旧目标切产物、随后又切回的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1469) @ALEXsun0
- 修复训练室进房后因通用识别提前写入场景缓存而跳过协助位换人的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1461) @NiceAfternoon
- 撤销 Windows 独立包的强制管理员权限要求 [PR](https://github.com/ArkMowers/arknights-mower/pull/1460) @ALEXsun0
- 修复鹰角启动动画变暗时误判未知并触发返回键的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1458) @NiceAfternoon
- 修复 MuMu 加速服务无响应弹窗阻挡游戏恢复前台的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1413) @NiceAfternoon
- 修复选人时职业筛选侧栏首次点击未生效后无法继续选人的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1408) @NiceAfternoon
- 修复购物和访友均由 Mower 处理或关闭时，已开启的信用作战被跳过的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1456) @ALEXsun0
- 修复公招结果在职业图标可识别前被关闭的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1406) @NiceAfternoon
- 修复 commit 与 PR skill 因流程出错导致 Changelog 主线不清的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1450) @NiceAfternoon
- 修复邮件收件人配置仅含空字符串或纯空白项时，无法默认发送给自己的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1455) @Fui-Reconk
- 修复收益演算在单回目标失效后未优先选择最低心情干员的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1454) @ALEXsun0
- 改善计算收益结果窗口的浏览与导航 [PR](https://github.com/ArkMowers/arknights-mower/pull/1452) @ALEXsun0
- 修复收益演算重排宿舍时忽略普通位顺序的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1453) @ALEXsun0
- 修正制造站无人机加速的预留数量计算 [PR](https://github.com/ArkMowers/arknights-mower/pull/1449) @ALEXsun0
- 修复软件更新重启后任务未按自动开始设置启动的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1448) @ALEXsun0
- 修正 Changelog 写作规则未明确区分维护对象与产物、未要求修复摘要说明实际旧错误的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1446) @NiceAfternoon
- 收益演算按全程开启线索交流计算会客室产量，计入已解锁且非涣散驻员的交流加速技能。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1445) @ALEXsun0
- 防止普通轮休占用用尽协调所需床位 [PR](https://github.com/ArkMowers/arknights-mower/pull/1442) @ALEXsun0
- 修复收益演算启动受阻和离线排班偏差 [PR](https://github.com/ArkMowers/arknights-mower/pull/1441) @ALEXsun0
- 修复贸易站跑单时机与回收站收取统计 [PR](https://github.com/ArkMowers/arknights-mower/pull/1443) @ALEXsun0
- 修复收益演算中低心情额外恢复的叠加 [PR](https://github.com/ArkMowers/arknights-mower/pull/1440) @ALEXsun0
- 修复收益演算的启动校验、宿舍周转和结果保存展示 [PR](https://github.com/ArkMowers/arknights-mower/pull/1437) @ALEXsun0
- 修复模拟器空闲关闭后的设备对象引用失效 [PR](https://github.com/ArkMowers/arknights-mower/pull/1434) @ALEXsun0
- 修复切表恢复主班时撤销整组下班 [PR](https://github.com/ArkMowers/arknights-mower/pull/1433) @ALEXsun0
- 修复普通达标离宿后误召回仍在休息的绑组 [PR](https://github.com/ArkMowers/arknights-mower/pull/1431) @ALEXsun0
- 使养成共享库存计入专精消耗并接受显式校准 [PR](https://github.com/ArkMowers/arknights-mower/pull/1430) @ALEXsun0
- 修复维护副表主班切入前的替班加速跑单 [PR](https://github.com/ArkMowers/arknights-mower/pull/1428) @ALEXsun0
- 提高入住隔离优先级并按恢复层级分配单回位 [PR](https://github.com/ArkMowers/arknights-mower/pull/1427) @ALEXsun0
- 修复自动救急达标主班反复进出宿舍 [PR](https://github.com/ArkMowers/arknights-mower/pull/1426) @ALEXsun0
- 保留副表切换期间的耗尽与跑单刷新规则 [PR](https://github.com/ArkMowers/arknights-mower/pull/1425) @ALEXsun0
- 修复 Mirror酱无需更新时误报下载信息不完整 [PR](https://github.com/ArkMowers/arknights-mower/pull/1423) @ALEXsun0
- 允许手选孑的精英阶段覆盖森空岛练度 [PR](https://github.com/ArkMowers/arknights-mower/pull/1419) @ALEXsun0
- 优先使用森空岛练度计算孑的基建效率 [PR](https://github.com/ArkMowers/arknights-mower/pull/1418) @ALEXsun0
- 隐藏菲亚交换心情后十分钟内的普通曲线点 [PR](https://github.com/ArkMowers/arknights-mower/pull/1416) @ALEXsun0
- 修复 Windows 中文图标路径导致的材料识别失败 [PR](https://github.com/ArkMowers/arknights-mower/pull/1415) @ALEXsun0
- 修复亿级龙门币数量丢失单位的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1414) @ALEXsun0
- 补齐 PR 交付的格式检查与交接评估 [PR](https://github.com/ArkMowers/arknights-mower/pull/1410) @NiceAfternoon
- 验证切产物后的 MAX 生产份数 [PR](https://github.com/ArkMowers/arknights-mower/pull/1409) @ALEXsun0
- 修复正常连续基建换班的场景超时误判 [PR](https://github.com/ArkMowers/arknights-mower/pull/1403) @NiceAfternoon
- 在每个绑组显示干员完整心情曲线 [PR](https://github.com/ArkMowers/arknights-mower/pull/1407) @ALEXsun0
- 保留模拟器管理程序查询超时后的就绪等待 [PR](https://github.com/ArkMowers/arknights-mower/pull/1391) @NiceAfternoon
- 修复基报灰色订单数漏读 [PR](https://github.com/ArkMowers/arknights-mower/pull/1402) @NiceAfternoon
- 修复 alpha 合入 dev 时文档检查的历史内容误判 [PR](https://github.com/ArkMowers/arknights-mower/pull/1404) @NiceAfternoon
- 统一十类设施的标题优先识别 [PR](https://github.com/ArkMowers/arknights-mower/pull/1400) @ALEXsun0
- 修复基报断裂数字被拆成多位的误读 [PR](https://github.com/ArkMowers/arknights-mower/pull/1393) @NiceAfternoon
- 统一项目正式文本的写作与检查流程 [PR](https://github.com/ArkMowers/arknights-mower/pull/1398) @NiceAfternoon
- 修复救急接管与整组换班的执行遗漏 [PR](https://github.com/ArkMowers/arknights-mower/pull/1387) @ALEXsun0
- 修复空闲关闭后的离线资源清理与恢复顺序 [PR](https://github.com/ArkMowers/arknights-mower/pull/1399) @ALEXsun0
- 按新计算表更新回收站默认估值 [PR](https://github.com/ArkMowers/arknights-mower/pull/1396) @ALEXsun0
- 降低多实例养成规划的加载开销 [PR](https://github.com/ArkMowers/arknights-mower/pull/1394) @ALEXsun0
- 按操作阶段隔离房间耗时预算 [PR](https://github.com/ArkMowers/arknights-mower/pull/1392) @ALEXsun0
- 按配置优先级稳定分配宿舍并刷新恢复计时 [PR](https://github.com/ArkMowers/arknights-mower/pull/1389) @ALEXsun0
- 校验 MAA 核心代次并区分安装完成与重启要求 [PR](https://github.com/ArkMowers/arknights-mower/pull/1245) @Well2333 @ALEXsun0
- 回收站材料识别统一采用 0.90 置信度 [PR](https://github.com/ArkMowers/arknights-mower/pull/1386) @ALEXsun0
- 修复训练列表最右侧卡片漏识别 [PR](https://github.com/ArkMowers/arknights-mower/pull/1385) @ALEXsun0
- 其他组占用工作替班时暂缓整组下班 [PR](https://github.com/ArkMowers/arknights-mower/pull/1384) @ALEXsun0
- 放开同组主班互填并按完整匹配计算床位 [PR](https://github.com/ArkMowers/arknights-mower/pull/1383) @ALEXsun0
- 修复活动导航被 tasks 目录忽略导致无法作战 [PR](https://github.com/ArkMowers/arknights-mower/pull/1382) @ALEXsun0
- 换班预演保留专精保护的训练室驻员 [PR](https://github.com/ArkMowers/arknights-mower/pull/1381) @ALEXsun0
- 复用姓名模板并适配长姓名裁剪 [PR](https://github.com/ArkMowers/arknights-mower/pull/1377) @ALEXsun0
- 修复失床回班清理并按原任务处理冲突 [PR](https://github.com/ArkMowers/arknights-mower/pull/1380) @ALEXsun0
- 跳过启动备份清理的正常锁竞争 [PR](https://github.com/ArkMowers/arknights-mower/pull/1378) @ALEXsun0
- 修复非首页刷新直接显示 JSON [PR](https://github.com/ArkMowers/arknights-mower/pull/1376) @ALEXsun0
- 修复单回临时名单的心情判断优先级 [PR](https://github.com/ArkMowers/arknights-mower/pull/1375) @ALEXsun0
- 修复桌面自动启动与更新后任务恢复 [PR](https://github.com/ArkMowers/arknights-mower/pull/1374) @ALEXsun0
- 将软件更新缓存放入同级 tmp 目录 [PR](https://github.com/ArkMowers/arknights-mower/pull/1373) @ALEXsun0
- 统一应用模块日志并补充共享 logger 准则 [PR](https://github.com/ArkMowers/arknights-mower/pull/1372) @ALEXsun0
- 修复进入回收站时误认训练室 [PR](https://github.com/ArkMowers/arknights-mower/pull/1370) @ALEXsun0
- 修复共享干员失床召回与替班心情准入 [PR](https://github.com/ArkMowers/arknights-mower/pull/1367) @ALEXsun0
- 修复手动五星招募自动选择 [PR](https://github.com/ArkMowers/arknights-mower/pull/1368) @ALEXsun0
- 桌面自动任务仅在 Mower 进程启动时触发 [PR](https://github.com/ArkMowers/arknights-mower/pull/1364) @ALEXsun0
- 修复清缓存后的宿舍绑组恢复与单回垫位 [PR](https://github.com/ArkMowers/arknights-mower/pull/1359) @ALEXsun0
- 删除临期理智药周末使用限制 [PR](https://github.com/ArkMowers/arknights-mower/pull/1363) @ALEXsun0
- /conf 响应禁止缓存 [PR](https://github.com/ArkMowers/arknights-mower/pull/1362) @Fui-Reconk
- 修复共享宿舍额度并检查换班确认冲突 [PR](https://github.com/ArkMowers/arknights-mower/pull/1355) @ALEXsun0
- 修复关闭自动专精时的训练室换班循环 [PR](https://github.com/ArkMowers/arknights-mower/pull/1357) @ALEXsun0
- 校验任务调用并刷新 Android 导航，支持 Mirror 资源更新 [PR](https://github.com/ArkMowers/arknights-mower/pull/1354) @ALEXsun0
- 允许零心情工作干员省略替班并加速排班校验 [PR](https://github.com/ArkMowers/arknights-mower/pull/1353) @ALEXsun0
- 修复 DroidCast 降级后的按住截图与资源恢复 [PR](https://github.com/ArkMowers/arknights-mower/pull/1352) @ALEXsun0

### Improvements

- 减少基建调度的重复心情演算与贸易站读单 [PR](https://github.com/ArkMowers/arknights-mower/pull/1626) @ALEXsun0
- 复用输入相同时的自动养成合成材料规划，减少状态查询和配置生成中的重复计算。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1612) @NiceAfternoon
- 暂停隐藏日志页的任务和状态轮询，重新显示时恢复轮询并触发刷新。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1611) @NiceAfternoon
- 减少 SSIM 均值滤波对已有 float64 数组的重复复制。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1610) @NiceAfternoon
- 减少换班预演中重复创建的驻员副本 [PR](https://github.com/ArkMowers/arknights-mower/pull/1608) @NiceAfternoon
- 批量筛选指定图像范围内的特征点，减少图像匹配的范围判断开销。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1607) @NiceAfternoon
- 从日志文件末尾读取限量时间线，取得所需记录后停止解析。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1606) @NiceAfternoon
- 减少心情曲线候选干员查询对历史表的回表读取。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1605) @NiceAfternoon
- 减少养成规划干员详情的账户统计开销 [PR](https://github.com/ArkMowers/arknights-mower/pull/1604) @NiceAfternoon
- 复用前端重复构建中内容未变的公共资源，减少重复复制。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1584) @NiceAfternoon
- 延长带内容哈希的前端构建资源缓存期限 [PR](https://github.com/ArkMowers/arknights-mower/pull/1583) @NiceAfternoon
- 缩短桌面程序启动阶段的模块加载时间，将基建调度等 solver 与截图存储延迟到实际使用时加载。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1582) @NiceAfternoon
- 减小运行日志背景图片的文件体积 [PR](https://github.com/ArkMowers/arknights-mower/pull/1581) @NiceAfternoon
- 减少页面首次显示需要等待的请求 [PR](https://github.com/ArkMowers/arknights-mower/pull/1579) @NiceAfternoon
- 改用单图标路径导入前端所需图标，减少构建时对无关图标模块的处理。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1578) @NiceAfternoon
- 将长期设置归入所属实例或安装的配置目录 [PR](https://github.com/ArkMowers/arknights-mower/pull/1574) @ALEXsun0
- 改用 vuedraggable 随包发布的 ESM 源码，减少前端 JavaScript 的构建体积。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1538) @NiceAfternoon
- 省去截图 JPEG 编码子进程的一次整帧 Python 输入副本。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1522) @NiceAfternoon
- 按需加载日志页的新增任务表单及其拼音筛选依赖，首次点击「新增任务」时再请求。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1511) @NiceAfternoon
- 复用图像识别中相同资源模板的 ORB 特征，减少重复提取。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1510) @NiceAfternoon
- 减少副表条件在表达式和权限不变时的重复校验与编译。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1508) @NiceAfternoon
- 减少前端任务列表和运行状态的重复读取 @NiceAfternoon
- 减少排班表连续编辑时的重复保存，验证前会等待最新改动保存完成。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1503) @NiceAfternoon
- 降低按时间查看日志时的读取时间和临时内存占用。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1502) @NiceAfternoon
- 加快心情曲线和工休比报表从近期工作记录中筛选候选干员的查询。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1501) @NiceAfternoon
- 复用运行时 ADB 截图已确认的帧头长度 @NiceAfternoon
- 避免干员心情折线表在切换单条或整组曲线的显隐状态时重建图表。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1493) @NiceAfternoon
- 去除干员心情折线表首次载入自选观察表时的重复历史请求。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1492) @NiceAfternoon
- 省去心情报表页面未使用的月度工休统计 @NiceAfternoon
- 减少仓库物品类别识别时的临时内存分配。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1490) @NiceAfternoon
- 减少副表条件未变时的检查开销，省去不会使用的回退状态复制。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1489) @NiceAfternoon
- 加快心情曲线与工休统计的历史记录查询 @NiceAfternoon
- 去除 AI 助手模型输入中重复的当前请求 @NiceAfternoon
- 降低多实例识别和后台缓存的内存占用 [PR](https://github.com/ArkMowers/arknights-mower/pull/1459) @ALEXsun0 @NiceAfternoon
- 优化每日四点跑单保护以减少无人机消耗 [PR](https://github.com/ArkMowers/arknights-mower/pull/1480) @YuNHz

### Dependencies

- 升级 OCR 运行依赖并改用 PP-OCRv6 tiny [PR](https://github.com/ArkMowers/arknights-mower/pull/1649) @NiceAfternoon
- 升级桌面窗口使用的 pywebview 至 6.2.1 [PR](https://github.com/ArkMowers/arknights-mower/pull/1651) @NiceAfternoon
- 升级后端图像处理依赖 Pillow 至 13.0.0。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1646) @NiceAfternoon
- 升级后端运行依赖并统一安装清单 [PR](https://github.com/ArkMowers/arknights-mower/pull/1617) @NiceAfternoon
- 修复前端依赖 follow-redirects 在 Node.js 跨主机重定向时泄露认证头的问题。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1580) @NiceAfternoon
- 升级前端代码检查工具至 ESLint 10 并修复现有检查错误 [PR](https://github.com/ArkMowers/arknights-mower/pull/1534) @NiceAfternoon
- 升级 Vue Router 与 Vitest 并将前端自动构建切换至 Node 24 [PR](https://github.com/ArkMowers/arknights-mower/pull/1529) @NiceAfternoon
- 升级前端配置、排班和自动化状态管理所用的 Pinia 至 4.1.0。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1523) @NiceAfternoon
- 升级心情报表、更新包目录识别、日志高亮和浏览器引擎识别所用的前端依赖。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1516) @NiceAfternoon
- 更新前端的 Vue、Vite、图表、图片导出和拼音检索依赖。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1515) @NiceAfternoon
- 修复前端依赖的已知安全漏洞 @NiceAfternoon

### Maintenance

- 发布 4.1.6-alpha.13 [PR](https://github.com/ArkMowers/arknights-mower/pull/1658) @NiceAfternoon
- 重整项目文档分工与 Agent 工作流程 @NiceAfternoon

### Documentation

- 完善写作 skill，要求文案沿用含义匹配的已有业务称呼并写清操作关系。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1475) @NiceAfternoon
- mower-commit 与 mower-pr 明确标题须以主要动词及其宾语起笔，并规定需要进入更新日志的 PR 在 Summary 首段按最终 diff 写一份 Changelog。 [PR](https://github.com/ArkMowers/arknights-mower/pull/1439) @NiceAfternoon
- 明确查询模拟器状态超时说明的链接文字 [PR](https://github.com/ArkMowers/arknights-mower/pull/1411) @NiceAfternoon
- 完善 PR 写作与交付复盘流程 [PR](https://github.com/ArkMowers/arknights-mower/pull/1405) @NiceAfternoon
- 新增 mower-retro 编码会话复盘技能 [PR](https://github.com/ArkMowers/arknights-mower/pull/1401) @NiceAfternoon
- 新增与 PR 共用标题规则的提交说明 skill [PR](https://github.com/ArkMowers/arknights-mower/pull/1390) @NiceAfternoon
- 改进中文 PR 写作 skill 的标题与正文生成 [PR](https://github.com/ArkMowers/arknights-mower/pull/1379) @NiceAfternoon
- 新增按问题与证据组织说明的 Mower PR 技能 @NiceAfternoon

### Other

- 修复旧姓名缓存导致的训练室协助位换人测试失败 @NiceAfternoon
- 修复读屏响应缺失导致的训练室测试失败 @NiceAfternoon
- 移除训练室驻员测试中污染后续导入的 Skland 替身 @NiceAfternoon

**Full Changelog**: [v4.1.6-alpha.12...v4.1.6-alpha.13](https://github.com/ArkMowers/arknights-mower/compare/v4.1.6-alpha.12...v4.1.6-alpha.13)

## 4.1.6-alpha.12 - 2026-10-10

### New

- 改进 AI 助手、支持 Android 性能测试并更新文档 [PR](https://github.com/ArkMowers/arknights-mower/pull/1329) @ALEXsun0
- 将性能适配并入连接并增加游戏内选人测试 [PR](https://github.com/ArkMowers/arknights-mower/pull/1328) @ALEXsun0

### Bug Fixes

- 修复宿舍排除干员重复换入 [PR](https://github.com/ArkMowers/arknights-mower/pull/1349) @ALEXsun0
- 修复右侧卡片轻微裁切导致的选人失败 [PR](https://github.com/ArkMowers/arknights-mower/pull/1347) @NiceAfternoon
- 修复训练室末页选人错误 [PR](https://github.com/ArkMowers/arknights-mower/pull/1346) @NiceAfternoon
- 修复 HTTPS 和端口转发后的日志连接 [PR](https://github.com/ArkMowers/arknights-mower/pull/1348) @ALEXsun0
- 修复绑组回班纠错及副表心情条件选择 [PR](https://github.com/ArkMowers/arknights-mower/pull/1345) @ALEXsun0
- 修复贸易站订单暂停导致的跑单重试循环 [PR](https://github.com/ArkMowers/arknights-mower/pull/1339) @NiceAfternoon
- 改善普通日志浏览并区分调度图标 [PR](https://github.com/ArkMowers/arknights-mower/pull/1342) @ALEXsun0
- 删除重复性能提示并校验资源打包 [PR](https://github.com/ArkMowers/arknights-mower/pull/1332) @ALEXsun0
- 修复选人末页回弹后的旧坐标点击 [PR](https://github.com/ArkMowers/arknights-mower/pull/1341) @ALEXsun0
- 适配回收站材料产出收取提示 [PR](https://github.com/ArkMowers/arknights-mower/pull/1340) @ALEXsun0
- 允许全零心情工作绑组并验证最新排班 [PR](https://github.com/ArkMowers/arknights-mower/pull/1338) @NiceAfternoon
- 修复跑单中断后的贸易站原班恢复 @NiceAfternoon
- 修正自动性能档位的错误起始说明 [PR](https://github.com/ArkMowers/arknights-mower/pull/1336) @NiceAfternoon
- 修复正式安装包资源增量更新失败 [PR](https://github.com/ArkMowers/arknights-mower/pull/1335) @NiceAfternoon
- 修复实例关闭后更新登记残留的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1333) @NiceAfternoon
- 选人滑动按住期间截图并统一终点等待 [PR](https://github.com/ArkMowers/arknights-mower/pull/1331) @ALEXsun0
- 补充排班条件不满足时的手动刷新指引 [PR](https://github.com/ArkMowers/arknights-mower/pull/1330) @ALEXsun0
- 校验训练位干员技能与专精条件 [PR](https://github.com/ArkMowers/arknights-mower/pull/1327) @ALEXsun0
- 恢复保床规则并限制绑组Free额度 [PR](https://github.com/ArkMowers/arknights-mower/pull/1323) @ALEXsun0
- 更新程序内帮助、模型配置与邮件反馈 [PR](https://github.com/ArkMowers/arknights-mower/pull/1317) @ALEXsun0
- 统一基建技能数据归属并修复 Android 打包缺失 [PR](https://github.com/ArkMowers/arknights-mower/pull/1324) @ALEXsun0
- 修复换班延期后漏安排跑单 [PR](https://github.com/ArkMowers/arknights-mower/pull/1320) @NiceAfternoon
- 修复异常记录的日志级别与详情显示 [PR](https://github.com/ArkMowers/arknights-mower/pull/1319) @NiceAfternoon
- 修复 MaaTouch 触控结束后任务意外暂停 [PR](https://github.com/ArkMowers/arknights-mower/pull/1318) @NiceAfternoon
- 修复休息候补被计入必需床位 [PR](https://github.com/ArkMowers/arknights-mower/pull/1322) @ALEXsun0
- 修复特别关注标志导致训练室姓名漏识别 [PR](https://github.com/ArkMowers/arknights-mower/pull/1315) @ALEXsun0
- 备料完成后立即派发专精任务 [PR](https://github.com/ArkMowers/arknights-mower/pull/1316) @ALEXsun0
- 避免长任务正常结束时误报中断错误 [PR](https://github.com/ArkMowers/arknights-mower/pull/1314) @ALEXsun0
- 开发版与公测版接收更新的公开版本 [PR](https://github.com/ArkMowers/arknights-mower/pull/1313) @ALEXsun0
- 停止后续 macOS x64 构建 [PR](https://github.com/ArkMowers/arknights-mower/pull/1312) @ALEXsun0

### Improvements

- 减少 MaaTouch 调用开销 [PR](https://github.com/ArkMowers/arknights-mower/pull/1325) @NiceAfternoon

### Documentation

- 补充单元测试质量判断规范 [PR](https://github.com/ArkMowers/arknights-mower/pull/1343) @NiceAfternoon

### Other

- prerelease v4.1.6-alpha.12 [PR](https://github.com/ArkMowers/arknights-mower/pull/1350) @ALEXsun0

**Full Changelog**: [v4.1.6-alpha.11...v4.1.6-alpha.12](https://github.com/ArkMowers/arknights-mower/compare/v4.1.6-alpha.11...v4.1.6-alpha.12)

## 4.1.6-alpha.11 - 2026-10-09

### New

- 支持资源包增量 OTA 与整包回退 [PR](https://github.com/ArkMowers/arknights-mower/pull/1308) @ALEXsun0
- 适配旅骨 T5 加工并保留年的优先级 [PR](https://github.com/ArkMowers/arknights-mower/pull/1303) @ALEXsun0
- 选择干员时显示基建技能并优化排班编辑布局 [PR](https://github.com/ArkMowers/arknights-mower/pull/1298) @ALEXsun0
- 初步适配回收站选人与右侧设施拖动布局 [PR](https://github.com/ArkMowers/arknights-mower/pull/1295) @ALEXsun0
- 支持宿舍低优位排序及副表切换重排 [PR](https://github.com/ArkMowers/arknights-mower/pull/1293) @ALEXsun0
- 放宽宿管配置并按位置选择单回宿管 [PR](https://github.com/ArkMowers/arknights-mower/pull/1292) @ALEXsun0
- 支持养成项目合成排序与备齐提醒 [PR](https://github.com/ArkMowers/arknights-mower/pull/1282) @ALEXsun0
- 新增养成规划、一图流同步与库存联动 [PR](https://github.com/ArkMowers/arknights-mower/pull/1281) @ALEXsun0
- MAA 运行日志改为播报任务进度并上传掉落数据 [PR](https://github.com/ArkMowers/arknights-mower/pull/1249) @NiceAfternoon
- 新增默认开启的切产物总开关 [PR](https://github.com/ArkMowers/arknights-mower/pull/1262) @ALEXsun0
- 支持干员多绑组及独立替班 [PR](https://github.com/ArkMowers/arknights-mower/pull/1258) @ALEXsun0
- 副表支持干员名单增减 [PR](https://github.com/ArkMowers/arknights-mower/pull/1259) @ALEXsun0
- 添加加工候选内部休息顺序 [PR](https://github.com/ArkMowers/arknights-mower/pull/1254) @ALEXsun0
- 库存选关新增一键芯片上限、勾选与排序 [PR](https://github.com/ArkMowers/arknights-mower/pull/1247) @ALEXsun0
- 高级设置新增宿舍隔离分组 [PR](https://github.com/ArkMowers/arknights-mower/pull/1246) @ALEXsun0
- 支持同组宿舍绑组主班互填替班 [PR](https://github.com/ArkMowers/arknights-mower/pull/1244) @ALEXsun0
- 独立自动救急排班与初始化调度修复 [PR](https://github.com/ArkMowers/arknights-mower/pull/1236) @ALEXsun0
- 智能救急与基建技能练度筛选 [PR](https://github.com/ArkMowers/arknights-mower/pull/1227) @ALEXsun0
- 集成维护副表定时条件与提前跑单 [PR](https://github.com/ArkMowers/arknights-mower/pull/1219) @ALEXsun0
- 可选救急副表条件与个人恢复上限保护 [PR](https://github.com/ArkMowers/arknights-mower/pull/1215) @ALEXsun0
- 配置导出导入包含 tmp 数据表 [PR](https://github.com/ArkMowers/arknights-mower/pull/1211) @ALEXsun0
- 支持多模拟器实例绑定连接与设置页面一键启动测试 [PR](https://github.com/ArkMowers/arknights-mower/pull/1206) @NiceAfternoon
- 按生效排班自动补货源石碎片 [PR](https://github.com/ArkMowers/arknights-mower/pull/1201) @ALEXsun0
- 所有平台默认自动档 [PR](https://github.com/ArkMowers/arknights-mower/pull/1184) @ALEXsun0
- 支持排班报错分析与自定义模型接口 @ALEXsun0
- 支持还原当前运行排班 [PR](https://github.com/ArkMowers/arknights-mower/pull/1183) @ALEXsun0
- 可配置组内心情差距回班等待 [PR](https://github.com/ArkMowers/arknights-mower/pull/1172) @ALEXsun0

### Bug Fixes

- 校验干员头像并刷新活动数据与到期方案 [PR](https://github.com/ArkMowers/arknights-mower/pull/1310) @ALEXsun0
- 排班图片导入仅识别二维码，避免头像误认条码 [PR](https://github.com/ArkMowers/arknights-mower/pull/1309) @ALEXsun0
- isolate generator dependencies and OTA proxy fixtures @ALEXsun0
- preserve recycle and unknown building skills @ALEXsun0
- 自动补字使用主仓完整原字体 [PR](https://github.com/ArkMowers/arknights-mower/pull/1307) @ALEXsun0
- 补齐旅门骨并自动扩充模板字体子集 [PR](https://github.com/ArkMowers/arknights-mower/pull/1306) @ALEXsun0
- 排班图片导出适配回收站并兼容旧码 [PR](https://github.com/ArkMowers/arknights-mower/pull/1305) @ALEXsun0
- 修复维护副表跑单抑制及提前任务等待 [PR](https://github.com/ArkMowers/arknights-mower/pull/1304) @ALEXsun0
- 修复维护前专精换人及远期跑单避让日志 [PR](https://github.com/ArkMowers/arknights-mower/pull/1300) @ALEXsun0
- 修复 ADB 服务停止后连接恢复反复超时 [PR](https://github.com/ArkMowers/arknights-mower/pull/1299) @NiceAfternoon
- 修复休眠唤醒后误触发场景超时退出 [PR](https://github.com/ArkMowers/arknights-mower/pull/1297) @NiceAfternoon
- 修复延期后重复生成用尽下班任务 [PR](https://github.com/ArkMowers/arknights-mower/pull/1296) @NiceAfternoon
- 修复基建报告读取失败导致的数据丢失与重复记录问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1294) @NiceAfternoon
- 修复开发与审查流程中产生冗余决策记录的问题 [PR](https://github.com/ArkMowers/arknights-mower/pull/1291) @NiceAfternoon
- 允许固定宿舍替班留任原岗位 [PR](https://github.com/ArkMowers/arknights-mower/pull/1290) @ALEXsun0
- 修复 Windows MAA 资源更新入口缺失 [PR](https://github.com/ArkMowers/arknights-mower/pull/1289) @ALEXsun0
- 避免不可加工配方重复轮换干员 [PR](https://github.com/ArkMowers/arknights-mower/pull/1288) @ALEXsun0
- 统一专精换人与跑单的任务避让 [PR](https://github.com/ArkMowers/arknights-mower/pull/1287) @ALEXsun0
- 修复离线清理错误阻塞设备重连 [PR](https://github.com/ArkMowers/arknights-mower/pull/1286) @ALEXsun0
- 修复换班耗时估算与跑单前任务排期 [PR](https://github.com/ArkMowers/arknights-mower/pull/1285) @ALEXsun0
- 补齐菲亚梅塔交换前心情并对齐充能记录 [PR](https://github.com/ArkMowers/arknights-mower/pull/1284) @ALEXsun0
- 修复回班延期并加强副表设施校验 [PR](https://github.com/ArkMowers/arknights-mower/pull/1283) @ALEXsun0
- 修复共享换班挂起与专精保护确认 [PR](https://github.com/ArkMowers/arknights-mower/pull/1280) @ALEXsun0
- 修复索引历史外开发版的更新方向判断 [PR](https://github.com/ArkMowers/arknights-mower/pull/1279) @ALEXsun0
- 一键设置按类别递减空名单档位 [PR](https://github.com/ArkMowers/arknights-mower/pull/1278) @ALEXsun0
- 恢复默认填写 Mower 自带 ADB 路径 [PR](https://github.com/ArkMowers/arknights-mower/pull/1277) @ALEXsun0
- 按组确认上下班并修复多绑组共享替班 [PR](https://github.com/ArkMowers/arknights-mower/pull/1275) @ALEXsun0
- 识别 MuMu 12 运行时目录下的管理器并修正前端构建路径 [PR](https://github.com/ArkMowers/arknights-mower/pull/1276) @Fui-Reconk @ALEXsun0
- 自动性能从极高档开始 [PR](https://github.com/ArkMowers/arknights-mower/pull/1274) @ALEXsun0
- 移除同技能保护并保留中途缺料计划 [PR](https://github.com/ArkMowers/arknights-mower/pull/1273) @ALEXsun0
- 缩短高档选人等待并修复退出页面误判 [PR](https://github.com/ArkMowers/arknights-mower/pull/1271) @ALEXsun0
- 补齐多绑组替班的一键替换候选名单 [PR](https://github.com/ArkMowers/arknights-mower/pull/1269) @NiceAfternoon
- 修复初始充能和休息唤醒的调度衔接 [PR](https://github.com/ArkMowers/arknights-mower/pull/1268) @NiceAfternoon
- 修复共享 ADB 卡死恢复 [PR](https://github.com/ArkMowers/arknights-mower/pull/1267) @NiceAfternoon
- 跳过缺料计划并限制受保护训练室同技能续训 [PR](https://github.com/ArkMowers/arknights-mower/pull/1272) @ALEXsun0
- 修复选人状态图标干扰导致的名单校验超时 [PR](https://github.com/ArkMowers/arknights-mower/pull/1270) @ALEXsun0
- 库存选关优先剿灭和库存关卡并延后普通关卡 [PR](https://github.com/ArkMowers/arknights-mower/pull/1266) @ALEXsun0
- 副表切入切出保留休息状态 [PR](https://github.com/ArkMowers/arknights-mower/pull/1265) @ALEXsun0
- 切产物保留休息并在替班不足时召回主班 [PR](https://github.com/ArkMowers/arknights-mower/pull/1264) @ALEXsun0
- 副表替班切换保留主班状态并支持设施导入 [PR](https://github.com/ArkMowers/arknights-mower/pull/1263) @ALEXsun0
- 修复多绑组准入和副表纠错并隔离测试时钟 [PR](https://github.com/ArkMowers/arknights-mower/pull/1261) @ALEXsun0
- 修复多绑组色条及宿舍替班校验 [PR](https://github.com/ArkMowers/arknights-mower/pull/1260) @ALEXsun0
- 限定设施布局更新拖拽并同步训练室位置 [PR](https://github.com/ArkMowers/arknights-mower/pull/1257) @ALEXsun0
- 配置组内恢复时间差阈值并统一默认值 [PR](https://github.com/ArkMowers/arknights-mower/pull/1256) @ALEXsun0
- 已恢复组员让床不提前召回整组 [PR](https://github.com/ArkMowers/arknights-mower/pull/1255) @ALEXsun0
- 区分新入住单回抢占与空位补位 [PR](https://github.com/ArkMowers/arknights-mower/pull/1253) @ALEXsun0
- 撤回运行排班时同步恢复高级设置 [PR](https://github.com/ArkMowers/arknights-mower/pull/1252) @ALEXsun0
- 启动副表校验增加五秒预算，手动校验不限制耗时 [PR](https://github.com/ArkMowers/arknights-mower/pull/1250) @ALEXsun0
- 避免 MuMu 启动命令因继承输出句柄而阻塞 [PR](https://github.com/ArkMowers/arknights-mower/pull/1232) @NiceAfternoon
- 锁单回时保留菲亚梅塔原位 [PR](https://github.com/ArkMowers/arknights-mower/pull/1243) @ALEXsun0
- 解耦宿舍恢复与不养闲人清退 [PR](https://github.com/ArkMowers/arknights-mower/pull/1242) @ALEXsun0
- 按当前排班覆盖退出救急并调整候补恢复目标 [PR](https://github.com/ArkMowers/arknights-mower/pull/1241) @ALEXsun0
- 副表变更后撤销受影响的旧用尽预约 [PR](https://github.com/ArkMowers/arknights-mower/pull/1240) @ALEXsun0
- 修复自动救急周转、绑组替班及续行 [PR](https://github.com/ArkMowers/arknights-mower/pull/1237) @ALEXsun0
- 随开放日过滤开关隐藏表格占位 [PR](https://github.com/ArkMowers/arknights-mower/pull/1239) @ALEXsun0
- 单 Free 宿舍离宿后跨宿舍重算单回优先级 [PR](https://github.com/ArkMowers/arknights-mower/pull/1238) @ALEXsun0
- 修复未绑组候补回班遗漏 [PR](https://github.com/ArkMowers/arknights-mower/pull/1235) @ALEXsun0
- 修复智能救急启动并简化重复演算 [PR](https://github.com/ArkMowers/arknights-mower/pull/1234) @ALEXsun0
- 加工任务不依赖加工站静态人员 [PR](https://github.com/ArkMowers/arknights-mower/pull/1233) @ALEXsun0
- 改用模板识别训练室干员姓名 [PR](https://github.com/ArkMowers/arknights-mower/pull/1231) @ALEXsun0
- 跑单冲突时提前专精换人并保留跑单时间 [PR](https://github.com/ArkMowers/arknights-mower/pull/1230) @ALEXsun0
- 替换低心情候选对应的满员宿舍住客 [PR](https://github.com/ArkMowers/arknights-mower/pull/1229) @ALEXsun0
- 修复训练室身份确认与异常截图归档 [PR](https://github.com/ArkMowers/arknights-mower/pull/1228) @ALEXsun0
- 统一宿舍优先级与让床补偿 [PR](https://github.com/ArkMowers/arknights-mower/pull/1226) @ALEXsun0
- 完整校验副表组合，超限警告允许启动 [PR](https://github.com/ArkMowers/arknights-mower/pull/1225) @ALEXsun0
- 移除 ADB 接管，统一共享服务与异常恢复 [PR](https://github.com/ArkMowers/arknights-mower/pull/1224) @ALEXsun0
- 统一宿舍恢复规划与卡牌心情预估 [PR](https://github.com/ArkMowers/arknights-mower/pull/1223) @ALEXsun0
- 重构设备恢复并隔离自有 ADB 服务 [PR](https://github.com/ArkMowers/arknights-mower/pull/1222) @ALEXsun0
- 统一模拟器空闲关闭与输入前恢复 [PR](https://github.com/ArkMowers/arknights-mower/pull/1221) @ALEXsun0
- 修复最右列干员选中校验失败 [PR](https://github.com/ArkMowers/arknights-mower/pull/1220) @ALEXsun0
- 修复设备消失后的 DroidCast 清理阻塞 [PR](https://github.com/ArkMowers/arknights-mower/pull/1218) @ALEXsun0
- 隔离设置检测取消信号并调整启动文案 [PR](https://github.com/ArkMowers/arknights-mower/pull/1216) @ALEXsun0
- 适配仓库暗色模式与吸顶导航并修复界面缩放下的浮层定位 [PR](https://github.com/ArkMowers/arknights-mower/pull/1217) @NiceAfternoon
- 按候补配置顺序使用替班 [PR](https://github.com/ArkMowers/arknights-mower/pull/1212) @983122046 @ALEXsun0
- 在连接验证前保存已选择的模拟器实例 [PR](https://github.com/ArkMowers/arknights-mower/pull/1214) @ALEXsun0
- 保留 MuMu Pro 唤醒后的 ADB 重连预算 [PR](https://github.com/ArkMowers/arknights-mower/pull/1213) @ALEXsun0
- 恢复所选模拟器自动启动并统一检测设置 [PR](https://github.com/ArkMowers/arknights-mower/pull/1210) @ALEXsun0
- 隔离托管设备配置与备份导入 [PR](https://github.com/ArkMowers/arknights-mower/pull/1209) @ALEXsun0
- 修复 MuMu Pro 连接并支持多实例选择 [PR](https://github.com/ArkMowers/arknights-mower/pull/1208) @ALEXsun0
- 按宿舍合并清退并兼容未配置训练室 [PR](https://github.com/ArkMowers/arknights-mower/pull/1207) @ALEXsun0
- 修复无人机加速后切产物跨份延期 [PR](https://github.com/ArkMowers/arknights-mower/pull/1204) @ALEXsun0
- 完整收敛换班并保留充能消耗速度 [PR](https://github.com/ArkMowers/arknights-mower/pull/1203) @ALEXsun0
- 修复滚动通告遮挡时的干员选中校验失败 [PR](https://github.com/ArkMowers/arknights-mower/pull/1202) @ALEXsun0
- 修复维护唤醒后继续执行任务 [PR](https://github.com/ArkMowers/arknights-mower/pull/1200) @ALEXsun0
- 恢复无令牌本机日志读取 @ALEXsun0
- 修复重启后用尽回满干员提前回班 [PR](https://github.com/ArkMowers/arknights-mower/pull/1199) @ALEXsun0
- 修复专精期间协助位跟随排班纠错 [PR](https://github.com/ArkMowers/arknights-mower/pull/1198) @ALEXsun0
- 提前安排心情上限清退并优先到期关键任务 [PR](https://github.com/ArkMowers/arknights-mower/pull/1197) @ALEXsun0
- 隐藏子进程的 cmd 窗口 [PR](https://github.com/ArkMowers/arknights-mower/pull/1196) @ALEXsun0
- 隔离肥鸭充能并修复宿舍清退补位 [PR](https://github.com/ArkMowers/arknights-mower/pull/1194) @ALEXsun0
- 修复测试设置误报未绑定角色 [PR](https://github.com/ArkMowers/arknights-mower/pull/1193) @ALEXsun0
- 森空岛与网络测试结果支持复制 [PR](https://github.com/ArkMowers/arknights-mower/pull/1192) @ALEXsun0 @983122046
- 低心情合法替班重新考察候补 [PR](https://github.com/ArkMowers/arknights-mower/pull/1191) @ALEXsun0 @983122046
- 修复公招票数识别因数字碎片报错 [PR](https://github.com/ArkMowers/arknights-mower/pull/1190) @ALEXsun0
- 清理验证成功后的安装包与临时更新器 [PR](https://github.com/ArkMowers/arknights-mower/pull/1186) @ALEXsun0
- 修复登录过程与剿灭弹窗场景误判 [PR](https://github.com/ArkMowers/arknights-mower/pull/1188) @ALEXsun0
- 校准 Nightly OTA 版本方向并保障更新后实例恢复 [PR](https://github.com/ArkMowers/arknights-mower/pull/1187) @ALEXsun0
- 修复排班表头像遮挡操作栏 [PR](https://github.com/ArkMowers/arknights-mower/pull/1185) @ALEXsun0
- 修复满心情主班遗漏不养闲人清退 [PR](https://github.com/ArkMowers/arknights-mower/pull/1182) @ALEXsun0
- 收敛副表旧任务并避免房间重试阻塞调度 [PR](https://github.com/ArkMowers/arknights-mower/pull/1181) @ALEXsun0
- 统一跑单与专精换人前的宿舍避让 [PR](https://github.com/ArkMowers/arknights-mower/pull/1180) @ALEXsun0
- sort tray instances by port [PR](https://github.com/ArkMowers/arknights-mower/pull/1179) @ALEXsun0
- 修复归档中的选人及房间识别错误 [PR](https://github.com/ArkMowers/arknights-mower/pull/1177) @ALEXsun0
- 独立空床补位并保留重排唤醒任务 [PR](https://github.com/ArkMowers/arknights-mower/pull/1176) @ALEXsun0
- 从上一房间恢复后再进入目标房间 [PR](https://github.com/ArkMowers/arknights-mower/pull/1175) @ALEXsun0
- 隔离初始化补读并修复副表换班与肥鸭计时 [PR](https://github.com/ArkMowers/arknights-mower/pull/1174) @ALEXsun0
- 更新包仅包含构建后的 WebUI [PR](https://github.com/ArkMowers/arknights-mower/pull/1170) @ALEXsun0
- 更新后续接原任务队列 [PR](https://github.com/ArkMowers/arknights-mower/pull/1171) @ALEXsun0

### Improvements

- move generation originals to MowerFonts @ALEXsun0
- 统一宿舍逻辑并固定单回目标位置 [PR](https://github.com/ArkMowers/arknights-mower/pull/1205) @ALEXsun0
- 独立性能参数并增加极高选人档 [PR](https://github.com/ArkMowers/arknights-mower/pull/1178) @ALEXsun0

### Maintenance

- ignore local Codex workspace files @ALEXsun0

### Documentation

- 补充系统架构规范文档与一致性校验体系 [PR](https://github.com/ArkMowers/arknights-mower/pull/1195) @NiceAfternoon

### Other

- prerelease v4.1.6-alpha.11 [PR](https://github.com/ArkMowers/arknights-mower/pull/1311) @ALEXsun0
- fix(rescue) : 修正用尽干员救急准入与训练室部署 [PR](https://github.com/ArkMowers/arknights-mower/pull/1251) @ALEXsun0
- fix(rescue) : 修正救急替班门槛与退出导向分床 [PR](https://github.com/ArkMowers/arknights-mower/pull/1248) @ALEXsun0

**Full Changelog**: [v4.1.6-alpha.10...v4.1.6-alpha.11](https://github.com/ArkMowers/arknights-mower/compare/v4.1.6-alpha.10...v4.1.6-alpha.11)

## 4.1.6-alpha.10 - 2026-09-27

### New

- 为报错归档增加可配置磁盘上限 [PR](https://github.com/ArkMowers/arknights-mower/pull/1168) @ALEXsun0
- 支持报错归档筛选、合并与清理 [PR](https://github.com/ArkMowers/arknights-mower/pull/1160) @ALEXsun0
- 支持 Windows 与 Android Nightly OTA 开发版 [PR](https://github.com/ArkMowers/arknights-mower/pull/1159) @ALEXsun0
- 支持调整右侧训练室与办公室位置 [PR](https://github.com/ArkMowers/arknights-mower/pull/1155) @ALEXsun0

### Bug Fixes

- 使用游戏字体修正文字模板并移除截图覆盖 [PR](https://github.com/ArkMowers/arknights-mower/pull/1165) @ALEXsun0
- 固定单回床位并修正重配条件 [PR](https://github.com/ArkMowers/arknights-mower/pull/1166) @ALEXsun0
- 修复 γ 型技能识别并清理不可专精资源 [PR](https://github.com/ArkMowers/arknights-mower/pull/1163) @ALEXsun0
- 修复房间误判与训练室剩余时间日志 [PR](https://github.com/ArkMowers/arknights-mower/pull/1164) @ALEXsun0
- 恢复空床补人并修正心情上下限调度 [PR](https://github.com/ArkMowers/arknights-mower/pull/1162) @ALEXsun0
- 禁用高性能档位并限制自动档 [PR](https://github.com/ArkMowers/arknights-mower/pull/1161) @ALEXsun0
- 修复上下班副表收敛、补床与跑单校时 [PR](https://github.com/ArkMowers/arknights-mower/pull/1158) @ALEXsun0
- 更新后按载入心情数据模式重启 [PR](https://github.com/ArkMowers/arknights-mower/pull/1157) @ALEXsun0
- 移除房间位置选项中的截图提示 @ALEXsun0
- 调整不养闲人排除干员设置位置 [PR](https://github.com/ArkMowers/arknights-mower/pull/1156) @ALEXsun0

### Documentation

- 添加中英双语安全政策 @ALEXsun0

### Other

- prerelease v4.1.6-alpha.10 [PR](https://github.com/ArkMowers/arknights-mower/pull/1169) @ALEXsun0
- 精简重复用例并验证真实专精队列判断 [PR](https://github.com/ArkMowers/arknights-mower/pull/1167) @ALEXsun0

**Full Changelog**: [v4.1.6-alpha.9...v4.1.6-alpha.10](https://github.com/ArkMowers/arknights-mower/compare/v4.1.6-alpha.9...v4.1.6-alpha.10)

## 4.1.6-alpha.9 - 2026-09-26

### New

- 支持专精计划按职业交错排序 [(#1149)](https://github.com/ArkMowers/arknights-mower/pull/1149) @ALEXsun0
- 新增日志调度页面与时间窗口导出 [(#1148)](https://github.com/ArkMowers/arknights-mower/pull/1148) @ALEXsun0
- 关联运行日志与截图并归档报错画面 [(#1146)](https://github.com/ArkMowers/arknights-mower/pull/1146) @ALEXsun0
- 支持不养闲人排除名单并整合初始化 [(#1145)](https://github.com/ArkMowers/arknights-mower/pull/1145) @ALEXsun0
- 增加宿舍高优替班并恢复候补让床 [(#1144)](https://github.com/ArkMowers/arknights-mower/pull/1144) @ALEXsun0
- 将高级设置移入排班并支持导入导出 [(#1143)](https://github.com/ArkMowers/arknights-mower/pull/1143) @ALEXsun0
- 镜像完整包并压缩跨版本 OTA [(#1142)](https://github.com/ArkMowers/arknights-mower/pull/1142) @ALEXsun0
- 跨版本 OTA 并移除 MowerHotUpdate [(#1140)](https://github.com/ArkMowers/arknights-mower/pull/1140) @ALEXsun0

### Bug Fixes

- 修复满员保留、心情初始化与任务冲突 [(#1151)](https://github.com/ArkMowers/arknights-mower/pull/1151) @ALEXsun0
- 等待启动时间结束后再重启模拟器 [(#1150)](https://github.com/ArkMowers/arknights-mower/pull/1150) @ALEXsun0
- 调整常用资源分类和导航定位 [(#1147)](https://github.com/ArkMowers/arknights-mower/pull/1147) @ALEXsun0
- exclude summons from trainee name lookup [(#1141)](https://github.com/ArkMowers/arknights-mower/pull/1141) @ALEXsun0
- 修复副表校验、用尽换班、单回分配与满心情清退 [(#1138)](https://github.com/ArkMowers/arknights-mower/pull/1138) @983122046 @ALEXsun0
- 修复未开训误阻断和未建造训练室反复巡检 [(#1139)](https://github.com/ArkMowers/arknights-mower/pull/1139) @ALEXsun0

### Other

- prerelease v4.1.6-alpha.9 [(#1153)](https://github.com/ArkMowers/arknights-mower/pull/1153) @ALEXsun0

**Full Changelog**: [v4.1.6-alpha.8...v4.1.6-alpha.9](https://github.com/ArkMowers/arknights-mower/compare/v4.1.6-alpha.8...v4.1.6-alpha.9)

## 4.1.6-alpha.8 - 2026-09-25

### New

- 重构仓库页面并支持历史库存对比与走势分析 [(#1128)](https://github.com/ArkMowers/arknights-mower/pull/1128) @NiceAfternoon
- 增加可记忆的关闭与启动偏好 [(#1113)](https://github.com/ArkMowers/arknights-mower/pull/1113) @983122046
- 测试宿舍逻辑支持自定义心情上下限 [(#1132)](https://github.com/ArkMowers/arknights-mower/pull/1132) @ALEXsun0
- 增加重启续接进程操作 [(#1104)](https://github.com/ArkMowers/arknights-mower/pull/1104) @983122046 @ALEXsun0
- 手动编辑锁与副表下拉交互优化 [(#1117)](https://github.com/ArkMowers/arknights-mower/pull/1117) @983122046 @ALEXsun0
- 日志页支持定时启动 [(#1121)](https://github.com/ArkMowers/arknights-mower/pull/1121) @ALEXsun0
- 统一心情报表拖拽排序并支持自定义观察表 [(#1119)](https://github.com/ArkMowers/arknights-mower/pull/1119) @983122046
- 记录肥鸭充能前后心情 [(#1103)](https://github.com/ArkMowers/arknights-mower/pull/1103) @ALEXsun0
- 肥鸭心情曲线标注被充能干员 [(#1097)](https://github.com/ArkMowers/arknights-mower/pull/1097) @ALEXsun0
- preserve recovery targets across plan reorder [(#1094)](https://github.com/ArkMowers/arknights-mower/pull/1094) @ALEXsun0
- rebalance temporary group beds [(#1093)](https://github.com/ArkMowers/arknights-mower/pull/1093) @ALEXsun0

### Bug Fixes

- 保留恢复记录并修复测试逻辑满心情离宿 [(#1135)](https://github.com/ArkMowers/arknights-mower/pull/1135) @ALEXsun0
- keep title bar active on desktop and support late bridge readiness [(#1133)](https://github.com/ArkMowers/arknights-mower/pull/1133) @NiceAfternoon
- 使用模板匹配识别九色鹿因果 [(#1134)](https://github.com/ArkMowers/arknights-mower/pull/1134) @ALEXsun0
- 修复 Windows 窗口尺寸记忆与最大化状态同步 [(#1112)](https://github.com/ArkMowers/arknights-mower/pull/1112) @983122046
- 增加会客室线索流程在产物收取提示浮动时的等待处理 [(#1129)](https://github.com/ArkMowers/arknights-mower/pull/1129) @NiceAfternoon @ALEXsun0
- 稳定宿舍逻辑，不养闲人修复及其与宿舍候补干员联动 [(#1131)](https://github.com/ArkMowers/arknights-mower/pull/1131) @Hul11n @ALEXsun0
- 用游戏字体模板复核训练室技能 [(#1120)](https://github.com/ArkMowers/arknights-mower/pull/1120) @ALEXsun0
- 修复宿舍排班包含空闲位时换班读取心情异常 [(#1126)](https://github.com/ArkMowers/arknights-mower/pull/1126) @NiceAfternoon
- 避免切换产物后补队列确认误报超时 [(#1127)](https://github.com/ArkMowers/arknights-mower/pull/1127) @ALEXsun0
- 将数据标签限定于饼图，避免干扰心情曲线 [(#1125)](https://github.com/ArkMowers/arknights-mower/pull/1125) @983122046
- 恢复周计划控件并移除日志页重复操作 [(#1124)](https://github.com/ArkMowers/arknights-mower/pull/1124) @ALEXsun0
- 优先识别已展开的导航栏 [(#1122)](https://github.com/ArkMowers/arknights-mower/pull/1122) @ALEXsun0
- 校准房间姓名区域并训练模板 [(#1116)](https://github.com/ArkMowers/arknights-mower/pull/1116) @ALEXsun0
- 明确刷理智周计划三种执行状态 [(#1118)](https://github.com/ArkMowers/arknights-mower/pull/1118) @983122046
- 优化干员进驻的识别与选人流程 [(#1115)](https://github.com/ArkMowers/arknights-mower/pull/1115) @NiceAfternoon
- 阻止排班干员进入专精训练 [(#1109)](https://github.com/ArkMowers/arknights-mower/pull/1109) @ALEXsun0
- 验证排班时拦截未持有干员 [(#1111)](https://github.com/ArkMowers/arknights-mower/pull/1111) @ALEXsun0
- 扩展九色鹿垫刀素材类型 [(#1114)](https://github.com/ArkMowers/arknights-mower/pull/1114) @ALEXsun0
- 修正日志页空任务布局 [(#1108)](https://github.com/ArkMowers/arknights-mower/pull/1108) @ALEXsun0
- 修复葛朗台跑单对已就绪订单误报漏单的问题 @NiceAfternoon
- 优化运行日志布局与任务刷新 [(#1101)](https://github.com/ArkMowers/arknights-mower/pull/1101) @983122046 @ALEXsun0
- 在心情提示框显示肥鸭充能对象 [(#1100)](https://github.com/ArkMowers/arknights-mower/pull/1100) @ALEXsun0
- 合并延期排班并阻止单回宿舍循环 [(#1098)](https://github.com/ArkMowers/arknights-mower/pull/1098) @ALEXsun0
- 修复窗口刚打开时标题栏不显示资源包版本的问题 [(#1099)](https://github.com/ArkMowers/arknights-mower/pull/1099) @NiceAfternoon
- 修复重排后停摆与陈旧床位循环 [(#1096)](https://github.com/ArkMowers/arknights-mower/pull/1096) @ALEXsun0
- inherit unset backup room order [(#1095)](https://github.com/ArkMowers/arknights-mower/pull/1095) @ALEXsun0
- 使用包内版本信息校验手动安装包 [(#1092)](https://github.com/ArkMowers/arknights-mower/pull/1092) @ALEXsun0

### Improvements

- 重构测试宿舍逻辑的换班与副表调度 [(#1110)](https://github.com/ArkMowers/arknights-mower/pull/1110) @ALEXsun0
- 移除跑单状态读取的重复进房流程 [(#1107)](https://github.com/ArkMowers/arknights-mower/pull/1107) @ALEXsun0

### Other

- prerelease v4.1.6-alpha.8 [(#1137)](https://github.com/ArkMowers/arknights-mower/pull/1137) @NiceAfternoon
- 换床后重新采样令夕上限计时 [(#1136)](https://github.com/ArkMowers/arknights-mower/pull/1136) @ALEXsun0

**Full Changelog**: [v4.1.6-alpha.7...v4.1.6-alpha.8](https://github.com/ArkMowers/arknights-mower/compare/v4.1.6-alpha.7...v4.1.6-alpha.8)

## 4.1.6-alpha.7 - 2026-09-21

### New

- 支持入住宿舍前切表并重建单回顺序 [(#1087)](https://github.com/ArkMowers/arknights-mower/pull/1087) @ALEXsun0
- 规范训练室判定日志按中文语义与高亮规则展示进驻状态 @NiceAfternoon
- 支持按排班切换基建产物与订单 [(#1079)](https://github.com/ArkMowers/arknights-mower/pull/1079) @ALEXsun0
- 优化窗口在不同缩放比例下的最小尺寸限制与排版布局 @NiceAfternoon
- 支持 Windows MAA OTA 更新 [(#1080)](https://github.com/ArkMowers/arknights-mower/pull/1080) @ALEXsun0
- 联动截图间隔并调整性能档位控件 [(#1077)](https://github.com/ArkMowers/arknights-mower/pull/1077) @ALEXsun0
- 添加自适应设备性能预设 [(#1076)](https://github.com/ArkMowers/arknights-mower/pull/1076) @ALEXsun0
- 完善版本更新维护调度 [(#1075)](https://github.com/ArkMowers/arknights-mower/pull/1075) @ALEXsun0
- 随 Mower 更新 Python 环境并联合检查 MAA 接口 [(#1069)](https://github.com/ArkMowers/arknights-mower/pull/1069) @ALEXsun0

### Bug Fixes

- 统一宿舍休息优先级并修复不养闲人换床 [(#1039)](https://github.com/ArkMowers/arknights-mower/pull/1039) @ALEXsun0
- 修复副表切换时覆盖原上班任务的问题 [(#1090)](https://github.com/ArkMowers/arknights-mower/pull/1090) @NiceAfternoon
- 副表宿舍任务覆盖原宿舍安排 @ALEXsun0
- 修复干员进驻出现二次确认弹窗时识别超时导致排班中断的问题 [(#1089)](https://github.com/ArkMowers/arknights-mower/pull/1089) @NiceAfternoon
- 修复 Mower 刷理智任务未正常消费导致提前休眠的问题 [(#1088)](https://github.com/ArkMowers/arknights-mower/pull/1088) @NiceAfternoon
- 修复副表固定干员与动态宿舍反复抢位 [(#1086)](https://github.com/ArkMowers/arknights-mower/pull/1086) @983122046 @ALEXsun0
- 修复关闭自动专精后训练室纠错被跳过的问题 @NiceAfternoon
- 修复开始训练时核验训练位干员报错的问题 @NiceAfternoon
- 修复关闭自动专精功能时训练室排班纠错被意外跳过的问题 @NiceAfternoon
- 修复训练室面板括号文本残缺时无法识别训练干员的问题 @NiceAfternoon
- 修复训练位浮窗读取失败时误判为空位执行换人的问题 @NiceAfternoon
- 修复训练室处于训练状态时排班任务反复进出房间的问题 @NiceAfternoon
- 修复干员名包含全角括号时读取失败导致训练室反复重读的问题 @NiceAfternoon
- 修复训练位为空时未按计划换入干员导致无法启动专精的问题 @NiceAfternoon
- 修复关闭进驻详情浮窗时误退回基建总览界面的问题 @NiceAfternoon
- 修复输入框聚焦高亮轮廓被窗口边框遮挡的问题 @NiceAfternoon
- 允许训练室绑组继续自动专精 [(#1083)](https://github.com/ArkMowers/arknights-mower/pull/1083) @ALEXsun0
- 按四点切换理智周计划日期 [(#1082)](https://github.com/ArkMowers/arknights-mower/pull/1082) @ALEXsun0
- 完善加工站设置说明 [(#1081)](https://github.com/ArkMowers/arknights-mower/pull/1081) @ALEXsun0
- 分解后保留列表位置避免从头扫描 [(#1078)](https://github.com/ArkMowers/arknights-mower/pull/1078) @ALEXsun0
- 修复清缓存重启时副表误触发 [(#1074)](https://github.com/ArkMowers/arknights-mower/pull/1074) @ALEXsun0
- 修复重复发起森空岛签到的问题 [(#1073)](https://github.com/ArkMowers/arknights-mower/pull/1073) @NiceAfternoon
- 修复任务结束后无法正常休息 [(#1072)](https://github.com/ArkMowers/arknights-mower/pull/1072) @NiceAfternoon
- 修复在保存设置时因遗漏 ADB 路径而导致配置丢失与设备连接异常 [(#1071)](https://github.com/ArkMowers/arknights-mower/pull/1071) @NiceAfternoon
- 修复训练室协助位保护场景下专精任务无法启动的问题 [(#1070)](https://github.com/ArkMowers/arknights-mower/pull/1070) @NiceAfternoon
- 以新同步的森空岛库存校正加工计数 [(#1068)](https://github.com/ArkMowers/arknights-mower/pull/1068) @ALEXsun0

### Improvements

- 统一训练室读取与调度流程中的重排缓冲时间配置 @NiceAfternoon
- 优化进驻详情浮窗已开启时直接读取训练位槽位数据 @NiceAfternoon

### Documentation

- 更新专精自动化模块说明文档与内部说明 @NiceAfternoon

### Other

- prerelease v4.1.6-alpha.7 [(#1091)](https://github.com/ArkMowers/arknights-mower/pull/1091) @NiceAfternoon
- 修正训练室纠错测试用例在未满足前置条件时的误通过问题 @NiceAfternoon
- 隔离导航测试用例执行期间对数据文件的持久化修改 @NiceAfternoon
- 验证训练室被外部干员占用时不生成排班纠错任务 @NiceAfternoon

**Full Changelog**: [v4.1.6-alpha.6...v4.1.6-alpha.7](https://github.com/ArkMowers/arknights-mower/compare/v4.1.6-alpha.6...v4.1.6-alpha.7)

## 4.1.6-alpha.6 - 2026-09-16

### New

- 支持刷理智周计划与信用商店购物独立配置执行方式 [(#1066)](https://github.com/ArkMowers/arknights-mower/pull/1066) @NiceAfternoon
- 基建报表优化 [(#1055)](https://github.com/ArkMowers/arknights-mower/pull/1055) @DarrenDanielDay
- 按完整套装保留数量分解重复家具 [(#1014)](https://github.com/ArkMowers/arknights-mower/pull/1014) @ALEXsun0
- 四端更新验证后清理回退备份并完善宿主兼容 [(#1032)](https://github.com/ArkMowers/arknights-mower/pull/1032) @ALEXsun0
- 支持 Mower 热更新包与四端发行兼容 [(#1029)](https://github.com/ArkMowers/arknights-mower/pull/1029) @ALEXsun0
- 新增宿舍休息候补配置，支持缺床随组待命 [(#1019)](https://github.com/ArkMowers/arknights-mower/pull/1019) @ALEXsun0
- 支持宿舍绑组换班并修复单回入驻排序 [(#1018)](https://github.com/ArkMowers/arknights-mower/pull/1018) @ALEXsun0
- 增加专精材料预算与原料保留设置 [(#1025)](https://github.com/ArkMowers/arknights-mower/pull/1025) @ALEXsun0
- 支持全部配置导出与导入 [(#1027)](https://github.com/ArkMowers/arknights-mower/pull/1027) @ALEXsun0
- 支持源码仓库选择与基于目标分支最新版本的组合 PR 更新 [(#1020)](https://github.com/ArkMowers/arknights-mower/pull/1020) @ALEXsun0

### Bug Fixes

- 更新邮件提醒中QQ邮箱授权码的帮助链接 [(#1065)](https://github.com/ArkMowers/arknights-mower/pull/1065) @NiceAfternoon
- 修复跑单收取时因过渡动画导致的误报漏单问题 [(#1064)](https://github.com/ArkMowers/arknights-mower/pull/1064) @NiceAfternoon
- 修复用尽刷新干员换班时误重置贸易站跑单任务时间 [(#1063)](https://github.com/ArkMowers/arknights-mower/pull/1063) @NiceAfternoon
- 修复一图流上报设置中跳转链接失效 [(#1062)](https://github.com/ArkMowers/arknights-mower/pull/1062) @NiceAfternoon
- 增加低帧率适配并优化选人稳定性 [(#1037)](https://github.com/ArkMowers/arknights-mower/pull/1037) @ALEXsun0
- 仅刷新运行时宿舍优先级 [(#1060)](https://github.com/ArkMowers/arknights-mower/pull/1060) @ALEXsun0
- 修复添加专精任务后出现重复计划与任务的问题 [(#1058)](https://github.com/ArkMowers/arknights-mower/pull/1058) @NiceAfternoon
- 完善安排换人与收取任务异常时的处理流程 [(#1057)](https://github.com/ArkMowers/arknights-mower/pull/1057) @NiceAfternoon
- 修复训练室状态读取流程的异常 [(#1056)](https://github.com/ArkMowers/arknights-mower/pull/1056) @NiceAfternoon
- 恢复心情扫描核对并补齐未排班训练室读取 [(#1054)](https://github.com/ArkMowers/arknights-mower/pull/1054) @ALEXsun0
- 清缓存重启后优先恢复中途换人任务 [(#1053)](https://github.com/ArkMowers/arknights-mower/pull/1053) @ALEXsun0
- 一次性迁移旧版单档减半缓冲配置 [(#1052)](https://github.com/ArkMowers/arknights-mower/pull/1052) @ALEXsun0
- 修复线索交流副表切换并区分倒计时提示 [(#1051)](https://github.com/ArkMowers/arknights-mower/pull/1051) @ALEXsun0
- 修复场景识别缓存不刷新导致的空转 [(#1049)](https://github.com/ArkMowers/arknights-mower/pull/1049) @NiceAfternoon
- 修复训练室面板姓名漏字导致计划误判失败 [(#1048)](https://github.com/ArkMowers/arknights-mower/pull/1048) @ALEXsun0
- 本地合并单 PR，避免 GitHub 合并结果过期阻断 [(#1047)](https://github.com/ArkMowers/arknights-mower/pull/1047) @ALEXsun0
- 修复确认弹窗期间房间名单滚动无法退出 [(#1046)](https://github.com/ArkMowers/arknights-mower/pull/1046) @ALEXsun0
- 改为单 PR 更新并复用 GitHub 合并结果 [(#1044)](https://github.com/ArkMowers/arknights-mower/pull/1044) @ALEXsun0
- 使用 ZIP 原文件备份并避免重启覆盖配置 [(#1040)](https://github.com/ArkMowers/arknights-mower/pull/1040) @ALEXsun0
- 修正减半换人检查并支持分档缓冲 [(#1043)](https://github.com/ArkMowers/arknights-mower/pull/1043) @ALEXsun0
- 修复领取信息板信用时场景判断错误的问题 [(#1042)](https://github.com/ArkMowers/arknights-mower/pull/1042) @NiceAfternoon
- 补齐 scene.json 缺失的场景条目 [(#1041)](https://github.com/ArkMowers/arknights-mower/pull/1041) @NiceAfternoon
- 排班修改后重新生成宿舍优先级 [(#1038)](https://github.com/ArkMowers/arknights-mower/pull/1038) @ALEXsun0
- 修复无关进程导入 log 时清理截图的问题 [(#1016)](https://github.com/ArkMowers/arknights-mower/pull/1016) @NiceAfternoon
- 修复原协助者排班误拦截并保护训练室绑组 [(#1036)](https://github.com/ArkMowers/arknights-mower/pull/1036) @ALEXsun0
- 修复日志版本号被误识别为日期 [(#1035)](https://github.com/ArkMowers/arknights-mower/pull/1035) @ALEXsun0
- 修复宿舍单回重排的职业筛选与失败重选 [(#1034)](https://github.com/ArkMowers/arknights-mower/pull/1034) @ALEXsun0
- 校验基础技能等级并显示实际技能进度 [(#1033)](https://github.com/ArkMowers/arknights-mower/pull/1033) @ALEXsun0
- 避免重复入队并统一连续加工后的人员恢复 [(#1021)](https://github.com/ArkMowers/arknights-mower/pull/1021) @ALEXsun0
- 修复副表切换后提前回班及心情重复扣减 [(#1031)](https://github.com/ArkMowers/arknights-mower/pull/1031) @ALEXsun0
- 兼容排班表未配置训练室的自动专精 [(#1023)](https://github.com/ArkMowers/arknights-mower/pull/1023) @ALEXsun0
- 修复 PR 基线滞后与合并状态未知的误阻断 [(#1022)](https://github.com/ArkMowers/arknights-mower/pull/1022) @ALEXsun0
- 修复窗口吸附失效与拖出最大化后多出的标题栏 [(#1017)](https://github.com/ArkMowers/arknights-mower/pull/1017) @NiceAfternoon
- 按包内容识别离线安装与全局拖拽 [(#1015)](https://github.com/ArkMowers/arknights-mower/pull/1015) @ALEXsun0

### Improvements

- 跳过空闲训练室的倒计时重试 [(#1028)](https://github.com/ArkMowers/arknights-mower/pull/1028) @NiceAfternoon

### Documentation

- 完善专精自动化功能说明文档 [(#1059)](https://github.com/ArkMowers/arknights-mower/pull/1059) @NiceAfternoon

### Other

- prerelease 4.1.6-alpha.6 [(#1067)](https://github.com/ArkMowers/arknights-mower/pull/1067) @NiceAfternoon
- 恢复 swipe_noinertia 的滑动参数 [(#1050)](https://github.com/ArkMowers/arknights-mower/pull/1050) @NiceAfternoon
- 隔离槽位读取测试的自动专精开关 [(#1026)](https://github.com/ArkMowers/arknights-mower/pull/1026) @ALEXsun0
- 放宽进程控制测试就绪等待至30秒 [(#1024)](https://github.com/ArkMowers/arknights-mower/pull/1024) @ALEXsun0

**Full Changelog**: [v4.1.6-alpha.5...v4.1.6-alpha.6](https://github.com/ArkMowers/arknights-mower/compare/v4.1.6-alpha.5...v4.1.6-alpha.6)

## 4.1.6-alpha.5 - 2026-09-09

### New

- Revert "feat(workshop): 新增分解所有重复家具任务 (#1010)" [(#1013)](https://github.com/ArkMowers/arknights-mower/pull/1013) @ALEXsun0
- 按周计划方案保存库存选关规则 [(#1012)](https://github.com/ArkMowers/arknights-mower/pull/1012) @ALEXsun0
- 新增分解所有重复家具任务 [(#1010)](https://github.com/ArkMowers/arknights-mower/pull/1010) @ALEXsun0
- 按 BOX 自动选人并按专精进度准备材料 [(#1000)](https://github.com/ArkMowers/arknights-mower/pull/1000) @ALEXsun0
- 自动规划协助者并增加通用专精路线预览 [(#997)](https://github.com/ArkMowers/arknights-mower/pull/997) @ALEXsun0

### Bug Fixes

- 修复 MAA 回归测试进入真实休眠导致卡住 [(#1011)](https://github.com/ArkMowers/arknights-mower/pull/1011) @ALEXsun0
- 修复黑流树海误退出并支持任务结束后恢复主题 [(#1009)](https://github.com/ArkMowers/arknights-mower/pull/1009) @ALEXsun0
- 高门槛一键设置保留蚀清和技巧概要干员 [(#1008)](https://github.com/ArkMowers/arknights-mower/pull/1008) @ALEXsun0
- 排除无法在训练室专精的机械师与电弧 [(#1007)](https://github.com/ArkMowers/arknights-mower/pull/1007) @ALEXsun0
- 修复无心情加工与残留备料并增加休息优先级开关 [(#1006)](https://github.com/ArkMowers/arknights-mower/pull/1006) @ALEXsun0
- 修复多干员重复加工并按心情限制批量 [(#1005)](https://github.com/ArkMowers/arknights-mower/pull/1005) @ALEXsun0
- 修复 alpha Release 更新日志不显示 [(#1004)](https://github.com/ArkMowers/arknights-mower/pull/1004) @ALEXsun0
- 保护手动合成配置并完善宿舍与垫刀设置 [(#1002)](https://github.com/ArkMowers/arknights-mower/pull/1002) @ALEXsun0
- 纠错优先安排替班，无可用替班时保留叫回 [(#1003)](https://github.com/ArkMowers/arknights-mower/pull/1003) @ALEXsun0
- 隐藏 Windows ADB 端口探测控制台窗口 @ALEXsun0
- 允许渠道回退并要求点击安装后二次确认 @ALEXsun0
- 按 Latest 和 Pre-release 获取软件更新 @ALEXsun0
- 隔离网页连接断线，防止日志转发线程退出 @ALEXsun0
- 统一 MAA 软件名称的大小写 [(#996)](https://github.com/ArkMowers/arknights-mower/pull/996) @ALEXsun0

### Other

- prerelease v4.1.6-alpha.5 @NiceAfternoon

**Full Changelog**: [v4.1.6-alpha.4...v4.1.6-alpha.5](https://github.com/ArkMowers/arknights-mower/compare/v4.1.6-alpha.4...v4.1.6-alpha.5)

## 4.1.6-alpha.4 - 2026-09-08

### New

- 补齐肉鸽玩法字段下发并支持配置企鹅物流上报 id [(#994)](https://github.com/ArkMowers/arknights-mower/pull/994) @NiceAfternoon
- 补齐 MAA 肉鸽任务通用字段并按主题和策略显示对应字段 [(#991)](https://github.com/ArkMowers/arknights-mower/pull/991) @NiceAfternoon
- 新增 Mall 只买折扣与保留最大信用、Fight 一图流上报 [(#989)](https://github.com/ArkMowers/arknights-mower/pull/989) @NiceAfternoon
- 支持访问好友由 mower 原生或 MAA 处理 [(#988)](https://github.com/ArkMowers/arknights-mower/pull/988) @NiceAfternoon
- 改用 medicine_expire_days 支持按剩余天数使用理智药 [(#983)](https://github.com/ArkMowers/arknights-mower/pull/983) @NiceAfternoon
- 保存配置时只写入修改过的键 [(#977)](https://github.com/ArkMowers/arknights-mower/pull/977) @NiceAfternoon
- 将 Windows 端窗口改为无边框自绘标题栏并保留原生缩放 [(#979)](https://github.com/ArkMowers/arknights-mower/pull/979) @NiceAfternoon
- 完善更新进度、取消操作与自动检查 [(#966)](https://github.com/ArkMowers/arknights-mower/pull/966) @ALEXsun0
- 支持源码分支与提交切换并兼容不同 Python 环境 [(#965)](https://github.com/ArkMowers/arknights-mower/pull/965) @ALEXsun0
- 支持自动更新、实例进程控制与 SOCKS 代理 [(#962)](https://github.com/ArkMowers/arknights-mower/pull/962) @ALEXsun0
- 支持软件更新、多实例恢复与统一网络代理 [(#959)](https://github.com/ArkMowers/arknights-mower/pull/959) @ALEXsun0

### Bug Fixes

- 修复无边框窗口丢失的最小化、最大化与还原动画 [(#995)](https://github.com/ArkMowers/arknights-mower/pull/995) @NiceAfternoon
- retain operator branches in mastery resource data [(#993)](https://github.com/ArkMowers/arknights-mower/pull/993) @ALEXsun0
- 修复仓库加载、404兜底及下拉头像显示 [(#992)](https://github.com/ArkMowers/arknights-mower/pull/992) @ALEXsun0
- 修复 MAA 出错导致游戏被关闭 [(#990)](https://github.com/ArkMowers/arknights-mower/pull/990) @NiceAfternoon
- 修复 StartUp 与 Fight 未下发协议必填的 client_type [(#986)](https://github.com/ArkMowers/arknights-mower/pull/986) @NiceAfternoon
- 修复 WebUI 深色模式下输入框和选择框显示白色 [(#987)](https://github.com/ArkMowers/arknights-mower/pull/987) @ALEXsun0
- 修复调用 maa 信用作战时设置指定的编队不生效 [(#985)](https://github.com/ArkMowers/arknights-mower/pull/985) @NiceAfternoon
- 统一 ADB 与 scrcpy 重连并修正模拟器首次启动策略 [(#982)](https://github.com/ArkMowers/arknights-mower/pull/982) @ALEXsun0 @NiceAfternoon
- 完善实例扫描、日志与三端兼容 [(#976)](https://github.com/ArkMowers/arknights-mower/pull/976) @ALEXsun0
- 修复源码更新与资源版本在 Windows 中文环境下的异常 [(#978)](https://github.com/ArkMowers/arknights-mower/pull/978) @NiceAfternoon
- 修复森空岛瞬时网络错误导致仓库扫描中断 [(#975)](https://github.com/ArkMowers/arknights-mower/pull/975) @NiceAfternoon
- 修复 macOS 多开启动并统一托盘与平台默认配置 [(#973)](https://github.com/ArkMowers/arknights-mower/pull/973) @ALEXsun0
- 修复 MuMu12 更新重启后设备未就绪导致连接失败的问题 [(#974)](https://github.com/ArkMowers/arknights-mower/pull/974) @NiceAfternoon
- 修复访问好友时识别不到访问下位按钮导致提前结束的问题 [(#972)](https://github.com/ArkMowers/arknights-mower/pull/972) @NiceAfternoon
- 修复训练室面板因 OCR 噪声导致干员名误判 [(#970)](https://github.com/ArkMowers/arknights-mower/pull/970) @NiceAfternoon
- 修复打包后测试 Maa 连接时配置文件加载报错的问题 [(#969)](https://github.com/ArkMowers/arknights-mower/pull/969) @NiceAfternoon
- 修复源码更新与资源版本在 Windows 中文环境下的测试失败 [(#968)](https://github.com/ArkMowers/arknights-mower/pull/968) @NiceAfternoon
- 修复设备指纹服务不可达时森空岛认证误报设备信息无效 [(#967)](https://github.com/ArkMowers/arknights-mower/pull/967) @NiceAfternoon
- fix(log)：修复日志文件被多进程占用导致写入失败的问题 [(#964)](https://github.com/ArkMowers/arknights-mower/pull/964) @NiceAfternoon
- 放行 npm 元数据并增加强制更新二次确认 [(#963)](https://github.com/ArkMowers/arknights-mower/pull/963) @ALEXsun0
- 减少空闲日志并恢复每小时清理 [(#960)](https://github.com/ArkMowers/arknights-mower/pull/960) @ALEXsun0
- 修复模拟器自动启动及设备就绪判断 [(#957)](https://github.com/ArkMowers/arknights-mower/pull/957) @ALEXsun0

### Improvements

- 统一软件更新进度条与下载状态展示 [(#971)](https://github.com/ArkMowers/arknights-mower/pull/971) @ALEXsun0
- 分离截图预览、写盘与过期清理 [(#958)](https://github.com/ArkMowers/arknights-mower/pull/958) @ALEXsun0

### Dependencies

- 升级 vue 与 naive-ui 并适配新版输入组件行为 [(#980)](https://github.com/ArkMowers/arknights-mower/pull/980) @NiceAfternoon

### Maintenance

- 将日志页背景图更换为「结城理」精二立绘 [(#981)](https://github.com/ArkMowers/arknights-mower/pull/981) @NiceAfternoon

### Other

- prerelease v4.1.6-alpha.4 @NiceAfternoon

**Full Changelog**: [v4.1.6-alpha.3...v4.1.6-alpha.4](https://github.com/ArkMowers/arknights-mower/compare/v4.1.6-alpha.3...v4.1.6-alpha.4)

## 4.1.6-alpha.3 - 2026-09-05

### New

- 窗口标题显示资源包版本并在资源更新后实时刷新 [(#955)](https://github.com/ArkMowers/arknights-mower/pull/955) @NiceAfternoon
- 资源包展示版本号日期改为构建日期 [(#954)](https://github.com/ArkMowers/arknights-mower/pull/954) @NiceAfternoon
- 基建技能数据改为运行时下发 [(#953)](https://github.com/ArkMowers/arknights-mower/pull/953) @NiceAfternoon
- 支持活动结束或定时切换周计划 [(#952)](https://github.com/ArkMowers/arknights-mower/pull/952) @ALEXsun0
- 恢复刷理智表格计划并新增库存选关 [(#949)](https://github.com/ArkMowers/arknights-mower/pull/949) @ALEXsun0
- 资源包更新支持免重启与自动更新 [(#945)](https://github.com/ArkMowers/arknights-mower/pull/945) @ALEXsun0
- 新增 MAA 资源检查与更新 [(#946)](https://github.com/ArkMowers/arknights-mower/pull/946) @ALEXsun0
- 新增手动添加仓库扫描任务 [(#937)](https://github.com/ArkMowers/arknights-mower/pull/937) @NiceAfternoon
- 新增多平台 MAA 下载与更新功能 [(#932)](https://github.com/ArkMowers/arknights-mower/pull/932) @ALEXsun0

### Bug Fixes

- 仓库扫描遇到 MEMENTO 纪念品崩溃 [(#956)](https://github.com/ArkMowers/arknights-mower/pull/956) @NiceAfternoon
- 多开实例共用资源包 [(#951)](https://github.com/ArkMowers/arknights-mower/pull/951) @ALEXsun0
- 修复无人机加速面板首次点击未生效时误消费跑单任务 [(#948)](https://github.com/ArkMowers/arknights-mower/pull/948) @NiceAfternoon
- 刷新并缓存 MAA 更新版本 [(#947)](https://github.com/ArkMowers/arknights-mower/pull/947) @ALEXsun0
- 修复训练位已是计划干员时保护逻辑仍阻止开始训练 [(#943)](https://github.com/ArkMowers/arknights-mower/pull/943) @NiceAfternoon
- 修复低优替班轮休时重复占用床位导致大组无法下班的问题 [(#942)](https://github.com/ArkMowers/arknights-mower/pull/942) @NiceAfternoon
- Windows MAA 改为提示手动更新 [(#944)](https://github.com/ArkMowers/arknights-mower/pull/944) @ALEXsun0
- 修复场景图导航缓存不刷新导致空转刷日志的问题 [(#941)](https://github.com/ArkMowers/arknights-mower/pull/941) @NiceAfternoon
- 修复排班组纠错把已在岗成员计入纠错任务导致反复重排 [(#940)](https://github.com/ArkMowers/arknights-mower/pull/940) @NiceAfternoon
- 修复 WebView 启动失败时异常被静默吞掉无法记录 [(#939)](https://github.com/ArkMowers/arknights-mower/pull/939) @NiceAfternoon
- 修复森空岛签到失败与导入崩溃 [(#938)](https://github.com/ArkMowers/arknights-mower/pull/938) @NiceAfternoon
- 修复游戏数据更新后仓库扫描识别不准与资源生成崩溃的问题 [(#936)](https://github.com/ArkMowers/arknights-mower/pull/936) @NiceAfternoon
- 修复基建报表悬停收益 NaN 与干员心情折线表图例重叠 [(#935)](https://github.com/ArkMowers/arknights-mower/pull/935) @NiceAfternoon
- 修复检测基建通知时在全暗过渡帧越界崩溃 [(#933)](https://github.com/ArkMowers/arknights-mower/pull/933) @NiceAfternoon
- 修复 macOS 应用启动并改用 DMG 发布 [(#931)](https://github.com/ArkMowers/arknights-mower/pull/931) @ALEXsun0
- 修复专精换人任务档位错误显示为计划最终目标 [(#929)](https://github.com/ArkMowers/arknights-mower/pull/929) @NiceAfternoon
- 修复手动更新包在浏览器与桌面端导入失败 [(#930)](https://github.com/ArkMowers/arknights-mower/pull/930) @ALEXsun0
- 修复干员安排确认循环因识别失败抛错导致排班中断 [(#928)](https://github.com/ArkMowers/arknights-mower/pull/928) @NiceAfternoon
- 修复训练室排班纠错与收取流程 [(#927)](https://github.com/ArkMowers/arknights-mower/pull/927) @NiceAfternoon
- 修复仓库扫描在界面就绪前切标签导致误识别 [(#926)](https://github.com/ArkMowers/arknights-mower/pull/926) @NiceAfternoon

### Maintenance

- 医疗和重装专三协助位改为望并优化专精推荐展示 [(#934)](https://github.com/ArkMowers/arknights-mower/pull/934) @NiceAfternoon

**Full Changelog**: [v4.1.6-alpha.2...v4.1.6-alpha.3](https://github.com/ArkMowers/arknights-mower/compare/v4.1.6-alpha.2...v4.1.6-alpha.3)

## 4.1.6-alpha.2 - 2026-09-03

### New

- 新增资源更新与热更通道 [(#923)](https://github.com/ArkMowers/arknights-mower/pull/923) @NiceAfternoon
- 配置文件改走原子写并挪到 config/ 目录 [(#920)](https://github.com/ArkMowers/arknights-mower/pull/920) @NiceAfternoon

### Bug Fixes

- 修复排班图片导入在导出图被改过后失败 [(#922)](https://github.com/ArkMowers/arknights-mower/pull/922) @NiceAfternoon
- 修复一键替换干员漏换主副表全部字段的问题 [(#921)](https://github.com/ArkMowers/arknights-mower/pull/921) @NiceAfternoon
- 修复窗口尺寸配置不生效 [(#919)](https://github.com/ArkMowers/arknights-mower/pull/919) @NiceAfternoon
- 修复连接错误被误判导致运行中的游戏退出与资源残留 [(#918)](https://github.com/ArkMowers/arknights-mower/pull/918) @NiceAfternoon
- 修复 Linux 独立包缺少 pywebview 的 GTK 后端导致窗口无法启动 [(#917)](https://github.com/ArkMowers/arknights-mower/pull/917) @NiceAfternoon

### Improvements

- 精简识别热路径 DEBUG 日志 [(#925)](https://github.com/ArkMowers/arknights-mower/pull/925) @NiceAfternoon
- 图像识别改用纯 numpy 实现缩减打包体积 [(#916)](https://github.com/ArkMowers/arknights-mower/pull/916) @NiceAfternoon

### Dependencies

- changelog 按版本类型选取基准并新增依赖升级分组 [(#913)](https://github.com/ArkMowers/arknights-mower/pull/913) @NiceAfternoon
- 升级 echarts、vite、vitest 等前端依赖 [(#912)](https://github.com/ArkMowers/arknights-mower/pull/912) @NiceAfternoon

**Full Changelog**: [v4.1.6-alpha.1...v4.1.6-alpha.2](https://github.com/ArkMowers/arknights-mower/compare/v4.1.6-alpha.1...v4.1.6-alpha.2)

## 4.1.6-alpha.1 - 2026-09-01

### New

- 支持正式版与 alpha 的跨平台构建发布 ([#911](https://github.com/ArkMowers/arknights-mower/pull/911) @NiceAfternoon)
- 创建专精计划后立即开始训练 (@NiceAfternoon)
- 新增按干员是否空闲筛选专精计划 (@NiceAfternoon)
- 新增专精推荐显示真实技能名和显式保存专精计划与路线配置 (@NiceAfternoon)
- 新增协助位设置中的配置，优化专精计划管理，并将手动专精任务改为专精计划创建 (@NiceAfternoon)
- 新增全自动专精全局开关，专精相关任务由仓库扫描触发 (@NiceAfternoon)
- 专精训练进度改为按训练室画面识别结果更新 (@NiceAfternoon)
- 专精数据新增干员技能名称供界面显示与识别核对 (@NiceAfternoon)
- 修改专精计划状态与路线设置为数据库保存 (@NiceAfternoon)
- 新增数据库管理，并支持按类别删除记录 (@NiceAfternoon)
- 新增领取会客室信息板信用 ([#885](https://github.com/ArkMowers/arknights-mower/pull/885) @NiceAfternoon)
- 新增启动游戏自定义命令选项 ([#883](https://github.com/ArkMowers/arknights-mower/pull/883) @ALEXsun0)
- 新增缓存清零后刷新副表开关并修复训练室读取条件 ([#881](https://github.com/ArkMowers/arknights-mower/pull/881) @ALEXsun0)
- 优化全自动专精状态机，整合训练室状态检测到心情读取 ([#880](https://github.com/ArkMowers/arknights-mower/pull/880) @NiceAfternoon)
- 初步实现调用 MAA 刷生息演算 ([#878](https://github.com/ArkMowers/arknights-mower/pull/878) @NiceAfternoon)
- add MAA mac compatibility check ([#877](https://github.com/ArkMowers/arknights-mower/pull/877) @ALEXsun0)
- 重构全自动专精调度、增加加工站干员配置并修复邮件和无法删除的加工配置问题 ([#873](https://github.com/ArkMowers/arknights-mower/pull/873) @NiceAfternoon)
- 完善全自动专精功能 ([#871](https://github.com/ArkMowers/arknights-mower/pull/871) @NiceAfternoon)
- 实现全自动专精功能并优化合成方案配置 ([#862](https://github.com/ArkMowers/arknights-mower/pull/862) @mikuzc)
- add Closure order in report and trade order analysis ([#865](https://github.com/ArkMowers/arknights-mower/pull/865) @NiceAfternoon)
- 周计划关卡按开放时间过滤，活动期间可关闭 ([#860](https://github.com/ArkMowers/arknights-mower/pull/860) @clousky2020)
- 可露希尔 跑单 (@Shawnsdaddy)
- APIKEY 后门 (@Shawnsdaddy)
- 验证码solver (@Shawnsdaddy)
- changelog pop up (@Shawnsdaddy)
- 为 Mower AI 助手输出内容添加 markdown 渲染 ([#842](https://github.com/ArkMowers/arknights-mower/pull/842) @NiceAfternoon)
- add one more cause (@Shawnsdaddy)
- 周计划方案 (@Shawnsdaddy)
- 漏单分析 agent (@Shawnsdaddy)
- 完善森空岛签到功能并优化前端显示逻辑 ([#838](https://github.com/ArkMowers/arknights-mower/pull/838) @NiceAfternoon)
- 增加了森空岛的终末地签到和测试签到功能 ([#827](https://github.com/ArkMowers/arknights-mower/pull/827) @NiceAfternoon)
- MuMu截图增强 (@Shawnsdaddy)
- 添加多开器一键启动全部实例 (@yufuyufuyu)
- 分类新增 (@Shawnsdaddy)
- #743 新增检测 (@Shawnsdaddy)

### Bug Fixes

- 修复计划外训练与换人后任务、通知的干员、技能与档位显示 (@NiceAfternoon)
- 修复清空超时任务后只剩远期专精任务时基建安排不处理 (@NiceAfternoon)
- 修复替换组干员名称含引号时心情曲线查询失败 (@NiceAfternoon)
- 修复专精计划页显示无效的三星筛选项 (@NiceAfternoon)
- 修复任务接口未校验 Webview Token (@NiceAfternoon)
- 修复错误的创建专精任务，应该使用MasterySync正确地创建任务 ([#906](https://github.com/ArkMowers/arknights-mower/pull/906) @GodofTheFallen)
- 修复 MAA 连通性检测误报 ([#901](https://github.com/ArkMowers/arknights-mower/pull/901) @ALEXsun0)
- 最小化修复mower无法停止问题 ([#892](https://github.com/ArkMowers/arknights-mower/pull/892) @ALEXsun0)
- 修复启动前 MAA 连通性检查时序 ([#889](https://github.com/ArkMowers/arknights-mower/pull/889) @ALEXsun0)
- 统一任务间休眠收口，修复休息期间 /status 的 sleeping 状态 ([#884](https://github.com/ArkMowers/arknights-mower/pull/884) @djkcyl)
- 修复训练室空闲检测误判，优化全自动专精稳定性 ([#875](https://github.com/ArkMowers/arknights-mower/pull/875) @NiceAfternoon)
- 添加缺失的截图 (@Konano)
- 修复识别跑单订单价值时模板误匹配 ([#858](https://github.com/ArkMowers/arknights-mower/pull/858) @NiceAfternoon)
- 4.1.6专精模块修复完善 ([#855](https://github.com/ArkMowers/arknights-mower/pull/855) @mikuzc)
- release warpup (@Shawnsdaddy)
- 修复房间干员识别、用尽任务时间和见习任务跳过 ([#848](https://github.com/ArkMowers/arknights-mower/pull/848) @ALEXsun0)
- 修复跑单订单类型误判并适配新增材料分类 ([#851](https://github.com/ArkMowers/arknights-mower/pull/851) @NiceAfternoon)
- 修复 auto_get_res_new.py 中的解析逻辑，适配部分游戏数据字段从数字改为字符串 ([#849](https://github.com/ArkMowers/arknights-mower/pull/849) @NiceAfternoon)
- 处理闪断更新公告中的 24:00 时间 ([#850](https://github.com/ArkMowers/arknights-mower/pull/850) @clousky2020)
- ruff check (@Shawnsdaddy)
- 修复了连战次数识别错误和理智获取错误的问题并为更新日志添加 markdown 渲染 ([#843](https://github.com/ArkMowers/arknights-mower/pull/843) @NiceAfternoon)
- add missing code (@Shawnsdaddy)
- unit test failures (@Shawnsdaddy)
- ruff format (@Shawnsdaddy)
- 修复公招 (@Shawnsdaddy)
- 支持旧版本mumuapi (@yufuyufuyu)
- 滑动修复 (@Shawnsdaddy)
- 修复 option 不显示 (@Shawnsdaddy)
- 修复家具零件碳素组不合成 ([#778](https://github.com/ArkMowers/arknights-mower/pull/778) @HoverSoul)
- 解决linux中找不到zbar共享库问题 ([#780](https://github.com/ArkMowers/arknights-mower/pull/780) @pikahan)
- 修复：公招截图太快导致tag重复识别 ([#775](https://github.com/ArkMowers/arknights-mower/pull/775) @HoverSoul)
- 修复op_data.party_time未初始化问题 & 家具零件垫刀问题 ([#772](https://github.com/ArkMowers/arknights-mower/pull/772) @HoverSoul @Shawnsdaddy)
- 修复训练free /current bug (@Shawnsdaddy)
- 九色鹿逻辑判定修复 (@Shawnsdaddy)
- 仅在party时间过期或不存在时更新op_data.party_time，以修复跃跃排班表失效 (@HoverSoul)
- 计算点击次数方法修复 (@Shawnsdaddy)
- 修复边际case (@Shawnsdaddy)
- 无缝加工站bug修复+添加graph (@Shawnsdaddy)

### Improvements

- 提取基建进驻排序坐标、无人机界面等待与跑单时间读取为共用函数 (@NiceAfternoon)
- 优化前后端体积与启动性能，修复基建报表数据读取 ([#904](https://github.com/ArkMowers/arknights-mower/pull/904) @NiceAfternoon)
- 4.1.6仓库刷新逻辑优化 ([#857](https://github.com/ArkMowers/arknights-mower/pull/857) @mikuzc)
- 版本号更新 (@Shawnsdaddy)
- 游戏资源更新 (@Shawnsdaddy)
- 资源更新 (@Shawnsdaddy)
- 识别图片更新 (@Shawnsdaddy)
- 版本更新 (@Shawnsdaddy)
- 游戏数据更新 (@Shawnsdaddy)
- UI优化 (@Shawnsdaddy)
- 九色鹿优化 (@Shawnsdaddy)
- tool 更新 (@Shawnsdaddy)
- 游戏资源更新 (@Shawnsdaddy)
- 资源更新 (@Shawnsdaddy)
- 游戏资源更新 (@Shawnsdaddy)
- 提示词优化 (@Shawnsdaddy)
- 导航更新 (@Shawnsdaddy)
- 用尽任务优化 (@Anyk00)
- MAAapi更新 (@Anyk00)
- 九色鹿任务条件判定更新 (@Shawnsdaddy)
- 适配更新 (@Shawnsdaddy)
- 优化开发的打包步骤和文档 (@servis)
- 更新Q群 (@Shawnsdaddy)

### Maintenance

- run dev_tools formatting (@Shawnsdaddy)

### Documentation

- 为 README 添加 Docker 部署文档链接 ([#866](https://github.com/ArkMowers/arknights-mower/pull/866) @dhujsi)
- 更新 README 文档，修正格式和内容 (@Konano)
- 本地文档复活 (@Shawnsdaddy)

### Other

- 修复公招测试因模拟 NumPy 导致模型数据导入失败 (@NiceAfternoon)
- 更新 CHANGELOG 至 4.1.5.8 并优化打包体积 ([#903](https://github.com/ArkMowers/arknights-mower/pull/903) @NiceAfternoon)
- 更新游戏数据，修复专精调度/导航/日志等问题 ([#902](https://github.com/ArkMowers/arknights-mower/pull/902) @Shawnsdaddy @NiceAfternoon)
- Update master plan ([#895](https://github.com/ArkMowers/arknights-mower/pull/895) @Shawnsdaddy)
- 更新游戏数据（新增干员机械师） ([#899](https://github.com/ArkMowers/arknights-mower/pull/899) @WufeiHalf)
- 更新 CHANGELOG 至 4.1.5.7 并更新游戏数据 ([#890](https://github.com/ArkMowers/arknights-mower/pull/890) @NiceAfternoon)
- Update master plan ([#886](https://github.com/ArkMowers/arknights-mower/pull/886) @Shawnsdaddy)
- 更新 CHANGELOG 至 4.1.5.6 ([#874](https://github.com/ArkMowers/arknights-mower/pull/874) @NiceAfternoon)
- 更新 CHANGELOG 和 游戏数据 ([#872](https://github.com/ArkMowers/arknights-mower/pull/872) @NiceAfternoon)
- changelog (@Shawnsdaddy)
- 4.1.6专精模块 ([#854](https://github.com/ArkMowers/arknights-mower/pull/854) @mikuzc)
- changelog ([#852](https://github.com/ArkMowers/arknights-mower/pull/852) @NiceAfternoon)
- 游戏资源 (@Shawnsdaddy)
- changelog (@Shawnsdaddy)
- UI (@Shawnsdaddy)
- max AP (@Shawnsdaddy)
- Deepseek option (@Shawnsdaddy)
- auto-nav update final draft (clean up later) (@Shawnsdaddy)
- add missing code (@Shawnsdaddy)
- dev_tools (@Shawnsdaddy)
- 4.1.5 ([#837](https://github.com/ArkMowers/arknights-mower/pull/837) @Shawnsdaddy @NiceAfternoon @Well2333)
- 🐳 添加 Dockerfile、docker-compose.yml 和相关构建脚本，支持 Mower 镜像构建与运行 ([#825](https://github.com/ArkMowers/arknights-mower/pull/825) @Well2333)
- add pic (@Shawnsdaddy)
- draft (@Shawnsdaddy)
- 4.1.0 ([#821](https://github.com/ArkMowers/arknights-mower/pull/821) @Shawnsdaddy @Anyk00 @eiHeyH)
- 4.1.1 ([#809](https://github.com/ArkMowers/arknights-mower/pull/809) @Shawnsdaddy @Anyk00 @eiHeyH)
- 2025.10.1 ([#800](https://github.com/ArkMowers/arknights-mower/pull/800) @Shawnsdaddy @djkcyl)
- 移除不必要的操作 (@Shawnsdaddy)
- 移除diy.py (@Shawnsdaddy)
- 提前跑单卡死 (@Shawnsdaddy)
- 扩展颜色识别范围 (@citydirector)
- Update get_number (@citydirector)
- #622 (@Shawnsdaddy)
- MAA 调用退回主界面 (@Shawnsdaddy)
- fix 函数名typo (@Shawnsdaddy)
- #394 add new feature (@Shawnsdaddy)
- fix config not first load (@Shawnsdaddy)
- 加个catch 防止命令失败 (@Shawnsdaddy)
- 读基报等2秒动画 (@Shawnsdaddy)
- tool cmd update (@Shawnsdaddy)
- 结束后返回主界面 (@Shawnsdaddy)
- 会客室新家具支持 (@Shawnsdaddy)
- 施工完毕：九色鹿允许非基建材料垫刀 ([#779](https://github.com/ArkMowers/arknights-mower/pull/779) @HoverSoul)
- 修正：加工站任务的垫刀材料检查及添加报错提示 ([#777](https://github.com/ArkMowers/arknights-mower/pull/777) @HoverSoul)
- AI输出 改为流式 (@Shawnsdaddy)
- AI 添加FAQ工具 (@Shawnsdaddy)
- fix format (@Shawnsdaddy)
- 欢迎词 (@Shawnsdaddy)
- Add 读取数据库tool (@Shawnsdaddy)
- update requirement (@Shawnsdaddy)
- Agent ([#767](https://github.com/ArkMowers/arknights-mower/pull/767) @Shawnsdaddy)
- add submit issue tool (@Shawnsdaddy)
- 训练位放人 ([#759](https://github.com/ArkMowers/arknights-mower/pull/759) @Anyk00)
- init _agent (@Shawnsdaddy)
- 挤人上班时跳过回满改为跳过用尽回满 (@Anyk00)
- 允许通过本地图片训练识别模型 (@Anyk00)
- 清除宿舍信息前match (@Shawnsdaddy)
- 饼图工休比计算调整，调整为组内最低，同时点击组名按钮可以显示/隐藏全组干员工休比，饼图可拖拽，拖拽有做本地持久化 (@Suzuran-ley)
- bug fix (@Shawnsdaddy)
- 重新格式化了一下 (@Suzuran-ley)
- Revert "bugfix" (@Anyk00)
- 加工站任务防卡死 (@Shawnsdaddy)
- MAA运行中截图 (@Shawnsdaddy)
- 扫描前刷新一次仓库 (@Shawnsdaddy)
- 如果有下班任务，则跳过纠错 (@Shawnsdaddy)
- 识别干员使用多线程加速 (@Anyk00)
- bugfix (@Anyk00)
- 合并设置时保持有序 (@Shawnsdaddy)
- bug fix (@Shawnsdaddy)
- fix format (@Shawnsdaddy)
- 更改版本号 (@qiuming2022)
- 增加Linux系统下的Docker一键部署 (@servis)
- #743 九色鹿支持 (@Shawnsdaddy)
- 添加Linux系统下python源码打包文件spec以及构建部署方法 (@servis)
- 在README.md中添加本地源码部署的教程 (@servis)
- fix typo (@Shawnsdaddy)
- #743 加入任务流 (@Shawnsdaddy)
- #743 仓库数据存入数据库 (@Shawnsdaddy)
- 添加MAA连续战斗次数智能化，提高战斗效率 (@qiuming2022)
- 自动合成材料的初步实现 (@Shawnsdaddy)

**Full Changelog**: [2025.5.3.3...v4.1.6-alpha.1](https://github.com/ArkMowers/arknights-mower/compare/2025.5.3.3...v4.1.6-alpha.1)

## v4.1.5.8 - 2026-08-07

### 修复

- 修复 MAA 连通性检测误报
- 修复日志无输出的问题
- 修复专精 level 3 训练误插入换人任务的问题
- 专精升级改为读取倒计时成功后才标记 in_progress
- 修复活动关卡导航失败的问题
- 新增关卡体力消耗（AP）fallback 配置
- 修复 local operation 体力消耗为 None 导致的报错
- 游戏在后台时不强制退出，直接拉起前台
- MAA 配置缺失时友好降级
- 专精路线设置 - 默认值从JSON读取、自动保存、恢复默认修复

### 其他

- 更新游戏数据至SideStory `直到大地变为一颗酸橙`
- 优化打包体积

### 详细内容

#### 修复 fix

* 修复 mower 无法停止的问题（`/stop` 状态快照缺失字段导致接口报错） [#892](https://github.com/ArkMowers/arknights-mower/pull/892) [@ALEXsun0](https://github.com/ALEXsun0)

* 修复 MAA 连通性检测误报，补充启动前检查测试 [#901](https://github.com/ArkMowers/arknights-mower/pull/901) [@ALEXsun0](https://github.com/ALEXsun0)

* 修复专精调度、导航、日志等问题（训练时间读取真实倒计时、level 3 不再换人、导航失败、新增 AP fallback） [#902](https://github.com/ArkMowers/arknights-mower/pull/902) [@Shawnsdaddy](https://github.com/Shawnsdaddy)

* 修复专精路线设置默认值，专精计划改为从数据库读取 [#895](https://github.com/ArkMowers/arknights-mower/pull/895) [@Shawnsdaddy](https://github.com/Shawnsdaddy)

#### 清理 cleanup

* 删除 training_idle 死代码块与 half_off 剩余引用 [#895](https://github.com/ArkMowers/arknights-mower/pull/895) [@Shawnsdaddy](https://github.com/Shawnsdaddy)

#### 更新 update

* 更新游戏数据（新增干员机械师）及补充机械师基建技能描述 [#899](https://github.com/ArkMowers/arknights-mower/pull/899) [@WufeiHalf](https://github.com/WufeiHalf)

* 更新游戏数据，修复专精调度/导航/日志等问题 [#902](https://github.com/ArkMowers/arknights-mower/pull/902) [@Shawnsdaddy](https://github.com/Shawnsdaddy)

* 更新 CHANGELOG 至 4.1.5.8 并优化打包体积 [#903](https://github.com/ArkMowers/arknights-mower/pull/903) [@NiceAfternoon](https://github.com/NiceAfternoon)

## v4.1.5.7 - 2026-07-10

### 新增

- 新增 MAA 连通性测试与启动前检查
- 新增调用 MAA 刷生息演算，支持的主题有 `沙洲遗闻` 和 `重启锚点`
- 新增基建设置 `读取心情后先刷新副表`，开启后缓存清零重启会先读取心情并按载入心情数据模式自动重启，再触发副表和后续排班
- 新增启动游戏自定义命令选项，并预设唤醒无锁屏设备后启动游戏的命令
- 新增领取会客室信息板信用

### 修复

- 修复训练室空闲检测误判，优化全自动专精稳定性
- 优化全自动专精状态机，整合训练室状态检测到心情读取
- 统一任务间休眠收口，修复休息期间 /status 的 sleeping 状态
- 专精路线设置 - 默认值从JSON读取、自动保存、恢复默认修复

### 其他

- 更新游戏数据至故事集 `丛林症结`

### 详细内容

#### 新增 feat

* add MAA mac compatibility check [#877](https://github.com/ArkMowers/arknights-mower/pull/877) [@ALEXsun0](https://github.com/alexsun0)

* 初步实现调用 MAA 刷生息演算 [#878](https://github.com/ArkMowers/arknights-mower/pull/878) [@NiceAfternoon](https://github.com/NiceAfternoon)

* 新增缓存清零后刷新副表开关并修复训练室读取条件 [#881](https://github.com/ArkMowers/arknights-mower/pull/881) [@ALEXsun0](https://github.com/alexsun0)

* 新增启动游戏自定义命令选项 [#883](https://github.com/ArkMowers/arknights-mower/pull/883) [@ALEXsun0](https://github.com/alexsun0)

* 新增领取会客室信息板信用 [#885](https://github.com/ArkMowers/arknights-mower/pull/885) [@NiceAfternoon](https://github.com/NiceAfternoon)

#### 修复 fix

* 修复训练室空闲检测误判，优化全自动专精稳定性 [#875](https://github.com/ArkMowers/arknights-mower/pull/875) [@NiceAfternoon](https://github.com/NiceAfternoon)

* 优化全自动专精状态机，整合训练室状态检测到心情读取 [#880](https://github.com/ArkMowers/arknights-mower/pull/880) [@NiceAfternoon](https://github.com/NiceAfternoon)

* 统一任务间休眠收口，修复休息期间 /status 的 sleeping 状态 [#884](https://github.com/ArkMowers/arknights-mower/pull/884) [@djkcyl](https://github.com/djkcyl)

* 专精路线设置 - 默认值从JSON读取、自动保存、恢复默认修复 [#886](https://github.com/ArkMowers/arknights-mower/pull/886) [@Shawnsdaddy](https://github.com/Shawnsdaddy)

## 4.1.5.6

- 修复在无专精计划时重复添加加工站配置的问题
- 修复邮件发送基建报告时缺失龙舌兰赤金的问题
- 优化全自动专精功能
- 新增基建设置 `训练室协助位总是跟随排班`
- 新增自动合成配置的默认加工站干员设置
- 新增无专精计划时可使用自动合成配置添加全量材料合成配置
- 移除专精计划与排班表的冲突检测

详细内容：
### 新增 feat

- feat: 重构全自动专精调度、增加加工站干员配置并修复邮件和无法删除的加工配置问题 [(#873)@NiceAfternoon](https://github.com/ArkMowers/arknights-mower/commit/8a000046167caa90d40c9e526e98f6310d76ed0c)


## 4.1.5.5

- 新增全自动专精功能
- 优化合成方案配置
- 新增周计划关卡按开放时间过滤（活动期间可手动关闭）
- 在 基建报表 和 贸易订单分析 中增加可露希尔赤金
- 修复识别跑单订单价值时模板误匹配
- 仓库刷新逻辑优化
- 专精模块修复完善
- 更新游戏数据
- 网页文档中新增 专精推荐 和 Docker 部署

详细内容：
### 新增 feat

- feat: 完善全自动专精功能 [(#871)@NiceAfternoon](https://github.com/ArkMowers/arknights-mower/commit/2ee0cfd909c277ba5c978d4c2fa20a83ac313ac2)
- feat: 实现全自动专精功能并优化合成方案配置 [(#862)@mikuzc](https://github.com/ArkMowers/arknights-mower/commit/b54c7a89199fdf8e71731768a39c8be970564bef)
- feat: add Closure order in report and trade order analysis [(#865)@NiceAfternoon](https://github.com/ArkMowers/arknights-mower/commit/92c2cb2fc95043e816bdca1fbcdbfa2553269890)
- feat: 周计划关卡按开放时间过滤，活动期间可关闭 [(#860)@clousky2020](https://github.com/ArkMowers/arknights-mower/commit/42a8f6b9e8cdb0f4c662fd4c666dd47567225447)
- 4.1.6仓库刷新逻辑优化 [(#857)@mikuzc](https://github.com/ArkMowers/arknights-mower/commit/f72c81794102c27cbb762d7635c8181a3f7266fb)
- 4.1.6专精模块修复完善 [(#855)@mikuzc](https://github.com/ArkMowers/arknights-mower/commit/16e5a818a2119585237c4626f97cc4494243e2b3)

### 修复 fix

- fix: 修复识别跑单订单价值时模板误匹配 [(#858)@NiceAfternoon](https://github.com/ArkMowers/arknights-mower/commit/067aaffe3be283bf1baab27cf656635eb926560d)

### 文档 doc

- docs: 为 README 添加 Docker 部署文档链接 [(#866)@dhujsi](https://github.com/ArkMowers/arknights-mower/commit/612797cc15448bdabb02da1922642e9043ded839)
- 文档更新内容详见 [Commits - doc-pages](https://github.com/ArkMowers/arknights-mower/commits/doc-pages)


## 4.1.5.4

- 新增专精推荐模块
- 支持一图流干员练度导入
- 适配最大理智上限改为 210
- 新增专精推荐 Tab 页面
- 修复部分场景下的理智数据异常

详细内容：
### 新增 feat

- 专精推荐模块 [@Shawnsdaddy]
- 一图流干员练度导入 [@Shawnsdaddy]
- 4.1.6专精模块 [(#854)@mikuzc]

### 修复 fix

- 适配最大理智上限 210 [@Shawnsdaddy]

## 4.1.5.3

- 新增可露希尔跑单
- 处理闪断更新公告中不合法的结束时间
- 修复跑单订单类型识别不正确的问题
- 为新增的四种材料在仓库中分类
- 修复基建房间干员名称前缀匹配错误
- 防止用尽任务生成过期时间
- 领取奖励时跳过见习任务页检查

详细内容：
### 新增 feat
- 可露希尔跑单 [@Shawnsdaddy](https://github.com/ArkMowers/arknights-mower/commit/7ada670ab5050f9f2082da9f0289c0682a8ef729)

### 修复 fix
- 处理闪断更新公告中的 24:00 时间 [(#850)@clousky2020](https://github.com/ArkMowers/arknights-mower/commit/98e31804cb5b53c2116b3ffa902b2277535c4495)
- 修复 auto_get_res_new.py 中的解析逻辑，适配部分游戏数据字段从数字改为字符串 [(#849)@NiceAfternoon](https://github.com/ArkMowers/arknights-mower/commit/9071db83b10129037046715f581f7daca45e4c92)
- 修复跑单订单类型误判并适配新增材料分类 [(#851)@NiceAfternoon](https://github.com/ArkMowers/arknights-mower/commit/b6e23d2d93f09dd76597db53d66f96b87e267c4a)
- 修复房间干员识别、用尽任务时间和见习任务跳过 [(#848)@ALEXsun0](https://github.com/ArkMowers/arknights-mower/commit/1b2d9baff710aa5f8de2a8f1129de35b3980dbf4)

## 4.1.5.2
- 游戏数据更新
- 支持 可露希尔 跑单
- UI周计划更新（中文名字+开放日期显示）
- 新增解决验证码功能（需要设置MowerAI助手使用）
- 新增每日体力阈值功能
- 新增自动刷关（关卡自动导航需要设置MowerAI助手，否则可以在群里求导航路径配置文件在\tmp文件夹下）
- 新增版本改动信息提示
- AI助手输出内容支持 markdown 渲染
- 新增Deepseek深度思考选项
- 新增APIKEY后门（支持token.txt文件）
- 修复理智获取错误
- UI设置页面调整，大型任务移至获取信用及购物下方

## 4.1.5.1
- AI助手新增漏单分析工具
- 自动刷关软登录

## 4.1.5
- 游戏资源更新，新增多开命名显示，补充 Docker / 镜像构建相关支持。

## 4.1.4
- 游戏资源更新，新增森空岛终末地签到和测试签到功能。

## 4.1.3
- 资源更新。

## 4.1.2
- 修复提前跑单循环问题。

## 4.1.1
- 切换到 4.1.x 版本号体系，修复专精结算页面识别。

## 2025.10.1
- 游戏数据更新、识别图片更新、公招修复、兼容旧版 MuMu API，并清理部分无用操作。

## 2025.8.2.1
- 修复8.2 保活设置不触发问题
- UI修复DS 深度思考选项不显示
- 新增服务器维护期间提前跑单
- 新增服务器维护期间自动暂停任务

## 2025.8.2
- 九色鹿修复+优化
- 非工作站选人后心情排序移除（宿舍除外）
- 新增任务结束后台保活
- 读取基报2秒延时

## 2025.8.1
- 游戏资源更新

## 2025.7.3
- 游戏资源更新

## 2025.7.2
- 九色鹿合成修复了Key报错
- 游戏资源更新
- party时间小问题修复

## 2025.7.1.2
- AI新增了分析报错信息功能
- 多开器新增了一键全部启动
- 可能修复了加工站安排"Free"或者"Current"失败的bug（可是测下来可能还有其他问题）比如训练室房间是空会卡死，选人中间报错会卡死
- AI文本改为streaming

## 2025.7.1.1
- 把 7.1 没有加的训练室代码补进来了
- 训练位不可安排 3 星，或者技能未满级的 4 星以上干员（问 YJ 为什么）
- 训练位无法选择正在工作的干员
- AI更新了检索常见问题功能，内置了部分 FAQ 表（找不到可以反馈）
- 系统任务 + 报错存入数据库，以便以后用 AI 分析
- AI更新了防止乱问功能
- AI修复了找不到工具卡死的 bug

## 2025.7.1
- 清除宿舍信息前 match（修复莫名其妙纠错 bug）
- 允许通过本地图片训练识别模型
- MAAapi更新
- 用尽任务优化
- 挤人上班时跳过回满改为跳过用尽回满
- 本地文档复活
- 新增本地 AI 助手，目前仅接入 deepseek
- 仅在 party 时间过期或不存在时更新 op_data.party_time，以修复跃跃排班表失效
- 训练位放人
- 九色鹿逻辑判定修复
- 保全派驻导航更新

## 2025.6.3.1
- UI添加额外的报表分析+自定义产出
- 修复在某些条件下宿舍信息会丢失的bug
- 九色鹿字典报错修复

## 2025.6.3
- 新增MAA视J
- 仓库分类新增新材料
- 增加skd读取仓库材料频率
- 九色鹿计算点击修复
- 如果有未下完班任务，跳过纠错
- 合并副表优先级保持有序
- 九色鹿判定条件优化
- 加工任务新增防卡死机制（还未找到卡死bug root cause）

## 2025.6.2
- UI适配更新
- 新干员数据添加

## 2025.6.1.1
- 优化加工完截图时机
- 修复加工站概率卡死

## 2025.6.1
- 无缝材料合成支持九色鹿
- 修复了材料合成的已知bug

## 2025.5.5
- 无缝材料合成上线（九色鹿敬请期待）

## 2025.5.4.1
- 修复了仓库字典key报错
- 修复了材料中途不够导致的死循环

## 2025.5.4
- MAA连战支持（pikahan,qiuming2022）
- 无缝材料合成（暂不支持九色鹿）

## 2025.5.3.4
- 邮件发送订单报告修复
- 选人swipe计数时机修复
- 启动副表触发时机修复

## 2025.5.3.3
- UI截图设置加入缓存，图片url加入释放逻辑
- 职介选人前都会切一次ALL

## 2025.5.3.1beta
- 修正跑单时间时自动加速低级贸易站（如果未指定无人机贸易站）
- 选人时间如果略长（15s每个干员）则自动记录为使用职介筛选

## 2025.5.3
- 跑单自动加速低级无人机修复（Wei-png）

## 2025.5.3beta
- 基建跳转识别优化
- UI新增模拟器实时截图
- 切表自动清除宿舍优先级

## 2025.5.2
- ALL职介选择改成始终切ALL来规避YJbug【幸运104n,浮生泪】
- 除0报错【th.252_32贸...】
- 真实用尽在有组情况不触发

## 2025.5.1.1
- ALL职介选择优化【415470991】

## 2025.5.1
- 游戏新角色适配
- 职介筛选适配性更新

## 2025.4.2
- 邮件发送添加跑单信息
- 第一次启动自动切副表
- 中枢读取详细心情倒计时
- 重新更新了选人模型和元数据，请重新更新 4.2+ 资源

## 2025.4.1
- 新干员适配
- 修复不养闲人任务合并(Anyk00)
- 修复邮件发送时机(Anyk00)
- 修复重启游戏bug+优化添加专精任务(Anyk00)
- MAA导航api更新(Outsider225)

## 2025.3.1
- 新干员适配
- 发送时间revert

## 2025.2.3
- 修复了2.2的亿点点bug
- 邮件发送改为MAA停止后
- 读取时间失败不再显示error

## 2025.2.2
- 计算上班时间根据条件移除 强制优先级(anykk00)
- Docker构建文件更新(frlda)
- 模拟器卡死重启修复
- 恢复提前8分钟上班(anykk00)
- 下班+排序任务合并
- 修复party检测不到时间问题
- UI修复宿舍优先级显示问题
- 更新新干员

## 2025.2.1
- UI新增急救心情阈值(anykk00)
- 替换组心情监视(anykk00)
- 无人机上限提升
- UI更新+MAA领取奖励(anykk00)
- 联网增加30秒timeout时间，防止Mower卡死
- 释放不会增加过时任务【czt635】
- 宿舍移位优化（增加vip重排+自定义优先级）
- 新增自定义宿舍排序
- 减少进错房间重试次数

## 2025.1.4
- 重启线索功能

## 2025.1.3
- 适配游戏更新
- 暂时关闭线索功能
- 排班表添加活动室（UI）暂时不支持换人，没什么卵用的话以后会移除

## 2025.1.2
- 兼容老排班表如果低优先设置过多会排班出错（会报warning）【1121362417等】
- 修复若干小bug
- 用尽下班失败不会疯狂轰炸邮件
- 主班阿米娅下班无法被选择【2139689327】
- 选人二次确认修复【很多人】
- 后端移除部分最大分组数代码

## 2025.1.1
- 宿舍排序优化
- 正在激活的副表提醒【911804553】
- 强制弹性模式
- 弹性模式bug修复【1249033051】
- 新版MAA调用修复【2768543172等】
- 保全导航超重绝缘水泥修复【1772532975】
- 反馈log添加版本信息+排班表

## 2024.12.5.3
- 修复在低帧率模式下，选人会失败
- 修复在宿舍移位撤回情况导致宿舍数据被纠错清除【911804553】

## 2024.12.5.2
- 修复用尽下班会去宿舍再读取一次下班时间

## 2024.12.5.1
- 修复代码拼写错误【3023094357】
- 弹性模式 跳过plan逻辑优化 【911804553】

## 2024.12.5
- 职介筛选配色阈值调低【1079159658】
- 保全导能单元选择更新 【1772532975】
- 修复弹性模式在某些情况不会生成 用尽 下班任务
- 弹性模式 用尽 增加极端情况报错
- MAA如果中途停止依旧发送部分掉落信息

## 2024.12.4
- 修复新增宿舍移位任务检查时机失效【923857607,1404766716等】
- 修复非当前宿舍宿管在前会找不到【3634223326】
- 修复某些特定情况下会出现两个相同人 【3634223326,491134959,1404766716】
- 修复某些场景会卡死邮箱（之前改动代码没有复制进增量包）【923857607等】
- 移除某些日志打印（yk00）
- 新增新逻辑的用尽处理（还没有机会测试）

## 2024.12.3
- 邮箱识别修复 + 自动清除已读邮件【很多人】
- 排班逻辑优化（在宿舍直接滑动到最后，如果滑动太远会直接切回第一页）
- 新增弹性休息模式，具体改动请去 UI 基建设置界面查看（半测试，建议先试用）：最大分组数失效，低优先逻辑变更为强制低优先，回满逻辑变更为强制回满，整体平均心情低于心情阈值 * 0.75 时休息阶段塞满宿舍，否则只安排满 vip 位
- 新增宿舍排序逻辑（高效组会自动往前挪），可能与旧的休息模式混用产生问题，后续会根据反馈继续修正
- 无人机跑单改为接收订单（原先是滑动）
- 任务执行排序按照工作站然后宿舍 1-4
- 保全任务导航更新【1772532975】
- 肉鸽新增分队

## 2024.12.2
- UI 邮箱设置增加时差修正
- 修复宿舍职介排序不触发

## 2024.12.1.1
- 更新游戏资源

## 2024.12.1
- 新增识别订单并且将数据存至数据库 支持一键导入老订单截图 UI订单分析移动
- 新增安排重复干员检查【3634223326】
- 用尽刷新修复【911804553】（未测试）
- 修复特定情况下的选人问题【3634223326】（半测试）

## 2024.11.2.2
- 修复部分设备职业筛选卡住
- 修复待办事项收取CD不工作+改成15分钟CD
- 新增非葛朗台跑单截图

## 2024.11.2.1
- 移除测试代码
- 更新CD逻辑防止卡住+CD改成30分钟

## 2024.11.2
- 新增用户反馈（邮件自动上传log）
- 收取基建通知加入2小时CD（防止误触）
- 修复filter 识别

## 2024.11.1.4
- 搬运仓库扫描
- 修复 干员选择时 影响多个工作站 无法确认
- 房间检查逻辑优化
- 修复菲亚任务+贸易站刷新 卡死（未测试）
- 修复不养闲人概率循环
- 改动记录倒序排序

## 2024.11.1.3
- 改动收取TODO 限制为一次（）防止重复点击成一键休息

## 2024.11.1.2
- 新增职介筛选
- 如果出现 bug 请反馈至频道
- 可以前往 \arknights_mower\data\arrange_order.json ，将「职介选择开关」替换成 [] 以关闭该功能

## 2024.11.1.1
- 新干员基地选择模型更新
- UI头像更新
- 深海组心情倒序(临时解决）

## 2024.11.1
- 游戏UI界面适配更新
- 更新后卡死的可以更改截图方式

## 2024.10.1.3
- 预测最短休息时间排除加工站干员
- 跑单截图优化
- 必须从 10.1.2 以上更新

## 2024.10.1.2
- 修复专精任务无法添加
- 修复不养闲人未排除黑名单
- 新增休息预测最低休息时间功能（半测试）：生成上班任务时，如果预计算有干员会在休息完毕前用尽，则会修改上班时间为用尽前半小时；只在心情自救模式不生效的时候触发

## 2024.10.1.1
- 修正了异格的选人识别+添加头像

## 2024.10.1
- 不养闲人模式现在会随时塞心情未达到上限的干员去休息了
- UI 更新：副表支持输入房间，拖拽自动更新【所有其他表】对应数据
- 跑单截图加回来了
- 尝试修复skd签到
- 还有其他用户体验优化
- UI【重要】附表支持前后移动（可以将全局副表向后移动，因为同时满足条件的情况排序靠后的副表会覆盖前面的副表）

## 2024.9.4
- 新增功能：不养闲人任务合并
- 新增功能：自定义副表名称
- 新增功能：信用作战指定编队
- 基建逻辑优化：仅回满干员在同组无用尽的情况下会提前上班，移除仅回满干员心情上限 -0.5
- 使用优化：UI 路径改动
- 使用优化：调用 MAA 刷日常时可以手动停止 MAA
- 使用优化：工具人数据加入缓存
