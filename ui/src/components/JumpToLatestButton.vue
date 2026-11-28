<script setup>
import { NButton, NIcon } from 'naive-ui'
import ArrowDownOutline from '@vicons/ionicons5/es/ArrowDownOutline'
</script>

<template>
  <n-button round class="jump-latest">
    <template #icon><n-icon :component="ArrowDownOutline" aria-hidden="true" /></template>
    回到最新
  </n-button>
</template>

<style scoped>
.jump-latest {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  height: 40px;
  box-shadow: 0 3px 12px rgba(0, 0, 0, 0.12);
}
</style>
