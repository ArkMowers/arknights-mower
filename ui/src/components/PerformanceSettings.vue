<script setup>
import { computed } from 'vue'
import { useConfigStore } from '@/stores/config'

const props = defineProps({
  observation: { type: Object, default: null },
  disabled: { type: Boolean, default: false },
  labelWidth: { type: Number, default: 158 }
})
const config = useConfigStore()
const labels = { auto: '自动', xhigh: '极高', high: '高', medium: '中', low: '低' }
const options = computed(() =>
  Object.entries(labels)
    .filter(
      ([value]) => config.runtime_platform !== 'android' || !['xhigh', 'high'].includes(value)
    )
    .map(([value, label]) => ({ value, label }))
)
const recommendation = computed(() => {
  const mode = props.observation?.recommended_mode
  return props.observation?.status === 'available' &&
    options.value.some((item) => item.value === mode)
    ? mode
    : null
})
const resourceLabel = computed(() => {
  const info = props.observation
  return info?.status === 'available'
    ? `CPU ${info.cpu_cores} 核 · 内存 ${(info.memory_mb / 1024).toFixed(1)} GiB`
    : ''
})

function applyMode(mode) {
  if (props.disabled || !options.value.some((item) => item.value === mode)) return
  config.performance_mode = mode
}
</script>

<template>
  <n-form-item label="设备性能适配" :label-width="labelWidth">
    <n-space vertical :size="8">
      <n-space align="center" :wrap="false">
        <n-radio-group
          :value="config.performance_mode"
          :disabled="disabled"
          @update:value="applyMode"
        >
          <n-flex :size="12">
            <n-radio v-for="option in options" :key="option.value" :value="option.value">
              {{ option.label }}
            </n-radio>
          </n-flex>
        </n-radio-group>
        <help-text>
          测试连接时读取目标设备可见的 CPU 核数和内存总量，给出初步建议。
          核数和内存不能代表游戏实际响应速度，建议档位最高为“高”，采用建议需手动确认。
          自动档根据选人操作后的画面反馈和连续失败情况调整；桌面端从极高档开始，Android 从中档开始。
          极高档连续点击重排；高档缩短清空和翻页等待，完成后统一校验；中档等待稳定画面；低档多确认一帧。
          切换档位不修改独立设置的时间参数。当前生效：{{
            labels[config.performance_effective_mode] || '待运行'
          }}。
        </help-text>
      </n-space>
      <n-space v-if="resourceLabel" align="center" aria-live="polite">
        <n-text depth="3" class="performance-resources">{{ resourceLabel }}</n-text>
        <n-tag v-if="recommendation" size="small" :bordered="false">
          建议：{{ labels[recommendation] }}
        </n-tag>
        <n-button
          v-if="recommendation && config.performance_mode !== recommendation"
          size="small"
          secondary
          :disabled="disabled"
          @click="applyMode(recommendation)"
        >
          采用建议
        </n-button>
      </n-space>
      <n-text v-else-if="observation?.status === 'unavailable'" depth="3" role="status">
        {{ observation.message }}
      </n-text>
      <n-text v-else-if="config.runtime_platform !== 'android'" depth="3">
        测试连接后显示设备性能与建议档位。
      </n-text>
    </n-space>
  </n-form-item>
</template>

<style scoped>
.performance-resources {
  font-variant-numeric: tabular-nums;
}
</style>
