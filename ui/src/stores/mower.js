import { defineStore } from 'pinia'
import { ref } from 'vue'

import axios from 'axios'

export const useMowerStore = defineStore('mower', () => {
  const log = ref('')
  const ws = ref(null)
  const running = ref(false)

  function listen_ws() {
    ws.value = new WebSocket('ws://localhost:8000/log')
    ws.value.onmessage = (event) => {
      log.value += event.data + '\n'
    }
  }

  async function get_running() {
    const response = await axios.get('http://localhost:8000/running')
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
