import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useMowerStore = defineStore('mower', () => {
  const log = ref('')
  const ws = ref(null)

  function listen_ws() {
    ws.value = new WebSocket('ws://localhost:8000/log')
    ws.value.onmessage = (event) => {
      log.value += event.data + '\n'
    }
  }

  return {
    log,
    ws,
    listen_ws
  }
})
