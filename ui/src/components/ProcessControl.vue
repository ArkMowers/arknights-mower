<script setup>
import { inject, onMounted, onUnmounted, ref } from 'vue'
import { useConfigStore } from '@/stores/config'

const axios = inject('axios')
const config = useConfigStore()
const base = `${import.meta.env.VITE_HTTP_URL || ''}/process-control`
const info = ref(null)
const busy = ref(false)
const message = ref('')
const failed = ref(false)
const pendingKey = `mower-process-control:${base}`
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
      if (!failed.value && pending.action === 'restart') window.location.reload()
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
      message.value = '当前实例连接已关闭，可关闭此页面'
      sessionStorage.removeItem(pendingKey)
      return
    }
    message.value = '当前实例正在重启，等待重新连接…'
  }
  if (!disposed) timer = setTimeout(() => poll(pending), 1000)
}

async function submit(action) {
  busy.value = true
  failed.value = false
  try {
    await config.save_config()
    const { data } = await axios.post(
      `${base}/action`,
      { action },
      { headers: { 'X-Mower-Control': '1' } }
    )
    if (!data.ok) throw new Error(data.message)
    const pending = { id: data.id, action, startedAt: Date.now() }
    sessionStorage.setItem(pendingKey, JSON.stringify(pending))
    message.value = data.message
    await poll(pending)
  } catch (error) {
    busy.value = false
    failed.value = true
    message.value = errorMessage(error)
  }
}

onMounted(async () => {
  try {
    const { data } = await axios.get(`${base}/info`)
    if (!data.ok) throw new Error(data.message)
    info.value = data
    if (data.message) message.value = data.message
    const pending = JSON.parse(sessionStorage.getItem(pendingKey) || 'null')
    if (pending) {
      busy.value = true
      await poll(pending)
    }
  } catch (error) {
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
  <n-card title="进程操作">
    <n-space vertical>
      <n-text depth="3"
        >仅操作当前实例{{
          info?.name ? `（${info.name}）` : ''
        }}，其他实例和多开管理器不受影响。</n-text
      >
      <n-space>
        <n-popconfirm
          style="max-width: min(360px, calc(100vw - 32px))"
          @positive-click="submit('restart')"
        >
          <template #trigger>
            <n-button size="small" :disabled="busy || !info?.supported">重启 Mower 进程</n-button>
          </template>
          重启当前实例，保留名称、数据目录、端口和启动参数；原本运行中的任务将重置运行缓存后重新开始。
        </n-popconfirm>
        <n-popconfirm
          style="max-width: min(360px, calc(100vw - 32px))"
          @positive-click="submit('stop')"
        >
          <template #trigger>
            <n-button size="small" type="error" secondary :disabled="busy || !info?.supported"
              >结束 Mower 进程</n-button
            >
          </template>
          正常停止当前任务并结束此实例，网页连接将断开。
        </n-popconfirm>
      </n-space>
      <n-alert v-if="message" :type="failed ? 'error' : 'info'" aria-live="polite">{{
        message
      }}</n-alert>
    </n-space>
  </n-card>
</template>
