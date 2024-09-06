FROM ubuntu:22.04 AS ubuntu-base

# 设置环境变量以避免tzdata的交互式提示
ENV DEBIAN_FRONTEND noninteractive

# 安装必要的系统库
RUN apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.8 python3.8-venv python3.8-tk python3.8-dev python3-pip \
        build-essential libgirepository1.0-dev gcc libcairo2-dev pkg-config libzbar0 adb git \
        libgtk-3-dev gir1.2-webkit2-4.1 gir1.2-appindicator3-0.1 gobject-introspection tk8.6 \
        xvfb \
		dbus \
    && rm -rf /var/lib/apt/lists/*



# 使用官方Node.js 18镜像作为基础镜像构建前端
FROM node:18 AS node-base
WORKDIR /app/ui

# 安装前端依赖并构建
COPY ui/package*.json ./
COPY ui/. .
RUN npm ci
RUN npm run build --no-update-notifier



# 合并阶段，使用Python环境为基础，将构建好的前端加入
FROM ubuntu-base AS final
WORKDIR /app
COPY --from=node-base /app/ui/dist ./ui/dist
COPY . .


# 设置Python虚拟环境并安装依赖
RUN python3.8 -m venv venv

RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

RUN . venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt && pip install pycairo PyGObject

# 运行应用
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]