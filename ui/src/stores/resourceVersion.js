import { defineStore } from 'pinia'
import { ref } from 'vue'

import axios from 'axios'

export const useResourceVersionStore = defineStore('resourceVersion', () => {
  const info = ref({
    current_version: '',
    current_display: '',
    remote_version: '',
    remote_display: '',
    update_available: null,
    error: null
  })
  const loading = ref(false)
  const loaded = ref(false)
  const installing = ref(false)
  const install_message = ref('')

  async function loadResourceVersion(force = false) {
    if (loading.value) return info.value
    if (loaded.value && !force) return info.value
    loading.value = true
    try {
      const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/resource-version`)
      info.value = {
        current_version: response.data.current_version || '',
        current_display: response.data.current_display || '',
        remote_version: response.data.remote_version || '',
        remote_display: response.data.remote_display || '',
        update_available: response.data.update_available ?? null,
        error: response.data.error || null
      }
      loaded.value = true
    } catch (error) {
      info.value = { ...info.value, error: '网络错误：无法获取资源版本' }
    } finally {
      loading.value = false
    }
    return info.value
  }

  async function installResource() {
    if (installing.value) return
    installing.value = true
    install_message.value = ''
    try {
      const response = await axios.post(`${import.meta.env.VITE_HTTP_URL}/resource/install`)
      install_message.value = response.data.message || (response.data.ok ? '安装成功' : '安装失败')
      if (response.data.ok) {
        loaded.value = false
        await loadResourceVersion(true)
      }
    } catch (error) {
      install_message.value = error.response?.data?.message || '安装失败：网络错误'
    } finally {
      installing.value = false
    }
  }

  return {
    info,
    loading,
    loaded,
    installing,
    install_message,
    loadResourceVersion,
    installResource
  }
})
