<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { useConfigStore } from '@/stores/config'
import { sameDeviceProfile } from '@/utils/deviceSettings'

const props = defineProps({ disabled: { type: Boolean, default: false } })
const emit = defineEmits(['running'])
const config = useConfigStore()
const axios = inject('axios')
const base = `${import.meta.env.VITE_HTTP_URL || ''}/device/performance-test`
const labels = { xhigh: '极高', high: '高', medium: '中', low: '低' }
const job = ref({ status: 'idle' })
const pending = ref(false)
const error = ref('')
const running = computed(() => job.value.status === 'running')
const recommendation = computed(() => {
  const result = job.value
  if (
    result.status !== 'passed' ||
    !labels[result.recommended_mode] ||
    !result.device ||
    !config.device_profile ||
    !sameDeviceProfile(result.device, config.device_profile) ||
    !result.timing ||
    Object.entries(result.timing).some(([key, value]) => config[key] !== value)
  )
    return null
  return result.recommended_mode
})
const progress = computed(() => {
  const result = job.value
  if (running.value && result.phase === 'cleanup') return '正在取消暂选并退出选人页…'
  if (running.value && result.mode) {
    return `${labels[result.mode]}档 · 第 ${result.round}/3 次选人测试 · ${result.phase === 'preparing' ? '准备目标' : '连续滑动后选人及校验'}`
  }
  return result.message || ''
})
let timer
let disposed = false
let revision = 0

watch(running, (value) => emit('running', value), { immediate: true })

async function readStatus() {
  if (pending.value) return
  const current = revision
  try {
    const response = await axios.get(base)
    if (!disposed && current === revision) job.value = response.data
  } catch (reason) {
    if (!disposed && current === revision)
      error.value = reason.response?.data?.message || '读取性能测试状态失败'
  }
}

async function start() {
  if (props.disabled || pending.value || running.value) return
  pending.value = true
  error.value = ''
  ++revision
  try {
    // Save completion precedes device input, including a recently edited timing value.
    await config.save_config()
    if (disposed) return
    const response = await axios.post(base, {})
    if (!disposed) job.value = response.data
  } catch (reason) {
    if (!disposed)
      error.value = reason.response?.data?.message || reason.message || '游戏内性能测试启动失败'
  } finally {
    pending.value = false
  }
}

async function cancel() {
  if (pending.value || !running.value) return
  pending.value = true
  ++revision
  try {
    const response = await axios.delete(base, { data: { id: job.value.id } })
    if (!disposed) job.value = response.data
  } catch (reason) {
    if (!disposed) error.value = reason.response?.data?.message || '取消性能测试失败'
  } finally {
    pending.value = false
  }
}

function adopt() {
  if (props.disabled || running.value || !recommendation.value) return
  config.performance_mode = recommendation.value
}

onMounted(() => {
  void readStatus()
  timer = setInterval(readStatus, 1500)
})
onUnmounted(() => {
  disposed = true
  clearInterval(timer)
})
</script>

<template>
  <n-space vertical :size="8">
    <n-space align="center">
      <n-button
        v-if="!running"
        secondary
        size="small"
        :disabled="disabled || pending"
        :loading="pending"
        @click="start"
      >
        游戏内性能测试
      </n-button>
      <n-button
        v-else
        secondary
        size="small"
        :disabled="pending || job.phase === 'cleanup'"
        @click="cancel"
      >
        取消测试
      </n-button>
      <help-text>
        请停止任务并先保存设备设置。测试使用 Mower 的启动与导航流程，
        启动所选模拟器和游戏并进入基建；已在基建时继续进入宿舍一。
        登录验证或协议确认需先在游戏中手动完成。
        从极高档开始，每次测试先连续滑动三次，再选人并校验。
        每次选人独立计为一次测试，每档连续三次测试通过才推荐；一次失败立即降档重测。
        同时检查实际选中名单与重排结果。测试会取消暂选，不确认换人。
        测试期间请勿操作游戏，可随时取消。测试不设总时限，建议仅用于当前设备和时间参数。
      </help-text>
      <n-tag v-if="recommendation" size="small" :bordered="false"
        >实测建议：{{ labels[recommendation] }}</n-tag
      >
      <n-button
        v-if="recommendation && config.performance_mode !== recommendation"
        size="small"
        secondary
        :disabled="disabled || pending"
        @click="adopt"
      >
        采用建议
      </n-button>
    </n-space>
    <n-text v-if="progress" depth="3" role="status" aria-live="polite">{{ progress }}</n-text>
    <n-text v-if="job.status === 'passed' && !recommendation" depth="3"
      >设备或时间参数已变化，请重新测试。</n-text
    >
    <n-text
      v-for="trial in job.trials || []"
      :key="`${trial.mode}-${trial.round}`"
      :type="trial.ok ? 'success' : 'warning'"
      depth="3"
    >
      {{ labels[trial.mode] }}档第 {{ trial.round }} 次选人：{{ trial.ok ? '通过' : trial.message }}
    </n-text>
    <n-text v-if="error" type="error" role="alert">{{ error }}</n-text>
  </n-space>
</template>
