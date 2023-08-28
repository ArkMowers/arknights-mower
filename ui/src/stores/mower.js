import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import ReconnectingWebSocket from 'reconnecting-websocket'

import axios from 'axios'

export const useMowerStore = defineStore('mower', () => {
  const log_lines = ref([])

  const log = computed(() => {
    return log_lines.value.join('\n')
  })

  const ws = ref(null)
  const running = ref(false)

  const first_load = ref(true)

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
      log_lines.value.push(event.data)
      log_lines.value = log_lines.value.slice(-500)
    }
  }

  async function get_running() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/running`)
    running.value = response.data
  }

  return {
    log,
    log_lines,
    ws,
    running,
    listen_ws,
    get_running,
    first_load
  }
})
