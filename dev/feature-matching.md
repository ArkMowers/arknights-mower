---
sort: 5
---

# 特征匹配

特征匹配是 mower 中最方便的识别方法。在截图中匹配目标图像时，首先提取截图与目标图像的特征点，然后找出匹配的特征点对，利用匹配结果在截图中定位目标图像。

## 特征与特征点

`arknights_mower.utils.matcher` 中提供 `keypoints()` 与 `keypoints_scale_invariant()` 函数，可用于提取特征点。接受的参数为需要提取特征点的灰度图像。返回值为特征点元组与描述子矩阵构成的元组。

`keypoints_scale_invariant()` 提取的特征点与描述子具有尺度不变性，可用于匹配尺度不确定或发生变化的图像，但速度相较 `keypoints()` 更慢。

拐角、复杂的图案与纹理（包括文字）处可以提取到较多的特征点；在空白处很难提取到特征点。

<details>
<summary>使用示例</summary>
{% include feature-point.html %}
</details>

## 特征点的匹配

`arknights_mower.utils.matcher` 中的 `flann` 可用于匹配特征点。

对于目标图像中的每个特征点 $A$，使用 `flann.knnMatch(k=2)` 找出截图中与之距离最近的和第二近的两个特征点 $B_1$、$B_2$. 如果 $A$ 与 $B_1$ 的距离 $\text{d}(A, B_1)$ 和 $A$ 与 $B_2$ 的距离 $\text{d}(A, B_2)$ 的比值 $\frac{\text{d}(A, B_1)}{\text{d}(A, B_2)} <$ `GOOD_DISTANCE_LIMIT`，就认为 $A$ 与 $B_1$ 是一对“好”的匹配。

下面的例子展示了如何利用特征匹配在终端页面定位活动入口。其中 `res` 图像来自明日方舟网站，尺寸与游戏内截图未必一致，因此对于 `res` 使用 `keypoints_scale_invariant()` 提取特征点。对于截图，使用 `keypoints()` 提取特征点，仍然可以得到很好的匹配结果。

<details>
<summary>使用示例</summary>
{% include feature-matching.html %}
</details>

## 利用特征匹配定位目标图像

`arknights_mower.utils.matcher` 中的 `Matcher` 类可用于定位目标图片。

实例化 `Matcher` 类时，需传入灰度图像 `origin`。实例化过程中计算 `origin` 图像的特征点。

`Matcher` 类的实例方法 `match()` 接受 6 个参数，其中 `query` 必选：

- `query`：灰度目标图像；
- `draw`：控制是否绘制并显示匹配过程；
- `scope`：`origin` 在此区域内的特征点参与匹配；
- `dpi_aware`：匹配尺寸不确定，或尺寸有变化的目标图像时，将此选项设置为 `True`。默认为 `False`。
- `prescore`：SSIM 分数阈值。如果此参数为正值，则根据 SSIM 分数直接决定是否接受匹配结果。
- `judge`：在 `prescore` 为 0 时生效。如果为 `True`，使用支持向量机判断是否接受匹配结果，否则直接接受匹配结果。

如果匹配成功，`match()` 返回目标图片在截图中匹配到的区域；否则返回 `None`。

<details>
<summary>使用示例</summary>
{% include matcher.html %}
</details>

## 注意事项

### 性能

从截图提取特征点一般会花费数十毫秒，一次 FLANN 匹配也可能花费几毫秒到几十毫秒。大量使用特征匹配会导致脚本很慢。

### 目标图像截取

目标图像应尽量满足特征点数量多、尺寸小、与其它目标图像有较大区别。例如对于按钮，只截取按钮中独特的图案，或在文字中截取 3-5 字的关键词，相比截取整个按钮，往往能得到更好的效果。

### 随机性

FLANN 和 RANSAC 算法具有一定的随机性。若结果变化较大，可考虑重新截取目标图像，或换用其它匹配方式。

### 多目标

当目标图像在截图中多次出现时，目标图像的特征点与截图对应特征点的若干对匹配距离相近。在应用比例测试筛选特征点时，这些匹配都会被过滤掉，导致目标图像多次出现时无法匹配到结果。

如果要处理目标多次出现的情况，如果能够预知出现的范围，可以指定 `scope` 参数进行限制。

<details>
<summary>查看例子</summary>
{% include multi-matching.html %}
</details>
