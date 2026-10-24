<script setup>
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import SettingsSegmented from '@/components/SettingsSegmented.vue'
import { useGuiStore } from '@/stores/gui'

const gui = useGuiStore()
const { taskSettingsLayout, layoutDisabled, layoutSaving, layoutError } = storeToRefs(gui)
const layoutOptions = [
  { value: 'checklist', label: '任务清单' },
  { value: 'waterfall', label: '瀑布流' }
]

onMounted(() => void gui.load())
</script>

<template>
  <n-form-item label="任务配置显示" class="settings-appearance-row task-layout-preference">
    <div class="task-layout-preference-content">
      <SettingsSegmented
        :value="taskSettingsLayout"
        :options="layoutOptions"
        :disabled="layoutDisabled"
        :busy="layoutSaving"
        label="任务配置显示"
        @update:value="gui.setTaskSettingsLayout"
      />
      <n-alert v-if="layoutError" type="error" :show-icon="false" role="alert">
        {{ layoutError }}
        <n-button
          size="small"
          text
          :disabled="gui.loading || gui.saving || layoutSaving"
          @click="gui.retryTaskSettingsLayout"
        >
          重试
        </n-button>
      </n-alert>
    </div>
  </n-form-item>
</template>

<style scoped>
.task-layout-preference-content {
  display: grid;
  gap: 8px;
  width: 100%;
  min-width: 0;
}
</style>
