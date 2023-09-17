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
      log_lines.value = log_lines.value.concat(event.data.split('\n')).slice(-500)
      let task_line
      for (let i = log_lines.value.length - 1; i >= 0; --i) {
        task_line = log_lines.value[i].substring(15)
        if (task_line.startsWith('SchedulerTask')) {
          break
        }
      }
      const scheduler_task = task_line.split('||')
      const date_time_re = /time='[0-9]+-[0-9]+-[0-9]+ ([0-9]+:[0-9]+:[0-9]+)/
      const plan_re = /task_plan={(.*)}/
      const type_re = /task_type=TaskTypes\.(.*),/
      let task_text
      task_list.value = scheduler_task.map((x) => {
        const plan_text = plan_re.exec(x)[1].replace(/'/g, '"')
        if (plan_text) {
          task_text = Object.entries(JSON.parse('{' + plan_text + '}')).map(
            (x) => `${x[0]}: ${x[1].join(', ')}`
          )
        } else {
          task_text = [type_re.exec(x)[1]]
        }
        return {
          time: date_time_re.exec(x)[1],
          task: task_text
        }
      })
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
    first_load,
    task_list
  }
})
