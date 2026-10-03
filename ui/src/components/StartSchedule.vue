<script setup>
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import AlarmOutline from '@vicons/ionicons5/AlarmOutline'
import PlayIcon from '@vicons/ionicons5/Play'
import { useMowerStore } from '@/stores/mower'

const props = defineProps({
  start: { type: Function, required: true },
  startOptions: { type: Array, required: true },
  waiting: { type: Boolean, default: false }
})

const axios = inject('axios')
const message = useMessage()
const { scheduled_start_at } = storeToRefs(useMowerStore())
const now = ref(Date.now())
const showModal = ref(false)
const date = ref(Date.now())
const time = ref(Date.now())
const busy = ref(false)
let clock

onMounted(() => {
  clock = setInterval(() => (now.value = Date.now()), 1000)
})
onUnmounted(() => clearInterval(clock))

const countdown = computed(() => {
  const remaining = Math.max(0, Math.ceil((new Date(scheduled_start_at.value) - now.value) / 1000))
  const h = Math.floor(remaining / 3600)
  const m = Math.floor((remaining % 3600) / 60)
  const s = remaining % 60
  return [h, m, s].map((n) => String(n).padStart(2, '0')).join(':')
})

const startOptions = computed(() => [
  { label: '定时启动…', key: 'custom' },
  { type: 'divider', key: 'divider' },
  ...props.startOptions
])

const scheduledOptions = [
  { label: '取消定时启动', key: 'cancel' },
  { label: '立即开始执行', key: 'start' }
]

function openModal() {
  const target = scheduled_start_at.value
    ? new Date(scheduled_start_at.value).getTime()
    : Date.now() + 30 * 60000
  date.value = target
  time.value = target
  showModal.value = true
}

async function schedule(delaySeconds) {
  if (busy.value || props.waiting) return
  if (!Number.isFinite(delaySeconds) || delaySeconds <= 0 || delaySeconds > 30 * 86400) {
    message.error('请选择未来 30 天内的时间')
    return
  }
  busy.value = true
  try {
    const { data } = await axios.put(`${import.meta.env.VITE_HTTP_URL}/scheduled-start`, {
      delay_seconds: delaySeconds
    })
    scheduled_start_at.value = data.scheduled_start_at
    showModal.value = false
  } catch (error) {
    message.error(
      error.response?.status === 404
        ? '当前 Mower 进程尚未加载定时启动功能，请更新并重启进程'
        : error.response?.data?.error || '设置定时启动失败'
    )
  } finally {
    busy.value = false
  }
}

async function cancel() {
  if (busy.value) return
  busy.value = true
  try {
    await axios.delete(`${import.meta.env.VITE_HTTP_URL}/scheduled-start`)
    scheduled_start_at.value = null
  } catch (error) {
    message.error(error.response?.data?.error || '取消定时启动失败')
  } finally {
    busy.value = false
  }
}

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
  schedule(Math.ceil((target.getTime() - Date.now()) / 1000))
}

function select(key) {
  if (key === 'custom') openModal()
  else if (key === 'cancel') cancel()
  else if (key === 'start') props.start('2')
  else props.start(key)
}
</script>

<template>
  <drop-down
    :select="select"
    :options="scheduled_start_at ? scheduledOptions : startOptions"
    type="primary"
    :up="true"
  >
    <n-button
      v-if="scheduled_start_at"
      type="primary"
      :loading="busy"
      :disabled="busy"
      @click="openModal"
    >
      <template #icon
        ><n-icon><alarm-outline /></n-icon
      ></template>
      <span>{{ countdown }}</span>
    </n-button>
    <n-button
      v-else
      type="primary"
      @click="start('0')"
      :loading="waiting || busy"
      :disabled="waiting || busy"
    >
      <template #icon
        ><n-icon><play-icon /></n-icon
      ></template>
      <span class="start-label">开始执行</span>
    </n-button>
  </drop-down>
  <n-modal
    v-model:show="showModal"
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
        <n-button @click="showModal = false">取消</n-button>
        <n-button type="primary" :loading="busy" @click="confirm">确定</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<style scoped>
@container main-content (max-width: 500px) {
  .start-label {
    display: none;
  }
}

@supports not (container-type: inline-size) {
  @media (max-width: 500px) {
    .start-label {
      display: none;
    }
  }
}
</style>
