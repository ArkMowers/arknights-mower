<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { useConfigStore } from '@/stores/config'
import { sameDeviceProfile } from '@/utils/deviceSettings'
import { createScreenshotPreview } from '@/utils/screenshotPreview'

const props = defineProps({ disabled: { type: Boolean, default: false } })
const emit = defineEmits(['running'])
const config = useConfigStore()
const axios = inject('axios')
const base = `${import.meta.env.VITE_HTTP_URL || ''}/device/performance-test`
const labels = { xhigh: '极高', high: '高', medium: '中', low: '低' }
const job = ref({ status: 'idle' })
const pending = ref(false)
const error = ref('')
const screenshot = ref('')
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
let mounted = false
let previewJobId = null
const screenshotPreview = createScreenshotPreview({
  fetchSnapshot: (options) =>
    axios.get(`${base}/screenshot`, { ...options, params: { id: previewJobId } }),
  onChange: (url) => {
    screenshot.value = url
  }
})

function updateScreenshotPreview() {
  if (!mounted) return
  const id = running.value && !document.hidden ? job.value.id : null
  if (id !== previewJobId) screenshotPreview.stop()
  previewJobId = id
  if (id) screenshotPreview.start()
  else screenshotPreview.stop()
}

watch(running, (value) => emit('running', value), { immediate: true })
watch(() => [running.value, job.value.id], updateScreenshotPreview)

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
  mounted = true
  document.addEventListener('visibilitychange', updateScreenshotPreview)
  updateScreenshotPreview()
  void readStatus()
  timer = setInterval(readStatus, 1500)
})
onUnmounted(() => {
  if (mounted) document.removeEventListener('visibilitychange', updateScreenshotPreview)
  mounted = false
  disposed = true
  clearInterval(timer)
  screenshotPreview.stop()
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
        停止任务后测试，连接设备、启动游戏并进入宿舍一；登录验证、协议确认需手动完成。
        从极高开始，每次连续滑动三次后选人并校验，连续三次通过才推荐，一次失败立即降档。
        测试不确认换人，可随时取消。期间请勿操作游戏，采用建议需手动确认。
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
    <div v-if="running" class="performance-test-preview">
      <n-image
        v-if="screenshot"
        :src="screenshot"
        alt="本次游戏性能测试画面"
        object-fit="contain"
        class="performance-test-image"
      />
      <n-text v-else depth="3">等待本次测试画面…</n-text>
    </div>
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

<style scoped>
.performance-test-preview {
  width: 100%;
  max-width: 720px;
}

.performance-test-image {
  display: block;
}

.performance-test-image :deep(img) {
  width: 100%;
  max-height: 405px;
}
</style>
