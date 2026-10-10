import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useFacilityStore = defineStore('facility-state', () => {
  const states = ref({})
  const loaded = ref(false)
  const loadError = ref('')
  let loadedAt = 0
  let request = null

  async function load(force = false) {
    if (!force && loaded.value && Date.now() - loadedAt < 30_000) return states.value
    if (request) return request
    loadError.value = ''
    request = axios
      .get(`${import.meta.env.VITE_HTTP_URL}/facility-state`)
      .then((response) => {
        states.value = response.data || {}
        loaded.value = true
        loadedAt = Date.now()
        return states.value
      })
      .catch((error) => {
        loadError.value = error?.message || '读取设施状态失败'
        throw error
      })
      .finally(() => {
        request = null
      })
    return request
  }

  return { states, loaded, loadError, load }
})
