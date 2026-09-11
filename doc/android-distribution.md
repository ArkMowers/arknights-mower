# Android 独立发行版兼容

Android 壳在应用内提供 Linux CPython、共享 WebUI，以及独立的 Android MaaCore/后台游戏服务。APK 构建和发布由 [Arknights Mower Android 仓库](https://github.com/ALEXsun0/arknights-mower-android) 负责，上游不新增 APK 签名密钥或原生构建任务。

宿主设置 `MOWER_ANDROID=1`，并提供 `mower_android` 适配包与 `/android/*` API。桌面运行不加载这些适配器：

- `managed.normalize` 接管 ADB、模拟器、MAA路径和访问令牌；导入桌面配置时保留排班与任务设置。
- `device.AndroidDevice` 和 `maa.Asst` 将截图、输入和原生MAA调用交给Android宿主。Android的Bionic动态库不在Linux CPython进程内直接加载。
- MAA更新选择官方Android ARM64组件；缺少资产时拒绝，不能回退到Linux ARM64。Mirror酱无Android核心资产时显示原因；资源更新继续支持MaaResource。
- 共享WebUI显示“后台与系统”及Android独立更新页，隐藏桌面连接路径和Git源码版本管理。普通发行包只显示正式/公测渠道，Debug包可修改发行仓库；宿主API必须独立验证渠道、包名、签名与兼容协议，不能依赖前端隐藏。
- 支持APK、官方Android核心tar.gz和兼容MAA Python接口ZIP的选择/拖拽导入。APK由系统安装器确认，核心重启服务后生效，Python适配器在新实例创建时生效。它们不是桌面源码ZIP。

未设置该环境标记时，桌面更新API、Git源码部署与原连接设置保持原行为。直接向Android环境的`/software-update/*`发请求会在执行Git检查前拒绝；Android发行版使用自己的`/android/update/*`接口。

调试用宿主无需依靠`platform.system()`伪装成Android：Python实际运行在Linux用户空间，`MOWER_ANDROID`用于区分产品发行方式和控制器选择，底层Python平台信息保持真实。
