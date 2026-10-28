<script setup>
import { i18n } from '@/i18n'
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { createSaveCoordinator } from '@/utils/configPersistence'
import { readProcessActionStatus, submitProcessAction } from '@/utils/processAction'

const props = defineProps({
  compact: { type: Boolean, default: false },
  resumeOnly: { type: Boolean, default: false },
  running: { default: null }
})

const axios = inject('axios')
const config = useConfigStore()
const plan = usePlanStore()
const saves = createSaveCoordinator(config, plan)
const savesPaused = saves.paused
const base = `${import.meta.env.VITE_HTTP_URL || ''}/process-control`
const info = ref(null)
const busy = ref(false)
const message = ref('')
const failed = ref(false)
const pendingKey = `mower-process-control:${base}`
const effectiveRunning = computed(() => props.running ?? info.value?.running ?? false)
const canRunProcessAction = computed(
  () => !!(effectiveRunning.value && info.value?.supported && !busy.value && !savesPaused.value)
)
let timer
let disposed = false

function errorMessage(error) {
  return (
    error.response?.data?.message ||
    error.message ||
    i18n.global.t('settings.process.processOperationFailed')
  )
}

async function poll(pending) {
  if (disposed) return
  if (Date.now() - pending.startedAt > 240000) {
    busy.value = false
    failed.value = true
    message.value = i18n.global.t('settings.process.theOperationTimedOutCheckThisInstance')
    sessionStorage.removeItem(pendingKey)
    return
  }
  try {
    const data = await readProcessActionStatus({ axios, base, pending })
    message.value = data.message
    if (data.status !== 'running') {
      busy.value = false
      failed.value = data.status === 'failed'
      sessionStorage.removeItem(pendingKey)
      if (
        !failed.value &&
        ['restart', 'restart_resume', 'apply_schedule'].includes(pending.action)
      ) {
        window.location.reload()
      }
      return
    }
  } catch (error) {
    if (error.response) {
      busy.value = false
      failed.value = true
      message.value = errorMessage(error)
      sessionStorage.removeItem(pendingKey)
      return
    }
    if (pending.action === 'stop') {
      busy.value = false
      message.value = i18n.global.t('settings.process.thisInstanceHasDisconnectedYouCanClose')
      sessionStorage.removeItem(pendingKey)
      return
    }
    message.value = i18n.global.t('settings.process.thisInstanceIsRestartingWaitingToReconnect')
  }
  if (!disposed) timer = setTimeout(() => poll(pending), 1000)
}

async function submit(action) {
  if (busy.value || savesPaused.value) return
  busy.value = true
  failed.value = false
  try {
    const { data, pending } = await submitProcessAction({
      axios,
      saves,
      action,
      base,
      pendingKey
    })
    message.value = data.message
    await poll(pending)
  } catch (error) {
    busy.value = false
    failed.value = true
    message.value = errorMessage(error)
  }
}

function applySchedule() {
  if (canRunProcessAction.value) return submit('apply_schedule')
}

function restartResume() {
  if (canRunProcessAction.value) return submit('restart_resume')
}

defineExpose({ canRunProcessAction, applySchedule, restartResume })

function reload() {
  window.location.reload()
}

onMounted(async () => {
  try {
    const pending = JSON.parse(sessionStorage.getItem(pendingKey) || 'null')
    if (pending) {
      // Re-entering Settings attaches to the same persisted operation, even
      // while the old server is offline and /info is temporarily unavailable.
      saves.pause({ pendingOperation: true })
      busy.value = true
      await poll(pending)
      return
    }
    const { data } = await axios.get(`${base}/info`)
    if (!data.ok) throw new Error(data.message)
    info.value = data
    if (data.message) message.value = data.message
  } catch (error) {
    busy.value = false
    failed.value = true
    message.value = errorMessage(error)
  }
})
onUnmounted(() => {
  disposed = true
  clearTimeout(timer)
})
</script>

