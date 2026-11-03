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
let generation = 0
let timer
let controller
let disposed = false
const status_text = computed(() =>
  failed.value
    ? '状态读取失败'
    : completed.value === null
      ? '读取中'
      : completed.value
        ? '已完成'
        : '待执行'
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
    const { data } = await axios.get(
      `${import.meta.env.VITE_HTTP_URL || ''}/maa-long-task-status`,
      { signal }
    )
    if (current !== generation || disposed) return
    if (typeof data[props.kind]?.completed !== 'boolean') throw new Error('Invalid task status')
    completed.value = data[props.kind].completed
  } catch {
    if (current === generation && !disposed) failed.value = true
  } finally {
    if (current === generation && !disposed) timer = setTimeout(refresh, 5000)
  }
}
watch(
  () => [props.kind, props.settings],
  () => {
    completed.value = null
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
    <n-button v-if="failed" size="tiny" @click="refresh">重试</n-button>
  </n-flex>
</template>
