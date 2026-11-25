<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, required: true },
  subject: { type: String, default: '' },
  stage: { type: String, default: '' },
  disabled: Boolean
})
defineEmits(['set-completed'])
const labels = {
  pending: '待执行',
  completed: '已完成',
  running: '正在执行',
  attempted: '结算待确认',
  failed: '执行失败'
}
const text = computed(() => [props.stage, labels[props.status]].filter(Boolean).join(' · '))
const ariaLabel = computed(() => (props.subject ? `${props.subject} · ${text.value}` : undefined))
const options = [
  { label: '已完成', key: 'completed' },
  { label: '待执行', key: 'pending' }
]
</script>

<template>
  <n-dropdown
    v-if="status === 'attempted' || status === 'failed'"
    trigger="click"
    :options="options"
    :disabled="disabled"
    @select="$emit('set-completed', $event === 'completed')"
  >
    <n-button
      secondary
      size="small"
      type="warning"
      aria-haspopup="menu"
      :aria-label="ariaLabel"
      :disabled="disabled"
    >
      {{ text }}
    </n-button>
  </n-dropdown>
  <n-button
    v-else
    secondary
    size="small"
    :type="status === 'completed' ? 'success' : 'default'"
    :aria-label="ariaLabel"
    :aria-pressed="status === 'completed'"
    :disabled="disabled || status === 'running'"
    @click="$emit('set-completed', status !== 'completed')"
  >
    {{ text }}
  </n-button>
</template>
