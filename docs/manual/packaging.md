# 本地打包

本文介绍 Windows、Linux 和 macOS 的本地打包步骤。各平台在对应系统上构建；发布产物范围、签名、系统依赖与正式发布流程见 [跨平台发布说明](https://github.com/ArkMowers/arknights-mower/blob/alpha/doc/release-platforms.md)。

macOS 和 Linux 虽提供独立包，仍建议优先使用 [源码部署](source-deploy.md)。需要自行打包时，按下列步骤操作。

## 1. 准备源码和前端

先完成 [源码部署](source-deploy.md) 中的源码获取、前端构建和当前平台 Python 依赖安装，确认源码可以启动。以下命令在仓库根目录执行，使用同一个 `.venv` 环境。

## 2. Windows

在 PowerShell 中安装打包工具并构建：

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller==6.22.2
.\.venv\Scripts\python.exe scripts/prune_opencv.py
.\.venv\Scripts\python.exe -m PyInstaller webui_zip.spec
```

检查 `dist/mower/mower.exe` 和 `dist/mower/多开管理器.exe`，并验证两者可以打开。分发时保留整个 `dist/mower` 目录，不能只复制可执行文件。

## 3. Linux

1. 确保构建环境可以导入 PyGObject，并提供 GTK/WebKit2 typelib、ADB 和 `patchelf`。Ubuntu 24.04 的源码环境已按源码部署说明安装窗口依赖，还需：

   ```bash
   sudo apt install patchelf adb
   ./.venv/bin/python -c "import gi"
   ```

   使用系统 PyGObject 时，虚拟环境需以 `--system-site-packages` 创建，且 Python 版本与系统包一致。其他环境也可自行安装 PyGObject 及其编译依赖，见 [Linux 构建机依赖](https://github.com/ArkMowers/arknights-mower/blob/alpha/doc/release-platforms.md#构建机依赖)。

2. 安装打包工具并构建：

   ```bash
   ./.venv/bin/python -m pip install pyinstaller==6.22.2
   ./.venv/bin/python scripts/prune_opencv.py
   ./.venv/bin/python -m PyInstaller webui_zip_for_linux.spec
   ```

3. 检查 `dist/mower/mower` 和 `dist/mower/多开管理器`，并在图形桌面中验证窗口可以打开。程序输出本地 HTTP 地址时，也可使用浏览器访问该地址。

Linux 独立包仍依赖宿主提供兼容的 glibc、二维码识别及 GTK/WebKit2 等系统库。运行依赖和各发行版安装命令见 [宿主运行依赖](https://github.com/ArkMowers/arknights-mower/blob/alpha/doc/release-platforms.md#宿主运行依赖)。

## 4. macOS

1. 完成 [macOS 源码部署](source-deploy.md#macos)，确保 Homebrew `zbar` 等运行依赖可用。
2. 安装打包工具并构建：

   ```bash
   ./.venv/bin/python -m pip install pyinstaller==6.22.2
   ./.venv/bin/python scripts/prune_opencv.py
   ./.venv/bin/python -m PyInstaller webui_zip_for_macos.spec
   ```

   spec 调用 `prepare_macos_adb` 准备经过摘要校验的 Platform Tools；首次构建需要可以下载对应资源。

3. 检查 `dist/mower.app`，并验证主程序与多开管理器可以打开。

本地 `.app` 使用 PyInstaller ad-hoc 签名，不包含 Developer ID 签名或 Apple 公证；系统信任和宿主依赖见 [签名与系统依赖](https://github.com/ArkMowers/arknights-mower/blob/alpha/doc/release-platforms.md#签名与系统依赖)。这里的命令生成本地应用，Release 的 DMG、归档和校验清单由发布流水线处理。

## 5. 开发验证与模型重训

以下步骤面向修改识别模型或依赖的开发者，普通部署不需要执行。

1. 在 Python 3.12 环境安装开发依赖并运行识别等价测试：

   ```bash
   python -m pip install -r requirements-dev.txt
   python -m unittest arknights_mower.tests.vision_np_tests
   ```

   这些测试依赖 scipy、scikit-image 和 scikit-learn，缺少时会跳过。CI 的识别等价检查安装开发依赖后执行。

2. `auto_get_res_new.py` 重训 `NORMAL.pkl`、`CONSUME.pkl` 后，将 sklearn 模型折叠为运行时使用的 numpy 字典：

   ```bash
   python scripts/collapse_recognition_models.py
   ```

   脚本逐样本验证折叠结果后才替换模型；已经折叠的模型会跳过。运行时不需要上述三个开发库。

3. 修改依赖时，使用 Python 3.12 成对生成运行和开发锁文件，再验证公共依赖版本：

   ```bash
   python -m pip install pip==25.3 pip-tools==7.6.0
   python scripts/compile_requirements.py
   python -m unittest scripts.tests.requirements_sync_tests
   ```

   核对 `requirements.txt` 与 `requirements-dev.txt` 的变更；不要只更新其中一份。
