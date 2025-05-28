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

**提出建议、反馈 Bug，欢迎加入 QQ群：~~239200680~~（被爆破）, 521857729 QQ频道:ArkMower（频道号：2r118jwue4）。**

### 运行环境准备

git、python3.12、nodeJS 16以上

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

### 构建后端

```bash
cd ..
python -m venv venv
.\venv\Scripts\activate.bat
pip install -r requirements.txt
pip install Flask flask-cors flask-sock pywebview
```

### 打包

```bash
pip install pyinstaller
pyinstaller webui_zip.spec
```

生成的 `mower.exe` 在 `dist` 文件夹中，到此打包完成，已可使用。
