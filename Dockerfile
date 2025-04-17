FROM ubuntu:22.04 AS ubuntu-base
# 部署教程参考https://www.cnblogs.com/frinda/p/18702822
# 设置环境变量以避免tzdata的交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# 替换APT源为阿里云镜像源，提高下载速度，安装系统依赖和 Python 3.12
RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|https://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com/ubuntu|https://mirrors.aliyun.com/ubuntu|g' /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.12 python3.12-venv python3.12-tk python3.12-dev python3-pip \
                       build-essential libgirepository1.0-dev gcc libcairo2-dev fish nano wget pkg-config libzbar0 adb git \
                       libgtk-3-dev gir1.2-webkit2-4.1 gir1.2-appindicator3-0.1 gobject-introspection tk8.6 \
                       xvfb dbus && \
    rm -rf /var/lib/apt/lists/*

# 设置 Python 3.12 为默认 Python 版本
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 && \
    update-alternatives --set python3 /usr/bin/python3.12 && \
    update-alternatives --set python /usr/bin/python3.12

# 使用官方 Node.js 18 镜像作为基础镜像构建前端
FROM node:18 AS node-base
WORKDIR /app/ui

# 安装前端依赖并构建
COPY ui/package*.json ./ 
COPY ui/. .

RUN npm config set registry https://registry.npmmirror.com && \
    npm ci --verbose && \
    npm run build --no-update-notifier

# 将 Ubuntu 基础镜像作为最终运行镜像
FROM ubuntu-base AS final
WORKDIR /app

# 复制前端构建产出
COPY --from=node-base /app/ui/dist ./ui/dist
COPY . .

# 设置 pip 国内镜像源
RUN python3.12 -m ensurepip --upgrade && \
    pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

# 设置 Python 虚拟环境并安装依赖
RUN python3.12 -m venv venv && \
    . venv/bin/activate && \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install pycairo PyGObject

# 运行应用
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
