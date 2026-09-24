<script setup>
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { createSaveCoordinator } from '@/utils/configPersistence'

const props = defineProps({
  compact: { type: Boolean, default: false },
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
  return error.response?.data?.message || error.message || '进程操作失败'
}

async function poll(pending) {
  if (disposed) return
  if (Date.now() - pending.startedAt > 240000) {
    busy.value = false
    failed.value = true
    message.value = '操作等待超时，请检查当前实例及进程操作日志'
    sessionStorage.removeItem(pendingKey)
    return
  }
  try {
    const { data } = await axios.get(`${base}/status`, {
      params: { id: pending.id },
      timeout: 3000
    })
    if (!data.ok) throw new Error(data.message)
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
      message.value = '当前实例连接已关闭，可关闭此页面'
      sessionStorage.removeItem(pendingKey)
      return
    }
    message.value = '当前实例正在重启，等待重新连接…'
  }
  if (!disposed) timer = setTimeout(() => poll(pending), 1000)
}

async function submit(action) {
  if (busy.value || savesPaused.value) return
  let mayHaveSubmitted = false
  busy.value = true
  failed.value = false
  try {
    await saves.pauseAndDrain()
    // Once submitted, a lost response does not prove the restart was rejected.
    // Keep autosave paused until a fresh page reads the destination's config.
    mayHaveSubmitted = true
    const { data } = await axios.post(
      `${base}/action`,
      { action },
      { headers: { 'X-Mower-Control': '1' } }
    )
    if (!data.ok) {
      mayHaveSubmitted = false
      throw new Error(data.message)
    }
    const pending = { id: data.id, action, startedAt: Date.now() }
    sessionStorage.setItem(pendingKey, JSON.stringify(pending))
    message.value = data.message
    await poll(pending)
  } catch (error) {
    busy.value = false
    failed.value = true
    message.value = errorMessage(error)
    if (!mayHaveSubmitted || (error.response?.status >= 400 && error.response.status < 500)) {
      saves.resume()
    }
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
    <n-popconfirm
      v-if="!effectiveRunning"
      style="max-width: min(360px, calc(100vw - 32px))"
      @positive-click="submit('restart')"
    >
      <template #trigger>
        <n-button
          class="quick-run-btn"
          :loading="busy"
          :disabled="busy || savesPaused || !info?.supported"
          :title="failed ? message : ''"
        >
          重启程序
        </n-button>
      </template>
      保存当前配置后重启当前实例，不自动开始任务。
    </n-popconfirm>
    <n-text v-else-if="busy" depth="3" aria-live="polite">正在重启…</n-text>
    <n-space v-if="failed" align="center">
      <n-text type="error" aria-live="polite">{{ message }}</n-text>
      <n-button v-if="savesPaused" size="small" @click="reload">刷新页面</n-button>
    </n-space>
  </template>
  <n-card v-else title="进程操作">
    <n-space vertical>
      <n-text depth="3">
        仅操作当前实例{{ info?.name ? `（${info.name}）` : '' }}，其他实例和多开管理器不受影响。
      </n-text>
      <n-space>
        <n-popconfirm
          v-if="info?.running"
          style="max-width: min(360px, calc(100vw - 32px))"
          @positive-click="submit('restart_resume')"
        >
          <template #trigger>
            <n-button size="small" type="info" :disabled="busy || savesPaused || !info?.supported">
              重启续接
            </n-button>
          </template>
          保存当前配置后重启当前实例，并保留任务队列继续运行。
        </n-popconfirm>
        <n-popconfirm
          style="max-width: min(360px, calc(100vw - 32px))"
          @positive-click="submit('restart')"
        >
          <template #trigger>
            <n-button size="small" :disabled="busy || savesPaused || !info?.supported">
              重启 Mower 进程
            </n-button>
          </template>
          重启当前实例，保留名称、数据目录、端口和启动参数；原本运行中的任务将重置运行缓存后重新开始。
        </n-popconfirm>
        <n-popconfirm
          style="max-width: min(360px, calc(100vw - 32px))"
          @positive-click="submit('stop')"
        >
          <template #trigger>
            <n-button
              size="small"
              type="error"
              secondary
              :disabled="busy || savesPaused || !info?.supported"
            >
              结束 Mower 进程
            </n-button>
          </template>
          正常停止当前任务并结束此实例，网页连接将断开。
        </n-popconfirm>
      </n-space>
      <n-alert v-if="savesPaused" type="info">
        配置自动保存已暂停。配置导入或进程操作结束后，请刷新页面重新读取配置再编辑。
        <n-button v-if="!busy" size="small" @click="reload">刷新页面</n-button>
      </n-alert>
      <n-alert v-if="message" :type="failed ? 'error' : 'info'" aria-live="polite">
        {{ message }}
      </n-alert>
    </n-space>
  </n-card>
</template>

<style scoped>
.quick-run-btn {
  width: 108px;
  flex: 0 0 108px;
}
</style>
