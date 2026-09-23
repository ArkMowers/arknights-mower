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
const mode = ref('datetime')
const date = ref(Date.now())
const time = ref(Date.now())
const hours = ref(0)
const minutes = ref(30)
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
  hours.value = 0
  minutes.value = 30
  mode.value = 'datetime'
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
    message.error(error.response?.data?.error || '设置定时启动失败')
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
  if (mode.value === 'delay') {
    schedule(((hours.value || 0) * 60 + (minutes.value || 0)) * 60)
    return
  }
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
  else if (key === 'start') props.start('0')
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
    <n-tabs v-model:value="mode" type="segment">
      <n-tab-pane name="datetime" tab="指定时间">
        <n-space vertical>
          <n-date-picker v-model:value="date" type="date" style="width: 100%" />
          <n-time-picker v-model:value="time" style="width: 100%" />
        </n-space>
      </n-tab-pane>
      <n-tab-pane name="delay" tab="等待时长">
        <n-space>
          <n-input-number v-model:value="hours" :min="0" :max="720" style="width: 120px">
            <template #suffix>小时</template>
          </n-input-number>
          <n-input-number v-model:value="minutes" :min="0" :max="59" style="width: 120px">
            <template #suffix>分钟</template>
          </n-input-number>
        </n-space>
      </n-tab-pane>
    </n-tabs>
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
