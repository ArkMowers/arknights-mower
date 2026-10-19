# Mower Web UI

Mower 的 Vue 3 前端与 Python 后端同在本仓库。界面可运行在桌面 WebView 或浏览器中；开发时由 Vite 提供前端，连接正在运行的 Mower 后端。

## 开发

先按[根目录部署说明](../README.md#源码部署)准备 Python、Node.js、依赖和前端初始构建。以下以 Windows PowerShell 为例；其他系统使用根目录说明中的虚拟环境解释器。

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
| 配置差量保存             | [config.js](src/stores/config.js)                                                                         | [configPartial.test.js](src/stores/configPartial.test.js)                                                                   |
| 排班验证                 | [plan.js](src/stores/plan.js)                                                                             | [planValidation.test.js](src/stores/planValidation.test.js)                                                                 |

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
