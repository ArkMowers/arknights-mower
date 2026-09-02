FROM ubuntu:24.10 AS ubuntu-base
# 设置环境变量以避免tzdata的交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# 换源以使用国内镜像加速
RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|https://mirrors.tuna.tsinghua.edu.cn/ubuntu/|g' /etc/apt/sources.list.d/ubuntu.sources
RUN echo 'Acquire::https::Verify-Peer "false";' > /etc/apt/apt.conf.d/99disable-peer-verification

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y python3 python3-pip python3-venv adb curl jq ca-certificates libzbar0 libgl1 libglib2.0-0 && \
    rm -rf /var/lib/apt/lists/* && \
    rm /etc/apt/apt.conf.d/99disable-peer-verification

# 设置默认语言环境
ENV LANG=C.UTF-8

# 使用官方 Node.js 20 镜像作为基础镜像构建前端
FROM node:20 AS node-base
ENV LANG=C.UTF-8
WORKDIR /arknights-mower/ui
COPY ui/ ./
# 安装前端依赖
RUN npm install
# 构建前端应用
RUN npm run build

# 使用 Ubuntu 基础镜像
FROM ubuntu-base AS final

# 设置工作目录
WORKDIR /arknights-mower
COPY . .
COPY --from=node-base /arknights-mower/ui/dist ./ui/dist

# 安装 Python 依赖
RUN python3 -m venv venv && \
    . venv/bin/activate && \
    pip install -r requirements.in && \
    pip install pyinstaller && \
    pyinstaller webui_zip_for_linux.spec && \
    deactivate

RUN mv dist/mower /mower
COPY ./entrypoint.sh /
WORKDIR /mower
RUN rm -rf /arknights-mower

ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]

