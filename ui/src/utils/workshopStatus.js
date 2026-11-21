import { ref } from 'vue'

export function createWorkshopStatus(http, url, isRunning) {
  const data = ref(null)
  const stale = ref(false)
  const loading = ref(false)
  let active = false
  let request = 0
  let controller
  let timer

  async function refresh() {
    if (!active) return
    clearTimeout(timer)
    controller?.abort()
    const token = ++request
    if (document.hidden) {
      loading.value = false
      return
    }
    controller = new AbortController()
    loading.value = true
    try {
      const response = await http.get(url, { signal: controller.signal, timeout: 10000 })
      if (active && request === token) {
        data.value = response.data
        stale.value = false
      }
    } catch {
      if (active && request === token) stale.value = true
    } finally {
      if (active && request === token) {
        loading.value = false
        if (isRunning() && !document.hidden) timer = setTimeout(refresh, 15000)
      }
    }
  }

  function start() {
    if (active) return
    active = true
    document.addEventListener('visibilitychange', refresh)
    return refresh()
  }

  function stop() {
    active = false
    ++request
    clearTimeout(timer)
    controller?.abort()
    loading.value = false
    document.removeEventListener('visibilitychange', refresh)
  }

  return { data, stale, loading, refresh, start, stop }
}