<template>
  <template v-if="props.compact">
    <n-text v-if="busy" depth="3" aria-live="polite">{{
      i18n.global.t('settings.process.restarting')
    }}</n-text>
    <n-space v-if="failed" align="center">
      <n-text type="error" aria-live="polite">{{ message }}</n-text>
      <n-button v-if="savesPaused" size="small" @click="reload">{{
        i18n.global.t('settings.process.reloadPage')
      }}</n-button>
    </n-space>
  </template>
  <n-card v-else :title="i18n.global.t('settings.process.processControls')" class="process-control">
    <n-space vertical :size="16">
      <p class="process-control-summary">
        {{ i18n.global.t('settings.process.onlyThisInstance')
        }}{{ info?.name ? `（${info.name}）` : ''
        }}{{ i18n.global.t('settings.process.isAffectedOtherInstancesAndTheInstance') }}
      </p>
      <div class="process-control-actions">
        <div
          v-if="effectiveRunning"
          class="process-control-row"
          :data-settings-label="i18n.global.t('settings.process.restartResume')"
        >
          <div class="process-control-copy">
            <span>{{ i18n.global.t('settings.process.restartResume') }}</span>
            <p>
              {{ i18n.global.t('settings.process.saveTheCurrentConfigurationRestartThisInstance') }}
            </p>
          </div>
          <n-popconfirm
            style="max-width: min(360px, calc(100vw - 32px))"
            @positive-click="submit('restart_resume')"
          >
            <template #trigger>
              <n-button type="primary" :disabled="busy || savesPaused || !info?.supported">
                {{ i18n.global.t('settings.process.restartResume') }}
              </n-button>
            </template>
            {{ i18n.global.t('settings.process.saveTheCurrentConfigurationRestartThisInstance') }}
          </n-popconfirm>
        </div>
        <div
          v-if="!props.resumeOnly"
          class="process-control-row"
          :data-settings-label="i18n.global.t('settings.process.restartMowerProcess')"
        >
          <div class="process-control-copy">
            <span>{{ i18n.global.t('settings.process.restartMowerProcess') }}</span>
            <p>{{ i18n.global.t('settings.process.keepTheInstanceNameDataDirectoryPort') }}</p>
          </div>
          <n-popconfirm
            style="max-width: min(360px, calc(100vw - 32px))"
            @positive-click="submit('restart')"
          >
            <template #trigger>
              <n-button :disabled="busy || savesPaused || !info?.supported">
                {{ i18n.global.t('settings.process.restartMowerProcess') }}
              </n-button>
            </template>
            {{ i18n.global.t('settings.process.restartThisInstanceKeepingItsNameData') }}
          </n-popconfirm>
        </div>
        <div
          v-if="!props.resumeOnly"
          class="process-control-row"
          :data-settings-label="i18n.global.t('settings.process.stopMowerProcess')"
        >
          <div class="process-control-copy">
            <span>{{ i18n.global.t('settings.process.stopMowerProcess') }}</span>
            <p>{{ i18n.global.t('settings.process.stopTheCurrentTaskNormallyAndExit') }}</p>
          </div>
          <n-popconfirm
            style="max-width: min(360px, calc(100vw - 32px))"
            @positive-click="submit('stop')"
          >
            <template #trigger>
              <n-button type="error" secondary :disabled="busy || savesPaused || !info?.supported">
                {{ i18n.global.t('settings.process.stopMowerProcess') }}
              </n-button>
            </template>
            {{ i18n.global.t('settings.process.stopTheCurrentTaskNormallyAndExit') }}
          </n-popconfirm>
        </div>
      </div>
      <n-text v-if="props.resumeOnly && !effectiveRunning" depth="3">
        {{ i18n.global.t('settings.process.noTaskIsRunningSoRestartAnd') }}
      </n-text>
      <n-alert v-if="savesPaused" type="info">
        {{ i18n.global.t('settings.process.configurationAutosaveIsPausedAfterTheImport') }}
        <n-button v-if="!busy" size="small" @click="reload">{{
          i18n.global.t('settings.process.reloadPage')
        }}</n-button>
      </n-alert>
      <n-alert v-if="message" :type="failed ? 'error' : 'info'" aria-live="polite">
        {{ message }}
      </n-alert>
    </n-space>
  </n-card>
</template>

<style>
.process-control {
  container: process-control / inline-size;
}

.process-control-summary {
  margin: 0;
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.process-control-actions {
  display: grid;
}

.process-control-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 16px 0;
}

.process-control-row:first-child {
  padding-top: 0;
}

.process-control-row:last-child {
  padding-bottom: 0;
}

.process-control-row + .process-control-row {
  border-top: 1px solid var(--settings-card-border);
}

.process-control-copy {
  min-width: 0;
  font-size: 14px;
}

.process-control-copy p {
  margin: 4px 0 0;
  color: var(--mower-text-muted);
  font-size: 12px;
  line-height: 1.65;
  overflow-wrap: anywhere;
  text-wrap: pretty;
}

.process-control-row > .n-button {
  flex: none;
}

@container process-control (max-width: 400px) {
  .process-control-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }
}
</style>
