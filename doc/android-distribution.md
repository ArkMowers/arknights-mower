# Android 发行兼容

Windows、macOS、Linux 沿用现有实现。Android 宿主设置 `MOWER_ANDROID=1`，提供 `mower_android` 中的设备控制、配置接管与 MAA 适配器；Python 在 Linux 用户空间运行，Android 动态库由原生服务加载。

## 发布职责

| 内容 | 构建和发布来源 | Android 更新方式 |
| --- | --- | --- |
| Mower 程序、共享 WebUI、随程序资源及 Python 解释器/依赖 | 本仓库 Release 的 `arknights-mower_<version>_android_arm64.zip` | 共享软件更新页面，宿主校验后切换程序目录，重启 Mower 服务生效，无需重装 APK |
| MAA 核心、MAA 资源 | MAA 官方仓库 | 四端共用正式／公测渠道版本接口，从相同目标版本选择官方 Android ARM64 组件；资源使用官方 MaaResource |
| APK、MAA Python 兼容接口 | [arknights-mower-android](https://github.com/ALEXsun0/arknights-mower-android) Release | APK 使用系统安装器；Android 的检查 MAA 更新同时检查接口，仅内容变化时提示；也可手动导入，不要求升级 APK |

Android 暂时禁用 Mirror酱：不显示源选项和 CDK，已有 CDK 不影响官方默认源，后端拒绝 Mirror 的核心、资源和 CDK 查询。其他三端保持原有 Mirror 功能。缺少官方 Android 核心时明确失败，不回退 Linux 包。

APK 与 Mower 版本独立。日常 Mower/MAA 代码、WebUI、资源及兼容接口更新不要求用户更新 APK；只有 Android 系统能力或原生桥接变化时才需要新版 APK。首次使用完整环境热更新需安装 versionCode ≥ 29 的宿主。

## Mower 更新包协议

`scripts/build_android_runtime.py` 在 Debian bookworm ARM64 镜像内构建 Python 3.12 与当前 `requirements.in` 的依赖（排除桌面 GUI，OpenCV 使用 headless 版本），真实导入关键原生依赖后导出 rootfs。`scripts/package_android.py` 使用已注入版本、构建后的共享 WebUI 和该运行环境生成 ZIP。缺少运行环境时构建失败，不再静默生成只有源码的薄包。

根目录包含 `mower-android.json`、`mower/` 应用内容和 `python-runtime.zip.xz`。内层为 XZ 压缩的 ZIP，包含 Python 解释器、标准库、第三方依赖、Linux 共享库、证书及许可证，不含 `mower_android` 宿主、MAA 核心/接口、Mower 本体或用户配置。符号链接保存在 `.symlinks.json`，宿主在解压普通文件后恢复；绝对链接目标按 rootfs 内路径解释。`runtime.unpacked_size` 是内层 ZIP 全部文件解压后的总字节数（含 symlink 清单，不含最终恢复的链接）。

清单字段为 `kind="mower-android"`、`format=2`、`min_apk=29`、`version`、`revision`、`runtime_api=1`、`python="3.12"`、`platform="android"`、`arch="arm64"`，以及 `runtime={"file":"python-runtime.zip.xz","sha256":"…","unpacked_size":…}`。Python 小版本由实际归档的解释器名称取得。`runtime_api` 仅表示原生桥接协议，Python 依赖升级不再要求改变宿主 API。`requirements.txt` 供审查，手机不执行 pip 安装。

ARM64 PR CI 与正式发布都真实构建 Python 环境、运行原生依赖导入冒烟测试，并校验内外层 ZIP、解释器 ELF 架构、运行环境 digest、版本及必备文件；本仓库不构建 APK。

宿主负责检查来源/digest、清单版本和兼容协议，将包解压到独立版本目录，验证成功后原子切换；不得覆盖正在运行的程序、宿主接口或用户数据。不兼容/损坏包保留当前版本。热更新指无需重装 APK，已加载的 Python 模块需重启 Mower 服务生效。

软件更新共用 `SoftwareUpdate` 页面和 `/software-update/*` API。宿主在 `app.extensions["software_update_provider"]` 注册相同接口的 Release 更新器，报告当前 **Mower** 版本并选择本仓库的 Android ZIP；APK 更新属于原生应用设置。未注册时继续使用桌面更新器，认证与同源检查共用原有蓝图。

## 独立 APK 下载与自动构建

本仓库每次 Release 都构建并校验 Android Mower 热更新 ZIP，生成的发布说明包含 [Android APK 与 Python 兼容接口下载链接](https://github.com/ALEXsun0/arknights-mower-android/releases)。不下载、转存或附带 APK / Python 兼容 ZIP，也不依赖 Android 仓库接口可用才能完成主仓库发版。

Android 仓库在默认发行分支上定期检查 Mower 与 MAA 的正式／公测 Release。检测到新版本后，拉取主仓库已发布的 Android 热更新包及 MAA 官方 Android ARM64 组件，构建内置新组件的签名 APK，连同 Python 兼容接口发布在 Android 仓库。两个仓库异步发布，GitHub 定时调度可能延迟；主仓库发版后不承诺新 APK 已经完成构建，也无需跨仓库写入凭据。只有内置组件变化的 APK 不应提示已有相同宿主的用户升级 APK。

使用「Prepare Release」前应确保包含 Android 打包流程的 PR 已合并至所选分支。发布准备通过 `workflow_call` 显式进入构建流程，不依赖 `GITHUB_TOKEN` 创建 tag 再触发另一条工作流。Android APK 的构建不由这个 token 跨仓库触发，而由 Android 仓库自行检测。

四端更新兼容任务共用 `update` 触发条件，手动运行或无法判定文件范围时保留完整检查。普通 WebUI 修改由公共前端任务验证；相关更新路径及正式发版仍验证真实 Android 归档。

仅 Android 的 MAA 检查会并行检查 MAA Python 兼容接口；两项失败独立显示，接口按内容摘要判断更新，手动导入或恢复后立即重新判断。其他三端不显示该接口组件，也不发起相关请求。

手机的唤醒、静音、后台恢复、局域网和日志设置由原生应用提供，不新增 Android WebUI 页面。
