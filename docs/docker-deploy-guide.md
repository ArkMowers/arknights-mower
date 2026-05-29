# Arknights Mower Docker 部署说明

本文档整理 Linux 环境下使用 Docker 部署 Arknights Mower 的基本流程。

## 适用场景

- Linux 主机或 NAS 环境
- Docker 与 Docker Compose 已安装
- 通过浏览器访问 WebUI
- 可按实际情况连接模拟器、远程 ADB 或 USB 调试设备

## 运行环境准备

- Docker 24.0 或更新版本
- Docker Compose v2
- Linux 主机
- 如使用真机 USB 连接，请先在安卓设备上开启 USB 调试，并确认主机侧 `adb devices` 能看到设备

## 克隆仓库

```bash
git clone https://github.com/ArkMowers/arknights-mower.git
cd arknights-mower
```

国内网络环境下，如果 `git clone` 较慢，也可以下载 main 分支 zip 后解压：

```text
https://codeload.github.com/ArkMowers/arknights-mower/zip/refs/heads/main
```

## 准备 MAA

容器启动脚本会在 `/MAA` 目录为空时尝试自动下载并解压最新版 MAA。

如果自动下载失败，或希望固定 MAA 版本，可以手动从 MAA Releases 下载对应 Linux 架构的 tar.gz 包，并解压到 `docker/maa/`：

```bash
cd arknights-mower/docker
mkdir -p maa
# 将下载好的 MAA Linux tar.gz 放到当前目录，例如 MAA-linux-x86_64.tar.gz
tar -xzf MAA-linux-*.tar.gz -C maa
```

## 使用默认 docker-compose.yml

仓库内已提供 `docker/docker-compose.yml`，适合通过端口映射访问 WebUI，并按需配置 ADB、MAA 与数据目录。

```bash
cd arknights-mower/docker
docker compose up -d
```

启动后可访问：

```text
http://127.0.0.1:58000?token=mower
http://局域网IP:58000?token=mower
```

## 真机 USB 连接示例

如果需要在容器中直接使用主机上的 USB 设备，可使用 host 网络并挂载 USB 设备与 ADB key。下面是一个可参考的 compose 示例：

```yaml
name: arknights-mower

services:
  mower:
    build:
      context: ..
      dockerfile: docker/Dockerfile
      # 如构建时需要代理，可按需开启：
      # args:
      #   HTTP_PROXY: http://proxy:port
      #   HTTPS_PROXY: http://proxy:port
      #   http_proxy: http://proxy:port
      #   https_proxy: http://proxy:port
    image: arknights-mower:latest
    container_name: arknights-mower
    restart: unless-stopped
    network_mode: host
    privileged: true
    environment:
      MOWER_TOKEN: mower
      MOWER_PORT: "58000"
      TZ: Asia/Shanghai
      # 如运行时需要代理，可按需开启：
      # HTTP_PROXY: http://proxy:port
      # HTTPS_PROXY: http://proxy:port
      # NO_PROXY: 127.0.0.1,localhost,::1
      # no_proxy: 127.0.0.1,localhost,::1
    volumes:
      - /dev/bus/usb:/dev/bus/usb
      - ${HOME}/.android:/root/.android
      - ./mower-data:/mower-data
      - ./maa:/MAA
```

说明：

- `network_mode: host` 适合需要直接访问主机网络、主机 ADB 服务或局域网设备的部署方式。
- `privileged: true` 与 `/dev/bus/usb` 挂载主要用于容器内直接访问 USB 设备；如果只连接远程 ADB 或模拟器，可以不启用。
- `${HOME}/.android:/root/.android` 用于复用主机侧 ADB 授权密钥；如果使用 `sudo` 运行 Docker，请注意 `${HOME}` 可能指向 root 的家目录。
- `./mower-data:/mower-data` 用于持久化配置与运行数据。
- `./maa:/MAA` 用于保存 MAA 文件，避免每次重建镜像后重复下载。

## 构建并启动

如果 compose 中使用 `build`，可执行：

```bash
cd arknights-mower/docker
docker compose build mower
docker compose up -d mower
```

如果只使用已构建好的本地镜像，可直接启动：

```bash
cd arknights-mower/docker
docker compose up -d mower
```

## 升级

升级前可以先备份数据目录：

```bash
cd arknights-mower/docker
cp -a mower-data mower-data.bak-$(date +%Y%m%d)
```

拉取新代码并重建：

```bash
cd arknights-mower
git pull origin main
cd docker
docker compose build --pull=false mower
docker compose up -d mower
```

`mower-data` 通过 volume 挂载，通常升级镜像不会丢失配置与计划数据。

## 常见排错

### 不认 USB 设备

先在主机检查：

```bash
lsusb
adb devices
```

`adb devices` 中设备状态应为 `device`，不能是 `unauthorized` 或 `offline`。如果是 `unauthorized`，需要在手机上确认允许 USB 调试，并确认 `.android/adbkey` 已存在。

### 容器反复重启

查看日志：

```bash
docker logs arknights-mower --tail 100
```

常见原因包括 MAA 下载失败、代理不通、配置文件异常等。

### 配置了代理但健康检查失败

健康检查访问的是容器本机的 `127.0.0.1`，如果代理环境变量影响了本地访问，可以添加：

```yaml
NO_PROXY: 127.0.0.1,localhost,::1
no_proxy: 127.0.0.1,localhost,::1
```
