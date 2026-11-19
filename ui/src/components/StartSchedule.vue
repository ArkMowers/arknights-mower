<script setup>
import { computed, defineAsyncComponent, inject, onMounted, onUnmounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMessage } from 'naive-ui'
import AlarmOutline from '@vicons/ionicons5/es/AlarmOutline'
import PlayIcon from '@vicons/ionicons5/es/PlayOutline'
import { useMowerStore } from '@/stores/mower'
import { useHalloweenSeason } from '@/composables/halloween'

const ScheduledStartDialog = defineAsyncComponent(() => import('./ScheduledStartDialog.vue'))
const halloweenActive = useHalloweenSeason()
const halloweenButtonTheme = computed(() =>
  halloweenActive.value
    ? {
        colorPrimary: '#f0bb76',
        colorHoverPrimary: '#facd90',
        colorPressedPrimary: '#dca45e',
        colorFocusPrimary: '#facd90',
        textColorPrimary: '#35291f',
        textColorHoverPrimary: '#35291f',
        textColorPressedPrimary: '#35291f',
        textColorFocusPrimary: '#35291f',
        textColorGhostPrimary: '#b77b38',
        textColorGhostHoverPrimary: '#986127',
        textColorGhostPressedPrimary: '#825020',
        borderPrimary: '1px solid #c89351',
        borderHoverPrimary: '1px solid #d9a15c',
        borderPressedPrimary: '1px solid #b57d39',
        borderFocusPrimary: '1px solid #d9a15c',
        rippleColorPrimary: '#dca45e'
      }
    : undefined
)

const props = defineProps({
  start: { type: Function, required: true },
  startOptions: { type: Array, required: true },
  waiting: { type: Boolean, default: false },
  glassMenu: { type: Boolean, default: false }
})

const axios = inject('axios')
const message = useMessage()
const { scheduled_start_at } = storeToRefs(useMowerStore())
const now = ref(Date.now())
const showModal = ref(false)
const dialogMounted = ref(false)
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
  dialogMounted.value = true
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

function select(key) {
  if (key === 'custom') openModal()
  else if (key === 'cancel') cancel()
  else if (key === 'start') props.start('2')
  else props.start(key)
}
</script>

<template>
  <n-config-provider :theme-overrides="{ Button: halloweenButtonTheme }" class="start-schedule">
    <drop-down
      :select="select"
      :options="scheduled_start_at ? scheduledOptions : startOptions"
      type="primary"
      :up="true"
      :glass-menu="glassMenu"
      :class="{ 'halloween-start': halloweenActive }"
    >
      <n-button
        v-if="scheduled_start_at"
        type="primary"
        :loading="busy"
        :disabled="busy"
        :theme-overrides="halloweenButtonTheme"
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
        :theme-overrides="halloweenButtonTheme"
        :class="{ 'halloween-start__button': halloweenActive }"
        aria-label="开始执行"
      >
        <template #icon
          ><n-icon><play-icon /></n-icon
        ></template>
        <span class="start-label">开始执行</span>
      </n-button>
    </drop-down>
  </n-config-provider>
  <ScheduledStartDialog
    v-if="dialogMounted"
    v-model:show="showModal"
    :scheduled-start-at="scheduled_start_at"
    :busy="busy"
    @schedule="schedule"
  />
</template>

<style scoped>
.start-schedule {
  display: inline-flex;
}
.halloween-start__button {
  box-shadow:
    inset 0 1px 0 #ffe5b680,
    0 2px 8px #c58b2926;
}
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
