<script setup>
import { inject, onMounted, onUnmounted } from 'vue'
import { createCrashRecovery } from '@/utils/crashRecovery'

const recovery = createCrashRecovery({
  axios: inject('axios'),
  base: import.meta.env.VITE_HTTP_URL || ''
})
const { status, busy, error } = recovery
let timer
let disposed = false

async function poll() {
  await recovery.refresh()
  if (!disposed) timer = setTimeout(poll, status.value.active ? 3000 : 15000)
}

onMounted(poll)
onUnmounted(() => {
  disposed = true
  clearTimeout(timer)
  recovery.dispose()
})
</script>

<template>
  <n-alert
    v-if="status.active"
    type="info"
    :title="status.automatic === false ? '自动恢复已停止' : '正在自动恢复'"
    role="status"
  >
    <n-space vertical :size="8">
      <n-text v-if="status.automatic !== false">
        程序发生异常后会自动重新读取设备、驻员和心情，再继续调度；暂时失败时会等待并重试。
      </n-text>
      <n-text v-else>任务已停止。需要继续时，可使用原有的开始按钮。</n-text>
      <n-text v-if="status.message" depth="3">{{ status.message }}</n-text>
      <n-button :disabled="busy" @click="recovery.refresh">刷新状态</n-button>
      <n-text v-if="error" type="error">{{ error }}</n-text>
    </n-space>
  </n-alert>
</template>
