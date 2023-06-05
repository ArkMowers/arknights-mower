# Mower Web UI

Mower 的新界面。短期目标是 Mower 继续保持桌面应用的形态，界面运行在 WebView 中，取代原来的界面。未来考虑支持在浏览器中运行界面。代码也为在其它网站上展示、编辑 Mower 的排班表提供了可能。

本仓库仅包含前端代码，运行需要后端代码支持。

## 开发

开发时需要分别运行后端和前端。

### 后端

需要 Python 3.8 或 3.9。

后端代码在 [ArkMowers/arknights-mower](https://github.com/ArkMowers/arknights-mower) 仓库中。

安装依赖：

```bash
pip install -r requirements.txt
pip install Flask flask-cors flask-sock pywebview
```

运行后端：

```bash
flask --app server run --port=8000 --reload
```

### 前端

需要 Node.js 16。

安装依赖：

```bash
npm install
```

运行前端的开发服务器：

```bash
npm run dev
```

根据输出提示，在浏览器中打开窗口即可。

在开发时，前端默认会访问本地 `8000` 端口以连接后端。可以建立 `.env.development.local` 文件，通过 `VITE_HTTP_URL` 指定连接其它地址。例如连接本地的 5000 端口：

```plaintext
VITE_HTTP_URL="http://localhost:5000"
```

## 构建与测试

此时无需运行前端的开发服务器，前端构建生产版本的静态文件：

```bash
npm run build
```

将生成的 `dist` 文件夹复制到 `arknights-mower` 的目录中。此时运行后端：

```运行
flask --app server run --port=8000
```

直接在浏览器中打开 <http://localhost:8000>，就能看到前端了；运行 `./webview_ui.py`，也能在 WebView 窗口中看到前端。

## 打包

安装依赖：

```bash
pip install pyinstaller
```

使用 `pyinstaller` 打包：

```bash
pyinstaller menu.spec
```

生成的 `mower.exe` 在 `dist` 文件夹中。
