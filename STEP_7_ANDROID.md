# Step 7: Android + Google Store

> 估算: 5-7 天
> 依赖: Step 1-5 完成 (全链路在 PC 验证通过)

## 目标

把 arknights-mower 打包为 Android APK, 用 MediaProjection 截图 + AccessibilityService 触控, 上架 Google Play Store。

## 核心方案: Chaquopy

[Chaquopy](https://chaquo.com/chaquopy/) 是 Android Gradle Plugin, 把 Python 代码打包进 APK:

| 依赖 | Chaquopy 支持 |
|---|---|
| `numpy` | ✅ 官方 Wheel |
| `opencv-python` | ✅ OpenCV NDK 6.0 + Python binding |
| `onnxruntime` | ✅ Android `.aar` |
| `PIL` | ✅ 纯 Python |
| `networkx` | ✅ 纯 Python |

## 交付物

```
android/
├── app/
│   ├── src/main/
│   │   ├── java/io/github/arkmowers/
│   │   │   ├── MainActivity.kt        # 启动器 Activity
│   │   │   ├── ScreenshotService.kt   # MediaProjection 截图服务
│   │   │   ├── TapperService.kt       # AccessibilityService 点击服务
│   │   │   └── PythonBridge.kt        # 调用 Python 入口
│   │   ├── python/
│   │   │   └── main.py                # Python 入口, import arknights_mower
│   │   └── AndroidManifest.xml
│   └── build.gradle.kts               # Chaquopy 配置
├── gradle/
└── build.gradle.kts
```

## Android Device Backend

### Screencap (MediaProjection)

```python
# utils/device/screencap/android.py
class AndroidScreencap:
    def capture(self) -> np.ndarray:
        # 从 MediaProjection ImageReader 获取帧
        # → crop 游戏区域 (16:9 letterbox)
        # → resize 到 1920×1080
        # → 返回 np.ndarray
        ...
```

### Control (AccessibilityService)

```python
# utils/device/control/android.py
class AndroidControl:
    def tap(self, x: float, y: float) -> None:
        # x, y 是比例坐标 0~1
        # → 转实际像素
        # → 通过 AccessibilityService.dispatchGesture 执行
        ...

    def swipe(self, x1, y1, x2, y2, duration) -> None:
        ...
```

### App 管理

```python
# utils/device/app/android.py
class AndroidApp:
    def launch(self):
        # 通过 PackageManager 启动 com.hypergryph.arknights
        ...

    def exit(self):
        # 通过 am force-stop
        ...
```

## 分辨率适配 (游戏区域检测)

```
MediaProjection raw (e.g. 1080×2340, 20:9)
  → 检测游戏渲染区域 (16:9 letterbox, e.g. 1080×1920)
  → crop 游戏区域
  → resize 到 1920×1080
  → 传给 Recognizer (现有代码零改动)
```

游戏区域检测方法:
- 取四角像素判断黑边
- 或通过 `dumpsys window` 获取游戏窗口尺寸
- 或扫描屏幕中已知 16:9 特征点

## Google Store 准备

- 隐私政策: 说明需要 MediaProjection + AccessibilityService 权限的原因
- 合规: AccessibilityService 仅用于游戏内点击, 不收集数据
- 商店截图: 模拟器运行效果 + 操作说明

## 验证

- 真机 (至少 3 种分辨率: 1080p / 1440p / 20:9) 跑通基建全流程
- 截图回放对比: Android 截图 vs PC 截图, 相同场景识别结果一致

## 允许的旧代码改动

- 新建 `utils/device/screencap/android.py`
- 新建 `utils/device/control/android.py`
- 新建 `utils/device/app/android.py`
- 无其他旧代码改动
