<script setup>
import { i18n } from '@/i18n'
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
        <span>{{ i18n.global.t('settings.background.logBackgroundImage') }}</span>
        <span class="settings-row-description">{{
          i18n.global.t('settings.background.appliesImmediatelySupportsPngJpegAndWebp')
        }}</span>
      </span>
    </template>
    <div class="log-background-controls">
      <div
        class="log-background-preview"
        :style="{ backgroundImage: `url('${background.url}')` }"
        role="img"
        :aria-label="
          background.customUrl
            ? i18n.global.t('settings.background.customLogBackgroundPreview')
            : i18n.global.t('settings.background.defaultLogBackgroundPreview')
        "
      ></div>
      <input
        ref="picker"
        class="log-background-input"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        :aria-label="i18n.global.t('settings.background.chooseALogBackgroundImage')"
        :disabled="background.busy || !background.loaded"
        @change="select"
      />
      <div class="log-background-actions">
        <n-button :disabled="background.busy || !background.loaded" @click="picker?.click()">{{
          i18n.global.t('settings.background.chooseImage')
        }}</n-button>
        <n-button
          :disabled="background.busy || !background.loaded || !background.customUrl"
          @click="background.reset"
          >{{ i18n.global.t('settings.background.restoreDefault') }}</n-button
        >
        <span role="status" class="log-background-status">{{
          background.busy
            ? i18n.global.t('settings.background.processing')
            : background.customUrl
              ? i18n.global.t('settings.background.usingCustomImage')
              : i18n.global.t('settings.background.usingDefaultImage')
        }}</span>
      </div>
      <n-alert v-if="background.error" type="error" :show-icon="false" role="alert">
        {{ background.error }}
        <n-button
          v-if="!background.loaded"
          text
          :disabled="background.busy"
          @click="background.load"
          >{{ i18n.global.t('settings.background.retry') }}</n-button
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
