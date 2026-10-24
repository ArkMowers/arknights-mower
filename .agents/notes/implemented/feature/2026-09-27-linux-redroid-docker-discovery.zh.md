---
title: Linux Redroid 本地 Docker 发现与绑定
status: implemented
category: feature
date: 2026-09-27
---

# Linux Redroid 本地 Docker 发现与绑定

[English](2026-09-27-linux-redroid-docker-discovery.md) | [中文](2026-09-27-linux-redroid-docker-discovery.zh.md)

## 1. 背景与动机
Redroid（Remote Android in Docker）是 Linux 环境下常用的云安卓容器方案。为了在不请求提权和不修改用户 Docker 守护进程的前提下提供自动发现，`linux.redroid` 预设接入了本地 Docker Engine 的受限只读发现协议。

---

## 2. 不变式与保证

- **[INV-01] 仅限本机 Docker Engine**：仅通过 `unix:///var/run/docker.sock` 访问本机 Docker；明确拒绝 Podman、K8s/Swarm 编排容器、远程 TCP Docker。
- **[INV-02] 隔离环境变量**：执行 Docker 命令时剥离 `DOCKER_HOST`、`DOCKER_CONTEXT`、`DOCKER_TLS` 等环境变量，确保操作完全限定在本地上下文。
- **[INV-03] 严格镜像白名单**：仅识别以 `redroid/redroid` 命名的官方仓库镜像（支持 tag 及 digest 标识）。
- **[INV-04] 回环网络约束**：容器内 `5555/tcp` 映射的宿主机端口必须绑定在回环地址（`127.0.0.1` 或 `::1`）；拒绝未发布端口或非回环绑定的容器。
- **[INV-05] 启停受控**：已停止的容器必须由用户在前端显式确认后才执行单次 `docker start`，系统绝不自动拉取镜像或修改端口映射。

---

## 3. 技术契约与检查要点

| 属性 | 用途 |
| :--- | :--- |
| `Id`, `Name` | 稳定绑定标识（64位十六进制 ID）与前端展示名称 |
| `Config.Image` | 校验是否匹配 `redroid/redroid` |
| `Config.Labels` | 排除 `io.kubernetes.` 与 `com.docker.swarm.` 编排容器 |
| `State.Status` | 区分 `running`、`stopped`、`restarting` |
| `NetworkSettings.Ports["5555/tcp"]` | 解析当前发布的 `HostPort` |

---

## 4. 验证

- 单元测试：`device_redroid_tests.py`、`device_redroid_io_tests.py`、`device_redroid_route_tests.py`
- 覆盖项：多容器过滤、动态端口变更、暂停状态报错、非法输出拦截。
