---
title: MuMu 12 运行时目录布局的管理器解析
status: implemented
category: bug-fix
date: 2026-10-07
---

# MuMu 12 运行时目录布局的管理器解析

## 契约

MuMu 12 厂商适配器在 `shell/`、`nx_main/`、`temp/main`、`temp/shell` 与安装根目录解析管理器。`temp/<pair>` 与 `.backup/<pair>` 是运行时目录对，因此「安装根目录」位于它们之上两级。已保存的「安装配置」把运行时目录作为 `installation_path`，或注册来源路径把运行时目录作为 `manager_path` 时，都解析到同一个根目录及其 `MuMuManager.exe`。

## 缺陷

检测只在 `shell/`、`nx_main/` 与安装根目录解析管理器候选。把 `MuMuManager.exe` 放在 `temp/main` 之下的版本在这些位置没有任何候选，于是模拟器正在运行时，检测仍以空候选列表报出 `missing_installation`。安装根目录后续会流入 ADB 解析与临时设备恢复，因此运行时目录绝不能作为该根目录被保存。

此布局的注册来源只提供 `UninstallString`：`InstallLocation` 为空，注册的根目录取自卸载程序的可执行文件父目录。执行管理器不能作为安装目录的证据，因此厂商适配器保留只读位置清单，绝不通过查询管理器来定位自身。

## 实现

`arknights_mower/utils/device/mumu_layout.py` 负责安装布局：根级目录（`shell`、`nx_main`）、运行时目录对（`temp`、`.backup`）、管理器位置，以及运行时目录对之上的根目录。Windows 检测适配器与 MuMu IPC 路径解析器共同读取该唯一清单，使验证截图、运行中的 IPC 适配器与端点解析不会彼此漂移。

## 验证

`arknights_mower/tests/device_mumu_io_tests.py` 覆盖从注册根目录、从父目录即根目录的卸载程序、以及从运行时目录候选解析管理器与根目录。`arknights_mower/tests/device_mumu_capture_tests.py` 覆盖在缺少安装目录时解析已保存的管理器路径，并拒绝把运行时目录当作自身根目录。管理器位于 `temp/main/MuMuManager.exe` 的实际 MuMu 12 安装会返回一个 `discovered` 候选，携带其运行中实例与当前 ADB 端点。
