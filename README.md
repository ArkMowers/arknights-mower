# arknights-mower

Mower 是为长期运行设计的开源明日方舟脚本。

## 功能介绍

- 基建：跑单、按心情动态换班；
- 森空岛：签到、仓库读取；
- 日常：公招、邮件、线索、清理智；
- 大型任务：生息演算、隐秘战线；
- 签到：五周年月卡、限定池每日一抽、矿区、孤星领箱子、端午签到……
- 调用 MAA：肉鸽、保全。

## 界面截图

![log](./img/log.png)
![settings](./img/settings.png)
![plan-editor](./img/plan-editor.png)
![riic-report](./img/riic-report.png)

## 下载与安装

已部署的程序可在 **Mower 设置 → 软件更新** 中检查正式版、公测版或开发版更新，并在更新后恢复当前实例。Release 独立包支持手动上传安装包离线安装；源码与独立包部署均可选择后台静默重启。首次启用、平台支持与失败恢复说明见 [软件更新与实例恢复](doc/software-update.md)。

软件更新可选择启动时自动检查及自动安装。设置页最底部的 **进程操作** 可单独重启或结束当前实例；重启保留多开管理器传入的名称、数据目录、端口和原运行状态。macOS 可勾选 **隐藏菜单栏图标**，重启后不创建托盘进程。

设置页下方的 **网络与下载代理** 可配置全局网络连接及 GitHub 下载代理站点（如 `https://ghfast.top/`）。填写后自动保存，后续连接使用新设置，并可测试 GitHub 下载接口是否可达。软件更新与资源更新位于其下方，宽屏并排显示。

资源包保存在共享的持久目录 `@app/resources`，各实例在任务间歇加载，不修改 internal 或已签名的 macOS 程序包。详见[共享资源存储与实例加载](doc/resource-storage.md)。

### 运行环境准备

git、Python 3.12、Node.js 16

### 克隆仓库

```bash
git clone -c lfs.concurrenttransfers=200 https://github.com/ArkMowers/arknights-mower.git
cd arknights-mower
```

### 构建前端

```bash
cd ui
npm install
npm run build
```

### 构建后端（Windows）

```bash
cd ..
python -m venv venv
.\venv\Scripts\activate.bat
pip install -r requirements.txt
pip install Flask flask-cors flask-sock pywebview
```

### 构建后端（Linux）

```bash
cd ..
python3 -m venv venv
. ./venv/bin/activate
pip install -r requirements.in
pip install Flask flask-cors flask-sock pywebview
```

### 识别等价测试与模型重训

scipy、scikit-image、scikit-learn 仅用于开发期 golden 对照与模型重训，不属于运行依赖：

```bash
pip install -r requirements-dev.txt
python -m unittest arknights_mower.tests.vision_np_tests
```

这些用例在上述三个库缺失时会整体跳过，因此 CI 的 `recognition-equivalence` 任务会安装开发依赖真正执行它们。

识别层加载的是不含 sklearn 对象的 numpy 字典，而 `auto_get_res_new.py` 重新训练仓库识别模型（`NORMAL.pkl`、`CONSUME.pkl`）后写出的仍是 sklearn 对象，需要再折叠一次才能被加载：

```bash
python scripts/collapse_recognition_models.py
```

折叠脚本会先用 sklearn 原模型逐样本校验折叠结果，校验通过才原地替换；模型已经是折叠格式时会跳过并提示。

运行依赖与开发依赖的锁文件必须由 Python 3.12 统一生成，避免环境 marker 与交付运行时不一致：

```bash
python -m pip install pip==25.3 pip-tools==7.6.0
python scripts/compile_requirements.py
```

两份锁文件必须成对生成，`scripts/tests/requirements_sync_tests.py` 会校验它们的公共依赖版本一致。

### 打包（Windows）

```bash
pip install pyinstaller
python scripts/prune_opencv.py
pyinstaller webui_zip.spec
```

生成的 `mower.exe` 在 `dist` 文件夹中，到此打包完成，已可使用。

### 打包（Linux）

