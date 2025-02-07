import { defineStore } from 'pinia'
import ReconnectingWebSocket from 'reconnecting-websocket'
import { computed, ref } from 'vue'

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
  const plan_condition = ref([])
  const waiting = ref(false)

  const first_load = ref(true)

  const get_task_id = ref(0)
  const task_list = ref([])

  function listen_ws() {
    let backend_url
    if (import.meta.env.DEV) {
      backend_url = import.meta.env.VITE_HTTP_URL
    } else {
      backend_url = location.origin
    }
    const ws_url = backend_url.replace(/^http/, 'ws') + '/log'
    ws.value = new ReconnectingWebSocket(ws_url)
    ws.value.onmessage = (event) => {
      log_lines.value = log_lines.value.concat(event.data.split('\n')).slice(-100)
    }
  }

  async function get_running() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/running`)
    running.value = response.data['running']
    plan_condition.value = response.data['plan_condition']
  }

  async function get_tasks() {
    if (running.value) {
      const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/task`)
      task_list.value = response.data
      get_task_id.value = setTimeout(get_tasks, 3000)
    } else {
      task_list.value = []
    }
  }

  return {
    log,
    log_mobile,
    log_lines,
    ws,
    running,
    plan_condition,
    waiting,
    listen_ws,
    get_running,
    first_load,
    task_list,
    get_task_id,
    get_tasks
  }
})
