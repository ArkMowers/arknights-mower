#!/usr/bin/env bash
set -euo pipefail

PORT="${MOWER_PORT:-58000}"
HTTP_PROXY="${HTTP_PROXY:-}"
MAA_DIR="/MAA"
DATA_DIR="/mower-data"
ADB_BIN="${MOWER_ADB_BIN:-/usr/bin/adb}"
SIMULATOR_FOLDER="/simulator"
ARCH="$(uname -m)"

if [ "${1:-}" = "--credential-recovery" ]; then
  export MOWER_DATA_DIR="${DATA_DIR}"
  export XDG_DATA_HOME="${XDG_DATA_HOME:-${DATA_DIR}/.local/share}"
  shift
  exec python -m arknights_mower.utils.credential_recovery "$@"
fi

## 代理环境变量
if [ -n "${HTTP_PROXY}" ]; then
  echo ""
  echo "🌐 检测代理连通性..."
  if curl -s --connect-timeout 3 --proxy "${HTTP_PROXY}" http://httpbin.org/ip >/dev/null 2>&1; then
    echo "✅ 代理连接正常"
    export HTTP_PROXY="${HTTP_PROXY}"
  elif curl -s --connect-timeout 3 http://httpbin.org/ip >/dev/null 2>&1; then
    echo "⚠️  代理不可达，将尝试直连"
    unset HTTP_PROXY
  else
    echo "❌ 网络连接异常, 建议检查网络或代理设置"
  fi
  echo ""
else
  echo ""
  echo "ℹ️ 未配置代理环境变量"
  echo ""
fi

mkdir -p "${DATA_DIR}"
export MOWER_DATA_DIR="${DATA_DIR}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-${DATA_DIR}/.local/share}"
export MOWER_REQUIRE_WEB_TOKEN=1

# 检测ADB路径
if [ ! -x "${ADB_BIN}" ]; then
  if command -v "${ADB_BIN}" >/dev/null 2>&1; then
    ADB_BIN="$(command -v "${ADB_BIN}")"
  elif command -v adb >/dev/null 2>&1; then
    ADB_BIN="$(command -v adb)"
  fi
fi

echo "📂 数据目录: ${DATA_DIR}"
echo "🛠️ 使用的ADB: ${ADB_BIN}"
echo "🎮 模拟器目录: ${SIMULATOR_FOLDER}"

# 如果MAA目录不存在或为空，则下载并解压最新版本
echo "🔍 检查MAA目录是否存在或为空..."
if [ ! -d "${MAA_DIR}" ] || [ -z "$(ls -A "${MAA_DIR}" 2>/dev/null)" ]; then
  echo "⬇️ 下载并安装最新版本的MAA..."
  url=$(curl -s https://api.github.com/repos/MaaAssistantArknights/MaaAssistantArknights/releases/latest \
    | jq -r --arg arch "${ARCH}" '.assets[] | select(.name | contains("linux") and contains($arch) and contains("tar")) | .browser_download_url' \
    | head -n 1)
  if [ -z "${url}" ]; then
    echo "❌ 无法找到MAA下载链接" >&2
    exit 1
  fi
  tmp_tar="/tmp/maa.tar.gz"
  curl -L -o "${tmp_tar}" "${url}"
  mkdir -p "${MAA_DIR}"
  tar -xzf "${tmp_tar}" -C "${MAA_DIR}"
  rm -f "${tmp_tar}"
  echo "✅ MAA已安装到${MAA_DIR}"
fi
echo ""

# 配置Mower
MOWER_PORT="${PORT}" MOWER_ADB_BIN="${ADB_BIN}" MOWER_MAA_DIR="${MAA_DIR}" \
  MOWER_SIMULATOR_FOLDER="${SIMULATOR_FOLDER}" python - <<'PY'
import os
import secrets
import sys

from arknights_mower.utils.credential_store import CredentialStoreError

try:
    from arknights_mower.utils import config
    from arknights_mower.utils.config_profiles import migrate_legacy_profiles

    migrate_legacy_profiles()
except CredentialStoreError:
    print(
        "凭据无法读取，原文件已保留。请停止容器后，用同一数据卷启动恢复入口："
        "python -m arknights_mower.utils.credential_recovery。"
        "恢复后关闭恢复服务，再重新启动 Mower。",
        file=sys.stderr,
    )
    raise SystemExit(78)

config.conf.maa_path = os.environ["MOWER_MAA_DIR"]
config.conf.maa_adb_path = os.environ["MOWER_ADB_BIN"]
config.conf.simulator = config.conf.simulator.model_copy(
    update={"simulator_folder": os.environ["MOWER_SIMULATOR_FOLDER"]}
)
webview = config.conf.webview
config.conf.webview = webview.model_copy(
    update={
        "token": webview.token or (
            os.environ.get("MOWER_TOKEN")
            if "token" not in webview.model_fields_set else ""
        ) or secrets.token_urlsafe(),
        "port": int(os.environ["MOWER_PORT"]),
        "tray": False,
    }
)
config.save_conf()
PY

echo "🚀 启动Mower服务, 端口: ${PORT}"
exec python -m flask --app server:app run --host=0.0.0.0 --port="${PORT}"
