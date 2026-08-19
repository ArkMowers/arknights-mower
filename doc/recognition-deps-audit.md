# 识别栈依赖移除影响核查

> 核查日期：2026-08-18 ｜ 分支：`feat/recognition-numpy` ｜ 用途：#129「移除 scipy/scikit-learn/scikit-image 运行依赖」的落地输入
> 本文件为只读核查产物，仅收集事实与引用，不做代码修改。
> 替换实现已就位：`arknights_mower/utils/vision_np.py`（纯 numpy + opencv，提供 `argrelmax/argrelmin/ssim/hog/linear_svc_predict/knn1_predict`）。

---

## 1. 直接引用清单

分类：`runtime→vision_np`（运行时代码，需改为 vision_np）｜`runtime-blocker`（运行时代码，但存在阻塞点，见 §5 步骤 1-2）｜`test`（golden 测试，可跳过）｜`training`（模型训练/导出）｜`other`（字符串/构建/元数据，非 import）

| 文件:行 | 用法 | 分类 |
|---|---|---|
| `arknights_mower/solvers/auto_fight.py:4` | `from scipy.signal import argrelmax` | runtime→vision_np |
| `arknights_mower/solvers/auto_fight.py:145` | `argrelmax(result, order=50)[0]` | runtime→vision_np |
| `arknights_mower/solvers/auto_fight.py:5` | `from skimage.metrics import structural_similarity` | runtime→vision_np |
| `arknights_mower/solvers/auto_fight.py:195` | `structural_similarity(img, res)` | runtime→vision_np |
| `arknights_mower/solvers/credit_fight.py:2` | `from scipy.signal import argrelmin` | runtime→vision_np |
| `arknights_mower/solvers/credit_fight.py:33` | `argrelmin(result, order=100)[0]` | runtime→vision_np |
| `arknights_mower/utils/recognize.py:7` | `from skimage.metrics import structural_similarity` | runtime→vision_np |
| `arknights_mower/utils/recognize.py:835` | `structural_similarity(gray, res_img)`（2D uint8，走 vision_np 默认 data_range=255 路径） | runtime→vision_np |
| `arknights_mower/utils/matcher.py:7` | `import sklearn.pipeline` | runtime（仅反序列化 svm.model 需要） |
| `arknights_mower/utils/matcher.py:8` | `import sklearn.preprocessing` | runtime（同上） |
| `arknights_mower/utils/matcher.py:9` | `import sklearn.svm` | runtime（同上） |
| `arknights_mower/utils/matcher.py:10` | `from skimage.metrics import structural_similarity as compare_ssim` | runtime→vision_np |
| `arknights_mower/utils/matcher.py:31-32` | `lzma.open(...models/svm.model)+pickle.loads` → 反序列化为 sklearn `Pipeline(StandardScaler+LinearSVC)` | runtime-blocker |
| `arknights_mower/utils/matcher.py:107` | `SVC.predict([score])[0]` | runtime→vision_np `linear_svc_predict` |
| `arknights_mower/utils/matcher.py:285` | `compare_ssim(query, rect_img, multichannel=True)`（0.23.2 对 2D 忽略 multichannel） | runtime→vision_np `.ssim`（去掉该参数） |
| `arknights_mower/solvers/depotREC.py:11` | `from skimage.feature import hog` | runtime→vision_np |
| `arknights_mower/solvers/depotREC.py:43-51` | `hog(模板, orientations=18, pixels_per_cell=(8,8), cells_per_block=(2,2), block_norm="L2-Hys", transform_sqrt=True, channel_axis=2)` | runtime→vision_np `.hog`（vision_np 固定此参数组） |
| `arknights_mower/solvers/depotREC.py:102-105` | `lzma.open(...CONSUME.pkl/NORMAL.pkl)+pickle.load` → 反序列化为 sklearn `KNeighborsClassifier(k=1, weights='distance')` | runtime-blocker |
| `arknights_mower/solvers/depotREC.py:147` | `模型名称.predict([物品特征])` | runtime→vision_np `knn1_predict` |
| `arknights_mower/tests/vision_np_tests.py:22-27` | scipy try/except 导入 + `HAS_SCIPY` 门控 | test |
| `arknights_mower/tests/vision_np_tests.py:30-35` | skimage try/except 导入 + `HAS_SKIMAGE` 门控 | test |
| `arknights_mower/tests/vision_np_tests.py:37-44` | sklearn try/except 导入 + `HAS_SKLEARN` 门控 | test |
| `arknights_mower/tests/vision_np_tests.py:58-86` | argrelmax/argrelmin 逐位 golden 比对 | test |
| `arknights_mower/tests/vision_np_tests.py:89-129` | SSIM golden（含 `multichannel=True` 形态，行 122） | test |
| `arknights_mower/tests/vision_np_tests.py:132-152` | HOG golden（depotREC 参数组，行 140-148） | test |
| `arknights_mower/tests/vision_np_tests.py:155-196` | LinearSVC/KNN 折叠比对（行 47-54 用 `pickle.loads` 加载真实模型 → 需要 sklearn 反序列化） | test |
| `auto_get_res_new.py:11` | `from skimage.feature import hog` | training |
| `auto_get_res_new.py:12` | `from sklearn.neighbors import KNeighborsClassifier` | training |
| `auto_get_res_new.py:643-651` | HOG 特征提取（训练特征，行 643 `hog(...)`） | training |
| `auto_get_res_new.py:666-671` | `KNeighborsClassifier(weights="distance", n_neighbors=1, n_jobs=-1).fit(...)`（行 670 `.fit`） | training |
| `auto_get_res_new.py:673-675, 681-684` | `lzma.open+pickle.dump` 保存 `NORMAL.pkl`/`CONSUME.pkl`（行 682-683） | training |
| `scripts/fix_runtime_dlls.py:13` | `SKLEARN_DLL = Path("dist/mower/_internal/sklearn/.libs/msvcp140.dll")` | other（build-time，移除 sklearn 后失效） |
| `scripts/fix_runtime_dlls.py:58-69` | sklearn DLL 版本对齐逻辑（`file_version(SKLEARN_DLL)`） | other（build-time） |
| `setup.py:24` | `"scikit_image==0.18.3"`（install_requires，PyPI 发布元数据，`python-publish.yml:31` 使用 setup.py 打包） | other |
| `setup.py:25` | `"scikit_learn>=1"`（install_requires） | other |
| `requirements.in:4-6` | 声明 scipy/scikit-image/scikit-learn | other（待移除） |
| `requirements.txt:255,257,259` + `:89,99,128,284,286` | pinned 版本 + `via scikit-*` 注释 | other（重新 pip-compile 后自动消失） |
| `.github/workflows/format-check-and-test.yml:38,44` | unittest job `pip install -r requirements.txt`（隐式安装 trio） | other（CI） |
| `Dockerfile:39` | `pip install -r requirements.in` | other（随 requirements.in 变化） |
| `docker/Dockerfile:31-36` | 基于 requirements.txt 生成 server 版 + `uv pip install --no-deps` | other（随 requirements.txt 变化） |
| `arknights_mower/utils/vision_np.py:1-3,12-13,24-25,37,117,122` | docstring 提及上游函数名（非 import） | other（保留） |

