# Android 发行兼容

Windows、macOS、Linux 沿用现有实现。Android 宿主设置 `MOWER_ANDROID=1`，提供 `mower_android` 中的设备控制、配置接管与 MAA 适配器；Python 在 Linux 用户空间运行，Android 动态库由原生服务加载。

MAA 四端共用正式／公测渠道版本接口。Android 从相同目标版本选择官方 ARM64 组件，缺失时明确失败，不回退 Linux 包。核心、资源的安装与生效方式由宿主处理。

软件更新共用 `SoftwareUpdate` 页面和 `/software-update/*` API。宿主可在 `app.extensions["software_update_provider"]` 注册实现相同接口的 Release 安装器。未注册时继续使用现有桌面更新器。安装器返回 `deployment="release"`，通过可选能力字段说明是否支持自动更新、静默重启和安装提示；默认值保持桌面行为。认证与同源检查共用原有蓝图。

手机的唤醒、静音、后台恢复等设置全部由原生应用提供，不在 Mower WebUI 增加页面。APK、MAA Python 兼容包和官方核心的构建发布由 [独立仓库](https://github.com/ALEXsun0/arknights-mower-android) 负责。上游 CI 验证 Android 适配协议、渠道版本一致性和组件选择，并保留三端桌面回归测试。
