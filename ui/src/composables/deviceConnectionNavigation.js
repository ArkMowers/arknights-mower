import { ref, shallowRef } from 'vue'

export const deviceConnectionNavigationKey = Symbol('device-connection-navigation')

export function createDeviceConnectionNavigation() {
  const request = shallowRef(null)
  const locked = ref(false)
  return {
    request,
    locked,
    open(action) {
      if (!['select', 'test', 'settings'].includes(action)) return null
      const next = { action }
      request.value = next
      return next
    },
    consume(current) {
      if (!current || request.value !== current) return false
      request.value = null
      return true
    }
  }
}
