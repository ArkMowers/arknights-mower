<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { useConfigStore } from '@/stores/config'
import { sameDeviceProfile } from '@/utils/deviceSettings'
import { createScreenshotPreview } from '@/utils/screenshotPreview'

const props = defineProps({ disabled: { type: Boolean, default: false } })
const emit = defineEmits(['running'])
const config = useConfigStore()
const axios = inject('axios')
const base = `${import.meta.env.VITE_HTTP_URL || ''}/device/performance-test`
const labels = computed(() => ({
  xhigh: t('devices.xhigh'),
  high: t('devices.high'),
  medium: t('devices.medium'),
  low: t('devices.low')
}))
const job = ref({ status: 'idle' })
const pending = ref(false)
const error = ref('')
const screenshot = ref('')
const running = computed(() => job.value.status === 'running')
const recommendation = computed(() => {
  const result = job.value
  if (
    result.status !== 'passed' ||
    !labels.value[result.recommended_mode] ||
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
  if (running.value && result.phase === 'cleanup') return t('devices.cleanup')
  if (running.value && result.mode) {
    return t('devices.testProgress', {
      mode: labels.value[result.mode],
      round: result.round,
      phase: result.phase === 'preparing' ? t('devices.preparing') : t('devices.testingSelection')
    })
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
      error.value = reason.response?.data?.message || t('devices.performanceStatusFailed')
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
      error.value =
        reason.response?.data?.message || reason.message || t('devices.performanceStartFailed')
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
    if (!disposed)
      error.value = reason.response?.data?.message || t('devices.performanceCancelFailed')
  } finally {
    pending.value = false
  }
}

function adopt() {
  if (config.manager_owned_device || props.disabled || running.value || !recommendation.value)
    return
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
        {{ t('devices.performanceTest') }}
      </n-button>
      <n-button
        v-else
        secondary
        size="small"
        :disabled="pending || job.phase === 'cleanup'"
        @click="cancel"
      >
        {{ t('devices.cancelTest') }}
      </n-button>
      <help-text> {{ t('devices.testHelp') }} </help-text>
      <n-tag v-if="recommendation" size="small" :bordered="false">
        {{ t('devices.recommendationPrefix') }} {{ labels[recommendation] }}</n-tag
      >
      <n-button
        v-if="
          !config.manager_owned_device &&
          recommendation &&
          config.performance_mode !== recommendation
        "
        size="small"
        secondary
        :disabled="disabled || pending"
        @click="adopt"
      >
        {{ t('devices.adopt') }}
      </n-button>
      <n-text v-if="config.manager_owned_device && recommendation" depth="3">
        {{ t('devices.managedRecommendation') }}
      </n-text>
    </n-space>
    <n-text v-if="progress" depth="3" role="status" aria-live="polite">{{ progress }}</n-text>
    <div v-if="running" class="performance-test-preview">
      <n-image
        v-if="screenshot"
        :src="screenshot"
        :alt="t('devices.testScreenshot')"
        object-fit="contain"
        class="performance-test-image"
      />
      <n-text v-else depth="3"> {{ t('devices.waitingScreenshot') }} </n-text>
    </div>
    <n-text v-if="job.status === 'passed' && !recommendation" depth="3">
      {{ t('devices.testChanged') }}
    </n-text>
    <n-text
      v-for="trial in job.trials || []"
      :key="`${trial.mode}-${trial.round}`"
      :type="trial.ok ? 'success' : 'warning'"
      depth="3"
    >
      {{
        t('devices.trialResult', {
          mode: labels[trial.mode],
          round: trial.round,
          result: trial.ok ? t('devices.passed') : trial.message
        })
      }}
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
