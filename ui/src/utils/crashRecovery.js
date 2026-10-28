import { computed, ref } from 'vue'
import { i18n } from '@/i18n'

export function createCrashRecovery({ axios, base = '' }) {
  const status = ref({ active: false })
  const busy = ref(false)
  const unavailable = ref(true)
  const backendError = ref('')
  const fallbackError = ref(false)
  const error = computed(
    () =>
      backendError.value ||
      (fallbackError.value ? i18n.global.t('runtime.recoveryServiceUnavailable') : '')
  )
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
      backendError.value = ''
      fallbackError.value = false
      return true
    } catch (failure) {
      if (!disposed) {
        unavailable.value = true
        if (status.value.active) {
          backendError.value = failure.response?.data?.message || ''
          fallbackError.value = !backendError.value
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
