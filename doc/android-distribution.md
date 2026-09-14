# Android 发行兼容

Windows、macOS、Linux 沿用现有实现。Android 宿主设置 `MOWER_ANDROID=1`，提供 `mower_android` 中的设备控制、配置接管与 MAA 适配器；Python 在 Linux 用户空间运行，Android 动态库由原生服务加载。

## 发布职责

| 内容 | 构建和发布来源 | Android 更新方式 |
| --- | --- | --- |
| Mower 程序、共享 WebUI、随程序资源 | 本仓库 Release 的 `arknights-mower_<version>_android_arm64.zip` | 共享软件更新页面，宿主校验后切换程序目录，重启 Mower 服务生效，无需重装 APK |
| MAA 核心、MAA 资源 | MAA 官方仓库 | 四端共用正式／公测渠道版本接口，从相同目标版本选择官方 Android ARM64 组件；资源使用官方 MaaResource |
| APK、MAA Python 兼容接口 | [arknights-mower-android](https://github.com/ALEXsun0/arknights-mower-android) Release | APK 使用系统安装器；接口包单独导入，不要求升级 APK |

Android 暂时禁用 Mirror酱：不显示源选项和 CDK，已有 CDK 不影响官方默认源，后端拒绝 Mirror 的核心、资源和 CDK 查询。其他三端保持原有 Mirror 功能。缺少官方 Android 核心时明确失败，不回退 Linux 包。

APK 与 Mower 版本独立。日常 Mower/MAA 代码、WebUI、资源及兼容接口更新不要求用户更新 APK；只有 Android 系统能力、原生桥接或内置 Python 运行环境不兼容时才需要新版 APK。

## Mower 更新包协议

`scripts/package_android.py` 使用已注入的版本和已构建的共享 WebUI，生成一个 ZIP：根目录是 `mower-android.json`，应用内容位于 `mower/`。它包含 Mower Python 源码、模型、资源、`server.py`、`ui/dist`、版本、依赖清单和许可证，不包含 Python 解释器/依赖、`mower_android` 宿主、MAA 核心/接口或用户配置。运行设备不需要 Git、npm 或源码部署。

清单字段为 `kind="mower-android"`、`format=1`、`version`、`revision`、`runtime_api=1`、`python="3.12"`、`platform="android"`、`arch="arm64"`。`runtime_api` 表示宿主 API 与内置依赖的兼容约定；改变必须依赖的运行环境能力时应升级此值，普通程序和资源更新保持不变。`requirements.txt` 记录本次程序的依赖供审查，不在手机上自动执行 pip 安装。

宿主负责检查来源/digest、清单版本和兼容协议，将包解压到独立版本目录，验证成功后原子切换；不得覆盖正在运行的程序、宿主接口或用户数据。不兼容/损坏包保留当前版本。热更新指无需重装 APK，已加载的 Python 模块需重启 Mower 服务生效。

软件更新共用 `SoftwareUpdate` 页面和 `/software-update/*` API。宿主在 `app.extensions["software_update_provider"]` 注册相同接口的 Release 更新器，报告当前 **Mower** 版本并选择本仓库的 Android ZIP；APK 更新属于原生应用设置。未注册时继续使用桌面更新器，认证与同源检查共用原有蓝图。

## 独立 APK 下载与自动构建

本仓库每次 Release 都构建并校验 Android Mower 热更新 ZIP，生成的发布说明包含 [Android APK 与 Python 兼容接口下载链接](https://github.com/ALEXsun0/arknights-mower-android/releases)。不下载、转存或附带 APK / Python 兼容 ZIP，也不依赖 Android 仓库接口可用才能完成主仓库发版。

Android 仓库在默认发行分支上定期检查 Mower 与 MAA 的正式／公测 Release。检测到新版本后，拉取主仓库已发布的 Android 热更新包及 MAA 官方 Android ARM64 组件，构建内置新组件的签名 APK，连同 Python 兼容接口发布在 Android 仓库。两个仓库异步发布，GitHub 定时调度可能延迟；主仓库发版后不承诺新 APK 已经完成构建，也无需跨仓库写入凭据。只有内置组件变化的 APK 不应提示已有相同宿主的用户升级 APK。

使用「Prepare Release」前应确保包含 Android 打包流程的 PR 已合并至所选分支。发布准备通过 `workflow_call` 显式进入构建流程，不依赖 `GITHUB_TOKEN` 创建 tag 再触发另一条工作流。Android APK 的构建不由这个 token 跨仓库触发，而由 Android 仓库自行检测。

四端更新兼容任务共用 `update` 触发条件，手动运行或无法判定文件范围时保留完整检查。普通 WebUI 修改由公共前端任务验证；相关更新路径及正式发版仍验证真实 Android 归档。

手机的唤醒、静音、后台恢复、局域网和日志设置由原生应用提供，不新增 Android WebUI 页面。
