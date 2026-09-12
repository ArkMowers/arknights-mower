# Android 发行兼容

Windows、macOS、Linux 沿用现有实现。Android 宿主设置 `MOWER_ANDROID=1`，提供 `mower_android` 中的设备控制、配置接管与 MAA 适配器；Python 在 Linux 用户空间运行，Android 动态库由原生服务加载。

## 发布职责

| 内容 | 构建和发布来源 | Android 更新方式 |
| --- | --- | --- |
| Mower 程序、共享 WebUI、随程序资源 | 本仓库 Release 的 `arknights-mower_<version>_android_arm64.zip` | 共享软件更新页面，宿主校验后切换程序目录，重启 Mower 服务生效，无需重装 APK |
| MAA 核心、MAA 资源 | MAA 官方仓库 | 四端共用正式／公测渠道版本接口，从相同目标版本选择官方 Android ARM64 组件；资源使用官方 MaaResource |
| APK、MAA Python 兼容接口 | [arknights-mower-android](https://github.com/ALEXsun0/arknights-mower-android) Release | APK 使用系统安装器；接口包单独导入，不要求升级 APK |

Android 暂时禁用 Mirror酱：不显示源选项和 CDK，已有 CDK 不影响官方默认源，后端拒绝 Mirror 的核心、资源和 CDK 查询。其他三端保持原有 Mirror 功能。缺少官方 Android 核心时明确失败，不回退 Linux 包。

APK 与 Mower 版本独立。日常 Mower/MAA 代码、WebUI、资源及兼容接口更新不应重新构建 APK；只有 Android 系统能力、原生桥接或内置 Python 运行环境不兼容时才需要新版 APK。

## Mower 更新包协议

`scripts/package_android.py` 使用已注入的版本和已构建的共享 WebUI，生成一个 ZIP：根目录是 `mower-android.json`，应用内容位于 `mower/`。它包含 Mower Python 源码、模型、资源、`server.py`、`ui/dist`、版本、依赖清单和许可证，不包含 Python 解释器/依赖、`mower_android` 宿主、MAA 核心/接口或用户配置。运行设备不需要 Git、npm 或源码部署。

清单字段为 `kind="mower-android"`、`format=1`、`version`、`revision`、`runtime_api=1`、`python="3.12"`、`platform="android"`、`arch="arm64"`。`runtime_api` 表示宿主 API 与内置依赖的兼容约定；改变必须依赖的运行环境能力时应升级此值，普通程序和资源更新保持不变。`requirements.txt` 记录本次程序的依赖供审查，不在手机上自动执行 pip 安装。

宿主负责检查来源/digest、清单版本和兼容协议，将包解压到独立版本目录，验证成功后原子切换；不得覆盖正在运行的程序、宿主接口或用户数据。不兼容/损坏包保留当前版本。热更新指无需重装 APK，已加载的 Python 模块需重启 Mower 服务生效。

软件更新共用 `SoftwareUpdate` 页面和 `/software-update/*` API。宿主在 `app.extensions["software_update_provider"]` 注册相同接口的 Release 更新器，报告当前 **Mower** 版本并选择本仓库的 Android ZIP；APK 更新属于原生应用设置。未注册时继续使用桌面更新器，认证与同源检查共用原有蓝图。

## 自动附带 Android 宿主产物

本仓库每次 Release 自动读取 Android 仓库的 Release，正式版只选择正式版，公测版可复用正式/公测版；跳过草稿、开发版及不兼容的宿主。从最新兼容 Release 原样下载 APK 和 Python ZIP，使用 GitHub asset digest 校验，再附到本次 Release。版本不需要与 Mower 一致，Release 正文记录实际来源 tag，不重新打包或改签 APK。MAA 包不转存，更新始终从官方获取。

Android 仓库需随 APK 和接口发布 `android-release.json`：

```json
{
  "format": 1,
  "runtime_api": 1,
  "apk": {"name": "mower-android-arm64.apk"},
  "maa_python": {"name": "mower-maa-python-1.0.0.zip"}
}
```

所有三个文件均需 GitHub 提供 `sha256:` asset digest。清单只用于构建期间匹配，不额外上传校验文件。没有兼容宿主 Release 时，CI 明确提示并继续发布 Mower 包和桌面产物；发现清单损坏、文件缺失或下载校验失败时发布失败，避免附带不完整组合。

手机的唤醒、静音、后台恢复、局域网和日志设置由原生应用提供，不新增 Android WebUI 页面。CI 验证更新包边界、宿主产物复用、渠道和组件选择，并保留三端桌面回归测试。
