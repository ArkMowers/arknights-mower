<script setup>
import { ref, watch } from 'vue'

const show = defineModel('show', { type: Boolean })
const props = defineProps({ scheduledStartAt: String, busy: Boolean })
const emit = defineEmits(['schedule'])
const date = ref(null)
const time = ref(null)

watch(
  show,
  (visible) => {
    if (!visible) return
    const target = props.scheduledStartAt
      ? new Date(props.scheduledStartAt).getTime()
      : Date.now() + 30 * 60000
    date.value = target
    time.value = target
  },
  { immediate: true }
)

function confirm() {
  const d = new Date(date.value)
  const t = new Date(time.value)
  const target = new Date(
    d.getFullYear(),
    d.getMonth(),
    d.getDate(),
    t.getHours(),
    t.getMinutes(),
    t.getSeconds()
  )
  emit('schedule', Math.ceil((target.getTime() - Date.now()) / 1000))
}
</script>

<template>
  <n-modal
    v-model:show="show"
    preset="card"
    title="定时启动"
    style="width: min(420px, calc(100vw - 32px))"
  >
    <n-text depth="3" style="display: block; margin-bottom: 12px">
      到达预约时间后，将清空运行缓存并启动 Mower。
    </n-text>
    <n-space vertical>
      <n-date-picker v-model:value="date" type="date" style="width: 100%" />
      <n-time-picker v-model:value="time" style="width: 100%" />
    </n-space>
    <template #footer>
      <n-space justify="end">
        <n-button @click="show = false">取消</n-button>
        <n-button type="primary" :loading="busy" @click="confirm">确定</n-button>
      </n-space>
    </template>
  </n-modal>
</template>
