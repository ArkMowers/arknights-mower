# 源码部署的 OCR 依赖迁移

本文用于把已有源码环境迁移到 `rapidocr==3.10.0`、PP-OCRv6 tiny 和 `opencv-python-headless`。首次部署直接按 [README 的源码部署步骤](../../README.md#源码部署)安装即可。

源码更新在需要改变依赖时，会为项目内自有且已有 pip 的普通虚拟环境保留副本并重建，不会保留原虚拟环境中的旧包；继承系统包的环境仍须完成下文检查。外部、共享或其他原地安装的环境只安装目标依赖，不自动移除旧发行包。`rapidocr-onnxruntime` 的依赖声明仍要求完整版 OpenCV；各 OpenCV 发行包又共用 `cv2`，直接叠加新包可能留下依赖冲突或混合文件。更新器使用发起更新时复制的旧版程序，目标提交中的改动不能替换正在执行的更新器。安装与恢复边界见 [Arknights Mower 软件更新子系统说明](../subsystems/software-update.md#source-dependency-environments)。

## 1. 优先创建独立环境

1. 记录当前源码提交，保留旧 Python 环境和用户数据。退出同一安装目录下的全部实例及多开管理器，确认相关 Mower 和共享 OCR 进程已经退出，再切换到目标源码；前端构建仍按 README 执行。
2. 按 README 的对应平台步骤创建一个新环境，例如 `.venv-ocr`，将命令中的 `.venv` 全部换为新名称，再安装依赖。需要使用系统 PyGObject 时，保留 README 要求的 `--system-site-packages` 设置。不要在共享环境中直接卸载其他程序正在使用的包。
3. 使用新环境的解释器完成下文检查，通过后再启动 Mower。启动命令始终指向新环境；保留旧环境直到确认更新可用。

## 2. 必须沿用原解释器时

先退出所有使用该环境的程序并备份环境，确认该解释器确实由自己维护。以下命令在目标源码根目录执行，`python` 必须替换成启动 Mower 的解释器路径；Windows 常见路径为 `.\.venv\Scripts\python.exe`，Linux/macOS 常见路径为 `./.venv/bin/python`。

```bash
python -m pip uninstall -y rapidocr-onnxruntime opencv-python opencv-python-headless opencv-contrib-python opencv-contrib-python-headless
python -m pip install -r requirements.in
```

必须先移除全部 OpenCV 发行包，再重新安装。只卸载完整版而保留已安装的 headless 版，可能删除两者共用的 `cv2` 文件；之后普通安装又可能因 headless 版本已满足要求而跳过修复。卸载时未安装的包会被跳过。

如果该解释器没有 pip，可使用现有 uv 执行相同操作，并把 `<解释器路径>` 换为启动 Mower 的解释器：

```bash
uv pip uninstall --python <解释器路径> rapidocr-onnxruntime opencv-python opencv-python-headless opencv-contrib-python opencv-contrib-python-headless
uv pip install --python <解释器路径> -r requirements.in
```

## 3. 安装后检查与恢复

仍使用实际启动 Mower 的解释器执行：

```bash
python -m pip check
python -c "import importlib.metadata as m; names=sorted(d.metadata['Name'].lower().replace('_','-') for d in m.distributions() if d.metadata.get('Name','').lower().replace('_','-') in {'opencv-python','opencv-python-headless','opencv-contrib-python','opencv-contrib-python-headless'}); print(names); assert names == ['opencv-python-headless']; import cv2; print(cv2.__version__)"
```

无 pip 环境将第一条换为 `uv pip check --python <解释器路径>`。检查应同时确认依赖没有冲突、只发现 `opencv-python-headless`，并且 `cv2` 可以导入。如果检测到虚拟环境继承的系统 OpenCV，不要删除共享系统包；改用隔离环境，并按 README 安装所需窗口依赖。新源码自带 tiny 模型；正常 OCR 初始化不需要在线下载模型。

任一步失败时先处理安装错误，再启动 Mower。需要回退时，恢复记录的源码提交和旧环境，并恢复与该提交对应的前端。若原环境已经原地修改，仅回退源码不会恢复已卸载的包；应从备份恢复环境，或为旧提交重新创建环境并安装它的依赖。软件更新器对原地环境的依赖恢复是重新安装旧清单，不能保证共享环境与操作前完全相同。上述操作不迁移配置、数据库或 `saved_state`，保留旧环境也不保证旧源码能读取新版本已经写入的数据。
