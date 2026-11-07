import { ref } from 'vue'

export function createCrashRecovery({ axios, base = '' }) {
  const status = ref({ active: false })
  const busy = ref(false)
  const unavailable = ref(true)
  const error = ref('')
  let disposed = false

  async function refresh() {
    if (disposed || busy.value) return false
    busy.value = true
    try {
      const { data } = await axios.get(`${base}/crash-recovery/status`, { timeout: 3000 })
      if (disposed) return false
      if (!data || typeof data.active !== 'boolean') {
        throw new Error('暂时无法读取自动恢复状态')
      }
      status.value = data
      unavailable.value = false
      error.value = ''
      return true
    } catch (failure) {
      if (!disposed) {
        unavailable.value = true
        if (status.value.active) {
          error.value = failure.response?.data?.message || '服务暂时不可用，恢复状态稍后自动刷新'
        }
      }
      return false
    } finally {
      if (!disposed) busy.value = false
    }
  }

  function dispose() {
    disposed = true
  }

  return { status, busy, unavailable, error, refresh, dispose }
}
