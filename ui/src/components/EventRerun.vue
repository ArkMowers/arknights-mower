<script setup>
import { inject, onMounted, onUnmounted, ref, watch } from 'vue'
import StageProgressButton from './StageProgressButton.vue'
import { useResourceVersionStore } from '@/stores/resourceVersion'

const resourceVersion = useResourceVersionStore()
const axios = inject('axios')
const statusUrl = `${import.meta.env.VITE_HTTP_URL || ''}/stage/event-rerun`
const event = ref(null)
const progress = ref({})
const failureReasons = ref({})
const retryableFailures = ref(null)
const loaded = ref(false)
const loadError = ref('')
const saving = ref(false)
const saveError = ref('')
let statusRequest
let timer

function applyStatus(data) {
  event.value = data.event
  progress.value = data.progress
  failureReasons.value = data.failure_reasons ?? {}
  retryableFailures.value = data.retryable_failures ?? null
  loadError.value = ''
}

function failureRetryHint(stage) {
  if (!retryableFailures.value) return ''
  return retryableFailures.value.includes(stage)
    ? '下次刷理智时会自动重试'
    : '需手动处理，点击关卡可更改状态'
}

async function refreshStatus() {
  if (saving.value) return
  if (statusRequest) return statusRequest
  statusRequest = (async () => {
    try {
      applyStatus((await axios.get(statusUrl)).data)
    } catch (error) {
      loadError.value = error.response?.data?.message || '读取复刻SS活动失败'
    } finally {
      loaded.value = true
    }
  })()
  try {
    await statusRequest
  } finally {
    statusRequest = null
  }
}

async function setCompleted(stage, completed) {
  if (saving.value || !event.value || progress.value[stage] === 'running') return
  const change = {
    event_key: event.value.key,
    stage,
    expected: progress.value[stage] || 'pending',
    completed
  }
  saving.value = true
  saveError.value = ''
  try {
    await statusRequest
    applyStatus((await axios.patch(statusUrl, change)).data)
  } catch (error) {
    saveError.value = error.response?.data?.message || '保存关卡状态失败'
  } finally {
    saving.value = false
  }
  if (saveError.value) await refreshStatus()
}

onMounted(() => {
  refreshStatus()
  timer = setInterval(refreshStatus, 5000)
})
onUnmounted(() => clearInterval(timer))
watch(() => resourceVersion.info.current_version, refreshStatus)
</script>

<template>
  <n-alert v-if="loadError" type="error">{{ loadError }}</n-alert>
  <n-text v-else-if="!loaded" depth="3">正在读取复刻SS活动</n-text>
  <n-text v-else-if="!event?.stages.length" depth="3"
    >当前没有开放的复刻普通战斗关，照常执行周计划。</n-text
  >
  <template v-else>
    <n-text>{{ event.name }}</n-text>
    <n-flex>
      <div v-for="stage in event.stages" :key="stage.code" class="rerun-stage">
        <StageProgressButton
          :stage="stage.code"
          :status="progress[stage.code] || 'pending'"
          :disabled="saving"
          @set-completed="setCompleted(stage.code, $event)"
        />
        <div
          v-if="
            progress[stage.code] === 'failed' && (failureReasons[stage.code] || retryableFailures)
          "
          class="rerun-failure"
        >
          <n-text v-if="failureReasons[stage.code]" type="warning">
            {{ failureReasons[stage.code] }}
          </n-text>
          <n-text v-if="retryableFailures" depth="2">{{ failureRetryHint(stage.code) }}</n-text>
        </div>
      </div>
    </n-flex>
  </template>
  <n-alert v-if="saveError" type="error">{{ saveError }}</n-alert>
</template>

<style scoped>
.rerun-stage {
  max-width: 100%;
}
.rerun-failure {
  display: grid;
  margin-top: 4px;
  max-width: 26em;
  overflow-wrap: anywhere;
  font-size: 13px;
}
</style>
