FROM python:3.12-slim AS base
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

RUN apt-get update && apt-get install -y --no-install-recommends \
    adb curl jq ca-certificates tar \
    libzbar0 libglib2.0-0 libgomp1 libatomic1 tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 构建 webui
FROM node:20-bookworm-slim AS ui-builder
WORKDIR /app/ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ .
RUN npm run build

# 构建 Python 虚拟环境
FROM base AS python-deps
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

RUN apt-get update && apt-get install -y --no-install-recommends build-essential binutils && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements.in ./
COPY docker/gen_server_requirements.py ./gen_server_requirements.py
RUN python gen_server_requirements.py requirements.txt requirements-server.txt \
    && uv venv /opt/venv --python /usr/local/bin/python3.12 \
    && uv pip install --python /opt/venv/bin/python --no-cache-dir --no-compile setuptools wheel \
    && uv pip install --python /opt/venv/bin/python --no-cache-dir --no-compile --no-deps -r requirements-server.txt \
    && find /opt/venv -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && find /opt/venv -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete \
    && find /opt/venv -type f -name '*.so' -exec strip --strip-unneeded {} + || true

# 构建运行时镜像
FROM base AS runtime
ENV PATH="/opt/venv/bin:${PATH}"
WORKDIR /app

COPY --from=python-deps /opt/venv /opt/venv
COPY --from=ui-builder /app/ui/dist ui/dist

COPY arknights_mower ./arknights_mower
COPY server.py webview_ui.py manager.py ./
COPY requirements.txt requirements.in ./
COPY docker/entrypoint.sh /usr/local/bin/mower-entrypoint.sh

RUN chmod +x /usr/local/bin/mower-entrypoint.sh

HEALTHCHECK --interval=10s --timeout=3s --retries=12 \
    CMD curl -fs "http://127.0.0.1:${MOWER_PORT:-58000}/status" || exit 1
ENTRYPOINT ["mower-entrypoint.sh"]
