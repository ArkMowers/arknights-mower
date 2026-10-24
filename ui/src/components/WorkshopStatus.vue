<script setup>
import { computed, onMounted, onUnmounted, watch } from 'vue'
import axios from 'axios'
import { NButton, NSpace, NText } from 'naive-ui'
import { useMowerStore } from '@/stores/mower'
import { createWorkshopStatus } from '@/utils/workshopStatus'

const props = defineProps({ revision: { type: Number, default: 0 } })
const mower = useMowerStore()
const model = createWorkshopStatus(
  axios,
  `${import.meta.env.VITE_HTTP_URL}/workshop-status`,
  () => mower.running
)
const { data, stale, loading } = model
const label = computed(() => {
  if (stale.value) return data.value ? '合成状态待刷新' : '合成状态读取失败'
  if (!data.value) return '正在读取合成状态'
  return (
    {
      idle: '暂无合成任务',
      ready: '可以合成',
      queued: '已排队',
      running: '正在合成',
      waiting: '等待合成条件',
      stopped: '调度器已停止',
      unavailable: '合成状态暂不可用'
    }[data.value.execution] || '合成状态暂不可用'
  )
})
watch([() => props.revision, () => mower.running], model.refresh)
onMounted(model.start)
onUnmounted(model.stop)
</script>

<template>
  <n-space size="small" align="center" style="margin-top: 12px" aria-live="polite">
    <n-text>{{ label }}{{ stale ? '（上次结果，读取失败）' : '' }}</n-text>
    <n-text v-if="data?.recipe" depth="3"
      >{{ data.project_name ? `${data.project_name} · ` : '' }}{{ data.recipe }}</n-text
    >
    <n-text v-for="(block, index) in data?.blockers || []" :key="index" depth="3">
      {{ block.operator ? `${block.operator}：` : '' }}{{ block.message }}
    </n-text>
    <n-button size="tiny" text :loading="loading" @click="model.refresh">刷新合成状态</n-button>
  </n-space>
</template>
