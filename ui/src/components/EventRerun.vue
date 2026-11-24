<script setup>
import { inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { useResourceVersionStore } from '@/stores/resourceVersion'

const resourceVersion = useResourceVersionStore()
const axios = inject('axios')
const base = import.meta.env.VITE_HTTP_URL || ''
const event = ref(null)
const progress = ref({})
const stageSeconds = ref(240)
const loaded = ref(false)
const loadError = ref('')
let statusRequest
let timer

function statusLabel(code) {
  if (progress.value[code] === 'completed') return '已完成'
  if (progress.value[code] === 'attempted') return '已启动，结算待确认'
  return '待执行'
}

async function refreshStatus() {
  if (statusRequest) return statusRequest
  statusRequest = (async () => {
    try {
      const { data } = await axios.get(`${base}/maa-long-task-status?kind=event_rerun`)
      event.value = data.event
      progress.value = data.progress
      stageSeconds.value = data.stage_seconds
      loadError.value = ''
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
    <n-text>{{ event.name }} · 每关预留 {{ stageSeconds / 60 }} 分钟</n-text>
    <n-flex>
      <n-tag v-for="stage in event.stages" :key="stage.code" :bordered="false">
        {{ stage.code }} · {{ statusLabel(stage.code) }}
      </n-tag>
    </n-flex>
  </template>
</template>
