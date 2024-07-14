---
sort: 5
---

# 特征匹配

特征匹配是 mower 中最方便的识别方法。在截图中匹配目标图像时，首先提取截图与目标图像的特征点，然后找出匹配的特征点对，利用匹配结果在截图中定位目标图像。

## 特征与特征点

`arknights_mower.utils.matcher` 中的 `ORB` 可用于提取特征点。

一般而言，在图像中，拐角、复杂的图案与纹理（包括文字）处可以提取到较多的特征点；在空白处，很难或无法提取到特征点。从复杂的图像中可以提取到更多的特征点。

<details>
<summary>使用示例</summary>
{% include feature-point.html %}
</details>

## 特征点的匹配

`arknights_mower.utils.matcher` 中的 `flann` 可用于匹配特征点。

对于目标图像中的每个特征点 $A$，使用 `flann.knnMatch(k=2)`找出截图中与之距离最近的和第二近的两个特征点 $B_1$、$B_2$. 如果 $A$ 与 $B_1$ 的距离 $\text{d}(A, B_1)$ 和 $A$ 与 $B_2$ 的距离 $\text{d}(A, B_2)$ 的比值小于 `GOOD_DISTANCE_LIMIT`，就认为 $A$ 与 $B_1$ 是一对“好”的匹配。

下面的例子展示了如何利用特征匹配在终端页面定位活动入口。

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
- `scope`：`origin` 的特征点中，在此区域内的特征点参与匹配；
- `dpi_aware`：大部分元素的尺寸不变，`dpi_aware` 默认为 `False`，若匹配结果与目标图像的尺寸相差较大时拒绝结果。对于尺寸有变化的元素，将此选项设置为 `True`；
- `prescore`：SSIM 分数阈值。如果此参数为正，则根据 SSIM 分数决定是否接受匹配结果。
- `judge`：在 `prescore` 为 0 时生效。如果为 `True`，则使用支持向量机判断是否接受匹配结果，否则直接接受匹配结果。

如果匹配成功，`match()` 返回目标图片在截图中匹配到的区域；否则返回 `None`。

<details>
<summary>使用示例</summary>
{% include matcher.html %}
</details>

## 注意事项

### 性能

从截图提取特征点一般会花费数十毫秒，一次 FLANN 匹配也会花费十几毫秒到几十毫秒。大量使用特征匹配会导致脚本很慢。

### 目标图像截取

目标图像应尽量满足特征点数量多、尺寸小、与其它目标图像有较大区别。例如对于按钮，只截取按钮中独特的图案，或在文字中截取 3-5 字的关键词，相比截取整个按钮，往往能得到更好的效果。

### 随机性

FLANN 和 RANSAC 算法具有一定的随机性。若结果变化较大，可考虑重新截取目标图像，或换用其它匹配方式。
