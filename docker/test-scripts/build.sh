#!/bin/bash

set -e

echo "==============================================="
echo "测试用镜像构建脚本, 请勿直接运行"
echo "==============================================="

# 代理设置 - Docker 构建时需要使用宿主机网络
# 获取宿主机IP (Linux)
HOST_IP=$(ip route get 1.1.1.1 | awk '{print $7; exit}' 2>/dev/null || echo "host.docker.internal")
export HTTP_PROXY=http://${HOST_IP}:7890
export HTTPS_PROXY=http://${HOST_IP}:7890

DOCKER_USERNAME=${DOCKER_USERNAME:-"well404"}

echo "🌐 使用代理: ${HTTP_PROXY}"

# 检查代理是否可达
echo ""
echo "🔍 检查代理连通性..."
if curl -s --connect-timeout 3 --proxy ${HTTP_PROXY} http://httpbin.org/ip >/dev/null 2>&1; then
    echo "✅ 代理连接正常"
elif curl -s --connect-timeout 3 http://httpbin.org/ip >/dev/null 2>&1; then
    echo "⚠️  代理不可达，将尝试直连"
    export HTTP_PROXY=""
    export HTTPS_PROXY=""
else
    echo "❌ 网络连接异常"
    echo "   建议检查网络或代理设置"
fi
echo ""

# 构建镜像
DATE_CODE="$(date +%d%H%M)"
echo "🏗️  构建镜像... ${FULL_IMAGE}"
docker build -f docker/Dockerfile \
    --build-arg HTTP_PROXY=${HTTP_PROXY} \
    --build-arg HTTPS_PROXY=${HTTPS_PROXY} \
    -t ${DOCKER_USERNAME}/arknights-mower:${DATE_CODE} \
    -t ${DOCKER_USERNAME}/arknights-mower:latest \
    .

echo ""
echo "✅ 镜像构建完成！"
echo ""

echo ""
echo "🚀 测试运行:"
SERVER_PORT=58010
echo "docker run --rm \
    -e MOWER_PORT=${SERVER_PORT} \
    -e MOWER_TOKEN=mowertest \
    -e HTTP_PROXY=${HTTP_PROXY} \
    -e HTTPS_PROXY=${HTTPS_PROXY} \
    -e NO_PROXY=localhost,127.0.0.1 \
    -p ${SERVER_PORT}:${SERVER_PORT} \
    ${DOCKER_USERNAME}/arknights-mower:latest \
    -n arknights-mower-test"
echo ""

echo "🧹 清理无用镜像/缓存 (可选):"
echo "   docker image prune -f            # 移除未被容器使用的悬空镜像"
echo "   docker builder prune -f          # 仅清理未使用的构建缓存"
echo ""

echo "🎉 构建完成！应用镜像已准备就绪"