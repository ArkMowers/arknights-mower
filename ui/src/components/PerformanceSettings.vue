<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global
import { computed, ref } from 'vue'
import { useConfigStore } from '@/stores/config'
import GamePerformanceTest from './GamePerformanceTest.vue'

const props = defineProps({
  observation: { type: Object, default: null },
  disabled: { type: Boolean, default: false },
  testEnabled: { type: Boolean, default: false },
  labelWidth: { type: Number, default: 158 }
})
const config = useConfigStore()
const gameTestRunning = ref(false)
const labels = computed(() => ({
  auto: t('devices.auto'),
  xhigh: t('devices.xhigh'),
  high: t('devices.high'),
  medium: t('devices.medium'),
  low: t('devices.low')
}))
const options = computed(() =>
  Object.entries(labels.value).map(([value, label]) => ({ value, label }))
)
const resourceLabel = computed(() => {
  const info = props.observation
  return info?.status === 'available'
    ? t('devices.resources', { cores: info.cpu_cores, memory: (info.memory_mb / 1024).toFixed(1) })
    : ''
})

function applyMode(mode) {
  if (
    config.manager_owned_device ||
    props.disabled ||
    gameTestRunning.value ||
    !options.value.some((item) => item.value === mode)
  )
    return
  config.performance_mode = mode
}
</script>

<template>
  <n-form-item :label="t('devices.performance')" :label-width="labelWidth">
    <n-space vertical :size="8">
      <n-space align="center" :wrap="false">
        <n-radio-group
          v-if="!config.manager_owned_device"
          :value="config.performance_mode"
          :disabled="disabled || gameTestRunning"
          @update:value="applyMode"
        >
          <n-flex :size="12">
            <n-radio v-for="option in options" :key="option.value" :value="option.value">
              {{ option.label }}
            </n-radio>
          </n-flex>
        </n-radio-group>
        <n-text v-else>
          {{ t('devices.currentModePrefix') }} {{ labels[config.performance_mode] }}
          {{ t('devices.managedModeSuffix') }}
        </n-text>
        <help-text>
          {{
            t('devices.performanceHelp', {
              mode: labels[config.performance_effective_mode] || t('devices.waitingRun')
            })
          }}
        </help-text>
      </n-space>
      <n-space v-if="resourceLabel" align="center" aria-live="polite">
        <n-text depth="3" class="performance-resources">{{ resourceLabel }}</n-text>
      </n-space>
      <n-text v-else-if="observation?.status === 'unavailable'" depth="3" role="status">
        {{ observation.message }}
      </n-text>
      <n-text v-else-if="config.runtime_platform !== 'android'" depth="3">
        {{ t('devices.resourcesHint') }}
      </n-text>
      <GamePerformanceTest
        :disabled="disabled || !testEnabled"
        @running="gameTestRunning = $event"
      />
    </n-space>
  </n-form-item>
</template>

<style scoped>
.performance-resources {
  font-variant-numeric: tabular-nums;
}
</style>
