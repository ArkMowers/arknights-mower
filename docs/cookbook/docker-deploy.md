# Docker 部署

本文使用仓库的 [服务端 Dockerfile](../../docker/Dockerfile) 和 [入口脚本](../../docker/entrypoint.sh)，介绍在 Linux 上构建、运行容器并通过浏览器访问 Mower 的步骤。

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

`maa/` 保存 MAA，`mower-data/` 保存 Mower 数据。入口脚本默认将 `XDG_DATA_HOME` 设置为
`/mower-data/.local/share`，使本机加密密钥随同一数据卷保留。保留这两个目录的完整内容，
包括 `mower-data/` 下的隐藏目录，即可在重建容器时继续使用已有文件。若自行覆盖 `XDG_DATA_HOME`，也需持久化其对应目录。

`MOWER_TOKEN` 用于首次设置访问令牌。已有非空令牌时，容器始终沿用数据目录中保存的值，
不会用旧的启动参数覆盖页面保存的新值。首次启动省略该参数时，程序会生成一个令牌。
令牌加密保存在 `mower.secrets.json`，不能再通过文本编辑器查看。首次部署请按示例设置自己保管的令牌，
并用它打开页面。

容器通常没有桌面系统凭据库，Mower 首次保存时会创建仅当前用户可读的固定混合私钥。
它位于挂载目录的 `.local/share/arknights-mower/credentials/private.key`，不属于缓存，
也不随界面的完整备份导出。请保留该文件及其目录权限；删除它后，已有密文无法解密，程序会报错并保留原文件。
如部署已有独立密钥管理方式，可只读挂载有效的混合私钥文件，再用 `MOWER_CREDENTIAL_KEY_FILE` 指定容器内的绝对路径；
文件内容为 96 字节混合私钥的 base64 编码，其中包含 64 字节 ML-KEM-768 种子和 32 字节 X25519 私钥。
文件须属于运行 Mower 的用户，权限设为 `0600`。
后续保存复用该私钥，不会因为修改密码而更换它；每次加密仍产生不同密文。
本功能从已有明文配置直接迁移，没有旧加密格式的升级流程。密钥丢失时可使用下文的独立恢复入口，
换机时可重新填写凭据，或导入此前单独导出的口令凭据备份。
详细规则见[配置备份子系统说明](../subsystems/config-backup.md#configuration-credential-storage)。
自行构建镜像时，依赖与后端能力检查见[凭据加密运行库](packaging.md#credential-encryption-runtime)。

host 网络模式不使用 `-p` 映射，`MOWER_PORT` 对应宿主监听端口。需要桥接网络时，可参考 [Compose 配置](../../docker/docker-compose.yml) 中的端口及数据卷映射；此时容器的 `127.0.0.1` 不再代表宿主，应按实际网络填写设备地址。Compose 文件内的相对数据卷路径以 `docker/` 目录为基准。

## 4. 验证与配置

1. 查看容器状态及启动日志：

   ```bash
   docker ps --filter name=arknights-mower
   docker logs --tail 100 arknights-mower
   ```

2. 等待 MAA 准备和服务启动完成，浏览器打开 `http://127.0.0.1:58000?token=replace-with-your-token`，令牌与启动参数保持一致。局域网访问时将地址换为宿主 IP。
3. 在任务配置的“连接与启动”中选择目标设备并测试连接，再配置排班与任务。入口脚本设置 MAA 目录和容器内 ADB 路径，具体设备地址仍需按环境填写。

登录后可在 **全部设置 → 网络与更新 → 访问端口与 Token** 查看或修改访问令牌。
保存后当前页面仍使用原令牌，新令牌在 Mower 重新启动后生效；容器重新创建时也保留已保存的值。
容器允许远程连接，保存空令牌时会提示「此部署允许远程访问，访问令牌不能为空。」。
旧配置中保存的空令牌会在容器启动时替换为随机令牌，不会以空令牌开放远程访问。

容器内使用 `/usr/bin/adb`，数据根目录为 `/mower-data`；浏览器入口不需要安装 GTK/WebKit2。自定义 ADB 可通过数据卷挂载，再用 `MOWER_ADB_BIN` 指定容器内路径。下载需要代理时，可通过 `HTTP_PROXY` 配置入口脚本使用的代理；实际网络设置也可在 Mower 页面调整。

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

重新执行第 3 节的 `docker run` 后，按第 4 节验证启动和数据。Docker 的程序更新由镜像重建管理，不要把桌面程序的内置更新当作镜像更新；说明见 [多实例与外部服务管理边界](../../doc/software-update.md#多实例失败恢复与首次启用)。

## 6. 私钥丢失后的凭据恢复

正常重建容器会继续使用数据卷中的私钥；普通缓存清理不会删除它。密钥文件被误删或损坏，
导致容器无法启动时，先停止原容器，再用相同镜像和数据卷运行独立恢复入口：

```bash
docker stop arknights-mower
docker run --rm -it \
  -p 127.0.0.1:58001:58001 \
  -v "$(pwd)/mower-data:/mower-data" \
  arknights-mower:latest \
  --credential-recovery --host 0.0.0.0 --port 58001
```

上例适用于本指南的服务镜像，数据卷路径须改成原容器实际使用的路径。
若原部署覆盖了 `XDG_DATA_HOME` 或指定外部密钥文件，还需沿用相同环境变量及挂载；
程序不会替换外部指定的密钥文件。这里将宿主端口只绑定到 `127.0.0.1`，
按终端显示的临时入口在宿主浏览器中访问；远程服务器可通过 SSH 端口转发访问。

先检查页面列出的不可读凭据，确实无法恢复原私钥时再输入确认文字执行重置。
排班、普通配置和数据库保留，无法读取的旧密文另存至 `credential-recovery`。
点击「关闭恢复服务」退出临时容器，再启动正常容器并按提示设置访问 Token。
随后重新填写凭据，或在设置页导入此前的口令凭据备份。恢复旧密文仍需要原私钥。
详细范围见[凭据备份与恢复操作说明](../../doc/config-backup.md#可选的口令凭据备份)。

在线参考：[Arknights-Mower 文档 — Docker 部署](https://arkmowers.github.io/arknights-mower/manual/docker-deploy/)。
