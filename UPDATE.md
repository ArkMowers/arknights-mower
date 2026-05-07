# arknights-mower 自动更新系统设计

## 当前问题

- 用户手动下载新版本 ZIP / 用 `git pull`
- 无版本检测
- 无增量更新
- 资源文件和代码打包在一起，更新要全量替换
- 手机端没有分发渠道

---

## 目标

1. **资源文件** (resources/*.png, models/*.onnx) 和 **代码** 分离
2. **资源文件** 可以增量热更新（不重启 APP）
3. **代码** 自动下载 + 下次重启生效
4. **多平台** 分发 (PC/Android)

---

## 架构

```
┌──────────────────────────────────────────────┐
│                 用户设备                        │
│                                                │
│  app/                                          │
│  ├── code/          ← 可执行代码 (下次重启生效)    │
│  ├── data/                                     │
│  │   ├── resources/  ← 游戏模板图片               │
│  │   ├── models/     ← 识别模型文件               │
│  │   └── config/     ← 用户配置                   │
│  └── tmp/           ← 运行时数据 (DB, 截图)        │
│                                                │
│  App Entry: 先检测 update → 下载新资源 → 启动    │
└──────────────────────────────────────────────────┘
```

## 更新协议 (HTTP/JSON)

### 版本检查请求

```http
GET https://update.arkmowers.com/v1/check

Response 200:
{
    "product": "arknights-mower",
    "current_version": "4.1.6",
    "platform": "windows" | "android",
    "server": "CN"
}
```

### 版本检查响应

```json
{
    "code": 0,
    "data": {
        "latest_code_version": "4.2.0",
        "latest_resource_version": 42,
        "update_available": true,
        "release_notes": "4.2.0 changelog...",
        "download_url": "https://update.arkmowers.com/v1/download/4.2.0/windows",
        "resources_diff_url": "https://update.arkmowers.com/v1/resources/diff/41/42?server=CN"
    }
}
```

## 更新流程

```
启动时:
  1. app_updater.check() → 比较版本号
  2. if 新版本:
       download_code_package()   → 下载 zip 到 app/update/
       verify_hash()
       replace app/code/          → 下次启动生效 (用 app/code.new/)
  3. if 资源有新版本:
       download_resources_diff() → 下载 diff zip
       ResourceManager.reload()  → 立即生效 (不重启)
  4. 正常启动

运行时 (定期轮询 or 用户手动):
  5. ResourceManager.check_update() → 只检查资源版本
  6. if 资源更新:
       download + reload

手机端:
  7. 同上流程, 下载的 zip 解压到 app 内部存储
  8. 通过 Chaquopy 的资源管理接口读取
```

## 代码分发

```
服务端打包:
  arknights-mower-v4.2.0-windows.zip
  ├── arknights_mower/
  │   ├── __init__.py
  │   ├── scheduler/
  │   ├── solvers/
  │   ├── utils/
  │   ├── services/
  │   └── ...
  ├── requirements.txt
  └── checksum.sha256

客户端下载后:
  app/
  ├── code/               ← 旧版本 (当前运行)
  └── code.new/           ← 新版本 (刚下载)
  
  重启时:
  删除 code/, code.new/ 重命名为 code/
```

## 资源热更新

资源文件增量 diff，不重新下载全量：

```
服务端维护:
  resources/v42/CN/
  resources/v42/US/
  resources/v41/CN/
  resources/v41/US/

diff 算法:
  比较 v41 → v42，只变动的文件打包成 zip
  resources-diff-41-to-42-CN.zip
  ├── infra/arrange/confirm_blue.png
  └── recruit/tag_资深干员.png

客户端:
  ResourceManager.load("infra/arrange/confirm_blue")
  1. 检查 app/data/resources/CN/infra/arrange/confirm_blue.png
  2. 不存在? 检查 app/data/resources/CN/.hot/ (热更新缓存)
  3. 再不存在? 回退到 app/code/resources/default_CN/
```

## 回滚

- 更新前备份 `app/code/` → `app/code.bak/`
- 如果新版本启动失败 (崩溃 / 退出码非零)，自动回滚
- 回滚后上报 crash log

## 手机端差异

| 阶段 | PC | Android |
|---|---|---|
| 下载 | HTTP 下载 zip | 同 |
| 解压 | zipfile | 同 |
| 代码替换 | 替换 `app/code/` 目录 | 替换内部存储目录 |
| 资源加载 | `cv2.imread` 文件 | `ResourceManager` 从文件或 AssetManager |
| 下次生效 | 重启进程 | `System.exit(0)` + 重新打开 Activity |

## 更新模块

```python
# services/updater.py

class Updater:
    def check(self) -> UpdateInfo: ...
    def download_code(self, info: UpdateInfo) -> Path: ...
    def download_resources(self, info: UpdateInfo, locale: str) -> Path: ...
    def apply_code(self, zip_path: Path) -> bool: ...
    def apply_resources(self, zip_path: Path) -> list[str]: ...
    def rollback(self) -> None: ...

class UpdateCheckHook(LifecycleHook):
    """注册到 MainLoop 的 hooks 链, 定期检查更新"""
    def should_run(self, state) -> bool: ...
    def execute(self, state, remaining) -> float: ...
```
