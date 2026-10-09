# arknights-mower

Mower 是为长期运行设计的开源明日方舟脚本，支持基建动态排班、跑单、日常任务、养成材料准备和自动专精，并可调用 MAA 执行作战与大型任务。

## 源码部署

macOS 和 Linux 虽有独立包，仍建议优先使用源码部署。以下说明适用于 Windows、Linux 和 macOS。

准备 Git、Python 3.12、Node.js 20.19+ 或 22.12+。Windows 需要 WebView2 运行时；Linux 桌面启动需要图形环境和 GTK/WebKit2。

### 获取源码与构建前端

```bash
git clone --branch alpha https://github.com/ArkMowers/arknights-mower.git
cd arknights-mower
cd ui
npm ci
npm run build
cd ..
```

以下 Python 命令均在仓库根目录执行，直接使用虚拟环境中的解释器，无须激活环境。

### Windows

在 PowerShell 中执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe webview_ui.py
```

### Linux

以下以 Ubuntu 24.04 桌面环境为例，安装系统窗口依赖，再创建能读取系统 PyGObject 的环境：

```bash
sudo apt update
sudo apt install python3.12-venv python3-tk python3-gi \
    gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-soup-3.0 \
    libzbar0 libgl1 libglib2.0-0 adb
python3.12 -m venv --system-site-packages .venv
./.venv/bin/python -m pip install -r requirements.in
./.venv/bin/python webview_ui.py
```

其他发行版需安装对应依赖，并确保 PyGObject 与环境中的 Python 版本一致。窗口及系统库说明见[平台依赖](doc/release-platforms.md#linux-独立包的窗口后端与宿主依赖)；无桌面的服务器可参考 [Docker 部署](docs/cookbook/docker-deploy.md)。

### macOS

安装 Python、Tk、二维码识别依赖，并准备程序默认使用的 ADB：

```bash
brew install python@3.12 python-tk@3.12 zbar
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements.in
./.venv/bin/python scripts/prepare_macos_adb.py
./.venv/bin/python webview_ui.py
```

ADB 准备脚本下载并校验官方 Platform Tools。已有对应离线 ZIP 时，可通过脚本的 `--archive` 参数指定。Intel Mac 使用源码部署；后续官方发行不再构建 macOS x64 独立包。

### 后续启动与首次配置

后续只需在仓库根目录执行对应系统的最后一条启动命令。将 `webview_ui.py` 换成 `manager.py` 可打开多开管理器。

1. 在 **Mower 设置** 中选择设备预设、检测并选定实例，完成连接测试。
2. 导入或编写排班，核对设施、主班、替班及宿舍容量，点击「验证排班」。
3. 按需配置日常任务、MAA、养成与专精，启动后观察一轮换班。
4. 使用 **配置导出与导入** 保存当前实例的配置和持久化业务数据。

性能档位通常保留「自动」。「设备性能适配」位于连接设置中，桌面端还提供「游戏内性能测试」；操作步骤见一条龙的「设备连接与性能适配」。训练位提示技能条件不符时，先在游戏中完成升级或更换干员，再到 **养成规划 → 刷新**，重新验证排班。

完整步骤及排班理论见程序内「一条龙」（[仓库 HTML 原文](ui/Mower入门指北.html)）。首次下载独立包仍从[项目 Releases](https://github.com/ArkMowers/arknights-mower/releases)获取；已有安装使用 **Mower 设置 → 软件更新**。源码部署更新前保留自己的改动，操作与恢复说明见[软件更新](doc/software-update.md)。

打包与其他部署方式：[本地打包](docs/cookbook/packaging.md) · [Docker 部署](docs/cookbook/docker-deploy.md)。

## 界面截图

![运行日志](img/log.png)
![设置](img/settings.png)
![排班编辑器](img/plan-editor.png)
![基建报表](img/riic-report.png)

## 建议与反馈

先查阅 [Mower 反馈表](https://docs.qq.com/sheet/DUEJ6UWN5VFVRU0dG?tab=BB08J2)，填写需要相应编辑权限。程序内反馈窗口通过已配置邮箱发送邮件；AI 助手也可在你明确要求后发送反馈，邮件提交不会自动写入腾讯表格。

请提供 Mower 版本、系统与架构、设备或模拟器、复现步骤、期望行为及实际现象，并附发生时间和相关日志。不要公开密码、授权码、访问令牌、API 密钥或完整配置备份。

QQ群：521857729；QQ 频道：ArkMower（频道号：2r118jwue4）。

## 关于 Mower-NG

Mower-NG 项目由前 Mower 项目开发者之一 [EE0000 (@ZhaoZuohong)](https://github.com/ZhaoZuohong) 基于 Mower 项目二次开发，现已独立运作为其个人开发的项目，与 Mower 项目不再有关联。

由于 [EE0000 (@ZhaoZuohong)](https://github.com/ZhaoZuohong) 已经退出 Mower 开发组，其在网络平台上发表的言论仅代表其个人观点，不代表 Mower 项目或 Mower 开发组的立场。我们敬请广大用户理性分析，并谨慎甄别相关信息。
