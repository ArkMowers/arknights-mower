

<center>
<img src="https://github.com/Konano/arknights-mower/raw/main/logo.png">
<h1>arknights-mower</h1>
</center>


[![GitHub License](https://img.shields.io/github/license/Konano/arknights-mower?style=flat-square)](https://github.com/Konano/arknights-mower/blob/master/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/arknights-mower?style=flat-square)](https://pypi.org/project/arknights-mower/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/arknights-mower?style=flat-square)](https://pypi.org/project/arknights-mower/)
[![GitHub Workflow Status](https://img.shields.io/github/workflow/status/Konano/arknights-mower/Upload%20PyPI?style=flat-square)](https://github.com/Konano/arknights-mower/actions/workflows/python-publish.yml)
![GitHub last commit (branch)](https://img.shields.io/github/last-commit/Konano/arknights-mower/main?style=flat-square)
[![Code Climate maintainability](https://img.shields.io/codeclimate/maintainability/Konano/arknights-mower?style=flat-square)](https://codeclimate.com/github/Konano/arknights-mower)
[![Telegram Group Online](https://img.shields.io/endpoint?color=blue&style=flat-square&url=https%3A%2F%2Ftg.sumanjay.workers.dev%2Fark_mover)](https://t.me/ark_mover)
<center>
7*24 小时不间断长草，让你忘掉这个游戏！
</center>


## ⚠ 注意事项

- 本程序不支持国服以外的明日方舟区服，支持官服和 Bilibili 服。
- 原理上，使用本程序没有任何被判定为作弊并被封号的风险，但是作者不对使用此程序造成的任何损失负责。
- 开发组人数稀少，有时不太能及时反馈和修复 Bug，见谅一下。也欢迎更多有能力有意向的朋友参与。
- 本软件目前仅支持1920*1080 分辨率，使用夜神模拟器可以解决大部分问题
## 主要功能

- 自动打开《明日方舟》，支持官服和 Bilibili 服
- 自动登录
    - 账户密码需要手动输入
- 读取基建心情，根据排班表***动态换班***力求最高工休比
- 支持***跑单操作***，可设置仅跑单模式
- 支持调用maa执行除基建外的长草活动
- 支持邮件提醒
- 自动使用菲亚梅塔恢复指定房间心情最低干员的心情并重回岗位（工作位置不变以避免重新暖机） [[参考使用场景](https://www.bilibili.com/video/BV1mZ4y1z7wx)]


## 安装

在 [Releases](https://github.com/Konano/arknights-mower/releases) 下载 Windows 可执行文件版本。
或进入下方qq群文件领取，目前软件迭代速度较快，进入群内可获取一手版本

## 使用教程

* 下载安装后，打开软件
* 设置adb地址（如127.0.0.1:5555）
* 配置排班表[[配置方法](https://www.bilibili.com/video/BV1KT411s7Ar)]或前往qq群寻找现成的排班表导入
* 点击开始执行



欢迎大家提交 Pull requests 增加更多的功能！

## 常见问题 Q&A

#### 运行时出现错误：’NoneType object has no attribute shape‘

此为缓存路径出现中文字符导致，多半是因为window用户名设置为中文了，请修改用户名为英文

#### 大量出现「识别出了点小差错」并卡死在特定界面

当前版本在非 1080p（1920x1080）分辨率下，对于部分界面的识别可能会出现错误，将模拟器修改为 1080p 分辨率可以解决大部分问题。如果在分辨率修改后问题仍未解决，可以在 Issue 页面提出。

#### 提示「未检测到相应设备。请运行 `adb devices` 确认列表中列出了目标模拟器或设备。」

- 夜神（Nox）模拟器：[解决办法](https://github.com/Konano/arknights-mower/issues/117#issuecomment-1118447644)

## 遇到报错？想要更多功能？

如果你在使用过程中遇到问题，欢迎通过提交 Issue 的方式报错或者提问。报告 Issue 时建议附上调试信息以便定位问题。

也欢迎加入交流群讨论：

- [Telegram Group](https://t.me/ark_mover)
- [QQ Group](https://jq.qq.com/?_wv=1027&k=4gWboTVI): 239200680

## Star History


[![Star History Chart](https://api.star-history.com/svg?repos=Konano/arknights-mower&type=Date)](https://star-history.com/#Konano/arknights-mower&Date)

