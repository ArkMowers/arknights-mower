<script setup>
import { useGuiStore } from '@/stores/gui'

const gui = useGuiStore()
</script>

<template>
  <n-form-item
    label="运行日志布局"
    data-settings-keywords="运行日志 布局 双栏 单栏 截图预览 任务列表 今日任务"
  >
    <n-button size="small" @click="gui.openRunningLogLayoutDialog">编辑布局</n-button>
  </n-form-item>
</template>