### 1.1 已核查、确证不存在的引用

以下均全仓（含 `ui/`、`scripts/`、`doc/`、`plan/`、`.github/`）大小写不敏感检索确认**无命中**：

- `scipy.ndimage`（`vision_np.py:37` 注释仅提到 `uniform_filter`，无 import）
- `scipy.signal` 除 auto_fight/credit_fight 之外的用法
- `skimage.io.imread` / `skimage.io.collection`（全仓 `imread` 均为 `cv2.imread`：`auto_get_res_new.py:659`、`poster_cropper.py:283`、`trading_order.py:86`）
- `sklearn.model_selection` / `train_test_split` / `cross_val`
- `sklearn.preprocessing` 在 Pipeline 反序列化之外的直接用法（matcher.py:8 仅保证反序列化 svm.model 可导入）
- `sklearn.neighbors` 除 `auto_get_res_new.py:12`（训练）之外的用法
- `joblib.dump/load`（三个模型的序列化全用 `pickle+lzma`：matcher.py:31-32、depotREC.py:102-105、auto_get_res_new.py:673-675）
- `imageio` / `tifffile` / `lazy_loader` / `threadpoolctl` 的任何直接 import（仅 requirements.txt 命中）
- `ui/` 前端 JS/Vue、`server.py`、`webview_ui.py`、`manager.py`、`dev_tools.py`、`poster_cropper.py` 等 root 脚本

