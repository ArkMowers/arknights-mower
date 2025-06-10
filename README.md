# arknights-mower

Mower 是为长期运行设计的、开源的明日方舟脚本。

## 关于 Mower-NG

**Mower-NG 项目是由前 Mower 项目开发者之一 [EE0000 (@ZhaoZuohong)](https://github.com/ZhaoZuohong) 基于 Mower 项目的二次开发，并且现已独立运作为其个人开发的项目，和 Mower 项目不再有任何关联。**

**由于 [EE0000 (@ZhaoZuohong)](https://github.com/ZhaoZuohong) 已经退出 Mower 开发组，其在网络平台上发表的言论仅代表其个人观点，不代表 Mower 项目或 Mower 开发组的立场。我们敬请广大用户理性分析，并谨慎甄别相关信息。**

## 功能介绍

- 基建：跑单、按心情动态换班；
- 森空岛：签到、仓库读取；
- 日常：公招、邮件、线索、清理智；
- 大型任务：生息演算、隐秘战线；
- 签到：五周年月卡、限定池每日一抽、矿区、孤星领箱子、端午签到……
- 调用 maa：肉鸽、保全。

## 界面截图

![log](./img/log.png)
![settings](./img/settings.png)
![plan-editor](./img/plan-editor.png)
![riic-report](./img/riic-report.png)

## 下载与安装

### 运行环境准备

git、python 3.12、nodeJS 16

### 克隆仓库

```bash
git clone -c lfs.concurrenttransfers=200 https://github.com/ArkMowers/arknights-mower.git --branch 2025.6.1
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
```

生成的 `mower.exe` 在 `dist` 文件夹中，到此打包完成，已可使用。

### 打包（Linux）

```bash
pip install pyinstaller
pyinstaller webui_zip_for_linux.spec
```

生成的 `mower` 在 `dist` 文件夹中，到此打包完成，已可使用。

注：Linux下运行，shell会显示如 `Running on http://127.0.0.1:53703`的输出，本地浏览器访问`http://127.0.0.1:53703`即进入mower的页面。

## Linux系统下的Docker一键部署

### 运行环境准备

Docker version 28.1.128.1.1 、Linux

### 克隆仓库

```bash
git clone -c lfs.concurrenttransfers=200 https://github.com/ArkMowers/arknights-mower.git --branch 2025.6.1
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

### 进入Mower

容器在后台启动以后，可以本地浏览器访问`http://127.0.0.1:58000?token=mower`或`http://局域网IP:58000?token=mower`。

此时，该容器已预先配置好maa以及adb设置，仅需要手动配置adb连接地址。

## 建议与反馈

**提出建议、反馈 Bug，欢迎加入 QQ群：~~239200680~~（被爆破）, 521857729 QQ频道:ArkMower（频道号：2r118jwue4）。**
