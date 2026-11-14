import { defineStore } from 'pinia'
import ReconnectingWebSocket from 'reconnecting-websocket'
import { computed, onScopeDispose, ref, toRaw, watch } from 'vue'

import axios from 'axios'

// 旧后端未提供绝对时间时，继续从 asctime 文本读取日志时间。
function parseLogTime(value) {
  if (typeof value !== 'string' || !value) return null
  const parsed = Date.parse(value.replace(',', '.').replace(' ', 'T'))
  return Number.isFinite(parsed) ? parsed : null
}

const LEGACY_LOG_SOURCE_LIMIT = 2000
const LEGACY_LOG_BYTE_LIMIT = 4 * 1024 ** 2
const logEncoder = new TextEncoder()
const legacyLogLineBytes = new WeakMap()

function boundLegacyLogLines(lines) {
  let first = lines.length
  let bytes = 2
  while (first > 0 && lines.length - first < LEGACY_LOG_SOURCE_LIMIT) {
    const line = toRaw(lines[first - 1])
    let size = legacyLogLineBytes.get(line)
    if (size === undefined) {
      size = logEncoder.encode(JSON.stringify(line)).byteLength
      if (line && typeof line === 'object') legacyLogLineBytes.set(line, size)
    }
    const separator = first < lines.length ? 1 : 0
    if (bytes + size + separator > LEGACY_LOG_BYTE_LIMIT) break
    bytes += size + separator
    first -= 1
  }
  return lines.slice(first)
}

