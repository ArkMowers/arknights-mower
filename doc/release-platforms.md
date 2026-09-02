`.github/workflows/release-build.yml` 是正式版与 alpha 测试版共用的跨平台
构建和 GitHub Release 流程。它使用 PyInstaller 6.22.2 构建 Windows x64、
Linux x64、Linux ARM64、macOS x64 与 macOS ARM64 产物。

## 发布入口

### 发布准备

`.github/workflows/prepare-release.yml` 提供 `workflow_dispatch` 手动入口。
[GitHub 的手动运行说明](https://docs.github.com/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
要求 workflow 已经存在于默认分支。维护者可以在运行时选择包含发布文件的目标
分支，再输入版本号。

发布准备任务按照以下顺序处理目标分支：

1. 确认运行目标是分支，并验证版本格式。
2. 检查 `origin` 是否指向当前 GitHub 仓库、远端分支是否发生变化，以及目标
   tag 是否已经存在。
3. 使用 `scripts/inject_version.py` 更新版本文件，使用
   `scripts/changelog_generator.py` 更新 `CHANGELOG.md`。
4. 创建发布准备提交和 annotated tag，再通过一次 `git push --atomic` 将两者
   写入所选分支和当前仓库。提交或 tag 任意一项无法写入时，远端不会保留另一项。
5. 将 tag 名称和提交 SHA 传给 `release-build.yml`，在同一次 workflow 链路中
   继续构建和发布。

这个入口只向当前仓库的 `origin` 写入内容。它不会根据 tag 查找来源分支，也
不会向其他远端或固定名称的分支推送。

### 外部 tag

直接向当前仓库推送合法 tag 也会触发 `release-build.yml`。这个入口验证 tag
格式、tag 指向的提交和 checkout 结果，只读取 tag 对应的代码，不修改任何分支。

共享构建本身没有 `workflow_dispatch` 入口。需要自动更新版本文件和
`CHANGELOG.md` 时，应当运行发布准备流程。

## 版本与 Release 类型

| tag 格式 | 注入版本 | GitHub Release |
| --- | --- | --- |
| `vX.Y.Z` | `X.Y.Z` | 普通 Release |
| `vX.Y.Z-alpha.N` | `X.Y.Z-alpha.N` | prerelease |

两种 Release 都会直接发布，不创建 draft。构建任务使用经过验证的 tag checkout，
确保版本注入、产物名称和 Release tag 对应同一个提交。

发布准备流程会将 changelog 写入所选分支。外部 tag 入口只在 workflow 工作区生成
Release 正文和带当前版本块的 `CHANGELOG.md`，并将后者放入打包产物，不写回
仓库分支。

## 平台矩阵

| 平台 | runner | PyInstaller spec | 产物 | 架构与运行检查 |
| --- | --- | --- | --- | --- |
| Windows x64 | `windows-latest` | `webui_zip.spec` | `.zip` | PE x64 |
| Linux x64 | `ubuntu-24.04` | `webui_zip_for_linux.spec` | `.tar.gz` | `file` x86-64、`ldd`、GUI 冒烟 |
| Linux ARM64 | `ubuntu-24.04-arm` | `webui_zip_for_linux.spec` | `.tar.gz` | `file` aarch64、`ldd`、GUI 冒烟 |
| macOS x64 | `macos-15-intel` | `webui_zip_for_macos.spec` | `.zip` | `file`、`lipo`、`otool`、`codesign --verify`、GUI 冒烟 |
| macOS ARM64 | `macos-15` | `webui_zip_for_macos.spec` | `.zip` | 同上 |

产物统一使用以下名称：

```text
arknights-mower_<version>_windows_x64.zip
arknights-mower_<version>_linux_x64.tar.gz
arknights-mower_<version>_linux_arm64.tar.gz
arknights-mower_<version>_macos_x64.zip
arknights-mower_<version>_macos_arm64.zip
```

Release 任务在全部平台构建成功后附加五个产物，并生成统一的 SHA-256 清单
`SHA256SUMS`。

## 构建检查

- 三个平台的构建都在安装依赖之后、PyInstaller 打包之前运行
  `scripts/prune_opencv.py`，移除 OpenCV 中不使用的 videoio FFmpeg 插件和
  级联分类器数据。脚本先把候选文件移到暂存目录并冒烟调用核心识别 API，通过
  后才真正删除，失败则回滚。
- Windows 构建下载并校验固定版本的 UPX，PyInstaller 通过 `PATH` 使用它压缩
  支持的 PE 文件。构建在打包前检查可执行文件的 PE 架构。
- Linux 构建检查主程序、`CHANGELOG.md` 和必要资源，验证 ELF 架构及动态库
  解析结果，再通过 Xvfb 运行 30 秒 GUI 冒烟。
- macOS spec 显式收集 pywebview Cocoa 后端依赖和当前 wheel 中存在的
  onnxruntime 动态库，并将主程序与多开管理器放入 `.app/Contents/MacOS`。
  构建任务检查应用目录结构、Mach-O 架构、外部动态库和 ad-hoc 签名，再运行
  20 秒 GUI 冒烟，最后使用 `ditto` 保留应用目录结构。

任意架构、动态库或冒烟检查失败时，对应构建任务失败，Release 任务不会执行。
PyInstaller 只在 Windows 使用 UPX；Linux 不执行 UPX 压缩，macOS spec 也显式
关闭 UPX，避免破坏 Mach-O 的 ad-hoc 签名。

## 签名与系统依赖

所有产物均为未签名构建：

- Windows 不使用商业证书、SignPath、MSIX 或自签证书。首次运行可能出现
  SmartScreen 提示。
- macOS 不使用 Developer ID、notarization 或 stapling。PyInstaller 只进行
  ad-hoc 签名，首次运行可能被 Gatekeeper 拦截，需要在「隐私与安全性」中手动
  允许。
- Linux 产物在 Ubuntu 24.04 上构建，要求运行环境提供兼容的 glibc、`libzbar0`、
  `libgl1`、`libglib2.0-0`、`libgtk-3-0` 与
  `libwebkit2gtk-4.1-0`。
- macOS 产物不打包 `zbar`，二维码识别需要运行环境通过 Homebrew 安装
  `zbar`。缺少 `zbar` 不影响主程序启动。

workflow 不读取代码签名 secrets。

## Windows ARM64

当前平台矩阵不包含 Windows ARM64。仓库锁定的
[`opencv-python==4.9.0.80`](https://pypi.org/project/opencv-python/4.9.0.80/)
和 [`rjieba==0.2.1`](https://pypi.org/project/rjieba/0.2.1/) 没有
`win_arm64` wheel，现有依赖安装步骤无法产出完整的 Windows ARM64 构建。

在依赖提供对应 wheel，或者仓库确定并验证固定版本的源码构建方案之前，
Windows ARM64 继续暂缓，避免它阻塞其他平台的 Release。

## 分发边界

这套流程只创建当前仓库的分支提交、tag 和 GitHub Release，不包含 OTA、
多仓库分发或镜像推送。现有 `.github/workflows/python-publish.yml` 仍是独立的
PyPI 发布流程，发布准备任务不会显式调用它。

## Linux 独立包的窗口后端与宿主依赖

上面各节描述跨平台构建与 Release 流程，这里补充 Linux 独立包运行时窗口后端的
两层依赖，以及各发行版的宿主安装命令。

### 窗口后端

| 平台 | 独立包窗口后端 | 依赖 |
| --- | --- | --- |
| Windows | `webview.platforms.edgechromium` | WebView2 |
| macOS | `webview.platforms.cocoa` | PyObjC |
| Linux | `webview.platforms.gtk` | PyGObject（`gi`） |

pywebview 在 Linux 上的默认调度是先试 GTK（`webview.platforms.gtk`），失败再试
Qt（`webview.platforms.qt`）。`KDE_FULL_SESSION` 或 `PYWEBVIEW_GUI=qt` 时反过来。

Linux **独立包**只随包分发 GTK 后端的 Python 依赖（`gi`/PyGObject），Qt 后端
（`qtpy` + PyQt/PySide）刻意不收集：它不是默认路径、体积也大。因此 Linux 独立包
一律走 GTK；Qt 版只能在源码运行时使用。

### 构建机依赖

构建机（运行 PyInstaller 的机器）需要在打包前安装 PyGObject 与 GTK/WebKit2 的
gir typelib，否则 `webui_zip_for_linux.spec` 收集不到 `gi`：

```bash
# Debian / Ubuntu
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-soup-3.0 libgirepository1.0-dev
```

如果使用 venv，需要用 `--system-site-packages` 创建以便看到系统 PyGObject，或在
venv 中 `pip install pygobject`（后者需先安装编译依赖）。

### 宿主运行依赖

宿主（运行独立包的机器）只需安装 GTK/WebKit2 原生库与 gir typelib，缺库时程序启动
会给出中文安装提示：

```bash
# Debian / Ubuntu
sudo apt install libgtk-3-0 libwebkit2gtk-4.1-0 gir1.2-webkit2-4.1 gir1.2-gtk-3.0 gir1.2-soup-3.0

# Fedora
sudo dnf install webkit2gtk4.1 gi-girepository libgtk-3

# Arch Linux
sudo pacman -S webkit2gtk-4.1 gobject-introspection
```

说明：Debian 的 `gir1.2-webkit2-4.1` 依赖 `libwebkit2gtk-4.1-0`，`gir1.2-gtk-3.0`
依赖 `libgtk-3-0`，`gir1.2-soup-3.0` 依赖 `libsoup-3.0-0`，传递依赖会随之安装。
Fedora 的 `webkit2gtk4.1 + gi-girepository` 覆盖 WebKit2 与 GObject 内省，`libgtk-3`
提供 GTK3。Arch 的 `webkit2gtk-4.1` 会带 `gobject-introspection` 与 GTK3。
