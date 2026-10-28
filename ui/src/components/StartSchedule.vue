<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import AlarmOutline from '@vicons/ionicons5/es/AlarmOutline'
import PlayIcon from '@vicons/ionicons5/es/Play'
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
  {
    get label() {
      return t('runtime.scheduleStartOption')
    },
    key: 'custom'
  },
  { type: 'divider', key: 'divider' },
  ...props.startOptions
])

const scheduledOptions = [
  {
    get label() {
      return t('runtime.cancelScheduledStart')
    },
    key: 'cancel'
  },
  {
    get label() {
      return t('runtime.startNow')
    },
    key: 'start'
  }
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
    message.error(t('runtime.future30Days'))
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
        ? t('runtime.scheduledStartUnavailable')
        : error.response?.data?.error || t('runtime.scheduleStartFailed')
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
    message.error(error.response?.data?.error || t('runtime.cancelScheduledStartFailed'))
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
      <span class="start-label">{{ t('runtime.start') }}</span>
    </n-button>
  </drop-down>
  <n-modal
    v-model:show="showModal"
    preset="card"
    :title="t('runtime.scheduleStart')"
    style="width: min(420px, calc(100vw - 32px))"
  >
    <n-text depth="3" style="display: block; margin-bottom: 12px">{{
      t('runtime.scheduledStartHelp')
    }}</n-text>
    <n-space vertical>
      <n-date-picker v-model:value="date" type="date" style="width: 100%" />
      <n-time-picker v-model:value="time" style="width: 100%" />
    </n-space>
    <template #footer>
      <n-space justify="end">
        <n-button @click="showModal = false">{{ t('runtime.cancel') }}</n-button>
        <n-button type="primary" :loading="busy" @click="confirm">{{
          t('runtime.confirm')
        }}</n-button>
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
