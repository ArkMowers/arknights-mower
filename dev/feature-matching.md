---
sort: 5
---

# 特征匹配

特征匹配是 mower 中最方便的识别方法。在截图中匹配目标图像时，首先提取截图与目标图像的特征点，然后找出匹配的特征点对，利用匹配结果在截图中定位目标图像。

## 特征与特征点

可以直接使用 `arknights_mower.utils.matcher` 中的 `ORB` 提取特征点。

一般而言，在图像中，拐角、复杂的图案与纹理（包括文字）处可以提取到较多的特征点；在空白处，很难或无法提取到特征点。从复杂的图像中可以提取到更多的特征点。

<details>
<summary>使用示例</summary>
{% include feature-point.html %}
</details>

## 特征点的匹配

可以直接使用 `arknights_mower.utils.matcher` 中的 `flann` 对特征点进行匹配。

<details>
<summary>使用示例</summary>
{% include feature-matching.html %}
</details>
