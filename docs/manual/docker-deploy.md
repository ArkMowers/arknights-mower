# Docker 部署

本文使用仓库的 [服务端 Dockerfile](https://github.com/ArkMowers/arknights-mower/blob/alpha/docker/Dockerfile) 和 [入口脚本](https://github.com/ArkMowers/arknights-mower/blob/alpha/docker/entrypoint.sh)，介绍在 Linux 上构建、运行容器并通过浏览器访问 Mower 的步骤。

## 1. 准备环境与源码

安装并启动 Docker Engine，确认 `docker version` 可以连接服务端。随后获取源码：

```bash
git clone --branch alpha https://github.com/ArkMowers/arknights-mower.git
cd arknights-mower
```

本地构建需要可以下载基础镜像、前端及 Python 依赖。容器首次启动时，如果 MAA 目录为空，入口脚本会从 MAA 官方 Release 下载与容器架构对应的版本。

## 2. 构建镜像

在仓库根目录执行，以根目录作为构建上下文：

```bash
docker build -f docker/Dockerfile -t arknights-mower:latest .
```

镜像构建前端和 Python 服务端，不需要宿主预先安装 Python 或 Node.js。这里指定 `docker/Dockerfile`，与根目录中通过 PyInstaller 构建的另一套 Dockerfile 区分。

## 3. 启动容器

创建持久化目录并启动。示例使用 Linux host 网络，让容器内的 ADB 可以访问宿主上的设备端口；请替换访问令牌：

```bash
mkdir -p maa mower-data
docker run -d \
    --name arknights-mower \
    --network host \
    --restart unless-stopped \
    -e TZ=Asia/Shanghai \
    -e MOWER_PORT=58000 \
    -e MOWER_TOKEN=replace-with-your-token \
    -v "$PWD/maa:/MAA" \
    -v "$PWD/mower-data:/mower-data" \
    arknights-mower:latest
```

`maa/` 保存 MAA，`mower-data/` 保存 Mower 数据。保留这两个目录即可在重建容器时继续使用已有文件。

host 网络模式不使用 `-p` 映射，`MOWER_PORT` 对应宿主监听端口。需要桥接网络时，可参考 [Compose 配置](https://github.com/ArkMowers/arknights-mower/blob/alpha/docker/docker-compose.yml) 中的端口及数据卷映射；此时容器的 `127.0.0.1` 不再代表宿主，应按实际网络填写设备地址。Compose 文件内的相对数据卷路径以 `docker/` 目录为基准。

## 4. 验证与配置

1. 查看容器状态及启动日志：

   ```bash
   docker ps --filter name=arknights-mower
   docker logs --tail 100 arknights-mower
   ```

2. 等待 MAA 准备和服务启动完成，浏览器打开 `http://127.0.0.1:58000?token=replace-with-your-token`，令牌与启动参数保持一致。局域网访问时将地址换为宿主 IP。
3. 在 Mower 设置中选择目标设备并测试连接，再配置排班与任务。入口脚本设置 MAA 目录和容器内 ADB 路径，具体设备地址仍需按环境填写。

容器内使用 `/usr/bin/adb`。自定义 ADB 可通过数据卷挂载，再用 `MOWER_ADB_BIN` 指定容器内路径。下载需要代理时，可通过 `HTTP_PROXY` 配置入口脚本使用的代理；实际网络设置也可在 Mower 页面调整。

## 5. 停止与更新

停止、再次启动已有容器：

```bash
docker stop arknights-mower
docker start arknights-mower
```

更新程序时，先在 Mower 中停止自动任务，再停止容器；获取目标源码并重新构建镜像，然后删除旧容器并按上文参数重新创建。数据卷目录不随容器删除。

```bash
docker stop arknights-mower
git pull --ff-only
docker build -f docker/Dockerfile -t arknights-mower:latest .
docker rm arknights-mower
```

重新执行第 3 节的 `docker run` 后，按第 4 节验证启动和数据。Docker 的程序更新由镜像重建管理，见 [多实例与外部服务管理边界](https://github.com/ArkMowers/arknights-mower/blob/alpha/doc/software-update.md#多实例失败恢复与首次启用)。
