#!/bin/bash

# 下载最新版MAA
curl -L -O $(curl -s https://api.github.com/repos/MaaAssistantArknights/MaaAssistantArknights/releases/latest | \
    jq -r ".assets[] | select(.name | contains(\"linux\") and contains(\"$(uname -m)\") and contains(\"tar\")) | .browser_download_url")

# 解压下载的文件
mkdir /MAA
tar -zxvf MAA-*.tar.gz -C /MAA
rm MAA-*.tar.gz

# 配置MAA路径
sed -i 's|D:\\\\MAA-v4.13.0-win-x64|/MAA|g' /mower/_internal/arknights_mower/utils/config/conf.py
# 配置adb路径
sed -i 's|D:\\\\Program Files\\\\Nox\\\\bin\\\\adb.exe|adb|g' /mower/_internal/arknights_mower/utils/config/conf.py
# 配置mower固定端口58000，访问时请使用http://127.0.0.1:58000?token=mower
sed -i 's|token: str = \"\"|token: str = \"mower\"|g' /mower/_internal/arknights_mower/utils/config/conf.py

# 启动mower应用
echo "Mower已启动！请浏览器访问http://127.0.0.1:58000?token=mower进入Mower界面"
/mower/mower