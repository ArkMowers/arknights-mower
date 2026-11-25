<script setup>
import { inject, onMounted, onUnmounted, ref, watch } from 'vue'
import StageProgressButton from './StageProgressButton.vue'
import { useResourceVersionStore } from '@/stores/resourceVersion'

const resourceVersion = useResourceVersionStore()
const axios = inject('axios')
const statusUrl = `${import.meta.env.VITE_HTTP_URL || ''}/stage/event-rerun`
const event = ref(null)
const progress = ref({})
const loaded = ref(false)
const loadError = ref('')
const saving = ref(false)
const saveError = ref('')
let statusRequest
let timer

function applyStatus(data) {
  event.value = data.event
  progress.value = data.progress
  loadError.value = ''
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
      <StageProgressButton
        v-for="stage in event.stages"
        :key="stage.code"
        :stage="stage.code"
        :status="progress[stage.code] || 'pending'"
        :disabled="saving"
        @set-completed="setCompleted(stage.code, $event)"
      />
    </n-flex>
  </template>
  <n-alert v-if="saveError" type="error">{{ saveError }}</n-alert>
</template>
