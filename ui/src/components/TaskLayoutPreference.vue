<script setup>
import { computed, onMounted } from 'vue'
import { i18n } from '@/i18n'
import { storeToRefs } from 'pinia'
import SettingsSegmented from '@/components/SettingsSegmented.vue'
import { useGuiStore } from '@/stores/gui'

const gui = useGuiStore()
const { taskSettingsLayout, layoutDisabled, layoutSaving, layoutError } = storeToRefs(gui)
const layoutOptions = computed(() => [
  { value: 'checklist', label: i18n.global.t('tasks.taskChecklist') },
  { value: 'waterfall', label: i18n.global.t('tasks.waterfallLayout') }
])

onMounted(() => void gui.load())
</script>

<template>
  <n-form-item
    :label="i18n.global.t('tasks.taskSettingsDisplay')"
    class="settings-appearance-row task-layout-preference"
  >
    <div class="task-layout-preference-content">
      <SettingsSegmented
        :value="taskSettingsLayout"
        :options="layoutOptions"
        :disabled="layoutDisabled"
        :busy="layoutSaving"
        :label="i18n.global.t('tasks.taskSettingsDisplay')"
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
          {{ i18n.global.t('tasks.retry') }}
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
