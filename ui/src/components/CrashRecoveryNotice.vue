<script setup>
import { inject, onMounted, onUnmounted, ref, watch } from 'vue'
import RefreshOutline from '@vicons/ionicons5/es/RefreshOutline'
import { createCrashRecovery } from '@/utils/crashRecovery'
import StatusNotification from '@/components/StatusNotification.vue'

const recovery = createCrashRecovery({
  axios: inject('axios'),
  base: import.meta.env.VITE_HTTP_URL || ''
})
const { status, busy, error } = recovery
const notificationVisible = ref(false)
const notificationKey = ref(0)
let lastOccurrence

watch(status, (current) => {
  if (!current.active) notificationVisible.value = false
  if (current.occurred_at) {
    if (lastOccurrence && current.occurred_at !== lastOccurrence) {
      notificationVisible.value = false
      notificationKey.value++
    }
    lastOccurrence = current.occurred_at
  }
  if (current.active && (current.automatic !== false || current.phase === 'failed')) {
    notificationVisible.value = true
  }
})

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
  <StatusNotification
    :key="notificationKey"
    :show="notificationVisible"
    :type="status.phase === 'failed' || status.automatic === false ? 'warning' : 'info'"
    :title="
      status.phase === 'failed'
        ? '自动恢复已暂停'
        : status.startup
          ? status.automatic === false
            ? '启动已停止'
            : '正在启动'
          : status.automatic === false
            ? '自动恢复已停止'
            : '正在自动恢复'
    "
  >
    <n-space vertical :size="8">
      <n-text v-if="status.phase === 'failed'">
        多次恢复后仍然失败，已保留未完成任务。检查错误后，可使用开始按钮继续。
      </n-text>
      <n-text v-else-if="status.automatic !== false && status.startup">
        启动前正在重新读取设备、驻员和心情，保存后按所选方式开始调度；暂时失败时会等待并重试。
      </n-text>
      <n-text v-else-if="status.automatic !== false">
        程序发生异常后会自动重新读取设备、驻员和心情，再继续调度；暂时失败时会等待并重试。
      </n-text>
      <n-text v-else>任务已停止。需要继续时，可使用原有的开始按钮。</n-text>
      <n-text v-if="status.message" depth="3">{{ status.message }}</n-text>
      <n-text v-if="status.trigger_message && !status.startup" depth="3">
        触发原因：{{ status.trigger_message }}
      </n-text>
      <n-text
        v-if="
          !status.startup &&
          status.last_failure_message &&
          status.last_failure_message !== status.trigger_message
        "
        depth="3"
      >
        最近一次失败：{{ status.last_failure_message }}
      </n-text>
      <n-text v-if="error" type="error">{{ error }}</n-text>
    </n-space>
    <template #action>
      <n-button size="small" :loading="busy" class="recovery-refresh" @click="recovery.refresh">
        <template #icon><RefreshOutline /></template>
        刷新状态
      </n-button>
    </template>
  </StatusNotification>
</template>

<style scoped>
.recovery-refresh {
  width: 112px;
}
</style>
