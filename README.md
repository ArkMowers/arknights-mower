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

## Usage

需要安装 ADB。

### From pip

```bash
pip3 install arknights-mower
arknights-mower -h
arknights-mower
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
python3 diy.py
```
