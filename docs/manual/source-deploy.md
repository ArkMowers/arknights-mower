# 源码部署

macOS 和 Linux 虽提供独立包，仍建议优先使用源码部署。

需要 Git、Python 3.12，以及 Node.js 20.19+ 或 22.12+。Linux 需要图形桌面环境；Windows 需要 WebView2 运行时。

## 获取源码并构建前端

以下步骤适用于 Windows、Linux 和 macOS，在终端依次执行：

```bash
git clone --branch alpha https://github.com/ArkMowers/arknights-mower.git
cd arknights-mower
cd ui
npm ci
npm run build
cd ..
```

完成后，在仓库根目录按对应系统安装 Python 依赖并启动。

## Windows

在 PowerShell 中执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe webview_ui.py
```

## Linux

以下以 Ubuntu 24.04 桌面环境为例。安装窗口后端、二维码识别等系统依赖，再创建可访问系统 PyGObject 的 Python 3.12 环境：

```bash
sudo apt install python3.12-venv python3-tk python3-gi \
    gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-soup-3.0 \
    libzbar0 libgl1 libglib2.0-0 adb
python3.12 -m venv --system-site-packages .venv
./.venv/bin/python -m pip install -r requirements.in
./.venv/bin/python webview_ui.py
```

其他发行版需使用对应的系统依赖包，并确保系统 PyGObject 与虚拟环境的 Python 版本一致。GTK/WebKit2 依赖说明见 [项目平台依赖说明](https://github.com/ArkMowers/arknights-mower/blob/alpha/doc/release-platforms.md#linux-独立包的窗口后端与宿主依赖)。

## macOS

使用 Homebrew 安装 Python、Tk 和二维码识别依赖，再安装当前平台的 Python 依赖：

```bash
brew install python@3.12 python-tk@3.12 zbar
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements.in
./.venv/bin/python webview_ui.py
```

## 启动与配置

后续启动只需在仓库根目录执行对应系统的最后一条命令。将 `webview_ui.py` 换成 `manager.py` 可启动多开管理器。

首次进入后，在 Mower 设置中选择设备并测试连接，再配置排班及所需任务。设备配置见[设备连接](device.md)，源码更新见[安装与更新](install.md#mower-sources)。

打包与其他部署方式：[本地打包说明](packaging.md) · [Docker 部署](docker-deploy.md)。
