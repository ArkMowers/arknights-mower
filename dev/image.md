---
sort: 4
---

# 图像处理基础函数

Mower 使用 OpenCV 处理图像，颜色通道顺序为 RGB。

## 加载与显示图像

### `loadimg()`

`arknights_mower/utils/image.py` 中提供了用于读取图像的函数 `loadimg()`。`loadimg()` 接受两个参数，第一个参数 `filename` 是图片文件名，第二个参数 `gray` 为 `True` 时返回灰度图像，否则返回 RGB 顺序的彩色图像。`gray` 默认为 `False`。

`loadimg()` 使用 `lru_cache` 以避免反复加载相同的文件。可使用 `loadimg.cache_clear()` 清除 LRU 缓存。

### `loadres()`

Mower 用于识别的图像素材全部位于 `arknights_mower/resources` 以及热更新目录 `tmp/hot_update` 下。使用 `loadimg()` 加载这些图片时，需要拼接出完整的路径，较为繁琐。`loadres()` 函数可简化从上述位置加载图片的过程。它接受两个参数，第一个参数 `res` 是图片资源名，第二个参数 `gray` 与 `loadimg()` 中保持一致。

图片资源名的规则如下：

1. 对于 `arknights_mower/resources` 下的 png 文件，只需写出相对 `resources` 的路径，并省略扩展名；
2. 以 `@hot/` 表示热更新目录 `tmp/hot_update`；
3. 对于 jpg 文件，在资源名中需要保留 `.jpg` 后缀。

| 资源名                             | 文件名                                             |
| ---------------------------------- | -------------------------------------------------- |
| `ope_select_start`                 | `arknights_mower/resources/ope_select_start.png`   |
| `navigation/episode`               | `arknights_mower/resources/navigation/episode.png` |
| `@hot/dragon_boat_festival/banner` | `tmp/hot_update/dragon_boat_festival/banner.png`   |
| `@hot/hortus/terminal.jpg`         | `tmp/hot_update/hortus/terminal.jpg`               |

`loadimg()` 与 `loadres()` 加载的图像，可直接用 `matplotlib` 显示。

<details>
<summary>使用示例</summary>
{% include loadimg.html %}
</details>