export const useMowerStore = defineStore('mower', () => {
  const log_lines = ref([])
  let nextLogId = 0
  let logStreamId = null
  let lastLogSequence = 0

  const log = computed(() => {
    return log_lines.value.map((line) => (typeof line === 'string' ? line : line.text)).join('\n')
  })

  const num_reg = /^[0-9].*/
  const log_mobile = computed(() => {
    const result = []
    for (const line of log_lines.value) {
      const text = typeof line === 'string' ? line : line.text
      if (text.match(num_reg)) {
        result.push(text.substring(24))
      } else {
        result.push(text)
      }
    }
    return result.join('\n')
  })

  const ws = ref(null)
  const running = ref(false)
  const status = ref('stopped')
  const status_label = computed(() =>
    !running.value
      ? '已停止'
      : ({ starting: '启动中', recovering: '等待设备恢复', sleeping: '休眠中' }[status.value] ??
        '运行中')
  )
  const scheduled_start_at = ref(null)
  const stop_after_round = ref(false)
  const maintenance_pause = ref(null)
  const auto_start_handled = ref(false)
  const desktop_startup_handled = ref(false)
  const ai_assistant_enabled = ref(null)
  const updates_enabled = ref(null)
  const deployment = ref(null)
  const plan_condition = ref([])
  const waiting = ref(false)

  const first_load = ref(true)

  const task_list = ref([])
  let taskPolling = false
  let taskTimer = null
  let taskRequest = null
  let statusRequest = null
  let runningRevision = 0
  const speed_msg = ref([])

  function clear_legacy_logs() {
    if (logStreamId === null) log_lines.value = []
  }

  function listen_ws() {
    const token = new URLSearchParams(window.location.search).get('token')
    let backend_url
    if (import.meta.env.DEV) {
      backend_url = import.meta.env.VITE_HTTP_URL
    } else {
      backend_url = location.origin
    }
    const ws_url = backend_url.replace(/^http/, 'ws') + '/log'
    ws.value = new ReconnectingWebSocket(ws_url)
    let awaitingHistory = true
    ws.value.onopen = () => {
      awaitingHistory = true
      if (token) ws.value.send(JSON.stringify({ token }))
    }
    ws.value.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'log') {
        const firstMessage = awaitingHistory
        awaitingHistory = false
        const synchronized =
          typeof data.stream_id === 'string' &&
          data.stream_id.length > 0 &&
          typeof data.snapshot === 'boolean' &&
          Array.isArray(data.records)
        const streamChanged = synchronized && data.stream_id !== logStreamId
        if (streamChanged) {
          logStreamId = data.stream_id
          lastLogSequence = 0
        }
        const seen = new Set()
        const records = synchronized
          ? data.records.filter((record) => {
              const seq = record?.seq
              if (
                !Number.isSafeInteger(seq) ||
                seq <= 0 ||
                seen.has(seq) ||
                (!data.snapshot && seq <= lastLogSequence)
              )
                return false
              seen.add(seq)
              return true
            })
          : data.records
        let lines
        if (Array.isArray(records) && (synchronized || records.length > 0)) {
          lines = records.map((r) => {
            const t = r.t ?? ''
            const level = r.level ?? ''
            const msg = r.msg ?? ''
            const text = t && level ? `${t} ${level} ${msg}` : msg
            const header =
              synchronized &&
              typeof t === 'string' &&
              t &&
              typeof level === 'string' &&
              level &&
              typeof msg === 'string'
                ? { t, level, msg }
                : null
            return {
              id: synchronized ? `${logStreamId}:${r.seq}` : ++nextLogId,
              ...(synchronized ? { seq: r.seq } : {}),
              at: Number.isFinite(r.at) ? r.at : parseLogTime(t),
              text,
              ...header,
              group: r.group ?? null,
              room: r.room ?? null,
              agents: r.agents ?? null,
              ...(r.task && typeof r.task === 'object' && !Array.isArray(r.task)
                ? { task: r.task }
                : {}),
              ...(r.recruitment &&
              typeof r.recruitment === 'object' &&
              !Array.isArray(r.recruitment)
                ? { recruitment: r.recruitment }
                : {}),
              ...(Array.isArray(r.backups) ? { backups: r.backups } : {}),
              ...(r.inventory && typeof r.inventory === 'object' && !Array.isArray(r.inventory)
                ? { inventory: r.inventory }
                : {}),
              ...(r.event && typeof r.event === 'object' && !Array.isArray(r.event)
                ? { event: r.event }
                : {}),
              ...(r.parent && typeof r.parent === 'object' && !Array.isArray(r.parent)
                ? { parent: r.parent }
                : {})
            }
          })
        } else if (typeof data.data === 'string' && (data.data || !firstMessage)) {
          lines = data.data.split('\n').map((text) => ({
            id: ++nextLogId,
            at: null,
            text,
            group: null,
            room: null,
            agents: null
          }))
        } else {
          lines = []
        }
        if (synchronized) {
          // 后端统一保留操作摘要和明细；重连快照替换缓存，序号稳定并阻止旧更新复活。
          const evicted = new Set(Array.isArray(data.evicted) ? data.evicted : [])
          const retained = data.snapshot || streamChanged ? [] : log_lines.value
          log_lines.value = retained.concat(lines).filter((line) => !evicted.has(line.seq))
          lastLogSequence = records.reduce(
            (latest, record) => Math.max(latest, record.seq),
            lastLogSequence
          )
        } else {
          // 旧后端在每次连接时先发送历史记录。
          const retained = firstMessage ? [] : log_lines.value
          logStreamId = null
          lastLogSequence = 0
          log_lines.value = boundLegacyLogLines(retained.concat(lines))
        }
      } else if (data.type === 'resource_updated') {
        // 资源包在别处被更新（安装/共享资源/手动上传）时，让标题栏的资源版本实时刷新
        import('@/stores/resourceVersion')
          .then(({ useResourceVersionStore }) =>
            useResourceVersionStore().loadResourceVersionLocal()
          )
          .catch(() => {})
      }
    }
  }

  function get_running() {
    if (statusRequest) return statusRequest
    const revision = runningRevision
    statusRequest = axios
      .get(`${import.meta.env.VITE_HTTP_URL}/status`, { timeout: 10000 })
      .then((response) => {
        if (revision !== runningRevision) return
        status.value = response.data.status
        running.value = status.value !== 'stopped'
        stop_after_round.value = running.value && response.data.stop_after_round === true
        maintenance_pause.value = running.value ? (response.data.maintenance_pause ?? null) : null
        scheduled_start_at.value = response.data.scheduled_start_at ?? null
        auto_start_handled.value = response.data.auto_start_handled === true
        desktop_startup_handled.value = response.data.desktop_startup_handled === true
        deployment.value = ['source', 'release'].includes(response.data.deployment)
          ? response.data.deployment
          : null
        updates_enabled.value =
          typeof response.data.updates_enabled === 'boolean' ? response.data.updates_enabled : null
        ai_assistant_enabled.value =
          typeof response.data.ai_assistant_enabled === 'boolean'
            ? response.data.ai_assistant_enabled
            : null
        plan_condition.value = response.data['plan_condition']
      })
      .finally(() => {
        statusRequest = null
      })
    return statusRequest
  }

  function cancel_task_poll() {
    clearTimeout(taskTimer)
    taskTimer = null
    const request = taskRequest
    taskRequest = null
    request?.controller.abort()
  }

  async function cancel_maintenance_pause(pauseId) {
    const revision = runningRevision
    await axios.delete(`${import.meta.env.VITE_HTTP_URL}/maintenance-pause`, {
      data: { id: pauseId },
      timeout: 10000
    })
    if (revision !== runningRevision) return
    runningRevision += 1
    if (maintenance_pause.value?.id === pauseId) maintenance_pause.value = null
    await get_tasks()
  }

  async function set_stop_after_round(enabled) {
    const revision = runningRevision
    const url = `${import.meta.env.VITE_HTTP_URL}/stop-after-round`
    const { data } = enabled
      ? await axios.put(url, null, { timeout: 10000 })
      : await axios.delete(url, { timeout: 10000 })
    if (revision !== runningRevision) return
    runningRevision += 1
    stop_after_round.value = running.value && data.stop_after_round === true
  }

  function get_tasks() {
    if (!taskPolling || !running.value) return Promise.resolve()
    if (taskRequest) return taskRequest.promise
    clearTimeout(taskTimer)
    taskTimer = null
    const request = { controller: new AbortController(), promise: null }
    taskRequest = request
    request.promise = axios
      .get(`${import.meta.env.VITE_HTTP_URL}/task`, {
        signal: request.controller.signal,
        timeout: 10000
      })
      .then((response) => {
        if (taskRequest === request) task_list.value = response.data
      })
      .catch((error) => {
        if (!request.controller.signal.aborted) console.error('任务读取失败', error)
      })
      .finally(() => {
        if (taskRequest !== request) return
        taskRequest = null
        taskTimer = setTimeout(() => {
          taskTimer = null
          void get_tasks()
        }, 3000)
      })
    return request.promise
  }

  function start_task_polling() {
    if (taskPolling) return taskRequest?.promise || Promise.resolve()
    taskPolling = true
    return get_tasks()
  }

  function stop_task_polling() {
    taskPolling = false
    cancel_task_poll()
  }

  watch(
    running,
    (active) => {
      runningRevision += 1
      if (active) void get_tasks()
      else {
        stop_after_round.value = false
        maintenance_pause.value = null
        cancel_task_poll()
        task_list.value = []
      }
    },
    { flush: 'sync' }
  )
  onScopeDispose(stop_task_polling)

  return {
    log,
    log_mobile,
    log_lines,
    ws,
    running,
    status,
    status_label,
    scheduled_start_at,
    stop_after_round,
    maintenance_pause,
    cancel_maintenance_pause,
    set_stop_after_round,
    auto_start_handled,
    desktop_startup_handled,
    ai_assistant_enabled,
    updates_enabled,
    deployment,
    plan_condition,
    waiting,
    listen_ws,
    clear_legacy_logs,
    get_running,
    first_load,
    task_list,
    get_tasks,
    start_task_polling,
    stop_task_polling,
    speed_msg
  }
})
