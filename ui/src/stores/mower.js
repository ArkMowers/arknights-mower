import { defineStore } from 'pinia'
import ReconnectingWebSocket from 'reconnecting-websocket'
import { computed, onScopeDispose, ref, watch } from 'vue'

import axios from 'axios'

export const useMowerStore = defineStore('mower', () => {
  const log_lines = ref([])

  const log = computed(() => {
    return log_lines.value.join('\n')
  })

  const num_reg = /^[0-9].*/
  const log_mobile = computed(() => {
    const result = []
    for (const i of log_lines.value) {
      if (i.match(num_reg)) {
        result.push(i.substring(24))
      } else {
        result.push(i)
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
    ws.value.onopen = () => {
      if (token) ws.value.send(JSON.stringify({ token }))
    }
    ws.value.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'log') {
        log_lines.value = log_lines.value.concat(data.data.split('\n')).slice(-100) // 追加日志
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
    set_stop_after_round,
    auto_start_handled,
    desktop_startup_handled,
    ai_assistant_enabled,
    updates_enabled,
    deployment,
    plan_condition,
    waiting,
    listen_ws,
    get_running,
    first_load,
    task_list,
    get_tasks,
    start_task_polling,
    stop_task_polling,
    speed_msg
  }
})
