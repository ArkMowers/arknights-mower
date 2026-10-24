# Mower Web UI

Mower 的 Vue 3 前端与 Python 后端同在本仓库。界面可运行在桌面 WebView 或浏览器中；开发时由 Vite 提供前端，连接正在运行的 Mower 后端。

## 设置与任务配置

[Mower 设置](src/pages/Settings.vue)管理界面与窗口、通知与助手、网络与更新、数据与维护。[任务配置](src/pages/TaskSettings.vue)是独立页面，默认位于侧边栏“运行日志”下方；页面左侧目录用于选择配置，右侧用于编辑参数。“连接与启动”提供设备配置，“基建排班”提供排班设置和编辑入口。移动端点击底栏“任务”即可进入任务配置。

侧栏的分组、页面副本、固定区域和保存边界由 Arknights Mower Web 访问子系统说明中的[侧栏偏好](../docs/subsystems/web-access.md#sidebar-preferences)与[布局和编辑规则](../docs/subsystems/web-access.md#sidebar-layout-and-editing)维护。源码启动标识、软件渠道徽标、资源名称与随活动时间变化的颜色见[侧栏版本徽标规则](../docs/subsystems/web-access.md#sidebar-version-badges)；资源元数据来自[已安装资源](../docs/subsystems/resource-update.md#installed-resource-metadata)。

在 Mower 设置 → 界面与窗口 → 常规中，“软件版本显示”选择版本号或版本类型，常驻预览标题旁的小型“版本类型语言”控件可切换中文或 English，默认使用 English。中文类型显示为“源码部署”“公测版”“开发版”“正式版”，沿用更新渠道的发布版本名称。预览徽标与侧栏共用这些选择，窄屏中的长版本号在节点内换行。保存失败时恢复原来的显示，并提供重试。完整行为见[软件版本徽标规则](../docs/subsystems/web-access.md#sidebar-version-badges)。

桌面自绘标题栏和 WebUI 的“实例”菜单显示多开管理器中的实例和进程状态，提供添加、启停、重命名、保存目录、实例配置和批量操作。菜单复用[多开管理器组件](manager/MowerManager.vue)及其确认、编辑保护和结果提示，后端行为见[实例管理说明](../docs/subsystems/web-access.md#7-desktop-instance-manager)。软件与资源版本在 Mower 名称下方左对齐。桌面标题栏高 36px，侧栏收起后宽 64px。左侧菜单标签与实例信息使用 12px 字号、22px 行高，菜单按钮高 22px，均在标题栏内垂直居中。下拉菜单主文字为 12px，普通选项高 32px。侧栏导航图标在展开时为 20px，收起时为 22px；标题栏侧栏按钮的图标为 14px。HTML 窗口控件宽 46px、高 36px，图标与左侧按钮处于同一水平线，关闭按钮保留红色反馈。页面紧接标题栏底边，原生拖动区域也以 36px 为高度边界。pywebview 壳的外边线和圆角由 Windows 原生窗口管理器绘制；页面不为边线预留外侧空隙，底部延伸到窗口边缘。常规按钮和输入框采用 8px 圆角，卡片、菜单和弹窗使用更柔和的圆角，侧栏滚动边缘以模糊渐隐衔接固定区域。

点击“常用”“数据报表”“资料”或自建分组的标题，可以展开或收起组内页面。分组标题与 Mower 名称左对齐，组内页面和固定底部入口向右缩进。已展开分组的箭头在悬停标题或用键盘聚焦标题内按钮时显示；鼠标移开并点击组内页面后，箭头恢复隐藏。收起分组的箭头一直显示。“⋯”按钮在悬停、键盘聚焦或菜单打开期间显示，在触屏和移动端抽屉中一直显示；移动端按钮有独立的点击区域，下拉菜单按操作用途分隔。页面的“取消置顶”会将当前副本放回原分组；原位置已有同页副本时，该操作会禁用，悬停可查看原因。置顶页的“移除此入口”仅删除当前副本。

直接拖动页面可调整顺序或移动分组，拖动分组标题可调整分组顺序。鼠标移动至少 8px 即可开始拖动，触屏需先按住 180ms 再移动至少 8px；普通点击立即导航，开始拖动后才显示抓手光标。拖动时，整行页面或整个分组作为浮层跟随指针，列表保留占位，其他项目平滑让位。拖动页面期间，收起的分组暂时展开以便移入，松开后恢复原来的展开状态。拖动不打开页面，松开后再点击仍正常导航；标题旁的菜单可照常使用。

导航列表或设置目录放不下全部内容时，滚动条两端显示上下三角，点击可向对应方向滚动；到顶或到底时，对应三角变淡并停用。没有溢出时不显示三角。

养成计划顺序、MAA 周计划、干员和宿舍选择标签共用拖动浮层外观，排班编辑与干员心情报表使用整张卡片快照作为拖动预览。养成计划中进行中的专精保持锁定，设施交换和各列表的排序规则继续由对应组件处理。

选择分组标题旁的“⋯ → 添加页面”，勾选需要的页面后点击底部“添加”；按钮括号内显示已选数量。需要独立页面或更多布局操作时，打开“视图 → 编辑侧边栏”。

“编辑侧边栏”弹窗集中提供新建、重命名、解散分组。将页面直接拖到目标分组、“独立页面”或“置顶”区域，即可调整顺序和归属；拖动分组的排序图标可调整分组顺序。分组可以全部解散；需要重新开始时，在弹窗底部选择“恢复默认”。编辑器中的修改随操作保存，关闭窗口即可返回当前页面。

点击 WebUI 左上角带下拉箭头的 Mower 名称，即可打开菜单；悬停“连接”“档案”“视图”或“帮助”可展开对应选项，也可用键盘或触屏选择。菜单底部分隔显示当前实例名、设备名和可用端口。桌面自绘标题栏保留各菜单按钮，两种形式共用[菜单组件](src/components/AppMenuBar.vue)。macOS 保留左侧原生红黄绿窗口按钮，应用菜单继续显示在窗口内；原生按钮占位、缩放和拖动规则见 [Arknights Mower 桌面窗口子系统说明](../docs/subsystems/desktop-window.md)。“实例”在桌面和浏览器中均可打开；WebUI 的保存目录填写运行 Mower 那台电脑上的完整路径，接口不可用时显示错误并提供重试。“视图”可显示、隐藏侧边栏或打开编辑弹窗，折叠按钮用于切换图标栏；“帮助”提供反馈问题、文档、更新日志和关于。菜单入口与身份信息来源见[共用菜单规则](../docs/subsystems/web-access.md#shared-app-menus)。

“连接”菜单进入任务配置页的“连接与启动”，该入口直接展开设备高级设置。“选择模拟器”显示连接操作，“连接设置”定位高级设置，“测试连接”执行现有只读检查并显示结果。任务运行或连接检查期间禁用测试；离开页面或切换配置后再次选择菜单项会重新定位，保留未保存的草稿。只读检查与保存边界遵循[设备控制说明](../docs/subsystems/device-control.md)。

“档案”菜单管理当前实例保存的多套设置与业务数据，提供新建、复制、重命名、切换及 ZIP 导入、导出。新建和复制时勾选沿用当前档案的内容；导入或切换时勾选保留当前的哪些内容。设备与游戏连接保持整组，其他设置、排班、库存、养成计划和历史按目录展开后分别选择。勾选项会写入目标档案，未应用的编辑器草稿在刷新时丢弃。切换前需停止任务并等待设备、更新操作结束；成功后刷新当前页面，且此次刷新不会自动开始任务。导出和重命名成功后不显示通知，错误及需要重新加载的提示继续保留。数据归属、失败恢复及接口边界见[已保存配置说明](../docs/subsystems/config-profiles.md)。

点击 Mower 设置入口后，设置在固定居中的弹窗中打开，主导航和进入前的页面保留在遮罩后。弹窗左侧保留搜索与分类，右侧每次显示一个分类并单独滚动；点击搜索结果可打开对应分类并定位。窄屏将搜索和横向分类放在内容上方。设置及其他弹窗的大小按可用窗口和界面缩放限制，内容过长时在弹窗内滚动。设置弹窗不能拖动，顶部只提供标题和关闭按钮；点击关闭按钮或按 Esc 返回原页，直接访问设置地址时返回运行日志。完整行为见[设置目录规则](../docs/subsystems/web-access.md#settings-directory)。

“界面与窗口”中的“常规”集中管理界面缩放、主题和显示偏好，“窗口”管理托盘及桌面窗口行为。缩放滑块、当前比例或待应用比例与“应用”按钮放在同一控制区域，点击“应用”后生效。“启动时窗口状态”控制下次打开桌面窗口时使用普通窗口、最大化窗口，或恢复上次状态。

显示主题可选亮色、暗色或跟随系统，默认仍为亮色。选择跟随系统后，界面随系统明暗变化，保存的选择保持“跟随系统”。

[运行日志](src/pages/Log.vue)在同一页面显示截图、任务列表和日志，截图与任务区域可调整高度。任务列表保持透明背景，仅在队列非空时显示，使用“时间”和“任务”两列，宽度不超过 600px，按后端顺序显示待执行时间、任务名称和房间安排。移动端截图按可用宽度等比铺开，右上角按钮可收起整个任务列表；矮屏可滚动内容，底部操作栏保持可见。移动端操作栏以一行显示启动或停止、橙色新增按钮和更多按钮，数据库管理、截图预览、自动滚动及新增任务说明放在更多面板中；点击启动按钮旁的箭头可选择其他启动方式。桌面保留原有直接入口。完整布局及手动调整规则见[任务配置与日志规则](../docs/subsystems/web-access.md#task-configuration)。

[任务配置组件](src/task-workflow/TaskConfiguration.vue)在“任务清单”视图内使用统一的左右面板，左侧目录可切换“任务”和“运行配置”，右侧显示所选参数。“任务”按“基建任务”“日常任务”“作战与空闲”分组，并提供“连接与启动”；“运行配置”集中提供“执行间隔”“运行参数”“账号与数据来源”“MAA 核心”。分组标题只显示文字，点击条目名称打开配置。搜索覆盖两类目录，没有单独的齿轮按钮。基建排班、无人机加速、加工站和奖励沿用各自的排班或参数条件，不增加总开关。

设置和任务配置都可搜索字段名称、说明及选项，并用空格组合多个关键词。例如“公招 三星”可找到公开招募，“深色”可找到暗色主题。SMTP 等条件字段在尚未选择对应模式时也可定位到所属卡片；搜索和点击结果不会改变模式、启用任务或保存配置。具体匹配方式及字段索引来源见[搜索规则](../docs/subsystems/web-access.md#settings-search)。

“执行间隔”编辑日常任务间隔，无人机加速、公开招募与信赖轮换在各自任务卡片中设置，沿用原有字段。切换面板或离开页面后返回均保留所选配置和设备草稿。任务配置页省去“查看待执行任务”入口，实际队列仍在运行日志中显示，`#task-queue` 继续定位任务列表；执行顺序与时机由后端决定。

在 Mower 设置 → 界面与窗口 → 常规 → 任务配置显示中选择“任务清单”或“瀑布流”，默认使用“任务清单”；选择保存在当前实例中，任务页不再显示切换按钮。瀑布流左侧提供搜索和目录，点击条目或搜索结果可定位右侧对应卡片，并用主题色边框和浅色背景短暂高亮；重复点击同一条目会重新高亮，切换目标则清除上一个高亮。可用宽度足够时，内容连续排成两列，目录条目也排成两列；宽度不足时，内容以单列居中，目录条目保持单列。卡片沿各列连续排列，避免固定分组在另一列留下大片空白。切换显示方式保留所选配置和草稿；保存失败时恢复原来的显示，并提供重试。完整布局、字段保存、页面保留及原 `/maasettings`、`#task-*` 地址的兼容行为见[任务配置规则](../docs/subsystems/web-access.md#task-configuration)。

桌面端瀑布流目录默认展开，点击“配置导航”右侧的收起按钮后，只保留 52px 宽的展开入口；下滑页面时仍可点击展开。收起后腾出的空间用于配置内容，宽度足够时卡片会由单列改为双列。重新展开时保留搜索、分类、所选配置和目录滚动位置，表单草稿也保持不变。收起目录不保存配置，不影响任务清单和移动端目录；从窄窗口切回桌面后恢复原来的展开或收起状态。

移动端的任务清单和瀑布流都将可折叠目录放在内容上方，下滑时目录固定在页面滚动区域顶部，底栏仍保持可见。展开目录后可滚动查找条目，目录高度随可用窗口限制，矮屏也可滚动目录内容。条目采用至少 44px 高的触屏点击区域；选择后自动收起目录，并让目标标题或卡片显示在目录下方。

移动端底栏依次提供“任务”“排班”“养成”“日志”“报表”“设置”“更多”，七个入口等宽排列，并保留设备底部安全区域。“日志”位于正中间，用稍大的图标、主题色底色和加粗文字突出显示；当前页面仍按路由高亮。“任务”直接打开任务配置，“设置”直接打开 Mower 设置；“排班”提供正常、救急排班入口，“报表”弹出数据报表中的七个原有页面，“更多”打开侧栏抽屉。

任务清单的“仓库物品混合读取”管理仓库读取来源；“运行配置”中的“账号与数据来源”管理账号、同步设置及收益统计口径；仓库历史保留在 Mower 设置中管理。配置字段和保存规则遵循现有[前端规范](AGENTS.md)，界面调整不改变配置格式。

## 开发

先按[根目录部署说明](../README.md#源码部署)准备 Python、Node.js、依赖和前端初始构建。以下以 Windows PowerShell 为例；其他系统使用根目录说明中的虚拟环境解释器。

### 使用示例数据预览

在 `ui/` 下运行：

```powershell
npm run preview:mock
```

打开 [离线预览](http://127.0.0.1:5179/?window_shell=1)，可查看带有 64 行日志、五项任务和示例截图的界面。预览使用真实页面组件，数据和设置编辑仅保存在浏览器内存中，刷新后恢复示例；截图标注为“离线预览 · 示例截图”。预览模式拦截接口和 WebSocket 请求，未提供的操作会返回拒绝结果。

[本地启动配置](../.claude/launch.json)的 `ui` 使用此浏览器预览入口；`ui-real` 保留真实后端联调入口。

要在 pywebview 桌面壳中查看同一套示例数据，先在 `ui/` 下构建示例页面，再回到仓库根目录启动：

```powershell
npm run build:mock
cd ..
python webview_ui.py --preview
```

示例构建写入独立的 `ui/dist-preview/`，桌面预览只为该目录启动本地静态服务，使用真实窗口按钮、拖动、缩放和系统边框。窗口关闭后释放静态服务，示例配置编辑保留在内存中。原有 `npm run build` 和 `python webview_ui.py` 继续使用真实数据；缺少示例构建时，`--preview` 会提示先运行 `npm run build:mock`。预览入口及其验证边界见[Web 访问与桌面实例说明](../docs/subsystems/web-access.md#8-offline-desktop-preview)。

### 后端

在仓库根目录启动后端和桌面窗口，并允许指定的 Vite 回环端口：

```powershell
$env:MOWER_DEV_PORT = '5173'
.\.venv\Scripts\python.exe webview_ui.py
```

在托盘菜单中选择「在浏览器中打开网页面板」。该地址包含后端实际端口及当前会话的 `token`。后端端口和 Vite 端口是两个不同的端口。

### 前端

在 `ui/` 下创建 `.env.development.local`，将 `VITE_HTTP_URL` 设为刚才地址的来源部分，不含查询参数。例如实际后端地址为 `http://127.0.0.1:18080/?token=…` 时：

```dotenv
VITE_HTTP_URL="http://127.0.0.1:18080"
```

在另一个 PowerShell 终端进入 `ui/`，使用与后端相同的 Vite 端口：

```powershell
$env:MOWER_DEV_PORT = '5173'
npm ci
npm run dev
```

在 Vite 输出的地址后追加后端地址中的 `?token=…`，保留原值。HTTP 请求及 WebSocket 都需要该凭证；只更改 `VITE_HTTP_URL` 无法通过认证。后端重启后，重新核对实际端口和会话凭证；更改 `.env.development.local` 后重启 Vite。

端口占用时，Vite 会报错。更换 Vite 端口需在后端和前端终端设置相同的 `MOWER_DEV_PORT` 并重启它们。认证与来源限制见[开发来源诊断](../docs/cookbook/device-troubleshooting.md#local-development-origin)。

## 修改入口与定向验证

| 任务                     | 源码入口                                                                                                  | 离线验证入口                                                                                                                |
| :----------------------- | :-------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------- |
| 设备选择、检测与设置保存 | [DeviceSettings.vue](src/components/DeviceSettings.vue)、[deviceSettings.js](src/utils/deviceSettings.js) | [deviceSettings.test.js](src/utils/deviceSettings.test.js)、[DeviceSettings.test.js](src/components/DeviceSettings.test.js) |
| 配置差量保存 | [config.js](src/stores/config.js) | [configPartial.test.js](src/stores/configPartial.test.js) |
| 导航、固定品牌头与设置目录 | [App.vue](src/App.vue)、[SidebarBrand.vue](src/components/SidebarBrand.vue)、[AppSidebar.vue](src/components/AppSidebar.vue)、[SettingsSidebar.vue](src/components/SettingsSidebar.vue)、[navigation.js](src/navigation.js) | [App.test.js](src/App.test.js)、[NavigationShell.test.js](src/components/NavigationShell.test.js)、[SettingsSidebar.test.js](src/components/SettingsSidebar.test.js)、[navigation.test.js](src/navigation.test.js) |
| 移动端底栏与页面选择 | [MobileTabBar.vue](src/components/MobileTabBar.vue)、[navigation.js](src/navigation.js) | [MobileTabBar.test.js](src/components/MobileTabBar.test.js)、[navigation.test.js](src/navigation.test.js) |
| 设置与任务搜索 | [SettingsLayout.vue](src/components/SettingsLayout.vue)、[TaskChecklistNavigation.vue](src/task-workflow/TaskChecklistNavigation.vue)、[settingsSearch.js](src/utils/settingsSearch.js)、[model.js](src/task-workflow/model.js) | [SettingsSidebar.test.js](src/components/SettingsSidebar.test.js)、[TaskWorkflow.test.js](src/task-workflow/TaskWorkflow.test.js) |
| 侧栏弹窗、分组、顺序与显示偏好 | [AppSidebar.vue](src/components/AppSidebar.vue)、[SidebarEditor.vue](src/components/SidebarEditor.vue)、[SidebarCustomize.vue](src/components/SidebarCustomize.vue)、[sidebarPreferences.js](src/composables/sidebarPreferences.js) | [SidebarEditor.test.js](src/components/SidebarEditor.test.js)、[SidebarCustomize.test.js](src/components/SidebarCustomize.test.js)、[sidebarPreferences.test.js](src/composables/sidebarPreferences.test.js)、[AppSidebar.test.js](src/components/AppSidebar.test.js)、[NavigationShell.test.js](src/components/NavigationShell.test.js) |
| 侧栏滚动、上下三角与端点状态 | [SidebarScroll.vue](src/components/SidebarScroll.vue) | [SidebarScroll.test.js](src/components/SidebarScroll.test.js) |
| 当前实例侧栏保存与窗口偏好并发写入 | [gui.py](../arknights_mower/utils/config/gui.py)、[侧栏 API](../arknights_mower/views/gui.py) | [gui_sidebar_tests.py](../arknights_mower/tests/gui_sidebar_tests.py)、[webview_ui_tests.py](../arknights_mower/tests/webview_ui_tests.py) |
| 拖动浮层、卡片预览与缩放定位 | [drag.css](src/styles/drag.css)、[dragPreview.js](src/utils/dragPreview.js)、[sortablePreview.js](src/utils/sortablePreview.js) | [dragPreview.test.js](src/utils/dragPreview.test.js)、[sortablePreview.test.js](src/utils/sortablePreview.test.js) |
| WebUI 实例管理与桌面共用适配 | [instanceManagement.js](src/utils/instanceManagement.js)、[MowerManager.vue](manager/MowerManager.vue)、[实例 HTTP 接口](../arknights_mower/views/instances.py) | [instanceManagement.test.js](src/utils/instanceManagement.test.js)、[MowerManager.test.js](manager/MowerManager.test.js)、[instances_http_tests.py](../arknights_mower/tests/instances_http_tests.py) |
| 标题栏、Mower 下拉菜单与身份信息 | [App.vue](src/App.vue)、[WindowTitlebar.vue](src/components/WindowTitlebar.vue)、[AppMenuBar.vue](src/components/AppMenuBar.vue) | [App.test.js](src/App.test.js)、[WindowTitlebar.test.js](src/components/WindowTitlebar.test.js)、[InstanceTitlebar.test.js](src/components/InstanceTitlebar.test.js) |
| 主页任务列表、任务配置页与执行间隔 | [Log.vue](src/pages/Log.vue)、[TaskSettings.vue](src/pages/TaskSettings.vue)、[TaskConfiguration.vue](src/task-workflow/TaskConfiguration.vue)、[TaskWorkflow.vue](src/task-workflow/TaskWorkflow.vue)、[TaskSettingsPanels.vue](src/components/TaskSettingsPanels.vue)、[model.js](src/task-workflow/model.js)、[queueNavigation.js](src/task-workflow/queueNavigation.js) | [Log.test.js](src/pages/Log.test.js)、[App.test.js](src/App.test.js)、[navigation.test.js](src/navigation.test.js)、[TaskConfiguration.test.js](src/task-workflow/TaskConfiguration.test.js)、[TaskWorkflow.test.js](src/task-workflow/TaskWorkflow.test.js)、[model.test.js](src/task-workflow/model.test.js)、[queueNavigation.test.js](src/task-workflow/queueNavigation.test.js) |
| 任务配置显示偏好与保存 | [TaskLayoutPreference.vue](src/components/TaskLayoutPreference.vue)、[gui.js](src/stores/gui.js)、[外观 API](../arknights_mower/views/gui.py) | [TaskLayoutPreference.test.js](src/components/TaskLayoutPreference.test.js)、[gui.test.js](src/stores/gui.test.js)、[gui_appearance_tests.py](../arknights_mower/tests/gui_appearance_tests.py) |
| 软件版本显示、类型语言与资源版本徽标 | [SoftwareVersionPreference.vue](src/components/SoftwareVersionPreference.vue)、[SoftwareVersionBadge.vue](src/components/SoftwareVersionBadge.vue)、[SidebarBrand.vue](src/components/SidebarBrand.vue)、[versionBadges.js](src/utils/versionBadges.js) | [SoftwareVersionPreference.test.js](src/components/SoftwareVersionPreference.test.js)、[SidebarBrand.test.js](src/components/SidebarBrand.test.js)、[versionBadges.test.js](src/utils/versionBadges.test.js)、[gui.test.js](src/stores/gui.test.js)、[gui_appearance_tests.py](../arknights_mower/tests/gui_appearance_tests.py) |
| 排班验证 | [plan.js](src/stores/plan.js) | [planValidation.test.js](src/stores/planValidation.test.js) |

从 `ui/` 执行与改动有关的测试，例如：

```bash
npm test -- src/utils/deviceSettings.test.js src/components/DeviceSettings.test.js
```

这些测试使用离线输入与替代的请求或组件依赖，验证界面状态和请求行为；通过不代表后端或真实设备完成操作。跨越配置、设备或调度边界时，沿[设备规范](../docs/subsystems/device-control.md#start-with-the-affected-operation)或[调度规范](../docs/subsystems/base-scheduler.md#start-with-the-affected-operation)选择对应后端测试。[UI 规范](AGENTS.md)规定配置与状态边界。

## 代码检查

在 `ui/` 中执行只读检查：

```bash
npm run lint:check
```

[ESLint 配置](eslint.config.js)检查 `.vue`、`.js`、`.jsx`、`.cjs` 和 `.mjs` 文件，使用 JavaScript recommended 与 Vue essential 规则。配置继续读取 [.gitignore](.gitignore) 中的忽略规则，并忽略隐藏文件和目录；浏览器源码与 Node 构建脚本分别使用对应的全局变量。

Vue 文件中的 TypeScript 脚本使用 TypeScript 解析器，未使用变量由对应的 TypeScript 规则检查；独立 `.ts` 文件仍不在本次检查范围内。

需要自动修复时执行 `npm run lint`，完成后审阅文件差异并运行受影响组件或工具的定向测试。格式检查和整理继续使用 Prettier。

## 构建与打包

需要生产静态文件时，在 `ui/` 执行：

```bash
npm run build
```

构建产物供后端与桌面启动器使用。平台打包与发布检查由[本地打包说明](../docs/cookbook/packaging.md)维护。
