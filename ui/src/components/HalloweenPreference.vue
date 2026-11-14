<script setup>
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import SettingsSegmented from '@/components/SettingsSegmented.vue'
import { useGuiStore } from '@/stores/gui'

const gui = useGuiStore()
const { halloweenMode, halloweenDisabled, halloweenSaving, halloweenError } = storeToRefs(gui)
const options = [
  { value: 'auto', label: '自动' },
  { value: 'on', label: '开启' },
  { value: 'off', label: '关闭' }
]

onMounted(() => void gui.load())
</script>

<template>
  <n-form-item
    class="settings-row-wide halloween-preference"
    data-settings-keywords="万圣节 装饰 巫异盛宴 节日 自动 开启 关闭"
  >
    <template #label>
      <span class="settings-row-copy">
        <span>万圣节装饰</span>
        <span class="settings-row-description"
          >自动模式在每年 10 月 24 日至 11 月 1 日显示。切换后立即生效。</span
        >
      </span>
    </template>
    <div class="halloween-preference-controls">
      <SettingsSegmented
        :value="halloweenMode"
        :options="options"
        :disabled="halloweenDisabled"
        :busy="halloweenSaving"
        label="万圣节装饰"
        @update:value="gui.setHalloweenMode"
      />
      <span v-if="halloweenSaving" role="status">正在保存…</span>
      <n-alert v-if="halloweenError" type="error" :show-icon="false" role="alert">
        {{ halloweenError }}
        <n-button
          text
          :disabled="gui.loading || (gui.loaded && halloweenDisabled)"
          @click="gui.retryHalloweenMode"
          >重试</n-button
        >
      </n-alert>
    </div>
  </n-form-item>
</template>

<style scoped>
.halloween-preference-controls {
  display: grid;
  gap: 8px;
  width: 100%;
  min-width: 0;
}
</style>
