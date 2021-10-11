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
    - 默认进行上一次作战
    - 若剿灭未完成则优先完成
    - 可自动通过体力药剂和源石回复体力
    - 可限定次数
    - 可指定关卡
- 自动完成公招

## Todo

- 自动更换基建干员
- 自动收取线索
- 自动收取未收邮件

## Usage

需要安装 ADB。

### From pip

```bash
pip3 install arknights-mower
arknights-mower
```

命令行使用说明如下：

```
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
        level 指定关卡名称，未指定则默认前往上一次作战
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
