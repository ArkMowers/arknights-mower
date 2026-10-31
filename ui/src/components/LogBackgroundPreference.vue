<script setup>
import { onMounted, ref } from 'vue'
import { useLogBackgroundStore } from '@/stores/logBackground'

const background = useLogBackgroundStore()
const picker = ref(null)

function select(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (file) void background.upload(file)
}

onMounted(() => void background.load())
</script>

<template>
  <n-form-item
    class="settings-row-wide log-background-preference"
    data-settings-keywords="运行日志 背景图 自定义 图片 恢复默认"
  >
    <template #label>
      <span class="settings-row-copy">
        <span>运行日志背景图</span>
        <span class="settings-row-description"
          >选择后立即生效。支持 PNG、JPEG、WebP，最大 8 MiB、2400 万像素。</span
        >
      </span>
    </template>
    <div class="log-background-controls">
      <div
        class="log-background-preview"
        :style="{ backgroundImage: `url('${background.url}')` }"
        role="img"
        :aria-label="background.customUrl ? '自定义运行日志背景图预览' : '默认运行日志背景图预览'"
      ></div>
      <input
        ref="picker"
        class="log-background-input"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        aria-label="选择运行日志背景图"
        :disabled="background.busy || !background.loaded"
        @change="select"
      />
      <div class="log-background-actions">
        <n-button :disabled="background.busy || !background.loaded" @click="picker?.click()"
          >选择图片</n-button
        >
        <n-button
          :disabled="background.busy || !background.loaded || !background.customUrl"
          @click="background.reset"
          >恢复默认</n-button
        >
        <span role="status" class="log-background-status">{{
          background.busy ? '正在处理…' : background.customUrl ? '使用自定义图片' : '使用默认图片'
        }}</span>
      </div>
      <n-alert v-if="background.error" type="error" :show-icon="false" role="alert">
        {{ background.error }}
        <n-button
          v-if="!background.loaded"
          text
          :disabled="background.busy"
          @click="background.load"
          >重试</n-button
        >
      </n-alert>
    </div>
  </n-form-item>
</template>

<style scoped>
.log-background-controls {
  display: grid;
  gap: 12px;
  width: 100%;
  min-width: 0;
}
.log-background-preview {
  width: 100%;
  max-width: 340px;
  aspect-ratio: 16 / 9;
  border: 1px solid var(--mower-border);
  border-radius: 8px;
  background-size: cover;
  background-position: 65% 50%;
}
.log-background-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.log-background-status {
  color: var(--mower-text-muted);
  font-size: 12px;
}
.log-background-input {
  display: none;
}
</style>
