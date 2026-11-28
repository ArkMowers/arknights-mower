<script setup>
// 页面读取数据时的骨架屏外壳。默认插槽里放页面自己排好的占位块（.skeleton-bone 等，见
// src/styles/skeleton.css），也可以放标题、标签、按钮等与读完后相同的静态部分。外壳让插槽
// 内容不可操作、不可聚焦，并对读屏软件隐藏，只读出 label。
// 外壳本身不加布局：页面给它的 class 落在根元素上，占位块直接按这个 class 的布局排列。
// 读完后内容直接在原处替换外壳；骨架里没有对应占位的内容才加 .skeleton-reveal 淡入。
defineProps({
  label: { type: String, required: true }
})
</script>

<template>
  <div class="loading-skeleton" role="status" aria-busy="true">
    <span class="loading-skeleton__label">{{ label }}</span>
    <div class="loading-skeleton__shapes" inert><slot /></div>
  </div>
</template>
