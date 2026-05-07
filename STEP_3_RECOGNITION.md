# Step 3: Recognition 代码优化

> 估算: 2-3 天
> 注意: 保留所有 3 条匹配路径, 只做代码组织优化

## 目标

把 `utils/recognize.py`(1049 行) 拆分为多个文件, 保持功能不变, 降低单个文件复杂度。

## 现状

```
utils/recognize.py      1049 行
└── class Recognizer:
    └── def find():      ~300 行   ← 3 条路径 + color 字典 + template_matching 字典
    └── def get_scene(): ~250 行   ← ~80 个 if/elif 场景判断
    └── helper methods:  ~500 行   ← check_xxx, detect_xxx, template_match 等
```

## 方案: 按匹配路径拆分文件

### 新结构

```
utils/
├── recognize/
│   ├── __init__.py              # export Recognizer
│   ├── base.py                  # Recognizer 基类 (属性/工具方法)
│   ├── find_color.py            # color 匹配路径 (单像素 + cmatch + SSIM)
│   ├── find_template.py         # template_matching 路径 (TM_CCOEFF_NORMED)
│   ├── find_feature.py          # ORB+SVM 路径 (原有 dpi_aware 逻辑)
│   ├── scene.py                 # get_scene() 的场景判断表
│   ├── constants.py             # color 字典 + template_matching 字典
│   └── ...

# 或者更扁平的拆分, 保持 import 路径不变:
utils/recognize.py               # 保留为薄壳, import 各子模块
utils/recognize_color.py         # color 匹配
utils/recognize_template.py      # template_matching  
utils/recognize_feature.py       # ORB+SVM
utils/recognize_scene.py         # get_scene 场景表
```

### find() 方法的拆分

```python
# 优化前: 一个方法 300 行, 3 条路径耦合
def find(self, res, ...):
    if res in color:        # ~120 行
        ...
    elif res in template_matching:  # ~100 行
        ...
    else:                   # ORB+SVM 路径 ~80 行
        ...

# 优化后: 策略路由
def find(self, res, ...):
    matcher = self._select_matcher(res)
    return matcher.match(self.gray, res, ...)

def _select_matcher(self, res):
    if res in self.color_dict:
        return ColorMatcher(self)
    elif res in self.template_dict:
        return TemplateMatcher(self)
    else:
        return FeatureMatcher(self)
```

### get_scene() 的拆分

```python
# 优化前: ~250 行 if/elif 链
def get_scene(self):
    if self.find("connecting"): ...
    elif self.find("confirm"): ...
    elif self.find("order_label"): ...
    # ... ~80 个 elif

# 优化后: 场景表驱动
SCENE_RULES = [
    ("connecting", Scene.CONNECTING),
    ("confirm", Scene.CONFIRM),
    ("order_label", Scene.ORDER_LIST),
    # ...
]

def get_scene(self):
    for res_name, scene in SCENE_RULES:
        if self.find(res_name):
            return scene
    return Scene.UNKNOWN
```

## 不做的改动

- **不砍 ORB+SVM 路径** — 保留 `dpi_aware`、`matcher.py`、`svm.model`
- **不改 color 字典内容** — 保留所有 ~80 个坐标条目
- **不改 template_matching 字典内容** — 保留所有 ~100 个坐标条目
- **不改 get_scene 的识别逻辑** — 只把 if/elif 结构化, 不改变匹配顺序和阈值

## 验证

- 全场景回归: 输入相同截图, 新旧 `find()` 返回相同 scope
- 新旧 `get_scene()` 场景识别一致
- `from arknights_mower.utils.recognize import Recognizer` 保持可用

## 允许的旧代码改动

- 新建 `utils/recognize/` 目录, 把 Recognizer 类拆进去
- 或新建 `utils/recognize_*.py` 扁平拆分
- 旧的 `utils/recognize.py` 保留为 import 桥接, 最后 Step 5 再删除
