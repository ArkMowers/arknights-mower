# ArknightsHelper

[![GitHub License](https://img.shields.io/github/license/Konano/arknights-mower)](https://github.com/Konano/arknights-mower/blob/master/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/arknights-mower)](https://pypi.org/project/arknights-mower/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/arknights-mower)](https://pypi.org/project/arknights-mower/)
[![GitHub Workflow Status](https://img.shields.io/github/workflow/status/Konano/arknights-mower/Upload%20PyPI)](https://github.com/Konano/arknights-mower/actions/workflows/python-publish.yml)
![GitHub last commit (branch)](https://img.shields.io/github/last-commit/Konano/arknights-mower/main)

7*24 小时不间断长草，让你忘掉这个游戏！

## 主要功能

- 自动打开《明日方舟》
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
- 自动更换基建排班干员（命令行模式下不支持）
- 支持游戏任意分辨率

## 运行须知

运行脚本需要安装 ADB。ADB 下载地址：

- Windows: https://dl.google.com/android/repository/platform-tools-latest-windows.zip
- Max: https://dl.google.com/android/repository/platform-tools-latest-darwin.zip
- Linux: https://dl.google.com/android/repository/platform-tools-latest-linux.zip

下载 ADB 后需要将 ADB 所在目录添加到环境变量中。请确认 `adb devices` 中列出了目标模拟器或设备：

```
$ adb devices
emulator-5554   device
```

### 常见问题

- 部分模拟器（如 MuMu、BlueStacks）需要自行启动 ADB server。
- 部分模拟器（如 MuMu）不使用标准模拟器 ADB 端口，ADB server 无法自动探测，需要另行 `adb connect`。
- 部分模拟器（如夜神）会频繁使用自带的旧版本 ADB 挤掉用户自行启动的新版 ADB。
- 部分非 VMM 模拟器（声称「不需要开启 VT」，如 MuMu 星云引擎）不提供 ADB 接口。

## 脚本启动

使用 pip 安装：

```bash
pip3 install arknights-mower
```

脚本可以在命令行模式下使用，具体例子如下：

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

命令行模式下脚本使用说明如下：

```
$ arknights-mower
usage: arknights-mower command [command args] [-d]
commands (prefix abbreviation accepted):
    base [-c] [-d[F][N]]
        自动处理基建的信赖/货物/订单/线索/无人机
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
    version
        输出版本信息
    help
        输出本段消息
    -d
        启用调试功能，调试信息将会输出到 /var/log/arknights-mower/ 中
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

## 自定义功能实现

<!-- 或者也可以从源码安装

```bash
git clone git@github.com:Konano/arknights-mower.git --depth=1
cd arknights-mower

#### 建议使用 venv 避免依赖包冲突
python3 -m venv venv
# 在 Windows cmd 中：
venv\Scripts\activate.bat
# 在 PowerShell 中：
& ./venv/[bS]*/Activate.ps1
# 在 bash/zsh 中：
source venv/bin/activate
#### venv end

pip3 install -r requirements.txt
# 可根据个人需求修改 diy.py
python3 diy.py
``` -->

## 遇到报错？想要更多功能？

如果你在使用过程中遇到问题，欢迎提交 Issue 报错或者提问。报告 Issue 时建议附上日志以便定位问题。

也欢迎加入交流群讨论：

- [Telegram Group](https://t.me/joinchat/eFkqRj1IWm9kYTBl)
- QQ Group：239200680
