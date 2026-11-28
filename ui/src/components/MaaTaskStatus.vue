<script setup>
import { computed, inject, onMounted, onScopeDispose, ref, watch } from 'vue'
import { useConfigStore } from '@/stores/config'

const props = defineProps({
  kind: { type: String, required: true },
  settings: { type: Object, required: true }
})
const axios = inject('axios')
const store = useConfigStore()
const completed = ref(null)
const failed = ref(false)
const detail = ref(null)
let generation = 0
let timer
let controller
let disposed = false
const status_text = computed(() => {
  if (failed.value) return '状态读取失败'
  if (completed.value === null) return '读取中'
  if (completed.value) return '已完成'
  if (detail.value?.items?.includes('running')) return '正在执行'
  if (detail.value?.failed || detail.value?.items?.includes('failed')) return '需要核对'
  return '待执行'
})
const completedItems = computed(
  () => detail.value?.items?.filter((item) => item === 'completed').length
)
const status_type = computed(() =>
  completed.value === null || failed.value ? 'default' : completed.value ? 'success' : 'warning'
)

async function refresh() {
  const current = ++generation
  clearTimeout(timer)
  controller?.abort()
  controller = new AbortController()
  const signal = controller.signal
  failed.value = false
  try {
    await store.flush_config_saves()
    if (current !== generation || disposed) return
    const queue = ['copilot', 'paradox'].includes(props.kind)
    const { data } = await axios.get(
      `${import.meta.env.VITE_HTTP_URL || ''}/maa-long-task-status${queue ? `?kind=${props.kind}` : ''}`,
      { signal }
    )
    if (current !== generation || disposed) return
    const status = queue ? data : data[props.kind]
    if (typeof status?.completed !== 'boolean') throw new Error('Invalid task status')
    completed.value = status.completed
    detail.value = status
  } catch {
    if (current === generation && !disposed) failed.value = true
  } finally {
    if (current === generation && !disposed) timer = setTimeout(refresh, 5000)
  }
}
defineExpose({ detail: computed(() => (failed.value ? null : detail.value)), refresh })
watch(
  () => [props.kind, props.settings],
  () => {
    completed.value = null
    detail.value = null
    refresh()
  },
  { deep: true }
)
onMounted(refresh)
onScopeDispose(() => {
  disposed = true
  ++generation
  clearTimeout(timer)
  controller?.abort()
})
</script>

<template>
  <n-flex align="center" :size="8">
    <n-text :type="status_type">{{ status_text }}</n-text>
    <n-text v-if="detail?.items?.length && !failed" depth="3">
      {{ completedItems }} / {{ detail.items.length }} 项已完成
    </n-text>
    <n-text v-if="kind === 'garrison' && detail && !failed">
      <template v-if="detail.mode === 'matches'"
        >已结算 {{ detail.count }}{{ detail.total ? ' / ' + detail.total : '' }} 局{{
          detail.total ? '' : '（不限）'
        }}</template
      >
      <template v-else>已确认达标 {{ detail.count }}/{{ detail.total }} 项策略</template>
    </n-text>
    <n-text v-if="detail?.message && !failed" type="warning">{{ detail.message }}</n-text>
    <n-button v-if="failed" size="tiny" @click="refresh">重试</n-button>
  </n-flex>
</template>
