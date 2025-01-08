FROM ubuntu:22.04 AS ubuntu-base

# 设置环境变量以避免tzdata的交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# 安装系统依赖和 Python 3.12
RUN apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.12 python3.12-venv python3.12-tk python3.12-dev python3-pip \
        build-essential libgirepository1.0-dev gcc libcairo2-dev pkg-config libzbar0 adb git \
        libgtk-3-dev gir1.2-webkit2-4.1 gir1.2-appindicator3-0.1 gobject-introspection tk8.6 \
        xvfb dbus && \
    rm -rf /var/lib/apt/lists/*

# 设置 Python 3.12 为默认 Python 版本
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 && \
    update-alternatives --set python3 /usr/bin/python3.12 && \
    update-alternatives --set python /usr/bin/python3.12


# 使用官方Node.js 18镜像作为基础镜像构建前端
FROM node:18 AS node-base
WORKDIR /app/ui

# 安装前端依赖并构建
COPY ui/package*.json ./
COPY ui/. .

RUN npm config set registry https://registry.npmmirror.com
RUN npm ci --verbose
RUN npm run build --no-update-notifier

FROM ubuntu-base AS final
WORKDIR /app
COPY --from=node-base /app/ui/dist ./ui/dist
COPY . .


# 设置pip国内镜像源
RUN python3.12 -m ensurepip --upgrade
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
# 设置 Python 虚拟环境并安装依赖
RUN python3.12 -m venv venv && \
    . venv/bin/activate && \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install pycairo PyGObject
	
# 运行应用
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
