# ArknightsHelper

《明日方舟》长草助手（开发中）

支持任意分辨率，7*24 小时不间断长草，让你忘掉这个游戏！

## Feature

- 自动打开《明日方舟》
- 自动登录
    - 账户密码需要手动输入
- 自动访友收信用
- 自动确认任务完成
- 自动刷体力
    - 默认进行上一次关卡
    - 若剿灭未完成则优先完成
    - 可自动通过体力药剂和源石回复体力
    - 可限定次数
    - 可指定关卡，包括主线、插曲、别传和资源收集四大区域
- 自动完成公招

## Todo

- 自动更换基建干员
- 自动收取线索
- 自动收取未收邮件
- 多设备选择

## Usage

需要安装 ADB。

### From pip

使用 pip 安装：

```bash
pip3 install arknights-mower
```

命令使用说明如下：

```
$ arknights-mower
usage: arknights-mower command [command args] [-d]
commands (prefix abbreviation accepted):
    base
        自动处理基建的信赖/货物/订单
    credit
        自动访友获取信用点
    shop [items ...]
        自动前往商店消费信用点
        items 优先考虑的物品，默认为从上到下从左到右购买
    recruit [agents ...]
        自动进行公共招募
        agents 优先考虑的公招干员，默认为火神和因陀罗
    mission
        收集每日任务和每周任务奖励
    operation [level] [n] [-r[N]] [-R[N]] [-e]
        自动进行作战，可指定次数或直到理智不足
        level 指定关卡名称，未指定则默认前往上一次关卡
        n 指定作战次数，未指定则默认作战直到理智不足
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

命令使用具体例子如下：

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

### From Source

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
```
