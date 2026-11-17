#!/bin/bash

if [ "${1:-}" = "--credential-recovery" ]; then
  export XDG_DATA_HOME="${XDG_DATA_HOME:-/mower-data/.local/share}"
  shift
  exec /mower/mower --credential-recovery "$@"
fi

# 下载最新版MAA
curl -L -O $(curl -s https://api.github.com/repos/MaaAssistantArknights/MaaAssistantArknights/releases/latest | \
    jq -r ".assets[] | select(.name | contains(\"linux\") and contains(\"$(uname -m)\") and contains(\"tar\")) | .browser_download_url")

# 解压下载的文件
mkdir /MAA
tar -zxvf MAA-*.tar.gz -C /MAA
rm MAA-*.tar.gz

# 配置MAA路径
export XDG_DATA_HOME="${XDG_DATA_HOME:-/mower-data/.local/share}"
export MOWER_REQUIRE_WEB_TOKEN=1
sed -i 's|D:\\\\MAA-v4.13.0-win-x64|/MAA|g' /mower/_internal/arknights_mower/utils/config/conf.py
# 配置adb路径
sed -i 's|D:\\\\Program Files\\\\Nox\\\\bin\\\\adb.exe|adb|g' /mower/_internal/arknights_mower/utils/config/conf.py
export MOWER_WEBVIEW_TOKEN="${MOWER_WEBVIEW_TOKEN:-${MOWER_TOKEN:-$(cat /proc/sys/kernel/random/uuid)}}"

# 启动mower应用
echo "Mower 启动后在 http://127.0.0.1:58000 提供访问，请使用 Web UI Token"
exec /mower/mower