先安装**构建机**上打包 pywebview GTK 后端所需的系统依赖（PyGObject 与 GTK/WebKit2
的 gir typelib，否则打包时 gi 收不进产物）：

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-soup-3.0 libgirepository1.0-dev
```

如果用的是 venv，需要让 venv 能看到系统的 PyGObject，用 `--system-site-packages`
创建，或在 venv 里 `pip install pygobject`（后者需要先安装编译依赖）。

再打包：

```bash
pip install pyinstaller
python scripts/prune_opencv.py
pyinstaller webui_zip_for_linux.spec
```

生成的 `mower` 在 `dist` 文件夹中，到此打包完成，已可使用。Linux 独立包的窗口后端是
GTK（`gi`/PyGObject），Qt 后端不随包分发。宿主若缺 GTK/WebKit2 原生库与 gir typelib，
程序启动时会给出中文安装提示，也可按发行版安装：

```bash
# Debian / Ubuntu
sudo apt install libgtk-3-0 libwebkit2gtk-4.1-0 gir1.2-webkit2-4.1 gir1.2-gtk-3.0 gir1.2-soup-3.0
# Fedora
sudo dnf install webkit2gtk4.1 gi-girepository libgtk-3
# Arch Linux
sudo pacman -S webkit2gtk-4.1 gobject-introspection
```

各发行版的详细依赖与打包命令见 `doc/release-platforms.md`。

注：Linux 下运行时，shell 会显示如 `Running on http://127.0.0.1:53703` 的输出，本地浏览器访问 `http://127.0.0.1:53703` 即进入 Mower 页面。

> Linux 独立包仍依赖宿主机的部分系统动态库，并非完全便携。产物在 Ubuntu 24.04
> 上构建，运行时要求 glibc >= 2.39，且需安装：`libzbar0`（二维码识别）、
> `libgl1` 与 `libglib2.0-0`（OpenCV）、`libgtk-3-0` 与 `libwebkit2gtk-4.1-0`
> （WebView 界面，Ubuntu 24.04 对应包名）。

### 打包（macOS）

```bash
pip install pyinstaller
brew install zbar
python scripts/prune_opencv.py
pyinstaller webui_zip_for_macos.spec
```

生成的 `mower.app` 在 `dist` 文件夹中，包含主程序与多开管理器。macOS 产物为
**unsigned experimental build**（PyInstaller 仅做 ad-hoc 签名，非 Developer ID
签名、未经 notarization），首次运行若被 Gatekeeper 拦截，需在「隐私与安全性」
中手动允许；二维码识别依赖宿主机 `zbar`（`brew install zbar`）。

### 正式版与 alpha 的产物和签名说明

正式版与 alpha 共用跨平台发布流水线，为五个平台生成统一命名的独立包，并附带
统一的 SHA-256 清单（SHA256SUMS）：

```text
arknights-mower_<version>_windows_x64.zip
arknights-mower_<version>_linux_x64.tar.gz
arknights-mower_<version>_linux_arm64.tar.gz
arknights-mower_<version>_macos_x64.dmg
arknights-mower_<version>_macos_arm64.dmg
```

发布入口、版本格式、构建检查和系统依赖见
[跨平台发布流水线](doc/release-platforms.md)。

Windows 与 macOS 产物均未签名：Windows 首次运行可能出现 SmartScreen 提示，请
选择「更多信息 -> 仍要运行」；macOS 为 unsigned experimental build，可能需要在
「隐私与安全性」中手动允许。建议下载后先核对 SHA256SUMS 再使用。

## Docker 部署

Docker 部署说明见 [Arknights-Mower 文档 - Docker 部署](https://arkmowers.github.io/arknights-mower/manual/docker-deploy/)。

## Linux系统下的Docker一键部署

### 运行环境准备

Docker version 28.1.128.1.1、Linux

### 克隆仓库

```bash
git clone -c lfs.concurrenttransfers=200 https://github.com/ArkMowers/arknights-mower.git
cd arknights-mower
```

### 镜像构建

```bash
docker build -t mower .
```

### 启动容器

```bash
docker run -d \
    --name mower\
    --network host \
    -e TZ="Asia/Shanghai" \
    --restart always \
    --memory 2g \
    mower
```

### 进入 Mower

容器在后台启动以后，可以本地浏览器访问 `http://127.0.0.1:58000?token=mower` 或 `http://局域网IP:58000?token=mower`。

此时，该容器已预先配置好 MAA 以及 ADB 设置，仅需要手动配置 ADB 连接地址。

## 建议与反馈

**提出建议、反馈 Bug，欢迎加入 QQ 群 (521857729) 或 QQ 频道 (ArkMower)（频道号：2r118jwue4）**

## 关于 Mower-NG

Mower-NG 项目由前 Mower 项目开发者之一 [EE0000 (@ZhaoZuohong)](https://github.com/ZhaoZuohong) 基于 Mower 项目二次开发，现已独立运作为其个人开发的项目，与 Mower 项目不再有关联。

由于 [EE0000 (@ZhaoZuohong)](https://github.com/ZhaoZuohong) 已经退出 Mower 开发组，其在网络平台上发表的言论仅代表其个人观点，不代表 Mower 项目或 Mower 开发组的立场。我们敬请广大用户理性分析，并谨慎甄别相关信息。