---

## 2. 传递依赖 closure

主证据：本机 `pip show` 实测（2026-08-18，安装版本与 requirements.txt 一致）+ `requirements.txt` 的 `via` 注释一致。

| 包 | 版本 | Requires（pip show 实测） | 归途 |
|---|---|---|---|
| scikit-image | 0.23.2 | imageio, lazy-loader, networkx, numpy, packaging, pillow, scipy, tifffile | **DROP** |
| scikit-learn | 1.4.2 | joblib, numpy, scipy, threadpoolctl | **DROP** |
| scipy | 1.13.0 | numpy | **DROP** |
| imageio | 2.34.2 | （Required-by: scikit-image） | **DROP**（无直接 import） |
| tifffile | 2024.7.2 | （Required-by: scikit-image） | **DROP**（无直接 import） |
| lazy-loader | 0.4 | （Required-by: scikit-image） | **DROP**（无直接 import） |
| joblib | 1.4.2 | （Required-by: scikit-learn） | **DROP**（无直接 import；模型为 pickle+lzma 非 joblib） |
| threadpoolctl | 3.5.0 | （Required-by: scikit-learn） | **DROP**（无直接 import） |
| numpy | 1.26.4 | — | **KEEP**：`requirements.in:3` 显式声明；另被 onnxruntime:148 / opencv-python:150 / shapely:154 直接依赖 |
| pillow | 10.3.0 | — | **KEEP**：`requirements.in:7` 显式声明；直接使用：captcha_solver.py:22、qrcode.py:6、server.py:449,496、webview_ui.py:10,79、auto_get_res_new.py:10 |
| networkx | 3.3 | — | **KEEP**：`requirements.in:34` 显式声明；直接使用 `arknights_mower/utils/graph.py:3`（虽然也是 scikit-image 的依赖，但项目独立声明，不能随 trio 移除） |
| packaging | 24.1 | — | **KEEP**：并非只有 trio 用，onnxruntime:171 / langchain-core:172 / langsmith:173 也依赖（不随移除消失） |
| opencv-python / pyzbar / onnxruntime / rapidocr-onnxruntime / ddddocr / base45 等 | — | — | **独立保留**，与 trio 无关（`requirements.in:2,14,10,11` 等） |

> 说明：`packaging` 在 requirements.txt:170-176 同时被 lazy-loader、scikit-image 和 onnxruntime/langchain-core/langsmith 依赖；由于后三者保留，移除 trio 后 packaging 仍在，无需处理。

---

## 3. 打包配置影响

### 3.1 PyInstaller spec（`webui_zip.spec`、`webui_zip_for_linux.spec`）

- **无**任何 scipy/sklearn/skimage/imageio/tifffile/joblib/threadpoolctl 的 `hiddenimports` 或 `excludes` 行。两文件的 `excludes` 仅列 torch/transformers/sympy/pytest 等（webui_zip.spec:56-75、webui_zip_for_linux.spec:54-72）。
- **模型文件打包路径**：`build_assets.py:46-61` `_collect_arknights_mower_datas()` 递归收集整个 `arknights_mower/` 包树（跳过 tests/、__pycache__），因此 `models/CONSUME.pkl`、`models/NORMAL.pkl`、`models/svm.model` 已自动进入 datas。**只要模型文件路径/文件名不变，spec 的 datas 无需任何修改**。
- 重写后无 import 即不会被 PyInstaller 打包；可选防御：在两 spec 的 `mower_a` Analysis `excludes` 追加 `"scipy", "skimage", "sklearn"`（非必须。`excludes` 匹配可导入的模块名，因此用 `skimage` 而不是发行包名 `scikit_image`）。

### 3.2 需要编辑的构建脚本/元数据

