import { defineStore } from 'pinia'
import { ref } from 'vue'

import axios from 'axios'

export const useMowerStore = defineStore('mower', () => {
  const log = ref('')
  const ws = ref(null)
  const running = ref(false)

  function listen_ws() {
    let backend_url
    if (import.meta.env.DEV) {
      backend_url = import.meta.env.VITE_HTTP_URL
    } else {
      backend_url = location.origin
    }
    const ws_url = backend_url.replace(/^http/, 'ws') + '/log'
    ws.value = new WebSocket(ws_url)
    ws.value.onmessage = (event) => {
      log.value += event.data + '\n'
    }
  }

  async function get_running() {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/running`)
    running.value = response.data
  }

  return {
    log,
    ws,
    running,
    listen_ws,
    get_running
  }
})
