# arknights-mower

Mower 是为长期运行设计的开源明日方舟脚本。

## 功能介绍

- 基建：跑单、按心情动态换班；
- 森空岛：签到、仓库读取；
- 日常：公招、邮件、线索、清理智；
- 大型任务：生息演算、隐秘战线；
- 签到：五周年月卡、限定池每日一抽、矿区、孤星领箱子、端午签到……
- 调用 MAA：肉鸽、保全。

## 界面截图

![log](./img/log.png)
![settings](./img/settings.png)
![plan-editor](./img/plan-editor.png)
![riic-report](./img/riic-report.png)

## 下载与安装

### 运行环境准备

git、Python 3.12、Node.js 16

### 克隆仓库

```bash
git clone -c lfs.concurrenttransfers=200 https://github.com/ArkMowers/arknights-mower.git
cd arknights-mower
```

### 构建前端

```bash
cd ui
npm install
npm run build
```

### 构建后端（Windows）

```bash
cd ..
python -m venv venv
.\venv\Scripts\activate.bat
pip install -r requirements.txt
pip install Flask flask-cors flask-sock pywebview
```

### 构建后端（Linux）

```bash
cd ..
python3 -m venv venv
. ./venv/bin/activate
pip install -r requirements.in
pip install Flask flask-cors flask-sock pywebview
```

### 打包（Windows）

```bash
pip install pyinstaller
pyinstaller webui_zip.spec
python scripts/fix_runtime_dlls.py
```

生成的 `mower.exe` 在 `dist` 文件夹中，到此打包完成，已可使用。

### 打包（Linux）

```bash
pip install pyinstaller
pyinstaller webui_zip_for_linux.spec
```

生成的 `mower` 在 `dist` 文件夹中，到此打包完成，已可使用。

注：Linux 下运行时，shell 会显示如 `Running on http://127.0.0.1:53703` 的输出，本地浏览器访问 `http://127.0.0.1:53703` 即进入 Mower 页面。

## Docker 部署

Docker 部署说明见 [docs/docker-deploy-guide.md](docs/docker-deploy-guide.md)。

## Linux系统下的Docker一键部署

### 运行环境准备

Docker version 28.1.128.1.1、Linux

### 克隆仓库

```bash
git clone -c lfs.concurrenttransfers=200 https://github.com/ArkMowers/arknights-mower.git
cd arknights-mower
```

### 镜像构建

```bash
docker build -t mower .
```

### 启动容器

```bash
docker run -d \
    --name mower\
    --network host \
    -e TZ="Asia/Shanghai" \
    --restart always \
    --memory 2g \
    mower
```

### 进入 Mower

容器在后台启动以后，可以本地浏览器访问 `http://127.0.0.1:58000?token=mower` 或 `http://局域网IP:58000?token=mower`。

此时，该容器已预先配置好 MAA 以及 ADB 设置，仅需要手动配置 ADB 连接地址。

## 建议与反馈

**提出建议、反馈 Bug，欢迎加入 QQ群：~~239200680~~（被爆破）, 521857729 QQ频道:ArkMower（频道号：2r118jwue4）。**