| 文件:行 | 内容 | 处置 |
|---|---|---|
| `scripts/fix_runtime_dlls.py:13,58-69` | 硬编码 `dist/mower/_internal/sklearn/.libs/msvcp140.dll` 版本对齐 | 移除 sklearn 后该 DLL 不存在 → 删除 sklearn 分支或整脚本改造 |
| `setup.py:24-25` | `scikit_image==0.18.3`、`scikit_learn>=1` | 从 install_requires 移除/更新（`python-publish.yml:31` 仍用 setup.py 打包） |
| `requirements.in:4-6` | 移除并重新 `pip-compile` | 见 §5 步骤 10 |

### 3.3 Docker

- 根 `Dockerfile:39` `pip install -r requirements.in`：无需改行，改 requirements.in 即可。
- `docker/Dockerfile:31-36`：requirements.txt 由 pip-compile 生成 → 移除 trio 后重跑 pip-compile 即自动去掉 trio 及其传递依赖；`docker/gen_server_requirements.py:17-31` 除 EXCLUDE/RENAME 外全量透传行，server 版自动同步。`uv pip install --no-deps`（行 36）要求所有传递依赖显式列出——numpy/pillow/networkx 等保留项仍在 requirements.txt 中，构建不破坏。

### 3.4 CI

- `.github/workflows/format-check-and-test.yml:38,44`：unittest job `pip install -r requirements.txt` → 若 trio 彻底移出，golden 测试自动 skip（vision_np_tests 全部门控）；若希望在 CI 继续校验等价性，需把 trio 放回 dev-only 依赖（见 §4 建议）。
- `pyinstaller-win-alpha.yml:33` 引用不存在的 `main.spec`（Glob 全仓无此文件）——遗留失效 workflow，与本票无直接关系，顺带提示。

---

## 4. 必须保留 scipy/sklearn/skimage 的文件（dev/train-only）

| 文件:行 | 原因 |
|---|---|
| `auto_get_res_new.py:11-12, 643-651, 666-671, 673-684` | 唯一模型训练/导出脚本：`KNeighborsClassifier.fit` + `skimage.feature.hog` 提取特征，直接产出 `NORMAL.pkl`/`CONSUME.pkl`（行 682-683） |
| `arknights_mower/tests/vision_np_tests.py`（全文） | golden 等价性测试，需 trio 作为参照实现；文件头（行 4-5）已注明「生产移除依赖后自动跳过」 |
| `scripts/fix_runtime_dlls.py` | build-time 脚本（引用 sklearn DLL；移除后应删除而非保留依赖） |
| `setup.py:24-25` | 发布元数据（`scikit_image==0.18.3` 甚至与 requirements 的 0.23.2 不一致，疑似过期） |

> 注意：`auto_get_res_new.py` **只能重训 KNN（CONSUME/NORMAL/MATERIAL）**；`models/svm.model`（804B）的再生成路径不在本仓库——`models/README.md:11-13` 仅描述其为「SVM 分类器，负责图像匹配判定」，仓库内无生成该文件的训练代码（svm 训练在仓库外）。这意味着 svm.model 的 sklearn-free 折叠只能对**现有文件**做一次性转换，无法用仓库内脚本重训。

**建议（决策权在他人，#129 需拍板）**：新增 dev-only 依赖声明（如 `requirements-dev.txt` 或 requirements.in 注释段）保留 trio，供 `auto_get_res_new.py` 重训与 `vision_np_tests.py` golden 校验；运行时依赖（requirements.in 主体）移除。

---

## 5. 移除落地 checklist（#129 输入）

### ⚠️ 阻塞点（必须先处理）

三个模型文件是 pickle 序列化的 **sklearn 对象**。`pickle.loads` 反序列化时会 `import` 对象定义模块：

- `matcher.py:31-32` 加载 svm.model → 需 `sklearn.pipeline` / `sklearn.preprocessing` / `sklearn.svm`（这正是 matcher.py:7-9 顶栏 import 的用途）
- `depotREC.py:102-105` 加载 CONSUME.pkl / NORMAL.pkl → 需 `sklearn.neighbors.KNeighborsClassifier`

