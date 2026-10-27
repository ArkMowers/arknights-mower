<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

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
  if (current.active && current.automatic !== false) notificationVisible.value = true
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
    :type="status.automatic === false ? 'warning' : 'info'"
    :title="
      status.startup
        ? status.automatic === false
          ? t('runtime.startupStopped')
          : t('runtime.starting')
        : status.automatic === false
          ? t('runtime.recoveryStopped')
          : t('runtime.recovering')
    "
  >
    <n-space vertical :size="8">
      <n-text v-if="status.automatic !== false && status.startup">{{
        t('runtime.startupRecoveryHelp')
      }}</n-text>
      <n-text v-else-if="status.automatic !== false">{{
        t('runtime.automaticRecoveryHelp')
      }}</n-text>
      <n-text v-else>{{ t('runtime.recoveryStoppedHelp') }}</n-text>
      <n-text v-if="status.message" depth="3">{{ status.message }}</n-text>
      <n-text v-if="status.trigger_message && !status.startup" depth="3"
        >{{ t('runtime.triggerPrefix') }}{{ status.trigger_message }}
      </n-text>
      <n-text
        v-if="
          !status.startup &&
          status.last_failure_message &&
          status.last_failure_message !== status.trigger_message
        "
        depth="3"
        >{{ t('runtime.lastFailurePrefix') }}{{ status.last_failure_message }}
      </n-text>
      <n-text v-if="error" type="error">{{ error }}</n-text>
    </n-space>
    <template #action>
      <n-button size="small" :loading="busy" class="recovery-refresh" @click="recovery.refresh">
        <template #icon><RefreshOutline /></template>{{ t('runtime.refreshStatus') }}</n-button
      >
    </template>
  </StatusNotification>
</template>

<style scoped>
.recovery-refresh {
  width: 112px;
}
</style>
