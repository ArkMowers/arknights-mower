---
sort: 1
---

# 安装与更新

**注意**：Mower 使用 Python 3.12，故不支持 Windows 7 及更早的 Windows 版本。

## 版本

自 2024 年 5 月起，mower 采取新的版本发布周期与命名规范：每年以春节、周年、夏活、半周年四个活动为节点，共发布四个版本，版本号以“年份+月份”命名。每个版本的支持周期为 6 个月，前 3 个月作为测试分支，开发新功能；后 3 个月作为稳定分支，只进行必要的维护与错误修复。

当前，稳定分支为 2024.02，测试版为 2024.05。

```mermaid
gantt

dateFormat YYYY.MM
axisFormat %Y.%m
title Mower 版本发布周期

v3.4.4  :done,   2023.11, 2024.05
2024.02 :active, 2024.05, 2024.08
2024.05 :active, 2024.05, 2024.11
2024.08 :done,   2024.08, 2025.02
2024.11 :done,   2024.11, 2025.05
```

## 下载

Mower 仅为 Windows 提供可执行文件。Linux 与 macOS 用户需要[从源码运行](#run-from-source)。

<h3 id="updater">更新器</h3>

更新器有两个版本：

- 新版更新器（[Funny-ppt/MowerUpdater](https://github.com/Funny-ppt/MowerUpdater)），由 [Funny-ppt](https://github.com/Funny-ppt/) 维护。
- 旧版更新器（[ArkMowers/updater](https://github.com/ArkMowers/updater)），由 [ZhaoZuohong](https://github.com/ZhaoZuohong/) 维护。

更新器从 [Mower 下载站](https://mower.zhaozuohong.vip/) 下载文件，既可全新安装，也可用于升级、降级。

新版更新器可检查并自动安装 mower 运行所需依赖。若新版更新器无法使用，可尝试旧版更新器。

### 直接下载

- GitHub：稳定版可从 [Releases](https://github.com/ArkMowers/arknights-mower/releases) 下载；测试版可从 [Actions](https://github.com/ArkMowers/arknights-mower/actions) 下载。
- 下载站：从 <https://mower.zhaozuohong.vip/> 直接下载 Zip 压缩包。

下载后解压运行即可。

如果 mower 无法正常运行（如窗口白屏、无法从带有二维码的图片导入排班表等），可尝试安装以下依赖：

- Microsoft Visual C++ 2013 Redistributable：<https://aka.ms/highdpimfc2013x64enu>
- Microsoft Visual C++ 2015-2022 Redistributable：<https://aka.ms/vs/17/release/vc_redist.x64.exe>
- Microsoft Edge WebView2：<https://go.microsoft.com/fwlink/p/?LinkId=2124703>

<h2 id="run-from-source">从源码运行</h2>

参照《[从源码运行 arknights-mower](https://blog.zhaozuohong.vip/2023/08/02/run-arknights-mower-from-source/)》。