**只要运行环境移除 sklearn，这 3 个文件在运行时加载即抛 `ModuleNotFoundError`**，与预测逻辑是否已由 vision_np 复刻无关。因此必须先把模型折叠成 sklearn-free 格式。

### 有序步骤

1. **一次性模型折叠脚本**（dev 环境、临时装有 trio）：
   - svm.model → `{"w": coef_[0]/scale_, "b": intercept_[0] - sum(coef_[0]*mean_/scale_)}`（折叠公式见 `vision_np_tests.py:161-162`）
   - CONSUME.pkl / NORMAL.pkl → `{"X": _fit_X, "y_idx": _y, "classes": classes_}`（字段见 `vision_np_tests.py:178`）
   - `lzma+pickle` 写回**同文件名同目录**，保持 `build_assets.py` 全树收集路径不变
2. `matcher.py:7-9` 删除 sklearn 三个 import；`:31-32` 加载新格式 dict；`:107` 改 `vision_np.linear_svc_predict(score, w, b)`
3. `matcher.py:285` 改 `vision_np.ssim(query, rect_img)`（**去掉 `multichannel=True`**，vision_np.ssim 无该参数，见 vision_np.py:41）
4. `depotREC.py:11,43-51` 改 `vision_np.hog`；`:102-105` 加载新格式 dict；`:147` 改 `vision_np.knn1_predict(物品特征, X, y_idx, classes)`
5. `auto_fight.py:4,145` → `vision_np.argrelmax(result, 50)`；`:5,195` → `vision_np.ssim(img, res)`
6. `credit_fight.py:2,33` → `vision_np.argrelmin(result, 100)`
7. `recognize.py:7,835` → `vision_np.ssim(gray, res_img)`
8. `vision_np_tests.py` 的 `_load_svm_model`/`_load_knn`（行 47-54）与 `TestLinearSvc/TestKnn1`（行 155-196）改读新格式；sklearn import（行 37-44）删除或改为仅 dev 环境
9. 全仓复跑 §1 检索确认无残留 import
10. `requirements.in:4-6` 移除 → 重新 `pip-compile`：imageio/tifffile/lazy-loader/joblib/threadpoolctl（requirements.txt:89,99,128,284,286）自动退出；networkx 因 requirements.in:34 独立声明而保留
11. `scripts/fix_runtime_dlls.py` 删除 sklearn 分支/改造
12. （可选）两 spec `mower_a` excludes 追加 `"scipy", "skimage", "sklearn"`
13. `setup.py:24-25` 同步移除/更新
14. dev 环境运行 `arknights_mower/tests/vision_np_tests.py` 确认等价性（SSIM 2.5e-8 / HOG 1.3e-6 / argrel 逐位 / SVC-KNN 折叠一致，见测试文件头 7-9）
15. Docker（`docker/Dockerfile`）+ PyInstaller（`webui_zip.spec`）构建冒烟

---

### 附：vision_np 提供的能力与调用形态对照

| 上游 | 调用点（现状） | vision_np 对应 |
|---|---|---|
| `scipy.signal.argrelmax(mode='clip')` | auto_fight.py:145 `(x, order=50)[0]` | `argrelmax(x, 50)`（vision_np.py:12） |
| `scipy.signal.argrelmin(mode='clip')` | credit_fight.py:33 `(x, order=100)[0]` | `argrelmin(x, 100)`（vision_np.py:24） |
| `skimage.metrics.structural_similarity` | auto_fight.py:195 / recognize.py:835（2D uint8）；matcher.py:285（`multichannel=True`） | `ssim(a, b)`（vision_np.py:41，uint8→dr=255，2D 默认路径） |
| `skimage.feature.hog`（18ori/8x8/2x2/L2-Hys/transform_sqrt/彩色最佳通道） | depotREC.py:43-51 | `hog(a)`（vision_np.py:73，固定参数组，与测试 vision_np_tests.py:140-148 对齐） |
| `sklearn Pipeline(StandardScaler+LinearSVC).predict` | matcher.py:107 | `linear_svc_predict(x, w, b)`（vision_np.py:116） |
| `sklearn KNeighborsClassifier(k=1, weights='distance').predict` | depotREC.py:147 | `knn1_predict(x, X, y_idx, classes)`（vision_np.py:121） |
