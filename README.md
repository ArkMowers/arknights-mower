<div align="center">

![logo](https://github.com/Konano/arknights-mower/raw/main/logo.png)

# arknights-mower

[![GitHub License](https://img.shields.io/github/license/Konano/arknights-mower?style=flat-square)](https://github.com/Konano/arknights-mower/blob/master/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/arknights-mower?style=flat-square)](https://pypi.org/project/arknights-mower/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/arknights-mower?style=flat-square)](https://pypi.org/project/arknights-mower/)
[![GitHub Workflow Status](https://img.shields.io/github/workflow/status/Konano/arknights-mower/Upload%20PyPI?style=flat-square)](https://github.com/Konano/arknights-mower/actions/workflows/python-publish.yml)
![GitHub last commit (branch)](https://img.shields.io/github/last-commit/Konano/arknights-mower/main?style=flat-square)

7*24 小时不间断长草，让你忘掉这个游戏！

</div>

## ⚠ 注意事项

- 本程序不支持国服以外的明日方舟区服。
- 原理上，使用本程序没有任何被判定为作弊并被封号的风险，但是作者不对使用此程序造成的任何损失负责。
- 开发作者课业繁重，有时不太能及时反馈和修复 Bug，见谅一下。

## 主要功能

- 自动打开《明日方舟》，支持官服和 Bilibili 服
- 自动登录
    - 账户密码需要手动输入
- 自动访友收取信用点
- 自动确认任务完成
- 自动刷体力
    - 默认进行上一次完成的关卡
    - 可设置成优先完成剿灭任务
    - 可自动通过体力药剂和源石回复体力
    - 可限定关卡次数和序列
    - 可指定关卡，包括主线、插曲、别传和资源收集四大区域
- 自动完成公招
- 自动收取邮件奖励
- 自动收取并安放线索
- 自动消耗无人机加速制造站
- 自动更换基建排班干员（单功能模式下不支持）
- 支持游戏任意分辨率（低于1080p的分辨率可能会有一些问题）


## 安装

```bash
pip3 install arknights-mower
```

也可以在 [Releases](https://github.com/Konano/arknights-mower/releases) 下载 Windows 可执行文件。

## 运行须知

运行脚本需要安装 ADB 并与安卓模拟器进行连接。
Windows下的夜神（Nox）模拟器会自动启动并连接自带的 ADB，如果对配置 ADB 比较苦手的人可以换用夜神（Nox）模拟器。

ADB 下载地址：
- Windows: https://dl.google.com/android/repository/platform-tools-latest-windows.zip
- Mac: https://dl.google.com/android/repository/platform-tools-latest-darwin.zip
- Linux: https://dl.google.com/android/repository/platform-tools-latest-linux.zip

下载 ADB 后需要将 ADB 所在目录添加到环境变量中。请确认 `adb devices` 中列出了目标模拟器或设备：

```
$ adb devices
emulator-5554   device
```

### 常见问题

- Linux 下可以使用 Anbox 来运行 Android 模拟器，[参见教程](https://www.cnblogs.com/syisyuan/p/12811595.html)
- 提示`ADB Server 未开启。请运行 adb server 以启动 ADB Serve。`：需要自行启动adb，夜神模拟器自带的adb在崩溃后也会出现这一错误提示，重启模拟器有几率解决这一问题。
- 大量出现`识别出了点小差错`并卡死在特定界面：当前版本非 1080p（1920x1080）分辨率下有些界面的识别可能出现错误，将模拟器修改为 1080p 分辨率可以解决大部分问题。如果分辨率修改并未解决问题，请在 issue 页面提出。

## 使用教程

### 计划任务模式
可以通过Windows可执行文件启动计划任务模式，自动进行收邮件、信用点、基建产出、消耗体力等。

第一次运行程序时，会在可执行文件的同目录（Windows可执行文件版本）或Home目录（Linux下为`~/`，Windows下为`%HOMEPATH%`或`C:/Users/你的用户名/`）处生成配置文件`config.yaml`（可执行文件版本）或`ark_mower.yaml`（Pypi版本）。该文件为一系列每日基础任务的模板，请参考该文件的注释来进行计划任务的配置，尤其是以TODO开头的部分可能需要根据自己的情况进行修改（如无人机加速位置），否则可能无法正常运行。

### 单独功能运行模式

也可以通过命令行模式启动指定运行的功能，Release页面中的可执行文件版与pypi安装的模块版均可以命令行模式启动。
命令行模式下的使用说明如下：

```
$ arknights-mower
usage: arknights-mower command [command args] [-d]
commands (prefix abbreviation accepted):
    base [plan] [-c] [-d[F][N]]
        自动处理基建的信赖/货物/订单/线索/无人机
        plan 表示选择的基建干员排班计划（需要搭配配置文件使用）
        -c 是否自动使用线索
        -d 是否自动消耗无人机，F 表示从上往下第几层（1-3），N 表示从左往右第几个房间（1-3），仅支持制造站
    credit
        自动访友获取信用点
    mail
        自动收取邮件
    mission
        收集每日任务和每周任务奖励
    shop [items ...]
        自动前往商店消费信用点
        items 优先考虑的物品，默认为从上到下从左到右购买
    recruit [agents ...]
        自动进行公共招募
        agents 优先考虑的公招干员，默认为火神和因陀罗
    operation [level] [times] [-r[N]] [-R[N]] [-e]
        自动进行作战，可指定次数或直到理智不足
        level 指定关卡名称，未指定则默认前往上一次关卡
        times 指定作战次数，未指定则默认作战直到理智不足
        -r 是否自动回复理智，最多回复 N 次，N 未指定则表示不限制回复次数
        -R 是否使用源石回复理智，最多回复 N 次，N 未指定则表示不限制回复次数
        -e 是否优先处理未完成的每周剿灭
    schedule
        执行配置文件中的计划任务
    version
        输出版本信息
    help
        输出本段消息
    -d
        启用调试功能，调试信息将会输出到 /var/log/arknights-mower/ 中
```

命令行模式下的具体使用例子如下：

```
arknights-mower operation
# 重复刷上一次关卡，直到理智不足停止
arknights-mower operation 99
# 重复刷上一次关卡 99 次
arknights-mower operation -r5
# 重复刷上一次关卡，使用理智药自动回复理智，最多消耗 5 瓶（直到理智不足停止）
arknights-mower operation -r
# 重复刷上一次关卡，使用理智药自动回复理智，直到理智药用完为止
arknights-mower operation 1-7 99 -R5
# 重复刷 1-7 关卡 99 次，使用源石自动回复理智，最多消耗 5 颗
arknights-mower operation GT-1 99 -r5 -R5
# 重复刷 GT-1 关卡 99 次，使用理智药以及源石自动回复理智，最多消耗 5 瓶理智药和 5 颗源石
arknights-mower recruit 因陀罗 火神
# 公招自动化，优先选择保底星数高的组合，若有多种标签组合保底星数一致则优先选择包含优先级高的干员的组合，公招干员的优先级从高到低分别是因陀罗和火神
arknights-mower shop 招聘许可 赤金 龙门币
# 在商场使用信用点消费，购买物品的优先级从高到低分别是招聘许可、赤金和龙门币，其余物品不购买
arknights-mower base -c -d33
# 自动收取基建中的信赖/货物/订单，自动放置线索，自动前往地下 3 层 3 号房间使用无人机加速生产（暂且只支持制造站加速）
```

命令可使用前缀或首字母缩写，如：

```
arknights-mower h
# 输出帮助信息
arknights-mower ope
# 重复刷上一次关卡，直到理智不足停止
arknights-mower o 1-7 99 -r5 -R5
# 重复刷 1-7 关卡 99 次，使用理智药以及源石自动回复理智，最多消耗 5 瓶理智药和 5 颗源石
```

## 更多高级功能

由于命令行长度限制，基建自动换班功能只能通过计划任务模式进行配置，或使用代码进行调用。




### 自定义diy.py
如果想使用定时运行等其他高级功能，可根据个人需求修改 [diy.py](https://github.com/Konano/arknights-mower/blob/main/diy.py) 并运行，具体见文件内注释说明。

如果想添加其他的功能，你甚至可以创建一个继承 `BaseSolver` 的自定义类，通过现有接口实现自己的想法。
```python
from arknights_mower.strategy import Solver

# 自定义基建排班
# 这里自定义了一套排班策略，实现的是两班倒，分为四个阶段
# 阶段 1 和 2 为第一班，阶段 3 和 4 为第二班
# 第一班的干员在阶段 3 和 4 分两批休息，第二班同理
# 每个阶段耗时 6 小时
plan = {
    # 阶段 1
    'plan_1': {
        # 办公室
        'contact': ['艾雅法拉'],
        # 宿舍
        'dormitory_1': ['杜林', '闪灵', '安比尔', '空弦', '缠丸'],
        'dormitory_2': ['推进之王', '琴柳', '赫默', '杰西卡', '调香师'],
        'dormitory_3': ['夜莺', '波登可', '夜刀', '古米', '空爆'],
        'dormitory_4': ['空', 'Lancet-2', '香草', '史都华德', '刻俄柏'],
        # 会客室
        'meeting': ['陈', '红'],
        # 制造站 + 贸易站 + 发电站
        'room_1_1': ['德克萨斯', '能天使', '拉普兰德'],
        'room_1_2': ['断罪者', '食铁兽', '槐琥'],
        'room_1_3': ['阿消'],
        'room_2_1': ['巫恋', '柏喙', '慕斯'],
        'room_2_2': ['红豆', '霜叶', '白雪'],
        'room_2_3': ['雷蛇'],
        'room_3_1': ['Castle-3', '梅尔', '白面鸮'],
        'room_3_2': ['格雷伊'],
        'room_3_3': ['砾', '夜烟', '斑点']
    },
    # 阶段 2
    'plan_2': {
        # 注释掉了部分和阶段 1 一样排班计划的房间，加快排班速度
        # 'contact': ['艾雅法拉'],
        'dormitory_1': ['杜林', '闪灵', '芬', '稀音', '克洛丝'],
        'dormitory_2': ['推进之王', '琴柳', '清流', '森蚺', '温蒂'],
        'dormitory_3': ['夜莺', '波登可', '伊芙利特', '深靛', '炎熔'],
        'dormitory_4': ['空', 'Lancet-2', '远山', '星极', '普罗旺斯'],
        # 'meeting': ['陈', '红'],
        # 'room_1_1': ['德克萨斯', '能天使', '拉普兰德'],
        # 'room_1_2': ['断罪者', '食铁兽', '槐琥'],
        # 'room_1_3': ['阿消'],
        # 'room_2_1': ['巫恋', '柏喙', '慕斯'],
        # 'room_2_2': ['红豆', '霜叶', '白雪'],
        # 'room_2_3': ['雷蛇'],
        # 'room_3_1': ['Castle-3', '梅尔', '白面鸮'],
        # 'room_3_2': ['格雷伊'],
        # 'room_3_3': ['砾', '夜烟', '斑点']
    },
    'plan_3': {
        'contact': ['普罗旺斯'],
        'dormitory_1': ['杜林', '闪灵', '格雷伊', '雷蛇', '阿消'],
        'dormitory_2': ['推进之王', '琴柳', '德克萨斯', '能天使', '拉普兰德'],
        'dormitory_3': ['夜莺', '波登可', '巫恋', '柏喙', '慕斯'],
        'dormitory_4': ['空', 'Lancet-2', '艾雅法拉', '陈', '红'],
        'meeting': ['远山', '星极'],
        'room_1_1': ['安比尔', '空弦', '缠丸'],
        'room_1_2': ['赫默', '杰西卡', '调香师'],
        'room_1_3': ['伊芙利特'],
        'room_2_1': ['夜刀', '古米', '空爆'],
        'room_2_2': ['香草', '史都华德', '刻俄柏'],
        'room_2_3': ['深靛'],
        'room_3_1': ['芬', '稀音', '克洛丝'],
        'room_3_2': ['炎熔'],
        'room_3_3': ['清流', '森蚺', '温蒂']
    },
    'plan_4': {
        # 'contact': ['普罗旺斯'],
        'dormitory_1': ['杜林', '闪灵', '断罪者', '食铁兽', '槐琥'],
        'dormitory_2': ['推进之王', '琴柳', '红豆', '霜叶', '白雪'],
        'dormitory_3': ['夜莺', '波登可', 'Castle-3', '梅尔', '白面鸮'],
        'dormitory_4': ['空', 'Lancet-2', '砾', '夜烟', '斑点'],
        # 'meeting': ['远山', '星极'],
        # 'room_1_1': ['安比尔', '空弦', '缠丸'],
        # 'room_1_2': ['赫默', '杰西卡', '调香师'],
        # 'room_1_3': ['伊芙利特'],
        # 'room_2_1': ['夜刀', '古米', '空爆'],
        # 'room_2_2': ['香草', '史都华德', '刻俄柏'],
        # 'room_2_3': ['深靛'],
        # 'room_3_1': ['芬', '稀音', '克洛丝'],
        # 'room_3_2': ['炎熔'],
        # 'room_3_3': ['清流', '森蚺', '温蒂']
    }
}

Solver().base(arrange=plan)
```


欢迎大家提交 Pull requests 一起完善功能！

## 遇到报错？想要更多功能？

如果你在使用过程中遇到问题，欢迎通过提交 Issue 的方式报错或者提问。报告 Issue 时建议附上调试信息以便定位问题。

也欢迎加入交流群讨论：

- [Telegram Group](https://t.me/joinchat/eFkqRj1IWm9kYTBl)
- [QQ Group](https://jq.qq.com/?_wv=1027&k=4gWboTVI): 239200680
